"""
Shared AI client with Gemini primary + OpenAI fallback.

Usage:
    from ai_client import generate_text

    text = generate_text(prompt)
    json_str = generate_text(prompt, json_mode=True, use_thinking=True)
    html = generate_text(prompt, temperature=0.8)
"""

import os
import time
import sys


GEMINI_MODEL = "gemini-3-flash-preview"
OPENAI_MODEL = "gpt-4.1-nano"
MAX_RETRIES = 3
BACKOFF_SECONDS = [2, 4, 8]


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in (
        "429",
        "resource_exhausted",
        "resourceexhausted",
        "quota",
        "overloaded",
        "too many",
        "capacity",
        "rate limit",
        "ratelimit",
    ))


def _gemini(prompt: str, json_mode: bool, temperature: float | None, use_thinking: bool) -> str:
    from google import genai
    from google.genai import types as genai_types

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

    config_kwargs: dict = {}
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    if use_thinking:
        config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_level="high")
    if temperature is not None:
        config_kwargs["temperature"] = temperature

    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(**config_kwargs),
    )
    return resp.text


def _openai(prompt: str, json_mode: bool, temperature: float | None) -> str:
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY", "")
    client = OpenAI(api_key=api_key)

    kwargs: dict = {
        "model": OPENAI_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if temperature is not None:
        kwargs["temperature"] = temperature

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def generate_text(
    prompt: str,
    json_mode: bool = False,
    temperature: float | None = None,
    use_thinking: bool = False,
) -> str:
    """
    Generate text using Gemini with exponential backoff retries.
    Falls back to OpenAI gpt-4.1-nano if Gemini fails after all retries.

    Raises RuntimeError if both providers fail.
    """
    last_exc: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            return _gemini(prompt, json_mode, temperature, use_thinking)
        except Exception as exc:
            if _is_rate_limit_error(exc):
                wait = BACKOFF_SECONDS[attempt] if attempt < len(BACKOFF_SECONDS) else BACKOFF_SECONDS[-1]
                print(
                    f"[ai_client] Gemini rate-limited (attempt {attempt + 1}/{MAX_RETRIES}), "
                    f"retrying in {wait}s...",
                    file=sys.stderr,
                )
                time.sleep(wait)
                last_exc = exc
            else:
                print(f"[ai_client] Gemini non-retryable error: {exc}", file=sys.stderr)
                last_exc = exc
                break

    print(
        f"[ai_client] Gemini failed after {MAX_RETRIES} attempts, falling back to OpenAI {OPENAI_MODEL}",
        file=sys.stderr,
    )

    try:
        return _openai(prompt, json_mode, temperature)
    except Exception as exc:
        raise RuntimeError(
            f"Both Gemini and OpenAI failed.\nGemini: {last_exc}\nOpenAI: {exc}"
        ) from exc
