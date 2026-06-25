"""RAG question-answering routes — backed by SQLite."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from config.settings import settings
from database import queries
from services.rag_service import rag_service

rag_bp = Blueprint("rag", __name__, url_prefix="/api")


def _get_user_id():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return user_id


def _get_chat_context(chat_id: str, user_id: str):
    """Resolve chat_id → attached files, transcripts, summaries from SQLite, ensuring ownership."""
    chat = queries.get_chat(chat_id)
    if not chat or chat.get("user_id") != user_id:
        return None, {}, {}, {}

    attached_ids = {f.get("fileId") for f in (chat.get("attached") or []) if f.get("fileId")}
    
    # 🔍 DEBUG: Print what we're looking for
    print(f"[RAG] Chat {chat_id} has attached file IDs: {attached_ids}")

    files_meta = {}
    transcripts = {}
    summaries = {}

    for fid in attached_ids:
        print(f"[RAG] Checking file ID: {fid}")
        f = queries.get_file(fid)
        if f and f.get("user_id") == user_id:
            files_meta[fid] = f
            print(f"[RAG] File metadata for {fid}: original_name={f.get('original_name')}") 
        else:
            print(f"[RAG] File not found or user mismatch for {fid}")
        
        t = queries.get_transcript(fid)
        if t:
            transcripts[fid] = t
            print(f"[RAG] Transcript found for {fid} (length: {len(t.get('full_text', ''))})")
        else:
            print(f"[RAG] No transcript for {fid}")
        
        s = queries.get_summary(fid)
        if s:
            summaries[fid] = s
            print(f"[RAG] Summary found for {fid}")

    print(f"[RAG] Total transcripts found: {len(transcripts)}")
    return chat, files_meta, transcripts, summaries


@rag_bp.route("/rag/ask", methods=["POST", "OPTIONS"])
def rag_ask():
    if request.method == "OPTIONS":
        return "", 200

    user_id = _get_user_id()
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    body = request.json or {}
    query = body.get("query", "").strip()
    chat_id = body.get("chat_id", "").strip()

    if not query:
        return jsonify({"error": "Empty query"}), 400

    chat, files_meta, transcripts, summaries = _get_chat_context(chat_id, user_id)
    if not chat:
        return jsonify({"answer": "Chat not found. Please refresh the page.", "sources": []}), 200

    # Get chat history (last 10 messages for context)
    chat_history = chat.get("messages", [])[-10:] if chat.get("messages") else []

    try:
        answer, sources = rag_service.answer(
            query=query,
            files_meta=files_meta,
            transcripts=transcripts,
            summaries=summaries,
            chat_history=chat_history
        )
        print(f"[rag] Q={query[:60]!r} -> {answer[:80]!r} (user: {user_id})")
        return jsonify({"answer": answer, "sources": sources}), 200
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@rag_bp.route("/rag/query", methods=["POST", "OPTIONS"])
def rag_query():
    """Alias for /rag/ask — matches the target API spec."""
    return rag_ask()


@rag_bp.route("/rag/refresh", methods=["POST", "OPTIONS"])
def rag_refresh():
    if request.method == "OPTIONS":
        return "", 200
    groq_available = bool(settings.GROQ_API_KEY)
    return jsonify({
        "status": "ok",
        "groq_available": groq_available,
        "message": "Groq API ready" if groq_available else "Groq API not configured"
    }), 200