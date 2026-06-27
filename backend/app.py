"""
AI Multimedia Platform — Flask application entry point.

Thin entry point: loads config, registers blueprints, serves frontend SPA.
All business logic lives in backend/services/.
All routing logic lives in backend/routes/.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

from config.settings import settings
from database.db import init_db
from routes import (
    upload_bp, transcript_bp, summary_bp, emotion_bp,
    rag_bp, chat_bp,
    audio_bp, pdf_bp,   # backward compat
)
from routes.auth_routes import auth_bp

# Frontend directory
FRONTEND_DIR = settings.BASE_DIR.parent / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config["SECRET_KEY"] = settings.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = settings.max_content_length

# Enable CORS for all routes
CORS(app, supports_credentials=True)

# ── Register Blueprints ──────────────────────────────────────────────────────

app.register_blueprint(auth_bp)
app.register_blueprint(upload_bp)
app.register_blueprint(transcript_bp)
app.register_blueprint(summary_bp)
app.register_blueprint(emotion_bp)
app.register_blueprint(rag_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(audio_bp)
app.register_blueprint(pdf_bp)


# ── Health & Info ─────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "2.0",
        "db": "sqlite",
        "environment": settings.ENVIRONMENT,
        "groq_configured": bool(settings.GROQ_API_KEY),
        "hf_configured": bool(settings.HF_TOKEN),
        "auth_enabled": True,
    }), 200


@app.route("/api/files")
def list_files():
    from database import queries
    from flask import session
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    files = queries.get_all_files(user_id)
    return jsonify(files), 200


@app.route("/api/debug/emotion/<file_id>")
def debug_emotion(file_id):
    import json
    from flask import session
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    transcript_file = settings.UPLOAD_FOLDER / file_id / "transcript.json"
    if not transcript_file.exists():
        return jsonify({"error": "File not found"}), 404
    data = json.loads(transcript_file.read_text(encoding="utf-8"))
    ea = data.get("emotion_analysis", {})
    return jsonify({
        "has_emotion_analysis": bool(ea),
        "overall": ea.get("overall"),
        "segments_count": len(data.get("segments_with_emotion", [])),
    }), 200


# ── Frontend Routes ──────────────────────────────────────────────────────────

@app.route("/")
def serve_index():
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/test.html")
def serve_test():
    return send_from_directory(str(FRONTEND_DIR), "test.html")


@app.route("/js/<path:filename>")
def serve_js(filename):
    js_dir = FRONTEND_DIR / "js"
    return send_from_directory(str(js_dir), filename)


@app.route("/css/<path:filename>")
def serve_css(filename):
    css_dir = FRONTEND_DIR / "css"
    if css_dir.exists():
        return send_from_directory(str(css_dir), filename)
    return jsonify({"error": "CSS directory not found"}), 404


# ── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.errorhandler(500)
def server_error(e):
    return jsonify({
        "error": "Internal server error",
        "message": str(e) if settings.DEBUG else "Please try again later"
    }), 500


@app.errorhandler(413)
def too_large(e):
    return jsonify({
        "error": "File too large",
        "max_size_mb": settings.MAX_CONTENT_MB
    }), 413


# ─── Initialize database on startup ──────────────────────────────────────────
init_db()
print("[startup] ✅ Database initialized")


# ─── Startup Preload ──────────────────────────────────────────────────────────

def _preload():
    """
    Warm up ALL heavy models at startup so the first request doesn't stall.
    This prevents Gunicorn worker timeouts on Railway.
    """
    print("[startup] 🚀 Preloading all AI models...")

    # ── 1. Emotion Service ──
    try:
        from services.emotion_service import emotion_service
        emotion_service.analyze_segment("warmup")
        print("[startup] ✅ Emotion models ready (DistilBERT + RoBERTa-go_emotions)")
    except Exception as exc:
        print(f"[startup] ⚠️ Emotion warmup skipped: {exc}")

    # ── 2. Transcription Service (Faster‑Whisper) ──
    try:
        from services.transcription_service import transcription_service
        # Force the model to load into memory
        transcription_service._load()
        print(f"[startup] ✅ Faster‑Whisper model ready (model={settings.WHISPER_MODEL}, device={transcription_service._device})")
    except Exception as exc:
        print(f"[startup] ⚠️ Whisper warmup failed: {exc}")

    # ── 3. Diarization Service (Pyannote) – A HEAVY ONE ──
    try:
        from services.diarization_service import diarization_service
        # Force the pipeline to download and load
        diarization_service._load()
        print(f"[startup] ✅ Pyannote diarization ready (model={settings.PYANNOTE_MODEL})")
    except Exception as exc:
        print(f"[startup] ⚠️ Diarization warmup failed: {exc}")

    # ── 4. RAG Embedder (Sentence‑Transformers for FAISS) ──
    try:
        from services.rag_service import rag_service
        # Force the embedding model to load
        rag_service._get_embedder()
        print(f"[startup] ✅ RAG embedding model ready (model={settings.EMBEDDING_MODEL})")
    except Exception as exc:
        print(f"[startup] ⚠️ RAG embedding warmup skipped: {exc}")

    # ── 5. Groq API check ──
    if settings.GROQ_API_KEY:
        print("[startup] ✅ Groq API configured")
    else:
        print("[startup] ⚠️ GROQ_API_KEY not set - summarization & RAG will fallback")

    # ── 6. HF Token check ──
    if settings.HF_TOKEN:
        print("[startup] ✅ HF_TOKEN configured")
    else:
        print("[startup] ⚠️ HF_TOKEN not set - diarization will fail!")

    # ── 7. Check data directories ──
    print(f"[startup] 📁 Data directory: {settings.DATA_DIR}")
    print(f"[startup] 📁 Upload directory: {settings.UPLOAD_FOLDER}")
    
    print("[startup] ✅ All services initialized")


# ══════════════════════════════════════════════════════════════════════════════
# 🚀 PRELOAD MODELS NOW – this runs when Gunicorn imports the app
# ══════════════════════════════════════════════════════════════════════════════
_preload()


# ─── Local development entry point ──────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print(f"  🚀 AI Multimedia Platform v2.0")
    print(f"  🌐 http://0.0.0.0:{settings.PORT}")
    print(f"  🔧 Environment: {settings.ENVIRONMENT}")
    print("=" * 60)
    
    # Models are already loaded from the global call, but we keep this for safety
    # (it will be a no‑op if already loaded, but just in case)
    _preload()
    
    app.run(
        debug=settings.DEBUG,
        port=settings.PORT,
        host="0.0.0.0"
    )