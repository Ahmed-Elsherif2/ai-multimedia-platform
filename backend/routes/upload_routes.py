"""
Upload routes — unified file intake for video, audio, and PDF.

POST /api/upload/video  — upload + full pipeline (synchronous, returns transcript)
POST /api/upload/audio  — upload only (process separately via /api/process/<id>)
POST /api/upload/pdf    — upload only (summarize separately via /api/summarize/<id>)
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from config.settings import settings
from database import queries
from utils.file_utils import (
    allowed_extension,
    extension_hint,
    is_video,
    is_audio,
    is_pdf,
    media_type,
    secure_save,
)

upload_bp = Blueprint("upload", __name__, url_prefix="/api")


def _get_user_id():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return user_id


# ── POST /api/upload/video ────────────────────────────────────────────────────

@upload_bp.route("/upload/video", methods=["POST", "OPTIONS"])
def upload_video():
    """
    Upload a video/audio file and run the full pipeline synchronously.
    Returns the complete transcript in one response.
    """
    if request.method == "OPTIONS":
        return "", 200

    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    file = request.files.get("video") or request.files.get("audio") or request.files.get("file")
    if file is None:
        return jsonify({"error": "No file provided. Expected field: 'video', 'audio', or 'file'"}), 400
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    if not allowed_extension(file.filename):
        return jsonify({
            "error": f"Unsupported file type '{Path(file.filename).suffix}'. "
                     f"Accepted: {extension_hint('media')}",
        }), 400

    file_id, saved_path = secure_save(file, settings.UPLOAD_FOLDER)
    ftype = media_type(file.filename)
    now = datetime.now().isoformat()

    queries.upsert_file(
        file_id=file_id,
        original_name=file.filename,
        file_path=str(saved_path),
        file_type=ftype,
        status="processing",
        uploaded_at=now,
        user_id=user_id,
    )

    from services.media_service import media_service
    result = media_service.process(file_id, saved_path)

    if result.status == "processed":
        queries.upsert_transcript(
            file_id=file_id,
            full_text=result.full_text,
            segments=result.transcript,
            conversation=result.conversation,
            per_speaker=result.per_speaker,
            speaker_count=result.speaker_count,
            duration=result.duration,
            emotion_analysis=result.emotion_analysis,
            created_at=datetime.now().isoformat(),
        )
        queries.update_file_status(file_id, "completed")

        return jsonify({
            "file_id": file_id,
            "status": "processed",
            "duration": result.duration,
            "duration_seconds": result.duration_seconds,
            "transcript": result.transcript,
            "conversation": result.conversation,
            "full_text": result.full_text,
            "per_speaker": result.per_speaker,
            "speaker_count": result.speaker_count,
            "emotion_available": result.emotion_available,
            "summary_available": False,
            "rag_available": True,
        }), 200
    else:
        queries.update_file_status(file_id, "failed")
        return jsonify({"file_id": file_id, "status": "failed", "error": result.error}), 500


# ── POST /api/upload/audio ────────────────────────────────────────────────────

@upload_bp.route("/upload/audio", methods=["POST", "OPTIONS"])
def upload_audio():
    """Upload an audio file. Processing triggered separately via /api/process/<id>."""
    if request.method == "OPTIONS":
        return "", 200

    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    file = request.files.get("audio") or request.files.get("file")
    if file is None:
        return jsonify({"error": "No file. Expected field: 'audio'"}), 400
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    if not is_audio(file.filename) and not is_video(file.filename):
        return jsonify({
            "error": f"Expected audio/video. Got '{Path(file.filename).suffix}'. "
                     f"Accepted: {extension_hint('media')}",
        }), 400

    file_id, saved_path = secure_save(file, settings.UPLOAD_FOLDER)
    queries.upsert_file(
        file_id=file_id,
        original_name=file.filename,
        file_path=str(saved_path),
        file_type=media_type(file.filename),
        status="uploaded",
        uploaded_at=datetime.now().isoformat(),
        user_id=user_id,
    )
    return jsonify({"file_id": file_id, "filename": file.filename}), 200


# ── POST /api/upload/pdf ──────────────────────────────────────────────────────

@upload_bp.route("/upload/pdf", methods=["POST", "OPTIONS"])
def upload_pdf():
    """Upload a PDF. Summarization triggered separately via /api/summarize/<id>."""
    if request.method == "OPTIONS":
        return "", 200

    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    file = request.files.get("pdf") or request.files.get("file")
    if file is None:
        return jsonify({"error": "No file. Expected field: 'pdf'"}), 400
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    if not is_pdf(file.filename):
        return jsonify({"error": "Only PDF files are accepted (.pdf)"}), 400

    file_id, saved_path = secure_save(file, settings.UPLOAD_FOLDER)
    queries.upsert_file(
        file_id=file_id,
        original_name=file.filename,
        file_path=str(saved_path),
        file_type="pdf",
        status="uploaded",
        uploaded_at=datetime.now().isoformat(),
        user_id=user_id,
    )
    return jsonify({"file_id": file_id, "filename": file.filename}), 200