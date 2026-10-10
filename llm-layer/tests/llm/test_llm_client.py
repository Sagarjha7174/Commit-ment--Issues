"""Provider wiring: Gemini path with a stand-in SDK (no key or network needed)."""

from types import SimpleNamespace

import pytest

from backend.app.llm.claims import ExplanationDraft, ExplanationText, WhatIfParse
from backend.app.llm.client import LLMClient, LLMSettings, LLMUnavailable, inline_refs
from backend.app.llm.explain import explain_sheet
from helpers import as_text, template_for


class FakeGemini:
    def __init__(self, text, finish="STOP"):
        self.calls = []
        self.models = SimpleNamespace(generate_content=self._gen)
        self.text, self.finish = text, finish

    def _gen(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return SimpleNamespace(
            text=self.text, candidates=[SimpleNamespace(finish_reason=self.finish)],
            usage_metadata=SimpleNamespace(prompt_token_count=100, candidates_token_count=50, thoughts_token_count=10,
                                           cached_content_token_count=0),
            model_version=model, response_id="r1")


def _settings(tmp_path):
    return LLMSettings(provider="gemini", model="gemini-test", use_cache=False, enabled=True,
                       log_path=tmp_path / "log.jsonl")


def test_schema_has_no_refs():
    s = inline_refs(ExplanationDraft.model_json_schema())
    assert "$ref" not in str(s) and "$defs" not in s


def test_gemini_valid_answer_is_used(tmp_path):
    sheet, good = template_for("york-demo-poor-semi")
    sdk = FakeGemini(as_text(good).model_dump_json())
    res = explain_sheet(sheet, client=LLMClient(_settings(tmp_path), sdk_client=sdk))
    assert res.source == "llm" and res.provider == "gemini"
    cfg = sdk.calls[0]["config"]
    assert cfg.response_mime_type == "application/json" and cfg.temperature == 0.0
    assert "FACTS (" in sdk.calls[0]["contents"]


def test_gemini_safety_block_falls_back(tmp_path):
    sheet, good = template_for("york-demo-poor-semi")
    sdk = FakeGemini(as_text(good).model_dump_json(), finish="SAFETY")
    res = explain_sheet(sheet, client=LLMClient(_settings(tmp_path), sdk_client=sdk))
    assert res.source == "template" and "refusal" in res.fallback_reason
    assert sdk.calls[0]["config"].thinking_config is None  # gemini-test is not a gemini-3 model


def test_gemini_invalid_json_raises_unavailable(tmp_path):
    client = LLMClient(_settings(tmp_path), sdk_client=FakeGemini("not json"))
    with pytest.raises(LLMUnavailable):
        client.structured(system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")


def test_provider_defaults(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("LLM_JUDGE_MODEL", raising=False)
    s = LLMSettings(provider="gemini")
    gen, judge = s.model_for("gemini", "explain"), s.model_for("gemini", "judge")
    assert gen.startswith("gemini") and judge.startswith("gemini") and gen != judge


class FakeOpenAICompat:
    def __init__(self, text, reject_json_schema=False):
        self.text, self.reject, self.calls = text, reject_json_schema, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, response_format, max_tokens, temperature, **extra):
        self.extra = extra
        import httpx
        import openai
        self.calls.append(response_format["type"])
        if self.reject and response_format["type"] == "json_schema":
            req = httpx.Request("POST", "http://x")
            raise openai.BadRequestError("no json_schema", response=httpx.Response(400, request=req), body=None)
        msg = SimpleNamespace(content=self.text)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5), model=model, id="c1")


def test_groq_json_schema_then_json_object_fallback(tmp_path):
    parsed = WhatIfParse(kind="change_measures", add=["heat_pump"], remove=[], unsupported=[])
    sdk = FakeOpenAICompat(parsed.model_dump_json(), reject_json_schema=True)
    c = LLMClient(LLMSettings(provider="groq", model="m", use_cache=False, enabled=True, log_path=tmp_path / "l"),
                  sdk_client=sdk)
    res = c.structured(system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")
    assert res.parsed == parsed and sdk.calls == ["json_schema", "json_object"] and res.provider == "groq"


def test_failed_provider_moves_to_next_in_chain(tmp_path):
    parsed = WhatIfParse(kind="change_measures", add=["solar_pv"], remove=[], unsupported=[])
    settings = LLMSettings(providers=("gemini", "groq"), use_cache=False, enabled=True, log_path=tmp_path / "l")
    client = LLMClient(settings)
    client._sdks["gemini"] = FakeGemini("not json")           # invalid output
    client._sdks["groq"] = FakeOpenAICompat(parsed.model_dump_json())
    res = client.structured(system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")
    assert res.provider == "groq" and res.parsed == parsed
    assert client._sdks["groq"].extra == {"reasoning_effort": "low"}  # gpt-oss parse model: short reasoning


def test_all_providers_failing_raises_with_reasons(tmp_path):
    settings = LLMSettings(providers=("gemini",), use_cache=False, enabled=True, log_path=tmp_path / "l")
    client = LLMClient(settings, sdk_client=FakeGemini("not json"))
    with pytest.raises(LLMUnavailable) as e:
        client.structured(system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")
    assert e.value.reason == "all_providers_failed" and "gemini: invalid_output" in e.value.detail


def test_cached_answer_needs_no_provider(tmp_path):
    parsed = WhatIfParse(kind="out_of_scope", add=[], remove=[], unsupported=["bills"])
    s1 = LLMSettings(providers=("groq",), use_cache=True, enabled=True, cache_dir=tmp_path, log_path=tmp_path / "l")
    LLMClient(s1, sdk_client=FakeOpenAICompat(parsed.model_dump_json())).structured(
        system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")
    offline = LLMClient(s1, sdk_client=FakeOpenAICompat("this would fail"))
    res = offline.structured(system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")
    assert res.cached and res.parsed == parsed


def test_rate_limiter_waits_or_skips():
    from backend.app.llm.client import RateLimiter
    lim = RateLimiter(rpm=2, tpm=1000)
    assert lim.acquire(400, max_wait=0) and lim.acquire(400, max_wait=0)
    assert lim.acquire(100, max_wait=0) is None      # third request in the minute: over rpm
    assert RateLimiter(rpm=0, tpm=500).acquire(600, max_wait=60) is None  # can never fit: skip at once


def test_chain_and_per_role_models(monkeypatch):
    for k in ("LLM_MODEL", "LLM_PARSE_MODEL", "LLM_JUDGE_MODEL", "LLM_PROVIDERS", "LLM_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    s = LLMSettings(providers=("groq", "gemini"))
    assert s.provider == "groq"
    assert s.model_for("groq", "explain") != s.model_for("groq", "parse")
    assert s.model_for("gemini", "judge").startswith("gemini")
    monkeypatch.setenv("LLM_PROVIDERS", "gemini, groq")
    assert LLMSettings().providers == ("gemini", "groq")


def test_committed_read_only_cache_is_used_without_keys(tmp_path):
    parsed = WhatIfParse(kind="out_of_scope", add=[], remove=[], unsupported=["grants"])
    committed, local = tmp_path / "committed", tmp_path / "local"
    writer = LLMSettings(providers=("groq",), use_cache=True, enabled=True, cache_dir=committed, read_cache_dirs=(),
                         log_path=tmp_path / "l")
    LLMClient(writer, sdk_client=FakeOpenAICompat(parsed.model_dump_json())).structured(
        system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")
    reader = LLMSettings(providers=("groq",), use_cache=True, enabled=True, cache_dir=local,
                         read_cache_dirs=(committed,), log_path=tmp_path / "l")
    res = LLMClient(reader, sdk_client=FakeOpenAICompat("unused")).structured(
        system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")
    assert res.cached and res.parsed == parsed and not any(local.glob("*.json"))


def test_cache_only_mode_never_calls_a_provider(tmp_path, monkeypatch):
    parsed = WhatIfParse(kind="out_of_scope", add=[], remove=[], unsupported=["grants"])
    writer = LLMSettings(providers=("groq",), use_cache=True, enabled=True, cache_dir=tmp_path, read_cache_dirs=(),
                         log_path=tmp_path / "l")
    LLMClient(writer, sdk_client=FakeOpenAICompat(parsed.model_dump_json())).structured(
        system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")
    monkeypatch.setenv("LLM_PROVIDERS", "none")
    cache_only = LLMSettings(use_cache=True, enabled=True, cache_dir=tmp_path, read_cache_dirs=(), log_path=tmp_path / "l")
    assert cache_only.providers == ()
    client = LLMClient(cache_only)
    assert client.structured(system="s", user="u", schema=WhatIfParse, role="parse", max_tokens=100,
                             purpose="t").cached
    with pytest.raises(LLMUnavailable):  # not cached -> no provider to ask
        client.structured(system="s", user="other", schema=WhatIfParse, role="parse", max_tokens=100, purpose="t")
