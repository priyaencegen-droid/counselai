import asyncio, json
from datetime import datetime, timezone
from sqlalchemy import delete, select, update
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.models.models import AnalysisBatch, AnalysisJob, Document, DocumentChunk, Report
from app.services.llm import embed, generate_map_memo, reduce_memos
from app.services.parser import chunk_blocks, extract_blocks

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
        jobs = (await db.execute(select(AnalysisJob).where(AnalysisJob.status.in_(["queued", "processing"])))) .scalars().all()
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

def _make_batches(docs: list[Document], max_chars: int) -> list[dict]:
    batches = []
    current = []
    chars = 0
    for doc in docs:
        for chunk in sorted(doc.chunks, key=lambda item: item.chunk_index):
            size = len(chunk.text)
            if current and chars + size > max_chars:
                batches.append(current)
                current = []
                chars = 0
            current.append({"filename": doc.filename, "location": json.loads(chunk.metadata_json).get("location", ""), "text": chunk.text})
            chars += size
    if current:
        batches.append(current)
    return batches

async def run_analysis(job_id: str, title: str | None = None):
    settings = get_settings()
    try:
        await update_job(job_id, status="processing", progress=5, current_step="Parsing documents")
        async with SessionLocal() as db:
            docs = (await db.execute(select(Document).where(Document.job_id == job_id).order_by(Document.id))).scalars().all()
        parsed = []
        total = len(docs)
        for index, doc in enumerate(docs, start=1):
            try:
                blocks = await asyncio.to_thread(extract_blocks, doc.stored_path)
                chunks = chunk_blocks(blocks, settings.chunk_size, settings.chunk_overlap)
                if not chunks:
                    raise RuntimeError(
                        f"No text could be extracted from {doc.filename}. "
                        "If it is a scanned PDF, provide a text-searchable copy or OCR it first."
                    )
                async with SessionLocal() as db:
                    fresh = await db.get(Document, doc.id)
                    if not fresh:
                        raise RuntimeError("Document disappeared during analysis")
                    await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
                    fresh.extracted_chars = sum(len(b["text"]) for b in blocks)
                    fresh.status = "parsed"
                    for chunk_index, chunk in enumerate(chunks):
                        vector = await embed(chunk["text"])
                        db.add(DocumentChunk(
                            document_id=doc.id,
                            chunk_index=chunk_index,
                            text=chunk["text"],
                            metadata_json=json.dumps({"filename": doc.filename, "location": chunk["location"]}),
                            embedding_json=json.dumps(vector) if vector else None,
                        ))
                    await db.commit()
                parsed.append({"filename": doc.filename, "chunks": chunks})
            except Exception as exc:
                await update_job(job_id, status="failed", current_step=f"Failed: {doc.filename}", error=str(exc))
                return
            progress = 5 + int(index / max(total, 1) * 50)
            await update_job(job_id, progress=progress, processed_files=index, current_step=f"Parsed {index}/{total} files")

        await update_job(job_id, progress=60, current_step="Running cross-document legal analysis")
        async with SessionLocal() as db:
            docs = (await db.execute(select(Document).where(Document.job_id == job_id).order_by(Document.id))).scalars().all()
            for doc in docs:
                await db.refresh(doc, ["chunks"])
            batches = _make_batches(docs, settings.max_context_chars_per_batch)
            saved = (await db.execute(select(AnalysisBatch).where(AnalysisBatch.job_id == job_id).order_by(AnalysisBatch.batch_index))).scalars().all()
            for index, source_chunks in enumerate(batches):
                source = "\n\n".join(f"SOURCE FILE: {chunk['filename']}\n[{chunk['location']}] {chunk['text']}" for chunk in source_chunks)
                if index >= len(saved):
                    db.add(AnalysisBatch(job_id=job_id, batch_index=index, source_json=json.dumps(source_chunks, ensure_ascii=False), status="pending"))
            await db.commit()
            saved = (await db.execute(select(AnalysisBatch).where(AnalysisBatch.job_id == job_id).order_by(AnalysisBatch.batch_index))).scalars().all()

        for index, batch in enumerate(saved):
            if batch.status == "completed" and batch.memo:
                continue
            source_chunks = json.loads(batch.source_json)
            source = "\n\n".join(f"SOURCE FILE: {chunk['filename']}\n[{chunk['location']}] {chunk['text']}" for chunk in source_chunks)
            await update_job(job_id, current_step=f"Analyzing batch {index + 1}/{len(saved)}")
            async with SessionLocal() as db:
                current_batch = await db.get(AnalysisBatch, batch.id)
                current_batch.status = "in_progress"
                current_batch.error = None
                await db.commit()
            try:
                memo = await generate_map_memo(index + 1, source)
            except Exception as exc:
                async with SessionLocal() as db:
                    current_batch = await db.get(AnalysisBatch, batch.id)
                    current_batch.status = "failed"
                    current_batch.error = f"{type(exc).__name__}: {exc}"
                    await db.commit()
                raise
            async with SessionLocal() as db:
                current_batch = await db.get(AnalysisBatch, batch.id)
                current_batch.status = "completed"
                current_batch.memo = memo
                current_batch.completed_at = datetime.now(timezone.utc)
                await db.commit()
            await update_job(job_id, progress=60 + int((index + 1) / max(len(saved), 1) * 30), current_step=f"Saved batch {index + 1}/{len(saved)}")

        async with SessionLocal() as db:
            completed = (await db.execute(select(AnalysisBatch).where(AnalysisBatch.job_id == job_id, AnalysisBatch.status == "completed").order_by(AnalysisBatch.batch_index))).scalars().all()
        report_markdown = await reduce_memos([batch.memo for batch in completed if batch.memo])
        await update_job(job_id, progress=92, current_step="Saving report")
        async with SessionLocal() as db:
            job = await db.get(AnalysisJob, job_id)
            if not job:
                return
            report = Report(
                job_id=job_id,
                title=title or f"Legal Analysis — {datetime.now().strftime('%d %b %Y, %H:%M')}",
                markdown=report_markdown,
                document_count=total,
            )
            db.add(report)
            await db.flush()
            job.status = "completed"
            job.progress = 100
            job.current_step = "Report ready"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
    except Exception as exc:
        await update_job(
            job_id,
            status="failed",
            current_step="Analysis failed",
            error=f"{type(exc).__name__}: {exc}",
        )
