"""Optional provider for the AI Brain's single synthesis call (any OpenAI-compatible chat-completions endpoint).

Off unless BOTH are set, so the offline demo and the tests never touch a network:
    TECC_BRAIN_LLM_URL    e.g. https://api.x.ai/v1/chat/completions (Grok) or any compatible gateway
    TECC_BRAIN_LLM_KEY    bearer token
    TECC_BRAIN_LLM_MODEL  optional model name (default "grok-4")
Whatever the provider returns is untrusted: graph/brain.py validates it and falls back to the rules on failure.
"""

from __future__ import annotations

import os

import httpx

from tecc_brain.graph.brain import BRAIN_TIMEOUT_S, BrainLLM

DEFAULT_MODEL = "grok-4"


def openai_compatible_llm(url: str, api_key: str, model: str = DEFAULT_MODEL, timeout_s: float = BRAIN_TIMEOUT_S) -> BrainLLM:
    def complete(system: str, payload: str) -> str:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": "BRAIN_INPUT:\n" + payload},
                ],
            },
            timeout=timeout_s,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    return complete


def brain_llm_from_env() -> BrainLLM | None:
    url, key = os.environ.get("TECC_BRAIN_LLM_URL"), os.environ.get("TECC_BRAIN_LLM_KEY")
    if not url or not key:
        return None
    return openai_compatible_llm(url, key, os.environ.get("TECC_BRAIN_LLM_MODEL", DEFAULT_MODEL))


__all__ = ["brain_llm_from_env", "openai_compatible_llm"]
