"""Chat history CRUD routes — backed by SQLite."""
from __future__ import annotations

import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from config.settings import settings
from database import queries

chat_bp = Blueprint("chat", __name__, url_prefix="/api")


# ─── Helper to create a chat for a user ──────────────────────────────────

def create_chat_for_user(user_id: str, title: str = "New Chat") -> dict:
    """Create a chat for a specific user."""
    chat = queries.insert_chat(
        chat_id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        created_at=datetime.now().isoformat(),
    )
    return chat


# ─── Routes ──────────────────────────────────────────────────────────────

@chat_bp.route("/chats", methods=["GET", "OPTIONS"])
def get_chats():
    if request.method == "OPTIONS":
        return "", 200
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    chats = queries.get_user_chats(user_id)
    return jsonify([_to_frontend(c) for c in chats]), 200


@chat_bp.route("/chats", methods=["POST", "OPTIONS"])
def create_chat():
    if request.method == "OPTIONS":
        return "", 200
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    chat = create_chat_for_user(
        user_id=user_id,
        title=(request.json or {}).get("title", "New Chat"),
    )
    return jsonify(_to_frontend(chat)), 201


@chat_bp.route("/chats/<chat_id>", methods=["GET", "OPTIONS"])
def get_chat(chat_id):
    if request.method == "OPTIONS":
        return "", 200
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    chat = queries.get_chat(chat_id)
    if not chat or chat.get("user_id") != user_id:
        return jsonify({"error": "Chat not found"}), 404
    
    return jsonify(_to_frontend(chat)), 200


@chat_bp.route("/chats/<chat_id>", methods=["PUT", "PATCH", "OPTIONS"])
def update_chat(chat_id):
    if request.method == "OPTIONS":
        return "", 200
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    # Check ownership
    chat = queries.get_chat(chat_id)
    if not chat or chat.get("user_id") != user_id:
        return jsonify({"error": "Chat not found"}), 404
    
    updated = queries.update_chat(chat_id, user_id, request.json or {})
    if updated:
        return jsonify(_to_frontend(updated)), 200
    return jsonify({"error": "Not found"}), 404


@chat_bp.route("/chats/<chat_id>", methods=["DELETE", "OPTIONS"])
def delete_chat(chat_id):
    if request.method == "OPTIONS":
        return "", 200
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    deleted = queries.delete_chat(chat_id, user_id)
    if deleted:
        return jsonify({"success": True}), 200
    return jsonify({"error": "Chat not found"}), 404


def _to_frontend(chat: dict) -> dict:
    return {
        "id": chat["id"],
        "userId": chat.get("user_id"),
        "title": chat.get("title", "Chat"),
        "pinned": bool(chat.get("pinned", False)),
        "messages": chat.get("messages", []),
        "attached": chat.get("attached", []),
        "processedFiles": chat.get("processedFiles", {}),
        "summarizedFiles": chat.get("summarizedFiles", {}),
        "failedFiles": chat.get("failedFiles", {}),
        "createdAt": chat.get("created_at", ""),
    }