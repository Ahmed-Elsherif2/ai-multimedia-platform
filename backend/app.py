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
    # Check if models are ready by testing if Pyannote loaded
    models_ready = False
    try:
        from services.diarization_service import diarization_service
        # Check if pipeline is loaded (won't download, just checks memory)
        models_ready = diarization_service._pipeline is not None
    except:
        pass
    
    return jsonify({
        "status": "ok",
        "version": "2.0",
        "db": "sqlite",
        "environment": settings.ENVIRONMENT,
        "groq_configured": bool(settings.GROQ_API_KEY),
        "hf_configured": bool(settings.HF_TOKEN),
        "auth_enabled": True,
        "models_ready": models_ready,
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


# ─── CONSOLE PRELOAD FUNCTION ───────────────────────────────────────────────
# Run this from Railway console: cd /app/backend && python -c "from app import console_preload; console_preload()"

def console_preload():
    """
    Preload all models – run this ONCE from the Railway console.
    This will download models to /root/.cache/huggingface (your volume).
    After this, all subsequent requests will be fast.
    
    How to run:
        cd /app/backend
        python -c "from app import console_preload; console_preload()"
    """
    import time
    
    print("=" * 60)
    print("🚀 PRELOADING MODELS – RUNNING ON RAILWAY CONSOLE")
    print("=" * 60)
    
    print(f"📁 Data directory: {settings.DATA_DIR}")
    print(f"📁 HF_TOKEN set: {'✅' if settings.HF_TOKEN else '❌'}")
    print(f"📁 GROQ_API_KEY set: {'✅' if settings.GROQ_API_KEY else '❌'}")
    print("")
    
    # ── 1. Emotion models ──
    print("📊 Loading Emotion models (DistilBERT + RoBERTa-go_emotions)...")
    start = time.time()
    try:
        from services.emotion_service import emotion_service
        emotion_service.analyze_segment("warmup")
        print(f"✅ Emotion models loaded in {time.time() - start:.1f}s")
    except Exception as e:
        print(f"⚠️ Emotion failed: {e}")
    
    # ── 2. Pyannote (HEAVY) ──
    print("🎙️ Loading Pyannote diarization (this takes 2-3 minutes)...")
    start = time.time()
    try:
        from services.diarization_service import diarization_service
        diarization_service._load()
        print(f"✅ Pyannote loaded in {time.time() - start:.1f}s")
    except Exception as e:
        print(f"⚠️ Pyannote failed: {e}")
    
    # ── 3. RAG embedder ──
    print("🧠 Loading RAG embedding model (sentence-transformers)...")
    start = time.time()
    try:
        from services.rag_service import rag_service
        rag_service._get_embedder()
        print(f"✅ RAG embedder loaded in {time.time() - start:.1f}s")
    except Exception as e:
        print(f"⚠️ RAG embedder failed: {e}")
    
    print("")
    print("=" * 60)
    print("✅ All models preloaded!")
    print("📁 Models saved to: /root/.cache/huggingface")
    print("🔄 This volume will persist across restarts and deployments")
    print("=" * 60)


# ─── Local development entry point ──────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print(f"  🚀 AI Multimedia Platform v2.0")
    print(f"  🌐 http://0.0.0.0:{settings.PORT}")
    print(f"  🔧 Environment: {settings.ENVIRONMENT}")
    print("=" * 60)
    
    # For local development, preload models
    console_preload()
    
    app.run(
        debug=settings.DEBUG,
        port=settings.PORT,
        host="0.0.0.0"
    )