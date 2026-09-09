from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import router
from app.core.config import get_settings
from app.db.database import init_db
from app.services.analyzer import recover_interrupted_jobs

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await recover_interrupted_jobs()
    yield

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

@app.get("/")
async def root():
    return {"name": settings.app_name, "status": "ok", "docs": "/docs", "health": "/health"}

@app.get("/health")
async def health():
    return {"status": "ok", "provider": settings.llm_provider}
