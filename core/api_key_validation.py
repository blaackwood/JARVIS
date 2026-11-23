"""Validate a user's own Gemini API key before saving first-run setup.

The key is never logged, displayed, or included in an exception message.
"""
from __future__ import annotations

from google import genai
from google.genai import types


def validate_gemini_api_key(api_key: str) -> tuple[bool, str]:
    """Authenticate the supplied key through Google's model-list endpoint."""
    key = str(api_key or "").strip()
    if len(key) < 20:
        return False, "Enter a complete Gemini API key from Google AI Studio."

    client = None
    try:
        client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=12_000),
        )
        page = client.models.list(
            config=types.ListModelsConfig(page_size=1)
        )
        # Force the first page to be fetched; the SDK pager is lazy.
        next(iter(page), None)
        return True, "Google accepted the API key. JARVIS can now connect."
    except Exception as exc:
        code = getattr(exc, "code", None)
        status = getattr(exc, "status_code", None)
        try:
            status = int(status or code or 0)
        except (TypeError, ValueError):
            status = 0
        detail = str(exc).lower()

        if status == 429 or "resource_exhausted" in detail or "quota" in detail:
            return False, (
                "Google recognized the request but the API quota/rate limit is "
                "currently exhausted. Check Usage and Limits in AI Studio, then try again."
            )
        if status in (400, 401, 403) or any(term in detail for term in (
            "api key not valid", "invalid api key", "permission_denied",
            "permission denied", "unauthorized",
        )):
            return False, (
                "Google rejected this key or Gemini API access is not enabled "
                "for its project. Create/check the key in Google AI Studio and try again."
            )
        if any(term in detail for term in (
            "timeout", "timed out", "connection", "name resolution",
            "network is unreachable",
        )):
            return False, (
                "JARVIS could not reach Google to validate the key. Check your "
                "internet connection and try again."
            )
        return False, (
            "Google could not validate this key. Check that it was copied "
            "correctly and that the Gemini API is available for its project."
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
