import asyncio
import json
import logging
from datetime import datetime, timezone
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.models.models import AnalysisBatch, AnalysisJob, Document, DocumentChunk, Report
from app.services.llm import embed, generate_map_memo, generate_title_search_report, reduce_memos
from app.services.parser import chunk_blocks, extract_blocks

logger = logging.getLogger("counselai.analyzer")

async def update_job(job_id: str, **values):
    async with SessionLocal() as db:
        job = await db.get(AnalysisJob, job_id)
        if not job:
            return
        for key, value in values.items():
            setattr(job, key, value)
        await db.commit()

async def recover_interrupted_jobs():
    async with SessionLocal() as db:
        jobs = (await db.execute(select(AnalysisJob).where(AnalysisJob.status.in_(["queued", "processing"])))).scalars().all()
        for job in jobs:
            job.status = "queued"
            job.current_step = "Queued for recovery"
            job.error = None
        await db.execute(
            update(AnalysisBatch)
            .where(AnalysisBatch.status == "in_progress")
            .values(status="pending", error="Recovered after worker restart")
        )
        await db.commit()
        job_ids = [job.id for job in jobs]
    for job_id in job_ids:
        asyncio.create_task(run_analysis(job_id))

def _make_batches(docs: list[Document], max_chars: int) -> list[list[dict]]:
    batches: list[list[dict]] = []
    current: list[dict] = []
    chars = 0
    for doc in docs:
        for chunk in sorted(doc.chunks, key=lambda item: item.chunk_index):
            size = len(chunk.text)
            if current and chars + size > max_chars:
                batches.append(current)
                current = []
                chars = 0
            loc = ""
            if chunk.metadata_json:
                try:
                    loc = json.loads(chunk.metadata_json).get("location", "")
                except Exception:
                    pass
            current.append({
                "filename": doc.filename,
                "location": loc,
                "text": chunk.text,
            })
            chars += size
    if current:
        batches.append(current)
    return batches

async def run_analysis(job_id: str, title: str | None = None):
    settings = get_settings()
    try:
        await update_job(job_id, status="processing", progress=5, current_step="Parsing documents", error=None)
        
        async with SessionLocal() as db:
            docs = (await db.execute(select(Document).where(Document.job_id == job_id).order_by(Document.id))).scalars().all()
        
        if not docs:
            raise RuntimeError("No documents found for this analysis job")

        total = len(docs)
        for index, doc in enumerate(docs, start=1):
            try:
                blocks = await asyncio.to_thread(extract_blocks, doc.stored_path)
                chunks = chunk_blocks(blocks, settings.chunk_size, settings.chunk_overlap)
                if not chunks:
                    raise RuntimeError(
                        f"No readable text could be extracted from '{doc.filename}'. "
                        "Please verify the file is not empty or corrupted."
                    )
                
                async with SessionLocal() as db:
                    fresh = await db.get(Document, doc.id)
                    if not fresh:
                        raise RuntimeError("Document was removed during analysis")
                    
                    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
                    fresh.extracted_chars = sum(len(b.get("text", "")) for b in blocks)
                    fresh.status = "parsed"
                    fresh.error = None
                    
                    chunk_objects = []
                    for chunk_index, chunk in enumerate(chunks):
                        vector = await embed(chunk["text"]) if settings.enable_embeddings else None
                        chunk_objects.append(DocumentChunk(
                            document_id=doc.id,
                            chunk_index=chunk_index,
                            text=chunk["text"],
                            metadata_json=json.dumps({"filename": doc.filename, "location": chunk.get("location", "")}),
                            embedding_json=json.dumps(vector) if vector else None,
                        ))
                    db.add_all(chunk_objects)
                    await db.commit()
            except Exception as exc:
                err_msg = f"Failed parsing {doc.filename}: {exc}"
                logger.exception(err_msg)
                await update_job(job_id, status="failed", current_step=f"Failed: {doc.filename}", error=err_msg)
                return

            progress = 5 + int(index / max(total, 1) * 45)
            await update_job(job_id, progress=progress, processed_files=index, current_step=f"Parsed {index}/{total} files")

        await update_job(job_id, progress=55, current_step="Preparing cross-document analysis batches")
        
        async with SessionLocal() as db:
            # Query documents with eagerly loaded chunks
            docs_with_chunks = (
                await db.execute(
                    select(Document)
                    .where(Document.job_id == job_id)
                    .options(selectinload(Document.chunks))
                    .order_by(Document.id)
                )
            ).scalars().all()
            
            batches = _make_batches(docs_with_chunks, settings.max_context_chars_per_batch)
            if not batches:
                raise RuntimeError("No text chunks available for cross-document analysis")

            # Clean any old batches for this job to ensure fresh run
            await db.execute(delete(AnalysisBatch).where(AnalysisBatch.job_id == job_id))
            for index, source_chunks in enumerate(batches):
                db.add(AnalysisBatch(
                    job_id=job_id,
                    batch_index=index,
                    source_json=json.dumps(source_chunks, ensure_ascii=False),
                    status="pending"
                ))
            await db.commit()

            saved = (
                await db.execute(
                    select(AnalysisBatch)
                    .where(AnalysisBatch.job_id == job_id)
                    .order_by(AnalysisBatch.batch_index)
                )
            ).scalars().all()

        total_batches = len(saved)
        if total_batches == 1:
            # Single batch: generate Title Search Report directly in one shot
            batch = saved[0]
            source_chunks = json.loads(batch.source_json)
            source = "\n\n".join(
                f"SOURCE FILE: {chunk['filename']}\n[{chunk.get('location', '')}] {chunk['text']}"
                for chunk in source_chunks
            )
            await update_job(job_id, progress=60, current_step="Generating Title Search Report")
            
            async with SessionLocal() as db:
                current_batch = await db.get(AnalysisBatch, batch.id)
                if current_batch:
                    current_batch.status = "in_progress"
                    await db.commit()

            report_markdown = await generate_title_search_report(source)

            async with SessionLocal() as db:
                current_batch = await db.get(AnalysisBatch, batch.id)
                if current_batch:
                    current_batch.status = "completed"
                    current_batch.memo = report_markdown
                    current_batch.completed_at = datetime.now(timezone.utc)
                    await db.commit()
        else:
            # Multiple batches: analyze batches with bounded concurrency (3 concurrent workers)
            semaphore = asyncio.Semaphore(3)
            completed_count = 0

            async def process_batch(index: int, b: AnalysisBatch):
                nonlocal completed_count
                async with semaphore:
                    source_chunks = json.loads(b.source_json)
                    source = "\n\n".join(
                        f"SOURCE FILE: {chunk['filename']}\n[{chunk.get('location', '')}] {chunk['text']}"
                        for chunk in source_chunks
                    )
                    async with SessionLocal() as db:
                        cb = await db.get(AnalysisBatch, b.id)
                        if cb:
                            cb.status = "in_progress"
                            cb.error = None
                            await db.commit()
                    try:
                        memo = await generate_map_memo(index + 1, source)
                        async with SessionLocal() as db:
                            cb = await db.get(AnalysisBatch, b.id)
                            if cb:
                                cb.status = "completed"
                                cb.memo = memo
                                cb.completed_at = datetime.now(timezone.utc)
                                await db.commit()
                    except Exception as exc:
                        async with SessionLocal() as db:
                            cb = await db.get(AnalysisBatch, b.id)
                            if cb:
                                cb.status = "failed"
                                cb.error = str(exc)
                                await db.commit()
                        raise
                    completed_count += 1
                    batch_progress = 55 + int(completed_count / max(total_batches, 1) * 35)
                    await update_job(job_id, progress=batch_progress, current_step=f"Completed batch {completed_count}/{total_batches}")

            await asyncio.gather(*(process_batch(i, b) for i, b in enumerate(saved)))

            await update_job(job_id, progress=92, current_step="Synthesizing final Title Search Report")
            async with SessionLocal() as db:
                completed_batches = (
                    await db.execute(
                        select(AnalysisBatch)
                        .where(AnalysisBatch.job_id == job_id, AnalysisBatch.status == "completed")
                        .order_by(AnalysisBatch.batch_index)
                    )
                ).scalars().all()
            
            memos = [b.memo for b in completed_batches if b.memo]
            if not memos:
                raise RuntimeError("No evidence memos were generated during batch analysis")
            report_markdown = await reduce_memos(memos)

        await update_job(job_id, progress=97, current_step="Saving Title Search Report")
        
        async with SessionLocal() as db:
            job = await db.get(AnalysisJob, job_id)
            if not job:
                return

            existing_report = (await db.execute(select(Report).where(Report.job_id == job_id))).scalar_one_or_none()
            report_title = title or f"Title Search Report — {datetime.now().strftime('%d %b %Y, %H:%M')}"
            
            if existing_report:
                existing_report.title = report_title
                existing_report.markdown = report_markdown
                existing_report.document_count = total
                existing_report.created_at = datetime.now(timezone.utc)
            else:
                report = Report(
                    job_id=job_id,
                    title=report_title,
                    markdown=report_markdown,
                    document_count=total,
                )
                db.add(report)
            
            await db.flush()
            job.status = "completed"
            job.progress = 100
            job.current_step = "Report ready"
            job.error = None
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

    except Exception as exc:
        err_msg = f"{type(exc).__name__}: {exc}"
        logger.exception("Analysis job %s failed: %s", job_id, err_msg)
        await update_job(
            job_id,
            status="failed",
            current_step="Analysis failed",
            error=err_msg,
        )

