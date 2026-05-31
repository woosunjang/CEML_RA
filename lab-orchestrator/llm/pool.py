"""
Lab Orchestrator — LLM Pool

Unified interface for multiple LLM providers:
  - OpenAI (gpt-4o, etc.)
  - Anthropic (claude-sonnet, etc.)
  - Google (gemini-flash, etc.)

Model name auto-detects provider. Override with explicit provider param.
"""

import asyncio
import logging
from typing import Optional

import openai

from orchestrator.config import (
    OPENAI_API_KEY, OPENAI_CHAT_MODEL, OPENAI_EMBEDDING_MODEL,
    ANTHROPIC_API_KEY, ANTHROPIC_CHAT_MODEL,
    GOOGLE_API_KEY,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model cost table (USD per 1M tokens)
# ---------------------------------------------------------------------------
MODEL_COSTS = {
    # OpenAI
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "o4-mini": {"input": 1.10, "output": 4.40},
    # Anthropic
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-3": {"input": 0.25, "output": 1.25},
    # Google
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
}

# Fallback models for retry
_FALLBACK = {
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-3",
    "google": "gemini-2.0-flash",
}


def _calc_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate cost in USD."""
    costs = MODEL_COSTS.get(model)
    if not costs:
        # Try prefix match
        for k, v in MODEL_COSTS.items():
            if model.startswith(k):
                costs = v
                break
    if not costs:
        return 0.0
    return (prompt_tokens * costs["input"] + completion_tokens * costs["output"]) / 1_000_000


async def _track_usage(provider: str, model: str, prompt_tokens: int, completion_tokens: int):
    """Record LLM usage asynchronously."""
    try:
        from integrations.usage_tracker import tracker
        cost = _calc_cost(model, prompt_tokens, completion_tokens)
        asyncio.create_task(
            tracker.log_llm_usage(
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
            )
        )
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Client singletons (lazy-loaded)
# ---------------------------------------------------------------------------
_openai_client = openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
_anthropic_client = None
_google_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None and ANTHROPIC_API_KEY:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


def _get_google():
    global _google_client
    if _google_client is None and GOOGLE_API_KEY:
        from google import genai
        _google_client = genai.Client(api_key=GOOGLE_API_KEY)
    return _google_client


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------
def _detect_provider(model: Optional[str]) -> str:
    """Auto-detect provider from model name."""
    if not model:
        return "openai"
    m = model.lower()
    if any(k in m for k in ["claude", "anthropic"]):
        return "anthropic"
    if any(k in m for k in ["gemini", "imagen"]):
        return "google"
    return "openai"


# ---------------------------------------------------------------------------
# Embeddings (OpenAI only)
# ---------------------------------------------------------------------------
def embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using OpenAI."""
    if not texts or not _openai_client:
        return []
    response = _openai_client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=texts,
    )
    sorted_data = sorted(response.data, key=lambda x: x.index)
    return [item.embedding for item in sorted_data]


# ---------------------------------------------------------------------------
# Chat completion — unified interface
# ---------------------------------------------------------------------------
async def generate_answer(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    temperature: float = 0.3,
    chat_history: Optional[list[dict]] = None,
    response_format: Optional[dict] = None,
) -> str:
    """Generate a chat completion from any supported provider.

    Args:
        system_prompt: System-level instructions.
        user_prompt: User question with context.
        model: Model name (auto-detects provider if not specified).
        provider: Override provider (openai | anthropic | google).
        temperature: Sampling temperature.
        chat_history: Previous conversation turns.
        response_format: OpenAI-specific format spec.

    Returns:
        Plain text response.
    """
    p = provider or _detect_provider(model)

    # Fallback: if provider API key is missing, fall back to OpenAI
    if p == "anthropic" and not ANTHROPIC_API_KEY:
        logger.warning(f"Anthropic key missing, falling back to OpenAI for model={model}")
        p = "openai"
        model = OPENAI_CHAT_MODEL
    elif p == "google" and not GOOGLE_API_KEY:
        logger.warning(f"Google key missing, falling back to OpenAI for model={model}")
        p = "openai"
        model = OPENAI_CHAT_MODEL

    # Retry with fallback on rate limit / timeout
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            if p == "anthropic":
                return await _call_anthropic(
                    system_prompt, user_prompt, model, temperature, chat_history
                )
            elif p == "google":
                return await _call_google(
                    system_prompt, user_prompt, model, temperature, chat_history
                )
            else:
                return await _call_openai(
                    system_prompt, user_prompt, model, temperature, chat_history,
                    response_format,
                )
        except Exception as e:
            err_str = str(e).lower()
            is_retriable = any(k in err_str for k in ["rate", "429", "timeout", "overloaded"])
            if is_retriable and attempt < max_retries:
                fallback = _FALLBACK.get(p)
                if fallback and fallback != model:
                    logger.warning(
                        f"LLM {model} failed (attempt {attempt+1}), "
                        f"retrying with fallback {fallback}: {e}"
                    )
                    model = fallback
                    await asyncio.sleep(1 * (attempt + 1))  # backoff
                    continue
            raise


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
async def _call_openai(
    system_prompt: str, user_prompt: str,
    model: Optional[str], temperature: float,
    chat_history: Optional[list[dict]],
    response_format: Optional[dict] = None,
) -> str:
    if not _openai_client:
        return "[ERROR] OpenAI API key not configured."

    model_name = model or OPENAI_CHAT_MODEL
    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": user_prompt})

    kwargs = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        kwargs["response_format"] = response_format

    try:
        response = _openai_client.chat.completions.create(**kwargs)
        # Track usage
        if response.usage:
            await _track_usage(
                "openai", model_name,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )
        return response.choices[0].message.content or ""
    except openai.RateLimitError as e:
        await _alert_llm_error("openai", model_name, "rate_limit", str(e))
        raise
    except openai.AuthenticationError as e:
        await _alert_llm_error("openai", model_name, "auth_error", str(e))
        raise
    except openai.APITimeoutError as e:
        await _alert_llm_error("openai", model_name, "timeout", str(e))
        raise
    except openai.APIError as e:
        await _alert_llm_error("openai", model_name, "api_error", str(e))
        raise


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
async def _call_anthropic(
    system_prompt: str, user_prompt: str,
    model: Optional[str], temperature: float,
    chat_history: Optional[list[dict]],
) -> str:
    client = _get_anthropic()
    if not client:
        return "[ERROR] Anthropic API key not configured."

    model_name = model or ANTHROPIC_CHAT_MODEL

    # Convert chat history to Anthropic format
    messages = []
    if chat_history:
        for msg in chat_history:
            role = msg["role"]
            if role == "system":
                continue  # Anthropic uses separate system param
            messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": user_prompt})

    try:
        response = client.messages.create(
            model=model_name,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
        )
        # Track usage
        if hasattr(response, 'usage') and response.usage:
            await _track_usage(
                "anthropic", model_name,
                getattr(response.usage, 'input_tokens', 0),
                getattr(response.usage, 'output_tokens', 0),
            )
        return response.content[0].text if response.content else ""
    except Exception as e:
        err_str = str(e).lower()
        if "rate" in err_str or "429" in err_str:
            err_type = "rate_limit"
        elif "auth" in err_str or "401" in err_str or "key" in err_str:
            err_type = "auth_error"
        else:
            err_type = "api_error"
        await _alert_llm_error("anthropic", model_name, err_type, str(e))
        raise


# ---------------------------------------------------------------------------
# Google (Gemini)
# ---------------------------------------------------------------------------
async def _call_google(
    system_prompt: str, user_prompt: str,
    model: Optional[str], temperature: float,
    chat_history: Optional[list[dict]],
) -> str:
    client = _get_google()
    if not client:
        return "[ERROR] Google API key not configured."

    model_name = model or "gemini-2.0-flash"

    # Combine system + user prompt for Gemini
    full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}"

    # Include chat history
    if chat_history:
        history_text = "\n".join(
            f"[{m['role']}]: {m['content']}" for m in chat_history
        )
        full_prompt = f"{system_prompt}\n\n## 대화 기록\n{history_text}\n\n---\n\n{user_prompt}"

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
            config={"temperature": temperature},
        )
        if response.candidates:
            parts = response.candidates[0].content.parts
            return "".join(p.text for p in parts if hasattr(p, "text"))
        return ""
    except Exception as e:
        err_str = str(e).lower()
        if "rate" in err_str or "429" in err_str or "quota" in err_str:
            err_type = "rate_limit"
        elif "auth" in err_str or "401" in err_str or "key" in err_str:
            err_type = "auth_error"
        else:
            err_type = "api_error"
        await _alert_llm_error("google", model_name, err_type, str(e))
        raise


# ---------------------------------------------------------------------------
# LLM error alert helper
# ---------------------------------------------------------------------------
async def _alert_llm_error(
    provider: str, model: str, error_type: str, detail: str,
):
    """Send LLM API error alert to #lab-alerts."""
    labels = {
        "rate_limit": "🚦 Rate Limit",
        "auth_error": "🔑 인증 오류 (키 만료/무효)",
        "timeout": "⏱️ Timeout",
        "api_error": "⚠️ API 오류",
    }
    label = labels.get(error_type, error_type)
    try:
        from integrations.slack_notifier import notify_error
        await notify_error(
            f"llm/{provider}",
            f"{label}: {model}",
            detail[:500],
        )
    except Exception:
        pass  # Never let alert failure block LLM calls


# ---------------------------------------------------------------------------
# Streaming (OpenAI only for now)
# ---------------------------------------------------------------------------
async def generate_answer_stream(
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    temperature: float = 0.3,
    chat_history: Optional[list[dict]] = None,
):
    """Generate a streaming chat completion. Yields text chunks."""
    if not _openai_client:
        yield "[ERROR] OpenAI API key not configured."
        return

    model_name = model or OPENAI_CHAT_MODEL

    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": user_prompt})

    stream = _openai_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=temperature,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
