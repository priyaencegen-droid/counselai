# CounselAI — Legal Document Analysis Dashboard

CounselAI is a full-stack, AI-powered legal document review and analysis platform built with **FastAPI**, **SQLite**, **React**, and **Tailwind CSS**. It supports batch processing of legal documents (PDF, DOCX, TXT, XLS, XLSX) using **Ollama** (local/cloud) or **OpenAI-compatible** LLM providers (e.g., OpenAI, Groq).

---

## 📑 Table of Contents

- [Features](#-features)
- [Tech Stack](#-tech-stack)
- [Project Flow & Architecture](#-project-flow--architecture)
- [Prerequisites](#-prerequisites)
- [Quick Start Guide](#-quick-start-guide)
  - [1. Backend Setup](#1-backend-setup)
  - [2. LLM Provider Configuration](#2-llm-provider-configuration)
  - [3. Frontend Setup](#3-frontend-setup)
- [Running the Application](#-running-the-application)
- [Project Directory Structure](#-project-directory-structure)
- [API Documentation](#-api-documentation)
- [Troubleshooting](#-troubleshooting)
- [Disclaimer](#-disclaimer)

---

## 🚀 Features

- **Bulk Document Upload**: Process multiple PDF, DOCX, TXT, XLS, and XLSX files with batch-size validation.
- **Smart Text Extraction & Chunking**: Configurable chunk sizes and overlaps with metadata preservation.
- **Map-Reduce LLM Analysis**: High-capacity document summarization and risk analysis capable of processing large document sets.
- **Flexible LLM Providers**: Support for local Ollama instances, Ollama Cloud, or OpenAI-compatible APIs (OpenAI, Groq, etc.).
- **Optional Embeddings**: Embedding support via Ollama (`nomic-embed-text`).
- **Persistent Job History**: SQLite-backed history with job status polling and automatic recovery of interrupted jobs.
- **Rich Report Viewer**: Markdown report viewer with export options (Copy, TXT export, and print-to-PDF).
- **Modern UI**: Clean interface built with React, Lucide Icons, and Tailwind CSS with dark/light mode support.

---

## 🛠 Tech Stack

- **Backend**: Python 3.10+, FastAPI, Uvicorn, SQLAlchemy (Async), aiosqlite, pydantic-settings, pypdf, python-docx
- **Frontend**: React 18+, TypeScript, Vite, Tailwind CSS, Lucide React, React Markdown
- **Database**: SQLite (via `aiosqlite`)
- **LLM / AI**: Ollama / OpenAI-compatible API

---

## 🔄 Project Flow & Architecture

The following diagram and step-by-step breakdown illustrate how data flows through the application from upload to final legal report generation:

```mermaid
flowchart TD
    subgraph UI ["Frontend (React + Tailwind)"]
        A[User Uploads Documents<br/>PDF, DOCX, TXT, XLS, XLSX] --> B[File Validation<br/>Size, count & extensions]
        B --> C[POST /api/upload]
        D[Start Analysis Button] --> E[POST /api/analyze]
        F[Live Job Polling<br/>GET /api/jobs/{id}] <--> G[Progress Tracker & Status]
        H[Render Markdown Report<br/>& History Sidebar]
    end

    subgraph Backend ["Backend (FastAPI + Async Worker)"]
        C --> I[Persist Files to Storage<br/>./storage/{job_id}/]
        E --> J[Initialize Job in SQLite DB]
        J --> K[Async Background Analysis Worker]
        
        subgraph Pipeline ["Document Ingestion & LLM Pipeline"]
            K --> L[Extract Raw Text<br/>pypdf / python-docx / UTF-8]
            L --> M[Text Normalization & Chunking<br/>CHUNK_SIZE & CHUNK_OVERLAP]
            M -.->|Optional| N[Generate Embeddings<br/>Ollama nomic-embed-text]
            M --> O[Map Stage:<br/>Batch-analyze chunks for clauses,<br/>obligations, risks & covenants]
            O --> P[Reduce Stage:<br/>Synthesize summaries into comprehensive<br/>legal assessment & risk matrix]
        end

        P --> Q[Save Final Report to SQLite DB]
        Q --> R[Mark Job as Completed]
    end

    R -.-> F
    Q -.-> H
```

### End-to-End Workflow Breakdown

1. **Document Ingestion (`Frontend -> Backend`)**:
  - User drags and drops or selects up to 100 legal documents (PDF, DOCX, TXT, XLS, XLSX).
   - Frontend validates batch size and constraints, then uploads files via `POST /api/upload`.
   - Files are stored asynchronously on disk (`./storage/{job_id}`) and metadata is tracked in SQLite.

2. **Job Initialization (`POST /api/analyze`)**:
   - The user triggers analysis with custom instructions or default legal review prompts.
   - An asynchronous background task is spawned, returning a `job_id` immediately so the UI remains non-blocking.

3. **Text Extraction & Chunking**:
   - File parsers extract raw text according to file format (`pypdf` for PDF, `python-docx` for DOCX, UTF-8 reader for TXT).
   - The document cleaner strips formatting noise and breaks large documents into semantic chunks using sliding windows (`CHUNK_SIZE` and `CHUNK_OVERLAP`).

4. **Map-Reduce LLM Intelligence Pipeline**:
   - **Map Phase**: Chunks are processed in batches by the LLM (`Ollama` or OpenAI/Groq) to identify specific clauses, covenants, liabilities, indemnity terms, termination conditions, and risks.
   - **Reduce Phase**: The LLM synthesizes all intermediate chunk summaries into an executive legal report with structured sections:
     - Executive Summary
     - Key Obligations & Deliverables
     - Risk Assessment & Liability Matrix
     - Inconsistencies, Ambiguities & Red Flags
     - Strategic & Actionable Recommendations

5. **Real-Time Polling & Resilient State Management**:
   - The frontend continuously polls `GET /api/jobs/{job_id}` for live status, stage transitions, and completion percentage.
   - If the backend restarts, interrupted jobs are automatically detected and managed via startup lifecycle hooks.

6. **Interactive Report Viewing, History & Export**:
   - Once complete, the markdown report is formatted in the UI with syntax styling and risk callouts.
   - Reports are permanently stored in SQLite, accessible from the past reports sidebar, and can be exported as `.txt`, copied to clipboard, or printed to PDF.

---

## 📋 Prerequisites

Before starting, ensure you have the following installed:

1. **Python**: Version `3.10` or higher (`python --version`)
2. **Node.js**: Version `18.x` or higher and `npm` (`node -v` and `npm -v`)
3. **LLM Engine**:
   - **Local Ollama** (Download from [ollama.com](https://ollama.com)), OR
   - An API key for an **OpenAI-compatible provider** (OpenAI, Groq, etc.)

---

## ⚡ Quick Start Guide

### 1. Backend Setup

Open a terminal and navigate to the `backend` directory:

```bash
cd backend
```

#### Step 1.1: Create and Activate a Virtual Environment

- **Windows (PowerShell)**:
  ```powershell
  python -m venv .venv
  .venv\Scripts\Activate.ps1
  ```
  *(If script execution is disabled, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first)*

- **Windows (Command Prompt)**:
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate.bat
  ```

- **macOS / Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

#### Step 1.2: Install Python Dependencies

```bash
pip install -r requirements.txt
```

#### Step 1.3: Configure Backend Environment Variables

Copy the example environment file:

- **Windows (PowerShell / CMD)**:
  ```powershell
  copy .env.example .env
  ```
- **macOS / Linux**:
  ```bash
  cp .env.example .env
  ```

---

### 2. LLM Provider Configuration

Edit `backend/.env` according to your preferred LLM provider:

#### Option A: Local Ollama (Default)

1. Make sure Ollama is installed and running:
   ```bash
   ollama serve
   ```
2. Pull the required models:
   ```bash
   ollama pull llama3.1:8b
   ollama pull nomic-embed-text
   ```
3. Set in `backend/.env`:
   ```env
   LLM_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.1:8b
   ENABLE_EMBEDDINGS=false
   ```

#### Option B: OpenAI / Cloud Provider

Set in `backend/.env`:
```env
LLM_PROVIDER=cloud
CLOUD_API_KEY=your_actual_api_key_here
CLOUD_BASE_URL=https://api.openai.com/v1
CLOUD_MODEL=gpt-4o-mini
```

*(For Groq, set `CLOUD_BASE_URL=https://api.groq.com/openai/v1` and `CLOUD_MODEL=llama-3.1-70b-versatile`)*

---

### 3. Frontend Setup

Open a new terminal window and navigate to the `frontend` directory:

```bash
cd frontend
```

#### Step 3.1: Install Node Dependencies

```bash
npm install
```

#### Step 3.2: Configure Frontend Environment Variables

Create `.env` from `.env.example`:

- **Windows (PowerShell / CMD)**:
  ```powershell
  copy .env.example .env
  ```
- **macOS / Linux**:
  ```bash
  cp .env.example .env
  ```

Ensure `frontend/.env` points to your backend URL:
```env
VITE_API_URL=http://localhost:8000
```

---

## 🏃 Running the Application

### 1. Start the Backend Server

From the `backend` directory (with virtual environment active):

```bash
uvicorn app.main:app --reload --port 8000
```
- API will be live at: `http://localhost:8000`
- Interactive Swagger API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 2. Start the Frontend Development Server

From the `frontend` directory:

```bash
npm run dev
```
- The frontend web app will be available at: `http://localhost:5173`

---

## 📂 Project Directory Structure

```text
counselai/
├── README.md               # Main project documentation
├── backend/
│   ├── .env.example        # Sample environment configuration
│   ├── requirements.txt    # Python dependencies
│   ├── app/
│   │   ├── main.py         # FastAPI app entry point & lifecycle
│   │   ├── api/            # API endpoints & routing
│   │   ├── core/           # App settings & configuration
│   │   ├── db/             # Database connection & models
│   │   └── services/       # Document extraction, chunking & LLM analysis
│   ├── data/               # SQLite database directory (auto-created)
│   └── storage/            # Stored documents directory (auto-created)
└── frontend/
    ├── package.json        # Frontend dependencies and scripts
    ├── .env.example        # Frontend environment sample
    ├── src/
    │   ├── main.tsx        # Frontend entry point
    │   ├── pages/          # Dashboard and report views
    │   ├── components/     # UI components (Upload, History, Viewer, etc.)
    │   └── lib/            # API client & HTTP helpers
    └── index.html          # HTML entry point
```

---

## 📖 API Documentation

Once the backend is running, open your browser and navigate to:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

### Key Endpoints:
- `POST /api/upload`: Upload batch documents for analysis
- `POST /api/analyze`: Trigger analysis job on uploaded documents
- `GET /api/jobs/{job_id}`: Poll status/progress of an analysis job
- `GET /api/reports`: List previous reports
- `GET /api/reports/{id}`: Fetch detailed analysis report
- `GET /health`: Server & LLM provider health status

---

## ❓ Troubleshooting

- **CORS Issues**: Ensure `CORS_ORIGINS` in `backend/.env` matches your frontend URL (`http://localhost:5173`).
- **Ollama Connection Refused**: Make sure the Ollama daemon is running with `ollama serve` and accessible at `http://localhost:11434`.
- **Port Conflict (8000 or 5173)**:
  - For backend: `uvicorn app.main:app --reload --port 8001` (update `VITE_API_URL` accordingly).
  - For frontend: Vite will automatically suggest an alternate port (e.g. `5174`), ensure `CORS_ORIGINS` in backend includes it.
- **PowerShell Execution Policy Error**: Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` before activating `.venv`.

---

## ⚖ Disclaimer

CounselAI is an AI-assisted legal document review tool designed for productivity and assistive insights. **It is not a substitute for legal advice from a qualified attorney.**
