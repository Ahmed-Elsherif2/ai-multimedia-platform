"""
RAGService — Retrieval-Augmented Generation over uploaded transcripts and PDFs.

Strategy
--------
1. Chunk transcripts and PDF full-text into overlapping windows.
2. Embed with sentence-transformers/all-MiniLM-L6-v2 (local, free).
3. Retrieve top-k chunks via FAISS cosine search.
4. Answer with Groq API (FREE, fast).
5. Maintain chat history for context-aware answers.
"""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

from config.settings import settings


# ── Rule-based short-circuit answers ─────────────────────────────────────────

_FILE_QUERIES = ("what file", "which file", "file name", "filename",
                 "what is the name", "name of the", "list the files",
                 "list files", "what files do you have", "what files are")
_SPEAKER_QUERIES = ("how many speaker", "number of speaker", "speaker count",
                    "how many people speak", "how many voices", "who speak")
_TRANSCRIPT_QUERIES = ("show transcript", "full transcript", "full text",
                       "show the text", "what did they say", "what was said")
_SUMMARY_QUERIES = ("what does the document", "about the pdf", "summarize the document",
                    "what is the pdf", "what does the pdf", "summary of the document",
                    "tell me about the document", "what is this document",
                    "summarize the pdf")


def _rule_based(
    query: str,
    files_meta: dict,
    transcripts: dict,
    summaries: dict,
) -> Optional[str]:
    q = query.lower().strip().rstrip("?")

    # ─── Deterministic commands ─────────────────────────────────────────────

    # 1. List files
    if any(p in q for p in ("list files", "list all files", "show files", "what files", "name the files", "uploaded files")):
        if not files_meta:
            return "No files have been uploaded to this chat yet."
        parts = []
        for fid, m in files_meta.items():
            name = m.get("originalName", fid)
            ft = m.get("type", "?")
            st = []
            if fid in transcripts:
                st.append("transcribed")
            if fid in summaries:
                st.append("summarised")
            status = " ✓ " + ", ".join(st) if st else " ⏳ not processed"
            parts.append(f"- **{name}** ({ft}){status}")
        return "Files in this chat:\n" + "\n".join(parts)

    # 2. Count files
    if any(p in q for p in ("how many files", "number of files", "count of files")):
        if not files_meta:
            return "No files have been uploaded to this chat yet."
        audio_count = sum(1 for m in files_meta.values() if m.get("type") == "audio")
        pdf_count = sum(1 for m in files_meta.values() if m.get("type") == "pdf")
        transcript_count = len(transcripts)
        summary_count = len(summaries)
        return f"Files: {len(files_meta)} total ({audio_count} audio, {pdf_count} PDF). Processed: {transcript_count} transcript(s), {summary_count} summary(ies)."

    # 3. List transcripts
    if any(p in q for p in ("list transcripts", "show transcripts", "what transcripts")):
        if not transcripts:
            return "No transcripts found. Process audio files first."
        names = []
        for fid in transcripts.keys():
            file_info = files_meta.get(fid, {})
            name = file_info.get("originalName", fid)
            if file_info.get("type") == "audio":
                names.append(f"- {name}")
        if names:
            return "**Transcripts:**\n" + "\n".join(names)
        return "No audio transcripts found."

    # 4. List summaries
    if any(p in q for p in ("list summaries", "show summaries", "what summaries")):
        if not summaries:
            return "No summaries found. Process PDF files first."
        names = []
        for fid in summaries.keys():
            file_info = files_meta.get(fid, {})
            name = file_info.get("originalName", fid)
            if file_info.get("type") == "pdf":
                names.append(f"- {name}")
        if names:
            return "**Summaries:**\n" + "\n".join(names)
        return "No PDF summaries found."

    # ─── Direct file lookup (works for ANY file name) ──────────────────────
    for fid, file_info in files_meta.items():
        file_name = file_info.get("originalName", "")
        name_lower = file_name.lower()
        name_without_ext = name_lower.rsplit('.', 1)[0] if '.' in name_lower else name_lower
        
        variants = [
            name_without_ext,
            name_without_ext.replace('_', ' '),
            name_lower,
        ]
        
        for variant in variants:
            if variant.isdigit():
                continue
            pattern = r'(?<![a-zA-Z0-9_\-\.])' + re.escape(variant) + r'(?![a-zA-Z0-9_\-\.])'
            if re.search(pattern, q, re.IGNORECASE):
                if fid in transcripts:
                    transcript_text = transcripts[fid].get("full_text", "")
                    if transcript_text:
                        return f"**Transcript for {file_name}:**\n\n{transcript_text}"
                    else:
                        return f"No transcript text found for {file_name}."
                else:
                    return f"The file **{file_name}** has been uploaded but not yet transcribed. Please process it first."

    # ─── Existing checks ────────────────────────────────────────────────────
    if any(p in q for p in _FILE_QUERIES):
        if not files_meta:
            return "No files have been uploaded to this chat yet."
        parts = []
        for fid, m in files_meta.items():
            name = m.get("originalName", fid)
            ft = m.get("type", "?")
            st = []
            if fid in transcripts:
                st.append(f"transcribed ({len(transcripts[fid].get('full_text',''))} chars)")
            if fid in summaries:
                st.append("summarised")
            parts.append(f"- **{name}** ({ft})" + (" ✓ " + ", ".join(st) if st else " ⏳ not processed"))
        return "Files in this chat:\n" + "\n".join(parts)

    if any(p in q for p in ("how many files", "number of files", "count of files")):
        a = sum(1 for m in files_meta.values() if m.get("type") == "audio")
        d = sum(1 for m in files_meta.values() if m.get("type") == "pdf")
        return f"There are {len(files_meta)} file(s): {a} audio and {d} PDF."

    if any(p in q for p in _SPEAKER_QUERIES):
        if not transcripts:
            return "No audio has been transcribed yet."
        lines = []
        for fid, t in transcripts.items():
            name = files_meta.get(fid, {}).get("originalName", fid)
            spks = list(t.get("per_speaker", {}).keys())
            lines.append(f"- {name}: {t.get('speaker_count', 0)} speaker(s) — {', '.join(spks) or 'unknown'}")
        return "Speaker information:\n" + "\n".join(lines)

    if any(p in q for p in _TRANSCRIPT_QUERIES):
        if not transcripts:
            return "No audio has been transcribed yet."
        parts = []
        for fid, t in transcripts.items():
            name = files_meta.get(fid, {}).get("originalName", fid)
            text = t.get("full_text", "").strip()
            parts.append(f"{name}:\n{text[:800]}{'...' if len(text) > 800 else ''}")
        return "\n\n".join(parts)

    if any(p in q for p in _SUMMARY_QUERIES):
        if not summaries:
            return "No documents have been summarised yet."
        parts = []
        for fid, s in summaries.items():
            name = files_meta.get(fid, {}).get("originalName", fid)
            if s.get("groq"):
                parts.append(f"**{name}** (Groq summary):\n{s['groq'][:1000]}")
            else:
                parts.append(f"**{name}** (summary):\n{(s.get('template') or '')[:1000]}")
        return "\n\n".join(parts)

    return None


# ── Vector retrieval ──────────────────────────────────────────────────────────

class RAGService:
    """
    Stateless per-request retrieval. The embedding model is loaded once
    at startup via _get_embedder() and cached at module level.
    
    Now supports chat history for context-aware conversations!
    """

    def __init__(self):
        self._embedder = None
        self._groq = None

    def _get_embedder(self):
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer
            print(f"[RAGService] loading embedder {settings.EMBEDDING_MODEL}...")
            self._embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
            print("[RAGService] embedder ready.")
        return self._embedder

    def _get_groq(self):
        """Lazy load Groq client"""
        if self._groq is None:
            from groq import Groq
            api_key = os.getenv('GROQ_API_KEY')
            if not api_key:
                raise ValueError(
                    "GROQ_API_KEY not set. Get one from: https://console.groq.com/keys"
                )
            self._groq = Groq(api_key=api_key)
            print("[RAGService] Groq client ready.")
        return self._groq

    # ── Groq health check ───────────────────────────────────────────────────

    @staticmethod
    def groq_available() -> bool:
        """Check if Groq API key is configured"""
        return bool(os.getenv('GROQ_API_KEY'))

    # ── LLM call with Groq + Chat History ─────────────────────────────────

    def _llm_answer(self, query: str, context: str, chat_history: list = None) -> str:
        """
        Answer using Groq API with chat history for context.
        
        Args:
            query: Current user question
            context: Retrieved document context
            chat_history: List of previous {role, content} messages
        """
        client = self._get_groq()
        model = os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')

        messages = []
        
        system_prompt = f"""
You are a helpful assistant that answers questions about uploaded audio transcripts and documents.

IMPORTANT RULES:
1. Answer ONLY based on the provided context
2. If the answer is not in the context, say "I cannot answer this based on the provided information"
3. Be concise and accurate
4. Use natural, conversational language
5. Reference previous conversation to maintain context
6. Use pronouns (it, they, this) appropriately based on the conversation history
7. Use bullet points or numbered lists if helpful

CONTEXT INFORMATION:
{context}
"""
        messages.append({"role": "system", "content": system_prompt})
        
        if chat_history:
            for msg in chat_history:
                if msg.get('role') in ['user', 'assistant']:
                    messages.append({
                        "role": msg['role'],
                        "content": msg['content']
                    })
        
        messages.append({"role": "user", "content": query})

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=600,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[RAGService] Groq API error: {e}")
            return f"Error generating answer: {str(e)}"

    # ── Context builder ────────────────────────────────────────────────────────

    def _build_context(
        self,
        query: str,
        transcripts: dict,
        summaries: dict,
        files_meta: dict,
    ) -> str:
        import numpy as np
        import faiss

        documents: List[dict] = []
        chunk = settings.RAG_CHUNK_SIZE
        overlap = 100

        print(f"[RAGService] Building context with {len(transcripts)} transcripts, {len(summaries)} summaries")

        # ── Audio transcripts ──────────────────────────────────────────────────
        for fid, t in transcripts.items():
            file_info = files_meta.get(fid, {})
            file_name = file_info.get("originalName", fid)
            
            per = t.get("per_speaker", {})
            body = "\n".join(f"{sp}: {tx}" for sp, tx in per.items()) if per else t.get("full_text", "")
            
            if len(body) < 200:
                if body.strip():
                    documents.append({"text": body, "label": f"Audio: {file_name}"})
            else:
                for i in range(0, min(len(body), 4000), chunk):
                    c = body[i: i + chunk]
                    if c.strip():
                        documents.append({"text": c, "label": f"Audio: {file_name}"})

        # ── PDF summaries ──────────────────────────────────────────────────────
        for fid, s in summaries.items():
            file_info = files_meta.get(fid, {})
            file_name = file_info.get("originalName", fid)
            
            full_text = s.get("full_text", "")
            if full_text:
                for i in range(0, len(full_text), chunk - overlap):
                    c = full_text[i: i + chunk]
                    if len(c) > 100:
                        documents.append({"text": c, "label": f"PDF: {file_name}"})
            
            if s.get("groq"):
                documents.append({"text": s["groq"][:2000], "label": f"PDF summary: {file_name}"})

        print(f"[RAGService] Created {len(documents)} document chunks for vector search")

        if not documents:
            return ""

        embedder = self._get_embedder()
        texts = [d["text"] for d in documents]
        doc_emb = embedder.encode(texts, convert_to_numpy=True).astype("float32")
        q_emb = embedder.encode([query], convert_to_numpy=True).astype("float32")

        index = faiss.IndexFlatL2(doc_emb.shape[1])
        index.add(doc_emb)
        k = min(settings.RAG_TOP_K, len(documents))
        _, idxs = index.search(q_emb, k)

        results = "\n\n".join(
            f"[{documents[i]['label']}]\n{documents[i]['text'].strip()}"
            for i in idxs[0]
            if 0 <= i < len(documents)
        )
        
        print(f"[RAGService] Retrieved {len(idxs[0])} chunks from vector search")
        return results

    # ── Public entry point ────────────────────────────────────────────────────

    def answer(
        self,
        query: str,
        files_meta: dict,
        transcripts: dict,
        summaries: dict,
        chat_history: list = None,
    ) -> Tuple[str, List]:
        """
        Answer *query* using rule-based patterns first, then vector RAG.
        
        Args:
            query: Current user question
            files_meta: File metadata
            transcripts: Transcript data
            summaries: Summary data
            chat_history: Previous chat messages for context
        
        Returns (answer_text, sources_list).
        """
        if not files_meta:
            return "No files uploaded yet. Upload some audio or PDF files and process them first.", []

        if not transcripts and not summaries:
            return "Files are uploaded but not processed yet. Click 'Process Content' first.", []

        answer = _rule_based(query, files_meta, transcripts, summaries)
        if answer is not None:
            return answer, []

        if not self.groq_available():
            return (
                "Groq API key is not configured.\n"
                "1. Get a free API key from: https://console.groq.com/keys\n"
                "2. Add it to your .env file: GROQ_API_KEY=your_key_here",
                [],
            )

        context = self._build_context(query, transcripts, summaries, files_meta)
        if not context:
            return "No relevant content found in the uploaded files.", []

        try:
            answer = self._llm_answer(query, context, chat_history)
            return answer, []
        except Exception as e:
            return f"Error generating answer with Groq: {str(e)}", []


rag_service = RAGService()