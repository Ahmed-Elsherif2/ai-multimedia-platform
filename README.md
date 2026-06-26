# AI Multimedia Platform

An AI-powered platform for processing audio/video files and PDF documents.
Upload a meeting recording and get back a full speaker-diarised transcript,
per-segment emotion analysis, document summaries, and a
conversational RAG interface for querying everything you've processed.

---

## Features

- **Speaker diarization** — Pyannote 3.1 separates speakers; Faster-Whisper aligns
  words to each speaker automatically.
- **Emotion analysis** — per-segment sentiment (DistilBERT) and 28-class
  emotion (go_emotions) for each speaker turn.
- **PDF summarization** — Groq API (primary) with template extraction fallback.
- **RAG Q&A** — FAISS + MiniLM-L6-v2 embeddings over uploaded content,
  answered by Groq with rule-based fallback.
- **Chat history** — persistent conversation threads stored in SQLite.
- **Multi-user authentication** — Login/register with bcrypt password hashing.
- **Single-page frontend** — six tabs: Dashboard, Processing, Analytics,
  Transcript, Summaries, History.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser (SPA)                           │
│          frontend/index.html + frontend/js/app.js               │
└─────────────────────────┬───────────────────────────────────────┘
                          │  REST / JSON
┌─────────────────────────▼───────────────────────────────────────┐
│                    Flask Application                            │
│                    backend/app.py                               │
│                                                                 │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐  │
│  │ audio_bp   │  │ pdf_bp   │  │ chat_bp  │  │  rag_bp     │  │
│  └─────┬──────┘  └────┬─────┘  └────┬─────┘  └──────┬──────┘  │
│        │              │             │                │         │
│  ┌─────▼──────────────▼─────────────▼────────────────▼──────┐  │
│  │                  backend/services/                        │  │
│  │                                                           │  │
│  │  DiarizationService   TranscriptionService                │  │
│  │  EmotionService       SummarizationService   RAGService   │  │
│  └─────────────────────────────────────────────────────────-─┘  │
│                                                                 │
│  backend/config/settings.py  ←  .env                           │
│  backend/database/           ←  SQLite (users, files, chats)   │
└─────────────────────────────────────────────────────────────────┘
                          │
                ┌─────────▼─────────┐
                │   Groq API        │
                └───────────────────┘
```

---

## Repository Structure

```
.
├── backend/                         # Production Flask application
│   ├── app.py                       # Main Flask entry point — registers blueprints, serves frontend
│   ├── check_users.py               # CLI utility to view registered users (passwords are hashed)
│   │
│   ├── config/
│   │   └── settings.py              # Central configuration — loads all env variables
│   │
│   ├── database/                    # SQLite database layer
│   │   ├── db.py                    # Connection management & schema creation (WAL mode)
│   │   ├── queries.py               # All CRUD operations (files, transcripts, summaries, chats, users)
│   │   └── migrate.py               # One-time JSON → SQLite migration script
│   │
│   ├── models/
│   │   └── schemas.py               # Typed response schemas (Transcript, Emotion, Summary, RAG)
│   │
│   ├── routes/                      # API route handlers
│   │   ├── auth_routes.py           # Login, register, logout, session management
│   │   ├── audio_routes.py          # Audio upload, processing, transcript & emotion retrieval
│   │   ├── chat_routes.py           # Chat history CRUD (create, read, update, delete)
│   │   ├── emotion_routes.py        # Emotion analysis run & fetch endpoints
│   │   ├── pdf_routes.py            # PDF upload & summarization
│   │   ├── rag_routes.py            # RAG Q&A endpoints (ask, refresh)
│   │   ├── summary_routes.py        # Summary generation & retrieval
│   │   ├── transcript_routes.py     # Transcript retrieval (with legacy aliases)
│   │   └── upload_routes.py         # Unified file intake (audio, video, PDF)
│   │
│   ├── services/                    # Core AI/ML services
│   │   ├── audio_extraction_service.py   # FFmpeg-based audio extraction to WAV
│   │   ├── diarization_service.py        # Speaker diarization via Pyannote 3.1
│   │   ├── emotion_service.py            # Sentiment (DistilBERT) + 28-class emotion (go_emotions)
│   │   ├── media_service.py              # Orchestrates full video/audio pipeline (parallel processing)
│   │   ├── pipeline.py                   # CLI audio processor (called via subprocess)
│   │   ├── rag_service.py                # Retrieval-Augmented Generation with Groq
│   │   ├── summarization_service.py      # PDF summarization (Groq + template fallback)
│   │   ├── transcript_alignment_service.py  # Aligns Whisper words to Pyannote speaker segments
│   │   └── transcription_service.py      # Speech-to-text via Faster-Whisper
│   │
│   ├── utils/                       # Helper utilities
│   │   ├── file_manager.py          # File operations, uploads, cleanup, storage management
│   │   ├── file_utils.py            # File validation, type detection, secure save
│   │   ├── gpu_utils.py             # GPU/device detection (CUDA, MPS, CPU)
│   │   ├── json_store.py            # Thread-safe JSON file store (deprecated — use SQLite)
│   │   ├── logging_utils.py         # Structured logging with elapsed-time tracking
│   │   ├── pipeline.py              # CLI pipeline entry point (called by routes)
│   │   ├── results_store.py         # In-memory result caching with file persistence
│   │   ├── status_tracker.py        # Processing status tracking
│   │   └── time_utils.py            # Time formatting helpers (HMS, timestamps)
│   │
│   ├── uploads/                     # File storage directory (audio, video, PDF uploads)
│   └── requirements.txt             # Python production dependencies
│
├── frontend/                        # Single-page application
│   ├── index.html                   # Main SPA with six tabs (Dashboard, Processing, Analytics, etc.)
│   ├── test.html                    # Alternative landing page / demo entry point
│   ├── css/
│   │   └── app.css                  # Custom dark theme styles, glass-morphism effects
│   └── js/
│       └── app.js                   # Frontend logic — auth, uploads, processing, RAG, UI updates
│
├── docs/
│   └── ADR-001-architecture.md      # Architecture Decision Record — design rationale
│
├── Dockerfile                       # Docker container configuration for Railway deployment
├── railway.json                     # Railway deployment configuration (build & start commands)
├── runtime.txt                      # Python version specification for Railway
├── .gitignore                       # Git ignore rules (.env, .venv, __pycache__, etc.)
├── .env.example                     # Environment variables template (copy to .env)
└── README.md                        # Project documentation (this file)
```

---

## Key Files Explained

| File | Purpose |
|------|---------|
| **`backend/app.py`** | Flask entry point — initializes database, registers blueprints, serves frontend |
| **`backend/database/db.py`** | SQLite connection manager with WAL mode, thread-local connections |
| **`backend/database/queries.py`** | All database operations — files, transcripts, summaries, chats, users |
| **`backend/routes/auth_routes.py`** | Handles user registration, login, logout, and session management |
| **`backend/routes/audio_routes.py`** | Audio upload, processing pipeline trigger, transcript & emotion retrieval |
| **`backend/services/transcription_service.py`** | Faster-Whisper integration for speech-to-text |
| **`backend/services/diarization_service.py`** | Pyannote speaker diarization with lazy loading |
| **`backend/services/rag_service.py`** | FAISS vector search + Groq API for intelligent Q&A |
| **`frontend/js/app.js`** | Main frontend controller — handles UI, API calls, and state management |

---

## Installation

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | 3.11 recommended for all ML dependencies |
| ffmpeg | Must be on `PATH` — used for audio/video conversion |
| Groq API Key | Get from [console.groq.com/keys](https://console.groq.com/keys) |
| HuggingFace Token | Required for Pyannote diarization model |

### Backend Setup

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Linux/Mac:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Copy environment variables
cp .env.example .env
# Edit .env and fill in your API keys
```

### Frontend Setup

The frontend is vanilla HTML/JS — no build step required. The Flask app
serves it directly from `frontend/`.

### Environment Variables

```bash
# Copy the example file
cp .env.example .env
# Then edit .env and fill in at minimum:
#   HF_TOKEN          — from https://huggingface.co/settings/tokens
#   GROQ_API_KEY      — from https://console.groq.com/keys
```

See [`.env.example`](.env.example) for the full variable reference.

Accept the pyannote model terms at:
https://huggingface.co/pyannote/speaker-diarization-3.1

---

## Running Locally

```bash
# 1. Start the Flask backend
cd backend
python app.py

# 2. Open the app
# Navigate to http://localhost:5000
```

The frontend is served directly by Flask at `/`.

---

## API Endpoints

### Authentication

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register a new user |
| POST | `/api/auth/login` | Login with username/password |
| POST | `/api/auth/logout` | Logout current user |
| GET | `/api/auth/me` | Get current user info |

### Audio

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload/audio` | Upload an audio/video file |
| POST | `/api/process/<file_id>` | Start diarization + transcription + emotion |
| GET | `/api/transcript/<file_id>` | Fetch transcript with speaker labels |
| GET | `/api/emotion/<file_id>` | Fetch emotion analysis results |
| GET | `/api/file/<file_id>/status` | Poll processing status |
| DELETE | `/api/file/<file_id>` | Delete file and all associated data |

### PDF

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload/pdf` | Upload a PDF |
| POST | `/api/summarize/<file_id>` | Summarize with Groq |
| GET | `/api/summary/<file_id>` | Fetch summary results |

### Chat

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/chats` | List all chat threads |
| POST | `/api/chats` | Create a new chat thread |
| PUT | `/api/chats/<chat_id>` | Update (rename) a thread |
| DELETE | `/api/chats/<chat_id>` | Delete a thread |

### RAG

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/rag/ask` | Query across all processed content |
| POST | `/api/rag/refresh` | Rebuild the FAISS index |

### Utility

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/cleanup/stats` | Storage usage statistics |
| DELETE | `/api/cleanup/all` | Delete all files |

---


## Deployment

### Railway (Recommended)

1. Push to GitHub.
2. Create a new Railway project and connect the repo.
3. Set environment variables in the Railway dashboard (copy from `.env.example`).
4. Deploy — Railway will automatically build and start your app, you can disable auto deployment in the settings.

**Required Environment Variables:**
- `HF_TOKEN` — Hugging Face token for Pyannote
- `GROQ_API_KEY` — Groq API key for summarization & RAG
- `SECRET_KEY` — Flask session secret (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- `DATA_DIR` — `/app/data` for persistent storage (without reseting the deployment)

### Docker

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_APP=backend/app.py
EXPOSE 5000
CMD ["python", "backend/app.py"]
```

```bash
docker build -t ai-multimedia-platform .
docker run -p 5000:5000 --env-file .env ai-multimedia-platform
```

### Cloud VM (EC2 / DigitalOcean / Azure VM)

```bash
# Clone and run the app
git clone <your-repo>
cd <repo>
cp .env.example .env   # fill in values
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/app.py
```

---

## Known Limitations

- **Processing is synchronous per-file** — long audio files (>5 minutes) may cause the HTTP request to time out; segmentations takes most of the time.
- **Memory usage** — Pyannote and sentence-transformers require ~3GB RAM. Railway Hobby plan (2GB) may need `DISABLE_PYANNOTE=true` or `DISABLE_RAG=true` to run smoothly.

---

## Architecture Decision Record

See [docs/ADR-001-architecture.md](docs/ADR-001-architecture.md) for the
full rationale behind the production restructuring — version conflicts
resolved, design decisions made, and alternatives considered.

---

## License

This project was built as a graduation project. All rights reserved.