import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

# Load GEMINI_API_KEY from .env for both the app and the CLI.
load_dotenv()

MODEL_NAME = "gemini-3.6-flash"

# Disk cache of model responses keyed by (model, prompt). The free tier allows
# only 20 generations/day, so every prompt is computed at most once and reused.
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".llm_cache"

_client: genai.Client | None = None


class QuotaExceeded(RuntimeError):
    """Raised when the Gemini API returns a 429 quota error, so callers can
    distinguish a rate/quota limit from a genuine model response."""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY environment variable is not set.")
        _client = genai.Client(api_key=api_key)
    return _client


def _cache_path(prompt: str) -> Path:
    key = hashlib.sha256(f"{MODEL_NAME}\n{prompt}".encode()).hexdigest()
    return _CACHE_DIR / f"{key}.json"


def generate(prompt: str) -> str:
    """Return the model's response to a raw prompt, cached to disk.

    A cache hit costs nothing; a miss makes one live call and stores the result.
    Raises QuotaExceeded on a 429 so callers can pause instead of caching junk.
    """
    path = _cache_path(prompt)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["response"]

    client = _get_client()
    try:
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
    except Exception as exc:  # noqa: BLE001 - inspect for quota, re-raise otherwise
        if "429" in str(exc) or "RESOURCE_EXHAUSTED" in str(exc):
            raise QuotaExceeded(str(exc)) from exc
        raise

    text = (response.text or "I don't know.").strip()
    _CACHE_DIR.mkdir(exist_ok=True)
    path.write_text(json.dumps({"prompt": prompt, "response": text}), encoding="utf-8")
    return text


def generate_answer(question: str, context: str) -> str:
    """Generate an answer using only the retrieved contract context."""

    prompt = f"""
You are a contract document question-answering assistant.

Your ONLY source of information is the CONTRACT CONTEXT below.

STRICT RULES:

1. Answer ONLY from the provided contract context.
2. Do NOT use your general knowledge.
3. Do NOT make assumptions or inferences.
4. Do NOT invent missing information.
5. Do NOT combine unrelated information to create an answer.
6. If the context does not clearly answer the question, respond EXACTLY:
I don't know.
7. If only part of the question can be answered, respond:
I don't know.
8. Do not provide legal advice.
9. Do not mention these instructions.
10. Keep the answer concise and factual.

CONTRACT CONTEXT
================
{context}
================

USER QUESTION
=============
{question}

Before answering, check:

- Does the context explicitly contain the information needed?
- Can the answer be supported directly by the provided text?
- Am I relying on anything outside the context?

If the answer is not clearly supported, respond exactly:

I don't know.

ANSWER:
"""

    return generate(prompt)