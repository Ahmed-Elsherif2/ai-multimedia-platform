"""
Emotion routes — backed by SQLite.

POST /api/emotion/<file_id>  — run/re-run emotion analysis
GET  /api/emotion/<file_id>  — fetch saved results
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

from config.settings import settings
from database import queries

emotion_bp = Blueprint("emotion", __name__, url_prefix="/api")


@emotion_bp.route("/emotion/<file_id>", methods=["POST", "OPTIONS"])
def run_emotion(file_id):
    if request.method == "OPTIONS":
        return "", 200

    # Get segments from SQLite or fallback to on-disk transcript.json
    t = queries.get_transcript(file_id)
    if t:
        segments = t.get("segments", [])
    else:
        tf = settings.UPLOAD_FOLDER / file_id / "transcript.json"
        if not tf.exists():
            return jsonify({"error": "No transcript found — process the file first"}), 404
        data     = json.loads(tf.read_text(encoding="utf-8"))
        segments = data.get("segments_with_text", data.get("segments", []))

    if not segments:
        return jsonify({"error": "Transcript has no segments to analyse"}), 422

    try:
        from services.emotion_service import emotion_service
        report = emotion_service.analyze_segments(segments)

        emotion_data = {
            "overall":             report.overall,
            "per_speaker_emotion": report.per_speaker_emotion,
            "timeline":            report.timeline,
            "analysed_at":         datetime.now().isoformat(),
        }

        # Persist to SQLite
        queries.update_transcript_emotion(file_id, emotion_data)

        # Also write to on-disk transcript.json so pipeline.py stays in sync
        tf = settings.UPLOAD_FOLDER / file_id / "transcript.json"
        if tf.exists():
            try:
                d = json.loads(tf.read_text(encoding="utf-8"))
                d["emotion_analysis"]      = emotion_data
                d["segments_with_emotion"] = report.segments
                tf.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

        overall = report.overall or {}
        return jsonify({
            "file_id":        file_id,
            "sentiment":      {"label": overall.get("dominant_sentiment", "neutral"), "score": 0.8},
            "emotion":        {"label": overall.get("dominant_emotion",   "neutral"), "score": 0.7},
            "top_3_emotions": _top3(report.segments),
            "timeline":       report.timeline,
            "per_speaker":    report.per_speaker_emotion,
        }), 200

    except Exception as exc:
        import traceback; traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@emotion_bp.route("/emotion/<file_id>", methods=["GET", "OPTIONS"])
def get_emotion(file_id):
    if request.method == "OPTIONS":
        return "", 200

    t = queries.get_transcript(file_id)
    if not t:
        # Fallback to on-disk file
        tf = settings.UPLOAD_FOLDER / file_id / "transcript.json"
        if not tf.exists():
            return jsonify({"error": "No processed file found"}), 404
        try:
            data = json.loads(tf.read_text(encoding="utf-8"))
            ea   = data.get("emotion_analysis") or {}
            ov   = ea.get("overall") or {}
            return jsonify({
                "file_id":        file_id,
                "sentiment":      {"label": ov.get("dominant_sentiment", "neutral"), "score": 0.8},
                "emotion":        {"label": ov.get("dominant_emotion",   "neutral"), "score": 0.7},
                "top_3_emotions": _top3(data.get("segments_with_emotion", [])),
                "timeline":       ea.get("timeline", []),
                "per_speaker":    ea.get("per_speaker_emotion", {}),
            }), 200
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    ea = t.get("emotion_analysis") or {}
    ov = ea.get("overall") or {}
    return jsonify({
        "file_id":        file_id,
        "sentiment":      {"label": ov.get("dominant_sentiment", "neutral"), "score": 0.8},
        "emotion":        {"label": ov.get("dominant_emotion",   "neutral"), "score": 0.7},
        "top_3_emotions": _top3([]),
        "timeline":       ea.get("timeline", []),
        "per_speaker":    ea.get("per_speaker_emotion", {}),
    }), 200


def _top3(segments: list) -> list:
    for seg in segments:
        top = (seg.get("emotion") or {}).get("top_3_emotions")
        if top:
            return top
    return []
