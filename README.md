# AI Multimedia Platform

An AI-powered platform for processing audio/video files and PDF documents.
Upload a meeting recording and get back a full speaker-diarised transcript,
per-segment emotion analysis, multi-model document summaries, and a
conversational RAG interface for querying everything you've processed.

---

## Features

- **Speaker diarization** — Pyannote 3.1 separates speakers; Whisper aligns
  words to each speaker automatically.
- **Emotion analysis** — per-segment sentiment (DistilBERT) and 28-class
  emotion (go_emotions) for each speaker turn.
- **PDF summarization** — Gemma 4 E4B GGUF (primary), T5-small (fallback),
  and template extraction (zero-dependency fallback).
- **RAG Q&A** — FAISS + MiniLM-L6-v2 embeddings over uploaded content,
  answered by Ollama/llama3.2 with rule-based fallback.
- **Chat history** — persistent conversation threads stored locally as JSON.
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
│  backend/utils/json_store.py  (thread-safe JSON persistence)   │
└─────────────────────────────────────────────────────────────────┘
                          │
                ┌─────────▼─────────┐
                │  Ollama daemon    │
                │  (llama3.2)       │
                └───────────────────┘
```

---

## Repository Structure

```
.
├── backend/                    Production Flask application
│   ├── app.py                  Thin entry point — blueprint registration only
│   ├── config/
│   │   └── settings.py         All config via environment variables
│   ├── routes/
│   │   ├── audio_routes.py     POST /api/upload/audio, POST /api/process/…
│   │   ├── pdf_routes.py       POST /api/upload/pdf, POST /api/summarize/…
│   │   ├── chat_routes.py      GET/POST/PUT/DELETE /api/chats
│   │   └── rag_routes.py       POST /api/rag/ask, POST /api/rag/refresh
│   ├── services/
│   │   ├── diarization_service.py
│   │   ├── transcription_service.py
│   │   ├── emotion_service.py
│   │   ├── summarization_service.py
│   │   └── rag_service.py
│   ├── utils/
│   │   ├── pipeline.py         CLI audio processor (called via subprocess)
│   │   └── json_store.py       Thread-safe JSON persistence
│   └── requirements.txt        Production-only dependencies
│
├── frontend/                   Single-page application
│   ├── index.html
│   └── js/app.js
│
├── research/                   University coursework (not imported by backend)
│   ├── diarization_lab/        Weeks 1–2: diarization + WER scripts
│   ├── evaluation_lab/         WER evaluation utilities
│   ├── summarization_lab/      Week 3: Gemma/T5/Pegasus experiments
│   ├── emotion_lab/            Week 4: emotion classification prototypes
│   ├── rag_lab/                Week 5: LangChain + Flan-T5 RAG experiment
│   └── README.md               Guide to each lab
│
├── docs/
│   └── ADR-001-architecture.md  Architecture Decision Record
│
├── .env.example                Copy to .env and fill in values
└── README.md                   This file
```

---

## Installation

### Prerequisites

| Requirement | Notes |
|-------------|-------|
| Python 3.11+ | 3.11 recommended for all ML dependencies |
| ffmpeg | Must be on `PATH` — used for audio/video conversion |
| Ollama | Required for RAG Q&A — install from https://ollama.com |
| HuggingFace account | Required for Pyannote diarization model |

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

# Optional: install llama-cpp-python for Gemma summarization
# CPU:  pip install llama-cpp-python
# GPU:  CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python
```

### Frontend Setup

The frontend is vanilla HTML/JS — no build step required.  The Flask app
serves it directly from `frontend/`.

### Environment Variables

```bash
# Copy the example file
cp .env.example .env
# Then edit .env and fill in at minimum:
#   HF_TOKEN          — from https://huggingface.co/settings/tokens
#   GEMMA_MODEL_PATH  — optional; template summarizer is used if blank
```

See [`.env.example`](.env.example) for the full variable reference.

Accept the pyannote model terms at:
https://huggingface.co/pyannote/speaker-diarization-3.1

---

## Running Locally

```bash
# 1. Start Ollama (in a separate terminal)
ollama serve
ollama pull llama3.2

# 2. Start the Flask backend
cd backend
python app.py

# 3. Open the app
# Navigate to http://localhost:5000
```

The frontend is served directly by Flask at `/`.

---

## API Endpoints

### Audio

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload/audio` | Upload an audio/video file; returns `file_id` |
| POST | `/api/process/<file_id>` | Start async diarization + transcription + emotion |
| GET | `/api/transcript/<file_id>` | Fetch transcript with speaker labels |
| GET | `/api/emotion/<file_id>` | Fetch emotion analysis results |
| GET | `/api/file/<file_id>/status` | Poll processing status |

### PDF

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/upload/pdf` | Upload a PDF; returns `file_id` |
| POST | `/api/summarize/<file_id>` | Summarize with Gemma/T5/template |
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

---

## Research Modules

Five laboratory folders under `research/` contain the university coursework
experiments that informed the production implementation.

| Lab | Week | Key output |
|-----|------|-----------|
| `diarization_lab/` | 1–2 | Selected pyannote/whisper combination |
| `evaluation_lab/` | 1–2 | WER benchmarks (base ~12%, small ~9%) |
| `summarization_lab/` | 3 | Gemma ROUGE-L 18 pts > T5-small |
| `emotion_lab/` | 4 | go_emotions 28-class over binary sentiment |
| `rag_lab/` | 5 | Validated MiniLM + FAISS; replaced Flan-T5 with Ollama |

See [research/README.md](research/README.md) for detailed lab documentation.

---

## Deployment

### Railway

1. Push to GitHub.
2. Create a new Railway project and connect the repo.
3. Set environment variables in the Railway dashboard (copy from `.env.example`).
4. Set the start command:
   ```
   cd backend && python app.py
   ```
5. **Note**: Ollama is not available on Railway's free tier.  Either use
   Railway Pro (which allows background services) or point `OLLAMA_URL` at
   a managed inference endpoint and update `OLLAMA_MODEL` accordingly.

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
# Install Ollama on the VM
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2

# Clone and run the app
git clone <your-repo>
cd <repo>
cp .env.example .env   # fill in values
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
python backend/app.py
```

Use `systemd` or `supervisor` to keep both the Flask app and `ollama serve`
running as background services.

---

## Known Limitations

- **No GPU-accelerated diarization by default** — runs on CPU.  Set
  `PYANNOTE_DEVICE=cuda` (add to settings) to enable GPU.
- **Gemma requires manual model download** — the GGUF file (~3.5 GB) must
  be downloaded separately and its path set in `GEMMA_MODEL_PATH`.
- **Ollama not available on Railway free tier** — rule-based RAG answers
  work without Ollama, but LLM-quality answers require it.
- **No authentication** — the API has no auth layer.  Do not expose to the
  public internet without adding authentication.
- **Processing is synchronous per-file** — long audio files (>1 hour) may
  cause the HTTP request to time out; a task queue (Celery/RQ) would be
  needed for production scale.

---

## Future Improvements

- Replace subprocess pipeline with Celery task queue for async processing
- Add Whisper `large-v3` support via `WHISPER_MODEL=large-v3`
- Speaker identification across sessions (voice embedding comparison)
- Streaming transcription output via Server-Sent Events
- Authentication layer (JWT or session-based)
- Multilingual support (Whisper is multilingual; emotion models need swapping)
- Export transcripts as DOCX / SRT / VTT

---

## Contributors

This project was built as a graduation project at [University Name].

| Role | Contribution |
|------|-------------|
| Ahmed | Diarization research, emotion analysis, backend architecture |
| [Team] | Frontend, RAG module, PDF summarization |

---

## Architecture Decision Record

See [docs/ADR-001-architecture.md](docs/ADR-001-architecture.md) for the
full rationale behind the production restructuring — version conflicts
resolved, design decisions made, and alternatives considered.
