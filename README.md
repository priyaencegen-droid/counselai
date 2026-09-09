# CounselAI — Legal Document Analysis Dashboard

Full-stack document-analysis dashboard using React + Tailwind + FastAPI + SQLite + Ollama/OpenAI-compatible cloud LLMs.

## Features
- Bulk PDF/DOCX/TXT upload, designed for 25+ files
- Per-file and batch size validation
- Asynchronous file writes and background analysis
- PDF, DOCX and TXT extraction
- Text cleaning and source metadata
- Configurable chunk size/overlap
- Optional Ollama embeddings persisted with chunks
- Map/reduce LLM analysis for large document sets
- Ollama or OpenAI-compatible cloud provider
- SQLite report history
- Job progress polling
- Markdown report renderer
- Copy, TXT export and browser PDF export
- Dark/light mode

## Important
The analysis is an AI-assisted legal document review tool. It should not be treated as a substitute for advice from a qualified lawyer.

## Quick start
See the step-by-step setup below or the README files in `backend/` and `frontend/`.
