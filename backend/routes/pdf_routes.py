"""PDF upload and summarization routes."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, session

from config.settings import settings
from database import queries
from utils.file_manager import file_manager
from utils.results_store import results_store

pdf_bp = Blueprint("pdf", __name__, url_prefix="/api")


def _get_user_id():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return user_id


@pdf_bp.route("/upload/pdf", methods=["POST", "OPTIONS"])
def upload_pdf():
    """Upload a PDF file."""
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    if "pdf" not in request.files:
        return jsonify({"error": "No PDF file"}), 400
    
    file = request.files["pdf"]
    if not file.filename:
        return jsonify({"error": "Empty filename"}), 400
    
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are accepted"}), 400
    
    upload_info = file_manager.save_upload(file)
    file_id = upload_info["file_id"]
    
    queries.upsert_file(
        file_id=file_id,
        original_name=upload_info["filename"],
        file_path=upload_info["path"],
        file_type="pdf",
        status="uploaded",
        uploaded_at=datetime.now().isoformat(),
        user_id=user_id
    )
    
    print(f"[pdf] uploaded {file.filename} -> {file_id} (user: {user_id})")
    return jsonify({
        "file_id": file_id,
        "filename": upload_info["filename"],
        "size": upload_info["size"],
        "type": "pdf",
        "message": "PDF uploaded successfully"
    }), 200


@pdf_bp.route("/summarize/<file_id>", methods=["POST", "OPTIONS"])
def summarize_pdf(file_id):
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    file_info = queries.get_file(file_id)
    if not file_info or file_info.get("user_id") != user_id:
        return jsonify({"success": False, "error": "File not found or access denied"}), 404
    
    existing = results_store.get(file_id)
    if existing and "summary" in existing:
        return jsonify({
            "success": True,
            "status": "already_done",
            "message": "PDF already summarized",
            "summary": existing["summary"]
        }), 200
    
    pdf_path = Path(file_info["file_path"])
    if not pdf_path.exists():
        return jsonify({"success": False, "error": "PDF file missing from disk"}), 404
    
    try:
        from services.summarization_service import summarization_service
        summary = summarization_service.summarize_pdf(pdf_path)
        
        queries.upsert_summary(
            file_id=file_id,
            full_text=summary.get("full_text", ""),
            groq=summary.get("groq", ""),
            template=summary.get("template", ""),
            original_length=summary.get("original_length", 0),
            summary_length=summary.get("summary_length", 0),
            compression_ratio=summary.get("compression_ratio", 0.0),
            model_used=summary.get("model_used", "template"),
            created_at=datetime.now().isoformat()
        )
        
        queries.update_file_status(file_id, "completed")
        results_store.save(file_id, {"summary": summary})
        
        print(f"[pdf] summarized {file_id} — {summary['original_length']:,} chars (user: {user_id})")
        
        return jsonify({
            "success": True,
            "status": "done",
            "file_id": file_id,
            "full_text_preview": summary["full_text"][:500] + "..." if len(summary["full_text"]) > 500 else summary["full_text"],
            "full_text_length": summary["original_length"],
            "groq": summary.get("groq", ""),
            "template": summary.get("template", ""),
            "compression_ratio": summary.get("compression_ratio", 0.0),
            "model_used": summary.get("model_used", "template"),
            "message": "Summary generated successfully"
        }), 200
        
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({
            "success": False,
            "error": str(exc),
            "status": "failed"
        }), 500


@pdf_bp.route("/summary/<file_id>", methods=["GET", "OPTIONS"])
def get_summary(file_id):
    if request.method == "OPTIONS":
        return "", 200
    
    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    file_info = queries.get_file(file_id)
    if not file_info or file_info.get("user_id") != user_id:
        return jsonify({"success": False, "error": "File not found or access denied"}), 404
    
    results = results_store.get(file_id)
    if results and "summary" in results:
        return jsonify({
            "success": True,
            "summary": results["summary"],
            "file_id": file_id
        }), 200
    
    summary = queries.get_summary(file_id)
    if summary:
        return jsonify({
            "success": True,
            "summary": dict(summary),
            "file_id": file_id
        }), 200
    
    return jsonify({"success": False, "error": "Summary not found"}), 404