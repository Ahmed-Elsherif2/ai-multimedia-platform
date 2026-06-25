"""
EmotionService — single production implementation for sentiment and emotion analysis.

Replaces:
  - research/emotion_lab/emotion_analyzers.py  (standalone research classes)
  - backend/utils/pipeline.py run_emotion_analysis() (inline duplicate)

Models
------
Sentiment : distilbert-base-uncased-finetuned-sst-2-english  (POSITIVE / NEGATIVE)
Emotion   : SamLowe/roberta-base-go_emotions                  (28-class GoEmotions)
"""
from __future__ import annotations

import os
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
warnings.filterwarnings("ignore")

_SENTIMENT_MODEL = "distilbert-base-uncased-finetuned-sst-2-english"
_EMOTION_MODEL   = "SamLowe/roberta-base-go_emotions"


@dataclass
class SegmentEmotion:
    emotion: str
    emotion_confidence: float
    sentiment: str
    sentiment_confidence: float
    top_3_emotions: List[dict] = field(default_factory=list)


@dataclass
class EmotionReport:
    segments: List[dict]
    overall: Optional[dict]
    per_speaker_emotion: dict
    timeline: List[dict]


class EmotionService:
    """
    Lazy-loads both classifiers on first call.
    Thread-safe for concurrent requests (models are read-only after loading).
    """

    def __init__(self):
        self._sentiment_pipe = None
        self._emotion_pipe   = None

    # ── Private loaders ──────────────────────────────────────────────────────

    def _load(self):
        if self._sentiment_pipe is not None:
            return
        try:
            from transformers import pipeline
            import torch
        except ImportError as exc:
            raise ImportError("transformers and torch are required for EmotionService") from exc

        from utils.gpu_utils import get_device
        from config.settings import settings
        _dev = get_device(settings.TORCH_DEVICE)
        device = 0 if _dev == "cuda" else (-1 if _dev == "cpu" else _dev)
        kwargs = {"device": device, "model_kwargs": {"use_safetensors": True}}
        print(f"[EmotionService] loading models on {_dev}")

        self._sentiment_pipe = pipeline(
            "text-classification",
            model=_SENTIMENT_MODEL,
            max_length=512,
            truncation=True,
            **kwargs,
        )
        self._emotion_pipe = pipeline(
            "text-classification",
            model=_EMOTION_MODEL,
            top_k=None,
            max_length=512,
            truncation=True,
            **kwargs,
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze_segment(self, text: str) -> Optional[SegmentEmotion]:
        """Analyze a single text segment. Returns None if text is too short."""
        if not text or len(text.split()) <= 2:
            return None
        self._load()
        try:
            emotions  = self._emotion_pipe(text[:512])[0]
            sentiment = self._sentiment_pipe(text[:512])[0]
            top3 = sorted(emotions, key=lambda x: x["score"], reverse=True)[:3]
            top  = top3[0]
            return SegmentEmotion(
                emotion=top["label"].lower(),
                emotion_confidence=round(top["score"], 3),
                sentiment=sentiment["label"].lower(),
                sentiment_confidence=round(sentiment["score"], 3),
                top_3_emotions=[
                    {"label": e["label"].lower(), "score": round(e["score"], 3)}
                    for e in top3
                ],
            )
        except Exception as exc:
            print(f"[EmotionService] segment analysis failed: {exc}")
            return None

    def analyze_segments(self, segments: List[dict]) -> EmotionReport:
        """
        Enrich a list of transcript segments with emotion data.

        Each segment dict must have: text, speaker, start, end.
        Returns an EmotionReport with enriched segments, overall stats,
        per-speaker stats, and a timeline list.
        """
        self._load()
        enriched: List[dict]    = []
        timeline: List[dict]    = []
        speaker_emotions: dict  = defaultdict(list)

        for seg in segments:
            text    = seg.get("text", "")
            speaker = seg.get("speaker", "UNKNOWN")
            result  = self.analyze_segment(text)
            seg_out = dict(seg)
            seg_out["emotion"] = None

            if result:
                seg_out["emotion"] = {
                    "emotion":              result.emotion,
                    "emotion_confidence":   result.emotion_confidence,
                    "top_3_emotions":       result.top_3_emotions,
                    "sentiment":            result.sentiment,
                    "sentiment_confidence": result.sentiment_confidence,
                }
                timeline.append({
                    "time":      seg.get("start", 0),
                    "emotion":   result.emotion,
                    "sentiment": result.sentiment,
                    "speaker":   speaker,
                    "text":      text[:100],
                })
                speaker_emotions[speaker].append({
                    "emotion":    result.emotion,
                    "sentiment":  result.sentiment,
                    "confidence": result.emotion_confidence,
                })

            enriched.append(seg_out)

        overall           = self._compute_overall(timeline)
        per_speaker       = self._compute_per_speaker(speaker_emotions)

        return EmotionReport(
            segments=enriched,
            overall=overall,
            per_speaker_emotion=per_speaker,
            timeline=timeline,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _compute_overall(timeline: List[dict]) -> Optional[dict]:
        if not timeline:
            return None
        emotion_counts:   dict = defaultdict(int)
        sentiment_counts: dict = defaultdict(int)
        for item in timeline:
            emotion_counts[item["emotion"]]   += 1
            sentiment_counts[item["sentiment"]] += 1
        return {
            "dominant_emotion":       max(emotion_counts,   key=emotion_counts.get),
            "dominant_sentiment":     max(sentiment_counts, key=sentiment_counts.get),
            "emotion_distribution":   dict(emotion_counts),
            "sentiment_distribution": dict(sentiment_counts),
            "total_segments_analyzed": len(timeline),
        }

    @staticmethod
    def _compute_per_speaker(speaker_emotions: dict) -> dict:
        result = {}
        for speaker, emotions in speaker_emotions.items():
            if not emotions:
                continue
            ec: dict = defaultdict(int)
            sc: dict = defaultdict(int)
            for e in emotions:
                ec[e["emotion"]]   += 1
                sc[e["sentiment"]] += 1
            result[speaker] = {
                "dominant_emotion":       max(ec, key=ec.get),
                "dominant_sentiment":     max(sc, key=sc.get),
                "emotion_distribution":   dict(ec),
                "sentiment_distribution": dict(sc),
                "segments_analyzed":      len(emotions),
            }
        return result


# Module-level singleton — shared across all requests (models loaded once).
emotion_service = EmotionService()
