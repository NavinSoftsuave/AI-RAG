import os

from dotenv import load_dotenv
from google import genai

# Load GEMINI_API_KEY from .env for both the app and the CLI.
load_dotenv()

MODEL_NAME = "gemini-3.6-flash"


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY environment variable is not set."
        )

    return genai.Client(api_key=api_key)


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

    client = _get_client()

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    if not response.text:
        return "I don't know."

    return response.text.strip()