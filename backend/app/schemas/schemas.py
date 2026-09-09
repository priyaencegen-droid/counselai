from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

class UploadFileResult(BaseModel):
    filename: str
    document_id: int
    size_bytes: int
    status: str

class UploadResponse(BaseModel):
    job_id: str
    files: list[UploadFileResult]
    rejected: list[dict]

class AnalyzeRequest(BaseModel):
    job_id: str
    title: str | None = Field(default=None, max_length=255)

class JobResponse(BaseModel):
    id: str
    status: str
    progress: int
    current_step: str
    total_files: int
    processed_files: int
    error: str | None = None
    completed_at: datetime | None = None
    report_id: int | None = None
    model_config = ConfigDict(from_attributes=True)

class SavedBatch(BaseModel):
    batch_index: int
    status: str
    memo: str | None = None
    error: str | None = None
    model_config = ConfigDict(from_attributes=True)

class JobStatusResponse(JobResponse):
    saved_batches: list[SavedBatch] = []

class ReportListItem(BaseModel):
    id: int
    job_id: str
    title: str
    document_count: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ReportDetail(ReportListItem):
    markdown: str
