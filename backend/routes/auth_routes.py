"""
Authentication routes — login, register, logout, profile.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from flask import Blueprint, request, jsonify, session
import bcrypt

from database import queries
from database.db import get_db

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/register", methods=["POST"])
def register():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    if len(username) < 3:
        return jsonify({"error": "Username must be at least 3 characters"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    # Check if user exists
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        return jsonify({"error": "Username already taken"}), 400

    # Hash password
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    user_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (id, username, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (user_id, username, hashed.decode("utf-8"), datetime.now().isoformat())
    )
    db.commit()

    # Create a default chat for the user
    from routes.chat_routes import create_chat_for_user
    create_chat_for_user(user_id, "My First Chat")

    # Log the user in
    session["user_id"] = user_id
    session["username"] = username

    return jsonify({
        "success": True,
        "user": {"id": user_id, "username": username}
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    db = get_db()
    user = db.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if not user:
        return jsonify({"error": "Invalid username or password"}), 401

    # Verify password
    if not bcrypt.checkpw(password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        return jsonify({"error": "Invalid username or password"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]

    return jsonify({
        "success": True,
        "user": {"id": user["id"], "username": user["username"]}
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True}), 200


@auth_bp.route("/me", methods=["GET"])
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    db = get_db()
    user = db.execute("SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        session.clear()
        return jsonify({"error": "User not found"}), 401

    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "created_at": user["created_at"]
    }), 200


@auth_bp.route("/profile", methods=["GET"])
def get_profile():
    """Get user profile settings."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    user = queries.get_user(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "id": user["id"],
        "username": user["username"],
        "diarization_enabled": bool(user.get("diarization_enabled", 1)),
        "created_at": user.get("created_at")
    }), 200


@auth_bp.route("/profile", methods=["PUT"])
def update_profile():
    """Update user profile settings."""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not authenticated"}), 401

    data = request.json or {}
    diarization_enabled = data.get("diarization_enabled")

    if diarization_enabled is None:
        return jsonify({"error": "diarization_enabled is required"}), 400

    success = queries.update_user_diarization(user_id, bool(diarization_enabled))
    if not success:
        return jsonify({"error": "Failed to update profile"}), 500

    return jsonify({
        "success": True,
        "diarization_enabled": bool(diarization_enabled)
    }), 200