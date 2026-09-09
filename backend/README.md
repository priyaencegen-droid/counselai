# CounselAI Backend

FastAPI + SQLite + Ollama/OpenAI-compatible LLM document analysis backend.

Run from this directory:

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```
