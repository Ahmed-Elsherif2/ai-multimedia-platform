# ADR-001 — Production Architecture Restructuring

| Field       | Value                            |
|-------------|----------------------------------|
| Date        | 2026-06-20                       |
| Authors     | AI Multimedia Platform Team      |
| Supersedes  | —                                |

---

## Context

The repository accumulated four distinct layers of code over a five-week
university project:

1. **Week 1–2 (DIR_GRAD/)** — standalone diarization research scripts, WER
   evaluation utilities, and a full copy of the FFmpeg source tree.
2. **Week 3 (ai-multimedia-platform/week3_document_summarization/)** — PDF
   summarization module with Gemma 4 E4B, T5-small, and a template baseline.
3. **Week 4 (emotion_analysis/)** — proper class-based emotion/sentiment
   analysis (`SentimentAnalyzer`, `EmotionAnalyzer`).
4. **Week 5 (RAG/)** — semantic search experiment over the arXiv dataset
   using LangChain + Flan-T5.

A production Flask backend (`backend/`) and single-page frontend
(`frontend/`) were developed in parallel, gradually importing research code
directly and, in some cases, reimplementing it inline.

### Problems this ADR resolves

| # | Problem | Impact |
|---|---------|--------|
| 1 | `torch==2.8.0` (research) vs `torch==2.3.0` (production) | Shared venv breaks on `pip install` |
| 2 | `pyannote.audio==3.4.0` vs `3.1.1` | Silent diarization output format drift |
| 3 | Gemma model path hardcoded to `C:/Users/{user}/models/...` | Fails on every machine except the original developer's |
| 4 | Emotion logic implemented twice (class in `emotion_analysis/` + inline in `pipeline.py`) | Bug fixes applied to one copy don't reach the other |
| 5 | Week 5 RAG module disconnected from production backend | Research findings wasted; backend reimplements from scratch |

---

## Decision

### 1 — Separate research from production at the filesystem level

All university assignments, experiments, notebooks, and benchmarking scripts
are moved into a `research/` tree:

```
research/
  diarization_lab/   ← DIR_GRAD/ scripts (no FFmpeg source)
  evaluation_lab/    ← WER evaluation scripts
  emotion_lab/       ← emotion_analysis/ module
  rag_lab/           ← RAG/ module
  summarization_lab/ ← week3_document_summarization/
```

**Rule**: production code (`backend/`) never imports from `research/`.
Research code is reference material only.

### 2 — One service per AI capability

Five service classes under `backend/services/` replace all duplicated and
inline logic:

| Service | Replaces |
|---------|----------|
| `EmotionService` | `emotion_analysis/emotion_analyzers.py` + `pipeline.py::run_emotion_analysis()` |
| `DiarizationService` | `pipeline.py` diarization block |
| `TranscriptionService` | `pipeline.py` transcription + alignment block |
| `SummarizationService` | `week3_document_summarization/summarizers.py` (no hardcoded path) |
| `RAGService` | `app.py` RAG functions (`_build_context`, `_ollama_answer`, `_rule_based_answer`) |

Each service is a module-level singleton (lazy-loaded on first use, then
cached for the process lifetime).

### 3 — Configuration via environment variables only

`backend/config/settings.py` is the single source of all configuration.
Every value is read from an environment variable with a safe default.

The Gemma model path is now `settings.GEMMA_MODEL_PATH` (from
`GEMMA_MODEL_PATH` in `.env`).  If the variable is empty, summarisation
degrades gracefully to the template extractor — no crash, no stack trace.

### 4 — Resolve version conflicts

Production virtualenv pins:

```
torch==2.3.1          # compatible with pyannote 3.1.1 + transformers 4.46
pyannote.audio==3.1.1 # proven stable in production
```

Research environments retain their own `research_requirements.txt` files
and must be installed in **separate** virtualenvs.

### 5 — RAG architecture decision: Ollama over Flan-T5

The Week 5 RAG experiment used `google/flan-t5-base` (HuggingFace inference,
~900 MB RAM) and LangChain.  The production backend uses Ollama + `llama3.2`
(~2 GB RAM, runs locally via a background daemon).

**Rationale for keeping Ollama in production:**
- `llama3.2` produces significantly higher-quality answers than `flan-t5-base`
  for open-domain QA.
- Ollama decouples LLM management from the Python process — model updates
  don't require redeployment.
- The Flan-T5 approach is archived in `research/rag_lab/` for reproducibility.

The same embedding model (`all-MiniLM-L6-v2`) and FAISS index are shared —
this part of the Week 5 research was validated and ported.

### 6 — Flask blueprints replace monolithic app.py

`app.py` is now ~120 lines (app factory + blueprint registration + startup).
Route logic lives in eight blueprints:

| Blueprint | Module | Notes |
| --------- | ------ | ----- |
| `upload_bp` | `routes/upload_routes.py` | New — video + audio + pdf intake |
| `transcript_bp` | `routes/transcript_routes.py` | New — transcript fetch + process trigger |
| `summary_bp` | `routes/summary_routes.py` | New — PDF summarization |
| `emotion_bp` | `routes/emotion_routes.py` | New — emotion analysis |
| `chat_bp` | `routes/chat_routes.py` | Updated to read/write SQLite |
| `rag_bp` | `routes/rag_routes.py` | Updated to read/write SQLite |
| `audio_bp` | `routes/audio_routes.py` | Kept for backward compatibility |
| `pdf_bp` | `routes/pdf_routes.py` | Kept for backward compatibility |

---

## Consequences

### Positive

- Any developer can clone the repo, copy `.env.example` → `.env`, fill in
  `HF_TOKEN` and optionally `GEMMA_MODEL_PATH`, and run the backend — no
  machine-specific values in code.
- Emotion analysis has one canonical implementation.  Fixing a model bug
  or swapping a model requires editing one file.
- Research artifacts are preserved and reproducible from their own
  requirements files.
- Adding a new AI capability = adding one service file + one route file +
  registering the blueprint in `app.py`.

### Negative / Trade-offs

- The production backend no longer imports directly from the research
  modules.  If a research breakthrough needs to reach production it must be
  ported into a service — this is intentional friction that prevents
  accidental coupling.
- Ollama must be running locally for RAG Q&A.  There is no pure-Python
  fallback LLM in production (rule-based answers cover the most common
  queries without Ollama).

### Risks

- `llama3.2` via Ollama is not available on Railway's free tier (no
  persistent background process).  Cloud deployments should use the Railway
  Pro plan or switch `OLLAMA_URL` to a managed inference endpoint.
- Gemma 4 E4B GGUF (~3.5 GB) requires the user to download and configure
  the model manually.  Summarization degrades gracefully to the template
  extractor when `GEMMA_MODEL_PATH` is not set.

---

## Alternatives Considered

| Alternative | Why rejected |
|-------------|-------------|
| Keep research imports in production | Prevents independent versioning; Week 5 RAG conflict demonstrated this clearly |
| Use LangChain in production RAG | Adds heavy dependency (~200 MB) for functionality already implemented cleanly in 80 lines |
| Upgrade to pyannote 3.4.0 in production | Requires torch 2.8.0 which conflicts with other production dependencies |
| Replace Ollama with OpenAI API | Introduces external API dependency and cost; offline-first is a stated requirement |

---

## Related Documents

- `research/README.md` — guide to the research labs
- `README.md` — installation and deployment
- `.env.example` — full list of environment variables

---

## Revision — 2026-06-21: SQLite migration + pipeline consolidation

### What changed

#### R1 — JSON file store replaced by SQLite

The original implementation stored metadata in four JSON files
(`data/files.json`, `data/transcripts.json`, `data/summaries.json`,
`data/chats.json`) and per-file results under `uploads/<id>/transcript.json`.

**Decision**: replace with a single SQLite database at `data/platform.db`.

| Aspect | JSON store | SQLite |
| ------ | ---------- | ------ |
| Concurrent writes | Race conditions under load | WAL mode — safe for multi-thread Flask |
| Query | Full file read + Python filter | SQL WHERE / JOIN |
| Schema enforcement | None — any key accepted | Typed columns, enforced at insert |
| Migration | — | `ON CONFLICT DO UPDATE` upsert; idempotent |

Four tables: `files`, `transcripts`, `summaries`, `chats`.
Binary files (`.mp4`, `.wav`, `.pdf`) remain on disk under `uploads/<id>/`.
All text and metadata (full transcript, segments JSON, emotion JSON, chat
messages) are stored in the database.
Thread-local connections (`threading.local`) prevent cross-thread sharing.

All existing data (34 files, 27 transcripts, 3 summaries, 1 chat) was
migrated once via `backend/database/migrate.py`. Hardcoded paths from the
original developer's machine were normalised to the current uploads folder.

#### R2 — Two new services extracted from existing ones

`DiarizationService` and `TranscriptionService` had grown to include
responsibilities outside their names.  Two new focused services were split out:

| New service | Extracted from | Responsibility |
| ----------- | -------------- | -------------- |
| `AudioExtractionService` | `DiarizationService` | ffmpeg WAV conversion, duration measurement |
| `TranscriptAlignmentService` | `TranscriptionService` | Word-level Whisper → Pyannote speaker mapping |

A sixth service, `MediaService`, was added as a pipeline orchestrator:

```text
AudioExtractionService → DiarizationService → TranscriptionService
  → TranscriptAlignmentService → EmotionService → persist to disk + SQLite
```

`MediaService.process(file_id, src_path)` returns a `MediaProcessingResult`
dataclass with all fields needed to respond to the frontend in one call.

#### R3 — Single-step video upload endpoint

**Before**: uploading a video was a two-step flow —
`POST /api/upload/audio` (save only) → user clicks "Process Content" →
`POST /api/process/<id>` (subprocess pipeline).

**After**: `POST /api/upload/video` runs `MediaService.process()` inline,
blocks until the full pipeline completes, and returns the transcript,
conversation, emotion results, and speaker count in a single response.
No polling or second click required.

Audio-only files (`.mp3`, `.wav`, etc.) retain the two-step flow since they
may not always need immediate processing.

#### R4 — Frontend routing conflict fixed

`handleAudioUpload()` in `frontend/js/app.js` already detected video
extensions but always sent the file to `/api/upload/audio` regardless.
The new endpoint was unreachable from the UI.

Fix: the upload handler now branches on `isVideo` —
video files call `POST /api/upload/video` (field: `video`, timeout: 11 min);
audio files call `POST /api/upload/audio` (field: `audio`, timeout: 2 min).
On success the video path caches the transcript immediately in
`chat.processedFiles` so the "Process Content" button stays disabled for
that file.

Re-uploading the same filename now replaces the existing `chat.attached`
entry instead of appending a duplicate.

#### R5 — Subprocess encoding hardened

`subprocess.run(..., text=True)` on Windows defaults to the system codepage
(cp1252), which cannot decode Arabic or other non-Latin characters in
Whisper output.  Added `encoding="utf-8"` to the `subprocess.run` call in
`routes/transcript_routes.py`.

### Updated service map

| Service | File | Role |
| ------- | ---- | ---- |
| `AudioExtractionService` | `services/audio_extraction_service.py` | ffmpeg WAV + duration |
| `DiarizationService` | `services/diarization_service.py` | Pyannote speaker segments |
| `TranscriptionService` | `services/transcription_service.py` | Whisper ASR |
| `TranscriptAlignmentService` | `services/transcript_alignment_service.py` | Word → speaker mapping |
| `EmotionService` | `services/emotion_service.py` | Sentiment + emotion per segment |
| `MediaService` | `services/media_service.py` | Pipeline orchestrator |
| `SummarizationService` | `services/summarization_service.py` | Gemma / T5 / template PDF summary |
| `RAGService` | `services/rag_service.py` | Embedding + Ollama Q&A |
