from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, File
from services.Groq_client import chat
from services.db import init_db, save_summary
import fitz  # PyMuPDF
import re
import json
import traceback
from typing import List

router = APIRouter()
init_db()

# ==============================
# Constants / Regex
# ==============================

META_PHRASES = [
    "here is a summary",
    "here’s a summary",
    "here is a clear and concise summary",
    "here’s a clear and concise summary",
    "this section discusses",
    "the above text says",
    "in summary,",
    "to summarize,",
    "executive summary (150–220 words)",
    "executive summary (150-220 words)",
]

HEADING_RE = re.compile(
    r"(?mi)^\s*(?:"
    r"INTRODUCTION|"
    r"(?:\d{1,2}\.\s+[A-Z][A-Za-z &/\-]+)|"
    r"CONCLUSION(?: AND ACCEPTANCE)?|"
    r"IN WITNESS WHEREOF"
    r")\s*$"
)

# When LLMs echo reducer instructions like “(150–220 words)”
LENGTH_LABEL_RE = re.compile(r"\(\s*\d+\s*[–-]\s*\d+\s*words\s*\)", re.IGNORECASE)


# ==============================
# Utilities
# ==============================

def clean_meta(text: str) -> str:
    """Remove narrator/meta phrases and normalize whitespace/punctuation."""
    out = (text or "").replace("\u2019", "'").replace("\u2014", "—")
    out = re.sub(r"\s+\n", "\n", out)
    # remove known meta phrases
    low = out.lower()
    for p in META_PHRASES:
        if p in low:
            out = re.sub(re.escape(p), "", out, flags=re.IGNORECASE)
    # remove residual length labels like "(150–220 words)"
    out = LENGTH_LABEL_RE.sub("", out)
    # collapse repeated spaces
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


async def safe_chat(
    messages: List[dict],
    temperature: float = 0.2,
    max_completion_tokens: int = 300,
) -> str:
    """Normalize different possible return shapes from the Groq client to a plain string."""
    out = await chat(messages, temperature=temperature, max_completion_tokens=max_completion_tokens)
    if isinstance(out, str):
        return out
    if isinstance(out, dict):
        if isinstance(out.get("content"), str):
            return out["content"]
        if "choices" in out and out["choices"]:
            ch0 = out["choices"][0]
            if isinstance(ch0, dict):
                msg = ch0.get("message") or {}
                if isinstance(msg, dict) and isinstance(msg.get("content"), str):
                    return msg["content"]
                if isinstance(ch0.get("text"), str):
                    return ch0["text"]
        return json.dumps(out)
    return str(out)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from a PDF; normalize hyphenation and whitespace."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Unable to open PDF: {e}")
    try:
        pages = [p.get_text("text") for p in doc]
        text = "\n".join(pages)
        text = re.sub(r"-\n", "", text)        # join hyphenation
        text = re.sub(r"\n{2,}", "\n\n", text) # collapse extra newlines
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()
    finally:
        doc.close()


def split_by_headings(text: str) -> List[str]:
    """Split contract by real headings like 'INTRODUCTION', '1. Duration ...', etc."""
    lines = text.splitlines()
    idxs = [i for i, ln in enumerate(lines) if HEADING_RE.match(ln)]
    if not idxs:
        return soft_chunks(text, 3500)
    sections: List[str] = []
    for j, start in enumerate(idxs):
        end = idxs[j + 1] if j + 1 < len(idxs) else len(lines)
        block = "\n".join(lines[start:end]).strip()
        if block:
            sections.append(block)
    return sections


def soft_chunks(text: str, chunk_size: int = 3500) -> List[str]:
    """Fallback chunking that prefers sentence boundaries to avoid mid-clause cuts."""
    chunks: List[str] = []
    i, n = 0, len(text)
    while i < n:
        j = min(i + chunk_size, n)
        boundary = text.rfind(". ", i, j)
        if boundary == -1 or boundary < i + int(chunk_size * 0.6):
            boundary = j
        else:
            boundary += 1
        chunk = text[i:boundary].strip()
        if chunk:
            chunks.append(chunk)
        i = boundary
    return chunks


def ensure_liability_complete(section_title: str, section_summary: str) -> str:
    """If Liability ended as 'own free will and', append 'risk.' (common truncation)."""
    if "liability" in section_title.lower():
        if re.search(r"own free will and\s*$", section_summary, flags=re.IGNORECASE):
            return section_summary + " risk."
    return section_summary


# ==============================
# Endpoints
# ==============================

@router.get("/llm-smoke")
async def llm_smoke():
    try:
        messages = [
            {"role": "system", "content": "You are a maths friendly tutor who is eager to help."},
            {"role": "user", "content": "What is 1 + 1?"}
        ]
        out = await safe_chat(messages, temperature=0.0, max_completion_tokens=20)
        return {"model_response": out}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "trace": traceback.format_exc()}
        )


@router.post("/summarize-pdf")
async def summarize_pdf(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        if not pdf_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        text = extract_text_from_pdf(pdf_bytes)
        if not text:
            raise HTTPException(
                status_code=400,
                detail="No extractable text. Is this a scanned PDF without OCR?"
            )

        sections = split_by_headings(text)
        section_summaries: List[str] = []

        for idx, section in enumerate(sections):
            # Title = first non-empty line (keeps original numbering like '1. Duration ...')
            title = next((ln.strip() for ln in section.splitlines() if ln.strip()), f"Section {idx + 1}")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a legal expert. Summarize the following contract section clearly and concisely. "
                        "Do NOT include meta phrases like 'here is a summary'. Use bullets only when helpful."
                    ),
                },
                {"role": "user", "content": section},
            ]
            raw = await safe_chat(messages, temperature=0.1, max_completion_tokens=320)
            cleaned = clean_meta(raw)
            cleaned = ensure_liability_complete(title, cleaned)
            section_summaries.append(f"### {title}\n{cleaned}")

        # Short reducer: polished Executive Summary that surfaces intro tone + duration flexibility if present
        reducer_prompt = (
            "Create a professional Executive Summary (~180 words) of the contract from the following section summaries. "
            "If present, mention the introductory purpose (clarity, professionalism, respect) and any flexibility in Duration "
            "(extension or early termination by mutual written consent). Do not invent facts. No meta language."
        )
        reducer_messages = [
            {"role": "system", "content": "You are a senior legal analyst and excellent writer."},
            {"role": "user", "content": reducer_prompt + "\n\n" + "\n\n".join(section_summaries)},
        ]
        executive = await safe_chat(reducer_messages, temperature=0.1, max_completion_tokens=380)
        executive = clean_meta(executive)

        final_summary = (
            "# Executive Summary\n"
            f"{executive}\n\n"
            "# Clause-by-Clause Summary\n" +
            "\n\n".join(section_summaries)
        )

        # Persist
        save_summary(file.filename, final_summary)

        return {
            "filename": file.filename,
            "summary": final_summary,
            "section_count": len(sections),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "trace": traceback.format_exc()}
        )
