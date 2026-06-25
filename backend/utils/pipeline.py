"""
Audio processing pipeline — CLI entry point called by audio_routes.py via subprocess.

Orchestrates the three production services:
  1. DiarizationService  — speaker segmentation (pyannote)
  2. TranscriptionService — speech-to-text (Whisper)
  3. EmotionService       — emotion + sentiment analysis

This file no longer duplicates any logic. Each capability lives in its
own service under backend/services/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow imports relative to backend/ when called via subprocess
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import warnings
warnings.filterwarnings("ignore")


def main():
    parser = argparse.ArgumentParser(description="AI Multimedia Platform — audio pipeline")
    parser.add_argument("--audio", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--whisper_model", default="base")
    parser.add_argument("--no-emotion", action="store_true")
    args = parser.parse_args()

    audio_path = Path(args.audio)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not audio_path.exists():
        print(json.dumps({"error": f"Audio file not found: {audio_path}"}))
        return 1

    print(f"Pipeline: {audio_path.name}")

    try:
        # ── 1. Audio extraction ───────────────────────────────────────────────────
        from services.audio_extraction_service import audio_extraction_service
        wav_path = audio_extraction_service.prepare_wav(audio_path, output_dir)

        # ── 2. Diarization ────────────────────────────────────────────────────────
        from services.diarization_service import diarization_service
        segments, speaker_segs, speaker_count = diarization_service.diarize(wav_path)

        # ── 3. Transcription ─────────────────────────────────────────────────────
        from services.transcription_service import transcription_service
        from services.transcript_alignment_service import transcript_alignment_service
        
        # Update whisper model if specified
        if args.whisper_model:
            from config.settings import settings
            settings.WHISPER_MODEL = args.whisper_model

        whisper_result = transcription_service.transcribe(wav_path)
        full_text, per_speaker_joined, segments_with_text, conversation = (
            transcript_alignment_service.align(whisper_result, speaker_segs)
        )
        print(f"Transcription: {len(full_text)} chars, {speaker_count} speaker(s)")

        # ── 4. Emotion analysis ───────────────────────────────────────────────────
        emotion_report = None
        if not args.no_emotion and segments_with_text:
            print("Running emotion analysis...")
            from services.emotion_service import emotion_service
            emotion_report = emotion_service.analyze_segments(segments_with_text)
            if emotion_report.overall:
                print(
                    f"Emotion: dominant={emotion_report.overall['dominant_emotion']}, "
                    f"sentiment={emotion_report.overall['dominant_sentiment']}"
                )

        # ── Build output ──────────────────────────────────────────────────────────
        output: dict = {
            "full_text": full_text,
            "conversation": conversation,
            "segments": segments,
            "segments_with_emotion": emotion_report.segments if emotion_report else [],
            "per_speaker": per_speaker_joined,
            "speaker_count": speaker_count,
            "model_info": {
                "whisper": args.whisper_model,
                "diarization": "pyannote/speaker-diarization-3.1",
                "emotion": "SamLowe/roberta-base-go_emotions",
                "sentiment": "distilbert-base-uncased-finetuned-sst-2-english",
            },
        }
        if emotion_report:
            output["emotion_analysis"] = {
                "overall": emotion_report.overall,
                "per_speaker_emotion": emotion_report.per_speaker_emotion,
                "timeline": emotion_report.timeline,
            }

        # ── Persist outputs ───────────────────────────────────────────────────────
        (output_dir / "transcript.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (output_dir / "transcript.txt").write_text(full_text, encoding="utf-8")

        with open(output_dir / "speakers.txt", "w", encoding="utf-8") as f:
            for speaker, text in per_speaker_joined.items():
                f.write(f"\n{'='*40}\n{speaker}\n{'='*40}\n{text}\n")

        with open(output_dir / "conversation.txt", "w", encoding="utf-8") as f:
            for turn in conversation:
                f.write(f"{turn['speaker']} [{turn['start']:.1f}s-{turn['end']:.1f}s]\n{turn['text']}\n\n")

        (output_dir / "segments.json").write_text(
            json.dumps(segments, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if emotion_report:
            (output_dir / "emotion_analysis.json").write_text(
                json.dumps({
                    "overall": emotion_report.overall,
                    "per_speaker_emotion": emotion_report.per_speaker_emotion,
                    "timeline": emotion_report.timeline,
                }, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

        print(f"\nDone — output in {output_dir}")
        print(json.dumps(output))
        return 0

    except Exception as e:
        error_output = {"error": str(e)}
        print(json.dumps(error_output))
        return 1


if __name__ == "__main__":
    sys.exit(main())