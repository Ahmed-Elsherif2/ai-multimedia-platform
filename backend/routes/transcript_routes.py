"""
Transcript routes — backed by SQLite.

GET  /api/transcripts/<file_id>    — fetch transcript
GET  /api/transcript/<file_id>     — legacy singular alias
GET  /api/file/<file_id>/status    — poll status
POST /api/process/<file_id>        — backward-compat trigger
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from config.settings import settings
from database import queries

transcript_bp = Blueprint("transcript", __name__, url_prefix="/api")


def _get_user_id():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return user_id


@transcript_bp.route("/transcripts/<file_id>", methods=["GET", "OPTIONS"])
def get_transcript(file_id):
    if request.method == "OPTIONS":
        return "", 200

    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    # Verify ownership
    file_info = queries.get_file(file_id)
    if not file_info or file_info.get("user_id") != user_id:
        return jsonify({"error": "File not found or access denied"}), 404

    # SQLite first
    t = queries.get_transcript(file_id)
    if t:
        return jsonify({
            "file_id": file_id,
            "full_text": t.get("full_text", ""),
            "transcript": t.get("segments", []),
            "conversation": t.get("conversation", []),
            "per_speaker": t.get("per_speaker", {}),
            "speaker_count": t.get("speaker_count", 0),
            "duration": t.get("duration", ""),
        }), 200

    # Fallback: per-file transcript.json on disk
    tf = settings.UPLOAD_FOLDER / file_id / "transcript.json"
    if tf.exists():
        try:
            data = json.loads(tf.read_text(encoding="utf-8"))
            return jsonify({
                "file_id": file_id,
                "full_text": data.get("full_text", ""),
                "transcript": data.get("segments_with_text", data.get("segments", [])),
                "conversation": data.get("conversation", []),
                "per_speaker": data.get("per_speaker", {}),
                "speaker_count": data.get("speaker_count", 0),
                "duration": data.get("duration", ""),
            }), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return jsonify({"error": "Transcript not found — has this file been processed?"}), 404


@transcript_bp.route("/transcript/<file_id>", methods=["GET", "OPTIONS"])
def get_transcript_legacy(file_id):
    if request.method == "OPTIONS":
        return "", 200
    return get_transcript(file_id)


@transcript_bp.route("/file/<file_id>/status", methods=["GET", "OPTIONS"])
def file_status(file_id):
    if request.method == "OPTIONS":
        return "", 200
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    f = queries.get_file(file_id)
    if not f or f.get("user_id") != user_id:
        return jsonify({"error": "File not found"}), 404
    return jsonify({"status": f.get("status", "unknown")}), 200


@transcript_bp.route("/process/<file_id>", methods=["POST", "OPTIONS"])
def process_audio(file_id):
    """Backward-compat: trigger pipeline via subprocess, then save to SQLite."""
    if request.method == "OPTIONS":
        return "", 200

    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    f = queries.get_file(file_id)
    if not f or f.get("user_id") != user_id:
        return jsonify({"error": "File not found or access denied"}), 404

    audio_path = f["file_path"]
    if not Path(audio_path).exists():
        return jsonify({"error": "Audio file missing from disk"}), 404

    if f.get("status") == "completed":
        t = queries.get_transcript(file_id)
        if t:
            return jsonify({"status": "completed", "transcript": t}), 200

    queries.update_file_status(file_id, "processing")

    try:
        output_dir = settings.UPLOAD_FOLDER / file_id
        output_dir.mkdir(exist_ok=True)
        pipeline_script = settings.BASE_DIR / "utils" / "pipeline.py"

        import os
        env = {**os.environ, "HF_TOKEN": settings.HF_TOKEN, "WHISPER_MODEL": settings.WHISPER_MODEL}

        proc = subprocess.run(
            [sys.executable, str(pipeline_script),
             "--audio", audio_path,
             "--output_dir", str(output_dir),
             "--whisper_model", settings.WHISPER_MODEL],
            capture_output=True, text=True, encoding="utf-8", timeout=600, env=env,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Pipeline failed: {proc.stderr[:500]}")

        td: dict = {"full_text": "", "segments": [], "per_speaker": {}, "speaker_count": 1}
        for line in reversed(proc.stdout.strip().split("\n")):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    td = json.loads(line)
                    break
                except json.JSONDecodeError:
                    pass

        queries.upsert_transcript(
            file_id=file_id,
            full_text=td.get("full_text", ""),
            segments=td.get("segments", []),
            conversation=td.get("conversation", []),
            per_speaker=td.get("per_speaker", {}),
            speaker_count=td.get("speaker_count", 0),
            emotion_analysis=td.get("emotion_analysis"),
            created_at=datetime.now().isoformat(),
        )
        queries.update_file_status(file_id, "completed")
        return jsonify({"status": "completed", "transcript": queries.get_transcript(file_id)}), 200

    except Exception as exc:
        queries.update_file_status(file_id, "failed")
        return jsonify({"error": str(exc)}), 500