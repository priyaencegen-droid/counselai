from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "CounselAI Legal Document Analysis"
    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./data/legal_analysis.db"
    storage_dir: str = "./storage"
    cors_origins: str = "http://localhost:5173"
    max_files_per_upload: int = 100
    max_file_size_mb: int = 50
    max_total_upload_size_mb: int = 500
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_map_model: str = "gpt-oss:20b"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_api_key: str = ""
    enable_embeddings: bool = False
    cloud_api_key: str = ""
    cloud_base_url: str = "https://api.openai.com/v1"
    cloud_model: str = "gpt-4o-mini"
    chunk_size: int = 20000
    chunk_overlap: int = 1000
    map_batch_size: int = 4
    max_context_chars_per_batch: int = 60000
    max_reduce_chars_per_batch: int = 80000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

@lru_cache
def get_settings() -> Settings:
    return Settings()
