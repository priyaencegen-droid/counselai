import asyncio
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.db.database import get_db
from app.models.models import AnalysisBatch, AnalysisJob, Document, Report
from app.schemas.schemas import AnalyzeRequest, JobResponse, JobStatusResponse, ReportDetail, ReportListItem, SavedBatch, UploadFileResult, UploadResponse
from app.services.analyzer import run_analysis

router = APIRouter()
settings = get_settings()
ALLOWED = {".pdf", ".docx", ".txt", ".xls", ".xlsx"}

async def save_upload(upload: UploadFile, destination: Path, max_bytes: int) -> int:
    written = 0
    with destination.open("wb") as out:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > max_bytes:
                raise ValueError("File exceeds size limit")
            out.write(chunk)
    return written

@router.post("/upload", response_model=UploadResponse)
async def upload(files: list[UploadFile] = File(...), db: AsyncSession = Depends(get_db)):
    if not files:
        raise HTTPException(400, "No files supplied")
    if len(files) > settings.max_files_per_upload:
        raise HTTPException(400, f"Maximum {settings.max_files_per_upload} files per batch")

    job_id = uuid.uuid4().hex
    batch_dir = settings.storage_path / job_id
    batch_dir.mkdir(parents=True, exist_ok=True)
    job = AnalysisJob(id=job_id, status="uploaded", current_step="Uploading files")
    db.add(job)
    await db.flush()

    accepted, rejected = [], []
    total_bytes = 0
    max_file = settings.max_file_size_mb * 1024 * 1024
    max_total = settings.max_total_upload_size_mb * 1024 * 1024

    for upload in files:
        filename = Path(upload.filename or "unnamed").name
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED:
            rejected.append({"filename": filename, "reason": "Only PDF, XLS, XLSX, DOCX and TXT are supported"})
            continue
        destination = batch_dir / f"{uuid.uuid4().hex}_{filename}"
        try:
            size = await save_upload(upload, destination, min(max_file, max_total - total_bytes))
        except ValueError as exc:
            destination.unlink(missing_ok=True)
            rejected.append({"filename": filename, "reason": str(exc)})
            continue
        total_bytes += size
        if total_bytes > max_total:
            destination.unlink(missing_ok=True)
            rejected.append({"filename": filename, "reason": f"Batch exceeds {settings.max_total_upload_size_mb} MB"})
            break
        doc = Document(job_id=job_id, filename=filename, stored_path=str(destination), file_type=ext[1:], size_bytes=size)
        db.add(doc)
        await db.flush()
        accepted.append(UploadFileResult(filename=filename, document_id=doc.id, size_bytes=size, status="uploaded"))

    if not accepted:
        await db.rollback()
        raise HTTPException(400, {"message": "No valid files", "rejected": rejected})

    job.total_files = len(accepted)
    job.progress = 10
    job.current_step = "Files uploaded"
    await db.commit()
    return UploadResponse(job_id=job_id, files=accepted, rejected=rejected)

@router.post("/analyze", response_model=JobResponse)
async def analyze(payload: AnalyzeRequest, db: AsyncSession = Depends(get_db)):
    job = await db.get(AnalysisJob, payload.job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status == "processing":
        return JobResponse.model_validate(job)
    if job.status == "completed":
        report = (await db.execute(select(Report).where(Report.job_id == job.id))).scalar_one_or_none()
        response = JobResponse.model_validate(job)
        response.report_id = report.id if report else None
        return response
    if job.total_files == 0:
        raise HTTPException(400, "No documents are attached to this job")
    job.status = "queued"
    job.progress = 10
    job.processed_files = 0  # Reset so UI doesn't show stale counts from a previous run
    job.error = None
    job.current_step = "Queued for analysis"
    await db.commit()
    asyncio.create_task(run_analysis(payload.job_id, payload.title))
    return JobResponse.model_validate(job)

@router.get("/jobs/{job_id}", response_model=JobResponse)
async def job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    report = (await db.execute(select(Report).where(Report.job_id == job_id))).scalar_one_or_none()
    response = JobResponse.model_validate(job)
    response.report_id = report.id if report else None
    return response

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def status(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(AnalysisJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    report = (await db.execute(select(Report).where(Report.job_id == job_id))).scalar_one_or_none()
    batches = (await db.execute(select(AnalysisBatch).where(AnalysisBatch.job_id == job_id).order_by(AnalysisBatch.batch_index))).scalars().all()
    response = JobStatusResponse.model_validate(job)
    response.report_id = report.id if report else None
    response.saved_batches = [SavedBatch.model_validate(batch) for batch in batches]
    return response

@router.get("/reports", response_model=list[ReportListItem])
async def reports(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Report).order_by(desc(Report.created_at)))
    return [ReportListItem.model_validate(report) for report in result.scalars().all()]

@router.get("/reports/{report_id}", response_model=ReportDetail)
async def report_detail(report_id: int, db: AsyncSession = Depends(get_db)):
    report = await db.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return ReportDetail.model_validate(report)
