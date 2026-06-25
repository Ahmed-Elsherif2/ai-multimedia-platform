"""
Summary routes — backed by SQLite.

POST /api/summarize/<file_id> — run summarization pipeline
GET  /api/summary/<file_id>  — fetch saved summary
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from database import queries
from services.summarization_service import summarization_service

summary_bp = Blueprint("summary", __name__, url_prefix="/api")


@summary_bp.route("/summarize/<file_id>", methods=["POST", "OPTIONS"])
def summarize_file(file_id):
    if request.method == "OPTIONS":
        return "", 200

    f = queries.get_file(file_id)
    if not f:
        return jsonify({"error": "File not found"}), 404
    pdf_path = Path(f["file_path"])
    if not pdf_path.exists():
        return jsonify({"error": "PDF file missing from disk"}), 404

    try:
        result = summarization_service.summarize_pdf(pdf_path)

        queries.upsert_summary(
            file_id=file_id,
            full_text=result.get("full_text", ""),
            groq=result.get("groq", ""),
            t5=result.get("t5", ""),
            template=result.get("template", ""),
            original_length=result.get("original_length", 0),
            summary_length=result.get("summary_length", 0),
            compression_ratio=result.get("compression_ratio", 0.0),
            model_used=result.get("model_used", "template"),
            created_at=datetime.now().isoformat(),
        )
        queries.update_file_status(file_id, "completed")

        return jsonify({
            "file_id": file_id,
            "full_text_preview": result["full_text"][:500] + "…",
            "full_text_length": result.get("original_length", 0),
            "groq": result.get("groq", ""),
            "t5": result.get("t5", ""),
            "template": result.get("template", ""),
            "compression_ratio": result.get("compression_ratio", 0.0),
            "model_used": result.get("model_used", "template"),
        }), 200

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@summary_bp.route("/summary/<file_id>", methods=["GET", "OPTIONS"])
def get_summary(file_id):
    if request.method == "OPTIONS":
        return "", 200
    s = queries.get_summary(file_id)
    if not s:
        return jsonify({"error": "Summary not found — has this file been summarized?"}), 404
    return jsonify(dict(s)), 200
