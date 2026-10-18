"""Optional provider for the AI Brain's single synthesis call: xAI Grok or Google Gemini, both through their
OpenAI-compatible chat-completions endpoints.

Off unless a key is set, so the offline demo and the tests never touch a network:
    TECC_BRAIN_LLM_KEY    bearer token (xAI key, or a Google AI Studio / Gemini API key)
    TECC_BRAIN_LLM_MODEL  model id (default "grok-4.3"), e.g. "gemini-3-flash-preview", "gemini-2.5-flash", "grok-4.7"
    TECC_BRAIN_LLM_URL    optional: inferred from the model when unset (gemini-* → Google, everything else → xAI)
    TECC_BRAIN_REASONING_EFFORT  Gemini only (default "low"): Gemini 3 thinks at "high" by default, which can miss
                          the Brain's 8 s timeout (a miss means HOLD). Accepts minimal / low / medium / high.
Whatever the provider returns is untrusted: graph/brain.py validates it and falls back on any failure.
"""

from __future__ import annotations

import os

import httpx

from tecc_brain.graph.brain import BRAIN_TIMEOUT_S, BrainLLM

DEFAULT_MODEL = "grok-4.3"
XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"
GEMINI_CHAT_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
DEFAULT_GEMINI_REASONING_EFFORT = "low"


def provider_for(model: str, url: str | None = None) -> str:
    """'gemini' or 'xai' — what the request body has to look like."""
    if model.lower().startswith("gemini") or (url and "generativelanguage.googleapis.com" in url):
        return "gemini"
    return "xai"


def default_url(model: str) -> str:
    return GEMINI_CHAT_URL if provider_for(model) == "gemini" else XAI_CHAT_URL


def request_body(system: str, payload: str, model: str, url: str | None = None) -> dict:
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": "BRAIN_INPUT:\n" + payload},
        ],
    }
    if provider_for(model, url) == "gemini":
        # Gemini 3: keep the default temperature (Google: below 1.0 "may lead to unexpected behavior, such as looping")
        # and cap thinking so the verdict arrives inside BRAIN_TIMEOUT_S. JSON is enforced by the prompt and by
        # validate_verdict (the compat endpoint's response_format support is not documented).
        body["reasoning_effort"] = os.environ.get("TECC_BRAIN_REASONING_EFFORT", DEFAULT_GEMINI_REASONING_EFFORT)
    else:
        body["temperature"] = 0
        body["response_format"] = {"type": "json_object"}
    return body


def openai_compatible_llm(url: str, api_key: str, model: str = DEFAULT_MODEL, timeout_s: float = BRAIN_TIMEOUT_S) -> BrainLLM:
    def complete(system: str, payload: str) -> str:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=request_body(system, payload, model, url),
            timeout=timeout_s,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    return complete


def brain_model() -> str:
    return os.environ.get("TECC_BRAIN_LLM_MODEL", DEFAULT_MODEL)


def brain_llm_from_env() -> BrainLLM | None:
    key = os.environ.get("TECC_BRAIN_LLM_KEY")
    if not key:
        return None
    model = brain_model()
    return openai_compatible_llm(os.environ.get("TECC_BRAIN_LLM_URL") or default_url(model), key, model)


__all__ = [
    "DEFAULT_MODEL", "GEMINI_CHAT_URL", "XAI_CHAT_URL", "brain_llm_from_env", "brain_model", "default_url",
    "openai_compatible_llm", "provider_for", "request_body",
]
