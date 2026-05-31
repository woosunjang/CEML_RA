"""
Lab Research Agents — OpenAI Client

Embedding and chat generation via OpenAI API.
"""

from typing import Optional

import openai

from app.config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, OPENAI_EMBEDDING_MODEL

# Initialize client
_client = openai.OpenAI(api_key=OPENAI_API_KEY)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using OpenAI's embedding API.

    Args:
        texts: List of strings to embed.

    Returns:
        List of embedding vectors (each is a list of floats).
    """
    if not texts:
        return []

    response = _client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=texts,
    )

    # Sort by index to maintain order
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]


def generate_answer(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
) -> str:
    """
    Generate a chat completion using OpenAI's API.

    Args:
        system_prompt: System-level instructions.
        user_prompt: User question with context.
        model: Override model name (defaults to env variable).

    Returns:
        Plain text response from the model.
    """
    model_name = model or OPENAI_CHAT_MODEL

    response = _client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )

    return response.choices[0].message.content or ""
