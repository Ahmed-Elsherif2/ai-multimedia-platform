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
        data = json.loads(tf.read_text(encoding="utf-8"))
        segments = data.get("segments_with_text", data.get("segments", []))

    if not segments:
        return jsonify({"error": "Transcript has no segments to analyse"}), 422

    try:
        from services.emotion_service import emotion_service
        report = emotion_service.analyze_segments(segments)

        emotion_data = {
            "overall": report.overall,
            "per_speaker_emotion": report.per_speaker_emotion,
            "timeline": report.timeline,
            "analysed_at": datetime.now().isoformat(),
        }

        # Persist to SQLite
        queries.update_transcript_emotion(file_id, emotion_data)

        # Also write to on-disk transcript.json so pipeline.py stays in sync
        tf = settings.UPLOAD_FOLDER / file_id / "transcript.json"
        if tf.exists():
            try:
                d = json.loads(tf.read_text(encoding="utf-8"))
                d["emotion_analysis"] = emotion_data
                d["segments_with_emotion"] = report.segments
                tf.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

        overall = report.overall or {}
        emotion_distribution = overall.get("emotion_distribution", {})
        sentiment_distribution = overall.get("sentiment_distribution", {})
        
        total_emotions = sum(emotion_distribution.values()) if emotion_distribution else 0
        total_sentiments = sum(sentiment_distribution.values()) if sentiment_distribution else 0
        
        dominant_emotion = overall.get("dominant_emotion", "neutral")
        dominant_sentiment = overall.get("dominant_sentiment", "neutral")
        
        emotion_confidence = round(emotion_distribution.get(dominant_emotion, 0) / max(total_emotions, 1), 3)
        sentiment_confidence = round(sentiment_distribution.get(dominant_sentiment, 0) / max(total_sentiments, 1), 3)
        
        return jsonify({
            "file_id": file_id,
            "sentiment": {
                "label": dominant_sentiment,
                "score": sentiment_confidence,
            },
            "emotion": {
                "label": dominant_emotion,
                "score": emotion_confidence,
            },
            "top_3_emotions": _get_top_emotions(report.segments),
            "timeline": report.timeline,
            "per_speaker": report.per_speaker_emotion,
            "emotion_distribution": emotion_distribution,
            "sentiment_distribution": sentiment_distribution,
        }), 200

    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@emotion_bp.route("/emotion/<file_id>", methods=["GET", "OPTIONS"])
def get_emotion(file_id):
    if request.method == "OPTIONS":
        return "", 200

    # ── Try SQLite first ──
    t = queries.get_transcript(file_id)
    if t:
        ea = t.get("emotion_analysis") or {}
        overall = ea.get("overall") or {}
        timeline = ea.get("timeline", [])
        per_speaker = ea.get("per_speaker_emotion", {})
        
        # ── Get emotion distribution from overall ──
        emotion_distribution = overall.get("emotion_distribution", {})
        sentiment_distribution = overall.get("sentiment_distribution", {})
        
        # ── Calculate confidence scores ──
        total_emotions = sum(emotion_distribution.values()) if emotion_distribution else 0
        total_sentiments = sum(sentiment_distribution.values()) if sentiment_distribution else 0
        
        dominant_emotion = overall.get("dominant_emotion", "neutral")
        dominant_sentiment = overall.get("dominant_sentiment", "neutral")
        
        emotion_confidence = round(emotion_distribution.get(dominant_emotion, 0) / max(total_emotions, 1), 3)
        sentiment_confidence = round(sentiment_distribution.get(dominant_sentiment, 0) / max(total_sentiments, 1), 3)
        
        # ── Get top emotions from the actual segments ──
        segments = t.get("segments", [])
        top_emotions = _get_top_emotions(segments)
        
        return jsonify({
            "file_id": file_id,
            "sentiment": {
                "label": dominant_sentiment,
                "score": sentiment_confidence,
            },
            "emotion": {
                "label": dominant_emotion,
                "score": emotion_confidence,
            },
            "top_3_emotions": top_emotions,
            "timeline": timeline,
            "per_speaker": per_speaker,
            "emotion_distribution": emotion_distribution,
            "sentiment_distribution": sentiment_distribution,
        }), 200

    # ── Fallback to on-disk file ──
    tf = settings.UPLOAD_FOLDER / file_id / "transcript.json"
    if not tf.exists():
        return jsonify({"error": "No processed file found"}), 404
    
    try:
        data = json.loads(tf.read_text(encoding="utf-8"))
        ea = data.get("emotion_analysis") or {}
        ov = ea.get("overall") or {}
        
        emotion_distribution = ov.get("emotion_distribution", {})
        sentiment_distribution = ov.get("sentiment_distribution", {})
        
        total_emotions = sum(emotion_distribution.values()) if emotion_distribution else 0
        total_sentiments = sum(sentiment_distribution.values()) if sentiment_distribution else 0
        
        dominant_emotion = ov.get("dominant_emotion", "neutral")
        dominant_sentiment = ov.get("dominant_sentiment", "neutral")
        
        emotion_confidence = round(emotion_distribution.get(dominant_emotion, 0) / max(total_emotions, 1), 3)
        sentiment_confidence = round(sentiment_distribution.get(dominant_sentiment, 0) / max(total_sentiments, 1), 3)
        
        segments = data.get("segments_with_emotion", data.get("segments", []))
        top_emotions = _get_top_emotions(segments)
        
        return jsonify({
            "file_id": file_id,
            "sentiment": {
                "label": dominant_sentiment,
                "score": sentiment_confidence,
            },
            "emotion": {
                "label": dominant_emotion,
                "score": emotion_confidence,
            },
            "top_3_emotions": top_emotions,
            "timeline": ea.get("timeline", []),
            "per_speaker": ea.get("per_speaker_emotion", {}),
            "emotion_distribution": emotion_distribution,
            "sentiment_distribution": sentiment_distribution,
        }), 200
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


def _get_top_emotions(segments: list) -> list:
    """Extract top 3 emotions from segments."""
    emotion_counts = {}
    
    for seg in segments:
        emotion_data = seg.get("emotion")
        if emotion_data:
            emotion = emotion_data.get("emotion")
            if emotion:
                emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1
    
    if not emotion_counts:
        return []
    
    # Sort by count descending and take top 3
    sorted_emotions = sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True)
    total = sum(emotion_counts.values())
    
    return [
        {"label": emotion, "score": round(count / total, 3)}
        for emotion, count in sorted_emotions[:3]
    ]