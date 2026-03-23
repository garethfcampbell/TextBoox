"""
Shared AI client with Gemini primary + OpenAI fallback.

Usage:
    from ai_client import generate_text

    text = generate_text(prompt)
    json_str = generate_text(prompt, json_mode=True, use_thinking=True)
    html = generate_text(prompt, temperature=0.8)
"""

import os
import sys
import time


GEMINI_MODEL = "gemini-3-flash-preview"
OPENAI_MODEL = "gpt-5-nano"
MAX_RETRIES = 3
BACKOFF_SECONDS = [2, 4, 8]


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True only for transient capacity / rate-limit errors worth retrying."""
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
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Cannot use OpenAI fallback. "
            "Please add the OPENAI_API_KEY environment variable."
        )

    from openai import OpenAI

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


def generate_content(
    prompt: str,
    json_mode: bool = False,
    temperature: float | None = None,
    use_thinking: bool = False,
) -> str:
    """Alias for generate_text — matches the task spec interface name."""
    return generate_text(prompt, json_mode=json_mode, temperature=temperature, use_thinking=use_thinking)


def generate_text(
    prompt: str,
    json_mode: bool = False,
    temperature: float | None = None,
    use_thinking: bool = False,
) -> str:
    """
    Generate text using Gemini with exponential backoff retries.

    - Rate-limit / overload errors are retried up to MAX_RETRIES times,
      then fall back to OpenAI gpt-4.1-nano.
    - Non-rate-limit Gemini errors (auth failures, invalid requests, etc.)
      are re-raised immediately without retrying or falling back.
    - Raises RuntimeError if both providers fail.
    """
    rate_limit_exc: Exception | None = None

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
                rate_limit_exc = exc
            else:
                # Non-transient error — re-raise immediately, no fallback
                print(f"[ai_client] Gemini non-retryable error: {exc}", file=sys.stderr)
                raise

    # All retries exhausted due to rate limiting — try OpenAI fallback
    print(
        f"[ai_client] Gemini exhausted after {MAX_RETRIES} rate-limited attempts, "
        f"falling back to OpenAI {OPENAI_MODEL}",
        file=sys.stderr,
    )

    try:
        return _openai(prompt, json_mode, temperature)
    except Exception as openai_exc:
        raise RuntimeError(
            f"Both Gemini and OpenAI failed.\n"
            f"Gemini: {rate_limit_exc}\n"
            f"OpenAI: {openai_exc}"
        ) from openai_exc
