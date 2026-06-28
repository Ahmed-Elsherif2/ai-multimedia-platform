"""Audio upload, processing, transcript, and emotion routes."""
from __future__ import annotations

import json
import subprocess
import sys
import uuid
import shutil
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from config.settings import settings
from database import queries
from database.db import get_db
from utils.file_manager import file_manager
from utils.status_tracker import status_tracker
from utils.results_store import results_store

audio_bp = Blueprint("audio", __name__, url_prefix="/api")


# ── Helper to check authentication ──────────────────────────────────────────
def _get_user_id():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return user_id


# ── Upload ────────────────────────────────────────────────────────────────────

@audio_bp.route("/upload/audio", methods=["POST", "OPTIONS"])
def upload_audio():
    """Upload an audio file."""
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    if "audio" not in request.files:
        return jsonify({"error": "No audio file"}), 400
    
    file = request.files["audio"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    
    upload_info = file_manager.save_upload(file)
    file_id = upload_info["file_id"]
    
    queries.upsert_file(
        file_id=file_id,
        original_name=upload_info["filename"],
        file_path=upload_info["path"],
        file_type=upload_info["type"],
        status="uploaded",
        uploaded_at=datetime.now().isoformat(),
        user_id=user_id
    )
    
    status_tracker.set_status(file_id, "uploaded")
    
    print(f"[audio] uploaded {file.filename} -> {file_id} (user: {user_id})")
    return jsonify({
        "file_id": file_id,
        "filename": upload_info["filename"],
        "size": upload_info["size"],
        "type": upload_info["type"],
        "message": "File uploaded successfully"
    }), 200


# ── Process ──────────────────────────────────────────────────────────────────

@audio_bp.route("/process/<file_id>", methods=["POST", "OPTIONS"])
def process_audio(file_id):
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    # Verify file belongs to user
    file_info = queries.get_file(file_id)
    if not file_info or file_info.get("user_id") != user_id:
        return jsonify({"error": "File not found or access denied"}), 404
    
    if results_store.has(file_id):
        results = results_store.get(file_id)
        return jsonify({
            "status": "already_processed",
            "message": "File already processed",
            "file_id": file_id,
            "transcript": results.get("transcript", {})
        }), 200
    
    if status_tracker.is_processing(file_id):
        return jsonify({
            "status": "processing",
            "message": "File is being processed"
        }), 202
    
    audio_path = Path(file_info["file_path"])
    if not audio_path.exists():
        return jsonify({"error": "Audio file missing from disk"}), 404
    
    # ── Check audio duration BEFORE processing ──
    from services.audio_extraction_service import audio_extraction_service
    duration = audio_extraction_service.get_duration(audio_path)
    print(f"[audio] Audio file: {audio_path.name}")
    print(f"[audio] File size: {audio_path.stat().st_size / 1024:.1f} KB")
    print(f"[audio] Audio duration: {duration:.2f}s")
    
    if duration < 16:
        print(f"[audio] ⚡ Short audio ({duration:.2f}s) – using fallback, skipping Pyannote diarization!")
    
    status_tracker.set_status(file_id, "processing")
    queries.update_file_status(file_id, "processing")
    
    try:
        from services.transcription_service import transcription_service
        from services.diarization_service import diarization_service
        from services.emotion_service import emotion_service
        
        print(f"[audio] Starting processing for {file_id} (user: {user_id})")
        
        # 1. Diarization first (will use fallback for short audio)
        print(f"[audio] Step 1: Diarization...")
        segments, speaker_segs, speaker_count = diarization_service.diarize(audio_path)
        print(f"[audio] Diarization complete: {speaker_count} speaker(s), {len(segments)} segments")
        
        # 2. Transcription with alignment
        print(f"[audio] Step 2: Transcription (Groq Whisper API)...")
        full_text, per_speaker, segs_with_text, conversation = (
            transcription_service.transcribe_and_align(audio_path, speaker_segs)
        )
        print(f"[audio] Transcription complete: {len(full_text)} characters")
        
        transcript_result = {
            "full_text": full_text,
            "segments": segs_with_text,
            "conversation": conversation,
            "per_speaker": per_speaker,
            "speaker_count": speaker_count
        }
        
        # 3. Emotion analysis
        print(f"[audio] Step 3: Emotion analysis...")
        emotion_result = None
        if segs_with_text:
            emotion_report = emotion_service.analyze_segments(segs_with_text)
            emotion_result = {
                "overall": emotion_report.overall,
                "per_speaker_emotion": emotion_report.per_speaker_emotion,
                "timeline": emotion_report.timeline
            }
            print(f"[audio] Emotion analysis complete: dominant={emotion_report.overall.get('dominant_emotion', 'unknown')}")
        else:
            print(f"[audio] ⚠️ No segments for emotion analysis")
        
        results = {
            "transcript": transcript_result,
            "emotion": emotion_result
        }
        
        queries.upsert_transcript(
            file_id=file_id,
            full_text=full_text,
            segments=segs_with_text,
            conversation=conversation,
            per_speaker=per_speaker,
            speaker_count=speaker_count,
            duration=str(duration),
            emotion_analysis=emotion_result,
            created_at=datetime.now().isoformat()
        )
        
        results_store.save(file_id, results)
        queries.update_file_status(file_id, "completed")
        status_tracker.set_status(file_id, "done", {"results": results})
        
        print(f"[audio] ✅ completed {file_id} in {duration:.1f}s audio duration (user: {user_id})")
        return jsonify({
            "status": "completed",
            "file_id": file_id,
            "transcript": transcript_result
        }), 200
        
    except Exception as exc:
        queries.update_file_status(file_id, "failed")
        status_tracker.set_status(file_id, "failed", {"error": str(exc)})
        print(f"[audio] ❌ error: {exc}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# ── Get Data ─────────────────────────────────────────────────────────────────

@audio_bp.route("/transcript/<file_id>", methods=["GET", "OPTIONS"])
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
    
    results = results_store.get(file_id)
    if results and "transcript" in results:
        return jsonify(results["transcript"]), 200
    
    transcript = queries.get_transcript(file_id)
    if transcript:
        return jsonify(transcript), 200
    
    return jsonify({"error": "Transcript not found"}), 404


@audio_bp.route("/emotion/<file_id>", methods=["GET", "OPTIONS"])
def get_emotion(file_id):
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    file_info = queries.get_file(file_id)
    if not file_info or file_info.get("user_id") != user_id:
        return jsonify({"error": "File not found or access denied"}), 404
    
    results = results_store.get(file_id)
    if results and "emotion" in results:
        return jsonify(results["emotion"]), 200
    
    transcript = queries.get_transcript(file_id)
    if transcript and transcript.get("emotion_analysis"):
        return jsonify(transcript["emotion_analysis"]), 200
    
    return jsonify({"error": "No emotion analysis found"}), 404


@audio_bp.route("/file/<file_id>/status", methods=["GET", "OPTIONS"])
def file_status(file_id):
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    file_info = queries.get_file(file_id)
    if not file_info or file_info.get("user_id") != user_id:
        return jsonify({"error": "File not found"}), 404
    
    status = status_tracker.get_status(file_id)
    if file_info:
        status["db_status"] = file_info.get("status", "unknown")
    
    if results_store.has(file_id):
        status["has_results"] = True
        status["status"] = "done"
    
    return jsonify(status), 200


# ── Delete ────────────────────────────────────────────────────────────────────

@audio_bp.route("/file/<file_id>", methods=["DELETE", "OPTIONS"])
def delete_file(file_id):
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    file_info = queries.get_file(file_id)
    if not file_info or file_info.get("user_id") != user_id:
        return jsonify({"error": "File not found or access denied"}), 404
    
    try:
        # 1. Delete physical file
        file_path = Path(file_info["file_path"])
        if file_path.exists():
            file_path.unlink()
            print(f"[Delete] Removed file: {file_path}")
        
        # 2. Delete transcript folder
        transcript_folder = settings.UPLOAD_FOLDER / file_id
        if transcript_folder.exists():
            shutil.rmtree(transcript_folder)
            print(f"[Delete] Removed folder: {transcript_folder}")
        
        # 3. Delete from results store
        if results_store.has(file_id):
            results_store.delete(file_id)
        
        # 4. Delete from status tracker
        status_tracker.delete_status(file_id)
        
        # 5. Delete from database (cascades to transcripts & summaries)
        queries.delete_file(file_id, user_id)
        
        print(f"[Delete] Successfully deleted file: {file_id} (user: {user_id})")
        
        return jsonify({
            "success": True,
            "file_id": file_id,
            "message": "File and all associated data deleted successfully"
        }), 200
        
    except Exception as e:
        print(f"[Delete] Error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@audio_bp.route("/cleanup/stats", methods=["GET", "OPTIONS"])
def get_storage_stats():
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        stats = queries.get_storage_stats(user_id)
        
        upload_dir = settings.UPLOAD_FOLDER
        total_size = 0
        file_count = 0
        
        if upload_dir.exists():
            for file_path in upload_dir.glob("**/*"):
                if file_path.is_file():
                    # Only count files that belong to this user
                    # (file_manager doesn't have user info, but we can check if file_id is in user's files)
                    # Since we can't efficiently filter here, we'll just count all physical files.
                    total_size += file_path.stat().st_size
                    file_count += 1
        
        return jsonify({
            "database": stats,
            "storage": {
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "file_count": file_count,
                "upload_dir": str(upload_dir)
            }
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@audio_bp.route("/cleanup/all", methods=["DELETE", "OPTIONS"])
def delete_all_files():
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    try:
        files = queries.get_all_files(user_id)
        
        deleted_physical = 0
        for file_info in files:
            file_id = file_info.get("id")
            file_path = Path(file_info.get("file_path", ""))
            
            if file_path.exists():
                file_path.unlink()
                deleted_physical += 1
            
            transcript_folder = settings.UPLOAD_FOLDER / file_id
            if transcript_folder.exists():
                shutil.rmtree(transcript_folder)
            
            if results_store.has(file_id):
                results_store.delete(file_id)
        
        count = queries.delete_all_files(user_id)
        
        print(f"[Delete] Deleted {count} files for user {user_id}")
        
        return jsonify({
            "success": True,
            "deleted_count": count,
            "deleted_physical": deleted_physical,
            "message": f"Deleted {count} files and associated data"
        }), 200
        
    except Exception as e:
        print(f"[Delete] Error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500