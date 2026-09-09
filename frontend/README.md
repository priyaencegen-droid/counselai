# CounselAI Frontend

React + TypeScript + Vite + Tailwind CSS web application for CounselAI.

## Quick Start

### 1. Install Dependencies

```bash
npm install
```

### 2. Environment Configuration

Copy `.env.example` to `.env`:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Ensure `VITE_API_URL` points to your backend:
```env
VITE_API_URL=http://localhost:8000
```

### 3. Run Development Server

```bash
npm run dev
```

The application will run at `http://localhost:5173`.

### 4. Production Build

```bash
npm run build
npm run preview
```
