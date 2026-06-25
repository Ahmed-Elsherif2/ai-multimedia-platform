"""
Audio processing pipeline - orchestrates diarization, transcription, and emotion analysis.
Hosting compatible with configurable paths.
"""
import os
import json
from pathlib import Path
from datetime import datetime

from config.settings import settings
from utils.file_manager import file_manager
from utils.results_store import results_store


def process_audio(file_id: str) -> dict:
    """
    Full audio processing pipeline
    Returns: dict with transcript, emotion, etc.
    """
    # Get file path using file_manager
    file_path = file_manager.get_upload_path(file_id)
    
    if not file_path:
        raise FileNotFoundError(f"Audio file for {file_id} not found")
    
    print(f"[Pipeline] Processing {file_path}")
    
    # 1. Diarization
    from services.diarization_service import DiarizationService
    diarization_service = DiarizationService()
    segments, speaker_segs, speaker_count = diarization_service.diarize(file_path)
    
    # 2. Transcription
    from services.transcription_service import TranscriptionService
    transcription_service = TranscriptionService()
    whisper_result = transcription_service.transcribe(file_path)
    
    # 3. Speaker alignment
    from services.transcript_alignment_service import transcript_alignment_service
    full_text, per_speaker, segs_with_text, conversation = (
        transcript_alignment_service.align(whisper_result, speaker_segs)
    )
    
    # 4. Emotion analysis
    from services.emotion_service import emotion_service
    emotion_report = emotion_service.analyze_segments(segs_with_text)
    
    # Build results
    results = {
        "transcript": {
            "full_text": full_text,
            "segments": segs_with_text,
            "conversation": conversation,
            "per_speaker": per_speaker,
            "speaker_count": speaker_count
        },
        "emotion": {
            "overall": emotion_report.overall,
            "per_speaker_emotion": emotion_report.per_speaker_emotion,
            "timeline": emotion_report.timeline
        }
    }
    
    # Save to results store
    results_store.save(file_id, results)
    
    print(f"[Pipeline] Results saved for {file_id}")
    
    return results