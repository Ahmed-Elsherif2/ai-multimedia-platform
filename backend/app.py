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

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

from config.settings import settings
from database.db import init_db
from routes import (
    upload_bp, transcript_bp, summary_bp, emotion_bp,
    rag_bp, chat_bp,
    audio_bp, pdf_bp,   # backward compat
)
from routes.auth_routes import auth_bp  # 🆕 Import auth blueprint

# Frontend directory
FRONTEND_DIR = settings.BASE_DIR.parent / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.config["SECRET_KEY"] = settings.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = settings.max_content_length

# Enable CORS for all routes
CORS(app, supports_credentials=True)  # 🆕 Allow cookies for sessions

# ── Register Blueprints ──────────────────────────────────────────────────────

# Authentication (must be registered first)
app.register_blueprint(auth_bp)  # 🆕

# New blueprints (preferred)
app.register_blueprint(upload_bp)
app.register_blueprint(transcript_bp)
app.register_blueprint(summary_bp)
app.register_blueprint(emotion_bp)
app.register_blueprint(rag_bp)
app.register_blueprint(chat_bp)

# Backward-compat blueprints (keep existing frontend working)
app.register_blueprint(audio_bp)
app.register_blueprint(pdf_bp)


# ── Health & Info ─────────────────────────────────────────────────────────────

@app.route("/api/health")
def health():
    """Health check endpoint for Railway/Hosting."""
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
    """Return all files for the current user."""
    from database import queries
    from flask import session
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    files = queries.get_all_files(user_id)
    return jsonify(files), 200


@app.route("/api/debug/emotion/<file_id>")
def debug_emotion(file_id):
    """Development helper — raw emotion data for a processed file."""
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
    """Serve the main frontend application."""
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.route("/test.html")
def serve_test():
    """Serve the test page (if exists)."""
    return send_from_directory(str(FRONTEND_DIR), "test.html")


@app.route("/js/<path:filename>")
def serve_js(filename):
    """Serve JavaScript files."""
    js_dir = FRONTEND_DIR / "js"
    return send_from_directory(str(js_dir), filename)


@app.route("/css/<path:filename>")
def serve_css(filename):
    """Serve CSS files (if exists)."""
    css_dir = FRONTEND_DIR / "css"
    if css_dir.exists():
        return send_from_directory(str(css_dir), filename)
    return jsonify({"error": "CSS directory not found"}), 404


# ── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    """Handle 404 errors gracefully."""
    if request.path.startswith("/api/"):
        return jsonify({"error": "API endpoint not found"}), 404
    return send_from_directory(str(FRONTEND_DIR), "index.html")


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors gracefully."""
    return jsonify({
        "error": "Internal server error",
        "message": str(e) if settings.DEBUG else "Please try again later"
    }), 500


@app.errorhandler(413)
def too_large(e):
    """Handle file too large errors."""
    return jsonify({
        "error": "File too large",
        "max_size_mb": settings.MAX_CONTENT_MB
    }), 413


# ── Startup ──────────────────────────────────────────────────────────────────

def _preload():
    """Warm up heavy models at startup so the first request doesn't stall."""
    print("[startup] Preloading services...")
    
    # 1. Emotion service
    try:
        from services.emotion_service import emotion_service
        emotion_service.analyze_segment("warmup")
        print("[startup] ✅ Emotion models ready")
    except Exception as exc:
        print(f"[startup] ⚠️ Emotion warmup skipped: {exc}")

    # 2. Check Groq configuration (your primary LLM)
    if settings.GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)
            # Quick test - list models (lightweight)
            print("[startup] ✅ Groq API configured")
        except Exception as exc:
            print(f"[startup] ⚠️ Groq API check failed: {exc}")
    else:
        print("[startup] ⚠️ GROQ_API_KEY not set - Groq summarization disabled")

    # 3. Check HF token (needed for diarization)
    if settings.HF_TOKEN:
        print("[startup] ✅ HF_TOKEN configured")
    else:
        print("[startup] ⚠️ HF_TOKEN not set - diarization may fail")

    # 4. Check data directories
    print(f"[startup] 📁 Data directory: {settings.DATA_DIR}")
    print(f"[startup] 📁 Upload directory: {settings.UPLOAD_FOLDER}")
    
    print("[startup] ✅ All services initialized")


if __name__ == "__main__":
    print("=" * 60)
    print(f"  🚀 AI Multimedia Platform v2.0")
    print(f"  🌐 http://0.0.0.0:{settings.PORT}")
    print(f"  🔧 Environment: {settings.ENVIRONMENT}")
    print("=" * 60)
    
    # Initialize database
    init_db()
    
    # Preload services
    _preload()
    
    # Run app
    app.run(
        debug=settings.DEBUG,
        port=settings.PORT,
        host="0.0.0.0"
    )