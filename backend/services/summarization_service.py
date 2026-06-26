"""
SummarizationService — PDF text extraction and multi-model summarization.

Models
------
Groq API        : Primary summarizer (FREE, 30 req/min)
T5-small        : HuggingFace seq2seq — fast baseline
Template        : Extractive heuristic — always available
"""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from config.settings import settings


# ── PDF extraction ────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: Path) -> str:
    try:
        import pdfplumber
    except ImportError as exc:
        raise ImportError("pdfplumber is required for PDF extraction") from exc

    text_parts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
    return "\n".join(text_parts)


# ── Base summarizer ───────────────────────────────────────────────────────────

class _BaseSummarizer(ABC):
    @abstractmethod
    def summarize(self, text: str, max_length: Optional[int] = None) -> str: ...

    @staticmethod
    def _clean(text: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"\n+", "\n", text)).strip()

    @staticmethod
    def _truncate(text: str, max_chars: int) -> str:
        return text[:max_chars] + ("..." if len(text) > max_chars else "")


# ── GROQ Summarizer (PRIMARY) ────────────────────────────────────────────────

class _GroqSummarizer(_BaseSummarizer):
    """Uses Groq API - FREE, FAST (1000+ tokens/sec)"""
    
    def __init__(self):
        self._client = None

    def _load(self):
        if self._client is not None:
            return
        from groq import Groq
        
        api_key = os.getenv('GROQ_API_KEY')
        if not api_key:
            print("[SummarizationService] GROQ_API_KEY not set.")
            return
        
        # ✅ CORRECT: Just pass api_key
        self._client = Groq(api_key=api_key)
        print("[SummarizationService] Groq client ready.")

    def summarize(self, text: str, max_length: Optional[int] = None) -> str:
        self._load()
        if self._client is None:
            return ""
        
        text = self._clean(text)
        length = max_length or 500
        
        prompt = f"""Summarize the following document with clear structure.

DOCUMENT:
{text[:50000]}

OUTPUT FORMAT (use exactly this structure):

## Overview
[1-2 sentences summarizing the main topic]

### Key Concepts
- Concept 1: [brief explanation]
- Concept 2: [brief explanation]
- Concept 3: [brief explanation]

### Main Points
1. [First main point]
2. [Second main point]
3. [Third main point]

### Important Details
- [Detail 1]
- [Detail 2]
- [Detail 3]

### Conclusion
[1-2 sentences summarizing the significance]

Make it scannable and well-organized. Use bold for emphasis where appropriate.
"""

        try:
            response = self._client.chat.completions.create(
                model=os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile'),
                messages=[
                    {"role": "system", "content": "You are a summarization expert. Always use Markdown with ## headings, bullet points, and numbered lists for clear, scannable summaries."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=length * 2,
                temperature=0.3
            )
            summary = response.choices[0].message.content.strip()
            return summary
        except Exception as e:
            print(f"[SummarizationService] Groq failed: {e}")
            return ""


# ── T5 summarizer (FALLBACK) ─────────────────────────────────────────────────

class _T5Summarizer(_BaseSummarizer):
    def __init__(self, model_name: str = "t5-small"):
        self._model_name = model_name
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is not None:
            return
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        print(f"[SummarizationService] loading {self._model_name}...")
        self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(self._model_name)

    def summarize(self, text: str, max_length: Optional[int] = None) -> str:
        self._load()
        text = self._clean(self._truncate(text, 4000))
        inputs = self._tokenizer(
            f"summarize: {text}",
            max_length=512, truncation=True, padding="max_length", return_tensors="pt",
        )
        outputs = self._model.generate(
            **inputs,
            max_length=max_length or 150,
            min_length=30, num_beams=4, length_penalty=2.0, early_stopping=True,
        )
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True).strip()


# ── Template (extractive) ─────────────────────────────────────────────────────

class _TemplateSummarizer(_BaseSummarizer):
    def __init__(self, num_sentences: int = 5):
        self._n = num_sentences

    def summarize(self, text: str, max_length: Optional[int] = None) -> str:
        text = self._clean(text)
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if len(s.strip()) > 10]
        if not sentences:
            return self._truncate(text, 500)
        n = min(self._n, len(sentences))
        total = len(sentences)
        scored = sorted(
            enumerate(sentences),
            key=lambda x: self._score(x[1], x[0], total),
            reverse=True,
        )[:n]
        return " ".join(s for _, s in sorted(scored, key=lambda x: x[0])).strip()

    @staticmethod
    def _score(s: str, pos: int, total: int) -> float:
        score = 0.0
        if pos < total * 0.2: score += 2.0
        if pos > total * 0.8: score += 1.5
        words = len(s.split())
        if 15 <= words <= 30: score += 1.0
        if words < 8: score -= 0.5
        return score


# ── Public facade ─────────────────────────────────────────────────────────────

class SummarizationService:
    """Groq primary, T5 fallback, Template last resort."""

    def __init__(self):
        self._groq = _GroqSummarizer()
        # self._t5 = _T5Summarizer()
        self._template = _TemplateSummarizer(num_sentences=5)

    def summarize_pdf(self, pdf_path: Path) -> dict:
        full_text = extract_text_from_pdf(pdf_path)
        if not full_text.strip():
            raise ValueError("No text could be extracted from the PDF.")

        print(f"[SummarizationService] extracted {len(full_text):,} chars from {pdf_path.name}")

        # 1. Groq (Primary)
        groq_summary = ""
        try:
            groq_summary = self._groq.summarize(full_text)
            print(f"[SummarizationService] Groq: {len(groq_summary)} chars")
        except Exception as exc:
            print(f"[SummarizationService] Groq skipped: {exc}")

        # 2. Template (Always available)
        template_summary = self._template.summarize(full_text)

        # 3. T5 (Fallback) - Skip on Railway
        t5_summary = ""
        if os.getenv("DISABLE_T5") != "true":
            try:
                t5_summary = self._t5.summarize(full_text[:4000])
                print(f"[SummarizationService] T5: {len(t5_summary)} chars")
            except Exception as exc:
                print(f"[SummarizationService] T5 skipped: {exc}")
        else:
            print("[SummarizationService] T5 disabled (DISABLE_T5=true)")

        if groq_summary:
            model_used = "groq-llama-3.3-70b"
            primary_summary = groq_summary
        elif t5_summary:
            model_used = "t5-small"
            primary_summary = t5_summary
        else:
            model_used = "template-fallback"
            primary_summary = template_summary

        summary_len = len(primary_summary)

        return {
            "full_text": full_text,
            "groq": groq_summary,
            "t5": t5_summary,
            "template": template_summary,
            "original_length": len(full_text),
            "summary_length": summary_len,
            "compression_ratio": round(summary_len / max(len(full_text), 1), 3),
            "model_used": model_used,
        }


summarization_service = SummarizationService()