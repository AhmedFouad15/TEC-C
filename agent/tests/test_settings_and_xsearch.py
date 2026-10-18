"""Live X Search toggle (TECC_ENABLE_X_SEARCH + Settings API), current model defaults, Gemini/xAI Brain requests."""

import json

import pytest
from fastapi.testclient import TestClient

import tecc_brain.graph.brain_llm as brain_llm
import tecc_brain.sentinel.grok as grok
from tecc_brain.app import app
from tecc_brain.reference import load_reference


@pytest.fixture(autouse=True)
def _reset_toggle(monkeypatch):
    monkeypatch.delenv("TECC_ENABLE_X_SEARCH", raising=False)
    grok.set_x_search(None)
    yield
    grok.set_x_search(None)


class Recorder:
    """Fake httpx.post: records every request and answers like the endpoint it was sent to."""

    def __init__(self, chat_text: str, responses_payload: dict | None = None):
        self.calls = []
        self.chat_text = chat_text
        self.responses_payload = responses_payload

    def __call__(self, url, headers=None, json=None, timeout=None):  # noqa: A002 — httpx's own keyword
        self.calls.append({"url": url, "body": json})
        body = self.responses_payload if url.endswith("/responses") else {"choices": [{"message": {"content": self.chat_text}}]}

        class Resp:
            def raise_for_status(self):
                pass

            def json(self):
                return body

        return Resp()


MACRO = '{"retail_capitulation_index": 70, "retail_euphoria_index": 20}'


def sentinel():
    return grok.GrokSentinel(load_reference(), api_key="test-key")


# --- toggle -------------------------------------------------------------------------------------------------


def test_x_search_is_off_by_default_and_follows_the_env(monkeypatch):
    assert grok.x_search_enabled() is False and grok.x_search_source() == "env"
    for value in ("true", "TRUE", "1", "yes", "on"):
        monkeypatch.setenv("TECC_ENABLE_X_SEARCH", value)
        assert grok.x_search_enabled() is True
    monkeypatch.setenv("TECC_ENABLE_X_SEARCH", "false")
    assert grok.x_search_enabled() is False


def test_runtime_override_and_reset(monkeypatch):
    monkeypatch.setenv("TECC_ENABLE_X_SEARCH", "false")
    assert grok.set_x_search(True) is True and grok.x_search_source() == "runtime"
    assert grok.set_x_search(None) is False and grok.x_search_source() == "env"


# --- request shapes ------------------------------------------------------------------------------------------


def test_toggle_off_uses_plain_chat_completions_with_the_current_default_model(monkeypatch):
    rec = Recorder(MACRO)
    monkeypatch.setattr(grok.httpx, "post", rec)
    rubric = sentinel().macro_rubric()
    assert rubric.retail_capitulation_index == 70
    call = rec.calls[0]
    assert call["url"].endswith("/chat/completions") and "tools" not in call["body"]
    assert call["body"]["model"] == grok.DEFAULT_GROK_MODEL == "grok-4.20-0309-non-reasoning"


def test_toggle_on_attaches_x_search_on_the_responses_api(monkeypatch):
    payload = {"output": [
        {"type": "custom_tool_call", "name": "x_search"},
        {"type": "message", "content": [{"type": "output_text",
                                         "text": f"Based on 40 recent posts: {MACRO}"}]},
    ]}
    rec = Recorder("unused", payload)
    monkeypatch.setattr(grok.httpx, "post", rec)
    grok.set_x_search(True)
    s = sentinel()
    assert s.macro_rubric().retail_capitulation_index == 70  # prose around the JSON is tolerated
    s.token_rubric("USDC", ["USDC volume up"])
    assert [c["url"].rsplit("/", 1)[1] for c in rec.calls] == ["responses", "responses"]
    body = rec.calls[0]["body"]
    assert body["tools"] == [{"type": "x_search"}] and body["input"][0]["role"] == "system"
    assert body["max_output_tokens"] == grok.X_SEARCH_MAX_OUTPUT_TOKENS


def test_headline_scoring_never_uses_live_search(monkeypatch):
    rec = Recorder('{"p_negative": 0.4}', {"output_text": '{"p_negative": 0.9}'})
    monkeypatch.setattr(grok.httpx, "post", rec)
    grok.set_x_search(True)
    signal = sentinel().score("USDC issuer delays redemptions")
    assert signal is not None and rec.calls and all(c["url"].endswith("/chat/completions") for c in rec.calls)


def test_a_bad_x_search_reply_falls_back_to_neutral(monkeypatch):
    monkeypatch.setattr(grok.httpx, "post", Recorder("unused", {"output": [{"type": "custom_tool_call"}]}))
    grok.set_x_search(True)
    rubric = sentinel().macro_rubric()
    assert (rubric.retail_capitulation_index, rubric.retail_euphoria_index) == (50, 50)


# --- Settings API --------------------------------------------------------------------------------------------


def test_settings_api_shows_and_toggles_x_search(monkeypatch):
    monkeypatch.setenv("GROK_API_KEY", "secret-grok")
    monkeypatch.setenv("TECC_BRAIN_LLM_KEY", "secret-brain")
    monkeypatch.setenv("TECC_BRAIN_LLM_MODEL", "gemini-3.8-flash")
    client = TestClient(app)
    view = client.get("/api/settings").json()
    assert view["x_search"] == {"enabled": False, "source": "env", "env_default": False, "available": True,
                                "price_note": view["x_search"]["price_note"]}
    assert view["brain"] == {"configured": True, "provider": "gemini", "model": "gemini-3.8-flash"}
    assert view["sentinel"]["model"] == grok.GROK_MODEL and view["pegguard"] == "deterministic"
    assert "secret" not in json.dumps(view)  # keys never leave the backend

    on = client.put("/api/settings/x-search", json={"enabled": True}).json()
    assert on["enabled"] is True and on["source"] == "runtime" and grok.x_search_enabled()
    back = client.put("/api/settings/x-search", json={"enabled": None}).json()
    assert back["enabled"] is False and back["source"] == "env"


def test_settings_api_is_behind_the_same_access_gate(monkeypatch):
    monkeypatch.setenv("TECC_API_TOKEN", "t0k")
    client = TestClient(app)
    assert client.put("/api/settings/x-search", json={"enabled": True}).status_code == 401
    assert grok.x_search_enabled() is False


# --- Brain provider: Gemini and xAI through TECC_BRAIN_LLM_MODEL ----------------------------------------------


def test_brain_defaults_and_provider_inference(monkeypatch):
    monkeypatch.delenv("TECC_BRAIN_LLM_MODEL", raising=False)
    assert brain_llm.brain_model() == "grok-4.3"
    assert brain_llm.provider_for("gemini-3.8-flash") == "gemini"
    assert brain_llm.provider_for("grok-4.7") == "xai"
    assert brain_llm.default_url("gemini-2.5-flash") == brain_llm.GEMINI_CHAT_URL
    assert brain_llm.default_url("grok-4.3") == brain_llm.XAI_CHAT_URL


def test_gemini_body_keeps_default_temperature_and_caps_thinking(monkeypatch):
    monkeypatch.delenv("TECC_BRAIN_REASONING_EFFORT", raising=False)
    body = brain_llm.request_body("sys", "{}", "gemini-3.8-flash")
    assert body["reasoning_effort"] == "low" and "temperature" not in body and "response_format" not in body
    xai = brain_llm.request_body("sys", "{}", "grok-4.3")
    assert xai["temperature"] == 0 and xai["response_format"] == {"type": "json_object"} and "reasoning_effort" not in xai


def test_brain_from_env_needs_only_key_and_model(monkeypatch):
    rec = Recorder('{"ok": true}')
    monkeypatch.setattr(brain_llm.httpx, "post", rec)
    monkeypatch.delenv("TECC_BRAIN_LLM_URL", raising=False)
    monkeypatch.setenv("TECC_BRAIN_LLM_KEY", "k")
    monkeypatch.setenv("TECC_BRAIN_LLM_MODEL", "gemini-3.8-flash")
    llm = brain_llm.brain_llm_from_env()
    assert llm("system", "{}") == '{"ok": true}'
    assert rec.calls[0]["url"] == brain_llm.GEMINI_CHAT_URL and rec.calls[0]["body"]["model"] == "gemini-3.8-flash"
    monkeypatch.delenv("TECC_BRAIN_LLM_KEY")
    assert brain_llm.brain_llm_from_env() is None  # no key → offline rules
