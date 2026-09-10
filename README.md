CounselAI — Legal Document Analysis Dashboard

CounselAI is a full-stack, AI-powered legal document review and analysis platform built with FastAPI, SQLite, React, and Tailwind CSS. It supports batch processing of legal documents (PDF, DOCX, TXT, XLS, XLSX) using Ollama (local/cloud) or OpenAI-compatible LLM providers (e.g., OpenAI, Groq).

📑 Table of Contents

Features

Tech Stack

Project Flow & Architecture

Prerequisites

Quick Start Guide

1. Backend Setup

2. LLM Provider Configuration

3. Frontend Setup

Running the Application

Project Directory Structure

API Documentation

Troubleshooting

Disclaimer

🚀 Features

Bulk Document Upload: Process multiple PDF, DOCX, TXT, XLS, and XLSX files with batch-size validation.

Smart Text Extraction & Chunking: Configurable chunk sizes and overlaps with metadata preservation.

Map-Reduce LLM Analysis: High-capacity document summarization and risk analysis capable of processing large document sets.

Flexible LLM Providers: Support for local Ollama instances, Ollama Cloud, or OpenAI-compatible APIs (OpenAI, Groq, etc.).

Optional Embeddings: Embedding support via Ollama (nomic-embed-text).

Persistent Job History: SQLite-backed history with job status polling and automatic recovery of interrupted jobs.

Rich Report Viewer: Markdown report viewer with export options (Copy, TXT export, and print-to-PDF).

Modern UI: Clean interface built with React, Lucide Icons, and Tailwind CSS with dark/light mode support.

🛠 Tech Stack

Backend: Python 3.10+, FastAPI, Uvicorn, SQLAlchemy (Async), aiosqlite, pydantic-settings, pypdf, python-docx

Frontend: React 18+, TypeScript, Vite, Tailwind CSS, Lucide React, React Markdown

Database: SQLite (via aiosqlite)

LLM / AI: Ollama / OpenAI-compatible API

End-to-End Workflow Breakdown

Document Ingestion (Frontend -> Backend):

User drags and drops or selects up to 100 legal documents (PDF, DOCX, TXT, XLS, XLSX).

Frontend validates batch size and constraints, then uploads files via POST /api/upload.

Files are stored asynchronously on disk (./storage/{job_id}) and metadata is tracked in SQLite.

Job Initialization (POST /api/analyze):

The user triggers analysis with custom instructions or default legal review prompts.

An asynchronous background task is spawned, returning a job_id immediately so the UI remains non-blocking.

Text Extraction & Chunking:

File parsers extract raw text according to file format (pypdf for PDF, python-docx for DOCX, UTF-8 reader for TXT).

The document cleaner strips formatting noise and breaks large documents into semantic chunks using sliding windows (CHUNK_SIZE and CHUNK_OVERLAP).

Map-Reduce LLM Intelligence Pipeline:

Map Phase: Chunks are processed in batches by the LLM (Ollama or OpenAI/Groq) to identify specific clauses, covenants, liabilities, indemnity terms, termination conditions, and risks.

Reduce Phase: The LLM synthesizes all intermediate chunk summaries into an executive legal report with structured sections:

Executive Summary

Key Obligations & Deliverables

Risk Assessment & Liability Matrix

Inconsistencies, Ambiguities & Red Flags

Strategic & Actionable Recommendations

Real-Time Polling & Resilient State Management:

The frontend continuously polls GET /api/jobs/{job_id} for live status, stage transitions, and completion percentage.

If the backend restarts, interrupted jobs are automatically detected and managed via startup lifecycle hooks.

Interactive Report Viewing, History & Export:

Once complete, the markdown report is formatted in the UI with syntax styling and risk callouts.

Reports are permanently stored in SQLite, accessible from the past reports sidebar, and can be exported as .txt, copied to clipboard, or printed to PDF.

📋 Prerequisites

Before starting, ensure you have the following installed:

Python: Version 3.10 or higher (python --version)

Node.js: Version 18.x or higher and npm (node -v and npm -v)

LLM Engine:

Local Ollama (Download from ollama.com), OR

An API key for an OpenAI-compatible provider (OpenAI, Groq, etc.)

⚡ Quick Start Guide

1. Backend Setup

Open a terminal and navigate to the backend directory:


cd backend


Step 1.1: Create and Activate a Virtual Environment

Windows (PowerShell):


python -m venv .venv

.venv\Scripts\Activate.ps1


(If script execution is disabled, run Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass first)

Windows (Command Prompt):


python -m venv .venv

.venv\Scripts\activate.bat


macOS / Linux:


python3 -m venv .venv

source .venv/bin/activate


Step 1.2: Install Python Dependencies


pip install -r requirements.txt


Step 1.3: Configure Backend Environment Variables

Copy the example environment file:

Windows (PowerShell / CMD):


copy .env.example .env


macOS / Linux:


cp .env.example .env


2. LLM Provider Configuration

Edit backend/.env according to your preferred LLM provider:

Option A: Local Ollama (Default)

Make sure Ollama is installed and running:


ollama serve


Pull the required models:


ollama pull llama3.1:8b

ollama pull nomic-embed-text


Set in backend/.env:


LLM_PROVIDER=ollama

OLLAMA_BASE_URL=http://localhost:11434

OLLAMA_MODEL=llama3.1:8b

ENABLE_EMBEDDINGS=false


Option B: OpenAI / Cloud Provider

Set in backend/.env:


LLM_PROVIDER=cloud

CLOUD_API_KEY=your_actual_api_key_here

CLOUD_BASE_URL=https://api.openai.com/v1

CLOUD_MODEL=gpt-4o-mini


(For Groq, set CLOUD_BASE_URL=https://api.groq.com/openai/v1 and CLOUD_MODEL=llama-3.1-70b-versatile)

3. Frontend Setup

Open a new terminal window and navigate to the frontend directory:


cd frontend


Step 3.1: Install Node Dependencies


npm install


Step 3.2: Configure Frontend Environment Variables

Create .env from .env.example:

Windows (PowerShell / CMD):


copy .env.example .env


macOS / Linux:


cp .env.example .env


Ensure frontend/.env points to your backend URL:


VITE_API_URL=http://localhost:8000


🏃 Running the Application

1. Start the Backend Server

From the backend directory (with virtual environment active):


uvicorn app.main:app --reload --port 8000


API will be live at: http://localhost:8000

Interactive Swagger API docs: http://localhost:8000/docs

Health check: http://localhost:8000/health

2. Start the Frontend Development Server

From the frontend directory:


npm run dev


The frontend web app will be available at: http://localhost:5173

📂 Project Directory Structure


counselai/

├── README.md               # Main project documentation

├── backend/

│   ├── .env.example        # Sample environment configuration

│   ├── requirements.txt    # Python dependencies

│   ├── app/

│   │   ├── main.py         # FastAPI app entry point & lifecycle

│   │   ├── api/            # API endpoints & routing

│   │   ├── core/           # App settings & configuration

│   │   ├── db/             # Database connection & models

│   │   └── services/       # Document extraction, chunking & LLM analysis

│   ├── data/               # SQLite database directory (auto-created)

│   └── storage/            # Stored documents directory (auto-created)

└── frontend/

    ├── package.json        # Frontend dependencies and scripts

    ├── .env.example        # Frontend environment sample

    ├── src/

    │   ├── main.tsx        # Frontend entry point

    │   ├── pages/          # Dashboard and report views

    │   ├── components/     # UI components (Upload, History, Viewer, etc.)

    │   └── lib/            # API client & HTTP helpers

    └── index.html          # HTML entry point


📖 API Documentation

Once the backend is running, open your browser and navigate to:

Swagger UI: http://localhost:8000/docs

ReDoc UI: http://localhost:8000/redoc

Key Endpoints:

POST /api/upload: Upload batch documents for analysis

POST /api/analyze: Trigger analysis job on uploaded documents

GET /api/jobs/{job_id}: Poll status/progress of an analysis job

GET /api/reports: List previous reports

GET /api/reports/{id}: Fetch detailed analysis report

GET /health: Server & LLM provider health status

❓ Troubleshooting

CORS Issues: Ensure CORS_ORIGINS in backend/.env matches your frontend URL (http://localhost:5173).

Ollama Connection Refused: Make sure the Ollama daemon is running with ollama serve and accessible at http://localhost:11434.

Port Conflict (8000 or 5173):

For backend: uvicorn app.main:app --reload --port 8001 (update VITE_API_URL accordingly).

For frontend: Vite will automatically suggest an alternate port (e.g. 5174), ensure CORS_ORIGINS in backend includes it.

PowerShell Execution Policy Error: Run Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass before activating .venv.

⚖ Disclaimer

CounselAI is an AI-assisted legal document review tool designed for productivity and assistive insights. It is not a substitute for legal advice from a qualified attorney.