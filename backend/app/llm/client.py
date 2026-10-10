"""Structured (JSON-schema) LLM calls over an ordered chain of providers.

- LLM_PROVIDERS=groq,gemini (comma list, tried in order; the template is always the last resort).
  If unset, every provider with a key in .env is used: anthropic, groq, gemini, openrouter, deepseek.
- Each role (explain / parse / judge) has its own model per provider; env overrides:
  LLM_MODEL / LLM_PARSE_MODEL / LLM_JUDGE_MODEL (first provider) or LLM_<ROLE>_MODEL_<PROVIDER>.
- Reasoning is turned down (Groq gpt-oss: reasoning_effort, Gemini 3: thinking_level, Anthropic: effort),
  which cuts output tokens and latency several-fold for this task.
- A shared token-bucket limiter per (provider, model) keeps requests inside free-tier limits; if the wait
  would be too long, the next provider is tried instead.
- A disk cache keyed by (provider, model, role, prompt, input, schema) makes demo runs instant and
  repeated evaluation runs reproducible and free.
- Any failure moves to the next provider; if all fail, LLMUnavailable tells the caller to use templates.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

try:  # .env holds the API keys; never committed
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
except ImportError:  # pragma: no cover
    pass

T = TypeVar("T", bound=BaseModel)

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
COMMITTED_CACHE = REPO_DIR / "eval" / "llm_cache"  # answers behind reported results and the demo; shipped in git
ROLES = ("explain", "parse", "judge")

# OpenAI-compatible providers: (base URL, API-key env var).
OPENAI_COMPAT = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "deepseek": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
}
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY",
           **{p: env for p, (_, env) in OPENAI_COMPAT.items()}}
AUTO_ORDER = ("anthropic", "groq", "gemini", "openrouter", "deepseek")

# Per provider and role. Confirm names with: venv/bin/python -m app.llm.client --list-models --provider X
MODELS = {
    # Groq judge: qwen3.8-27b allows only 1,000 output tokens/min on the free tier, too little for judging.
    "groq": {"explain": "openai/gpt-oss-120b", "parse": "openai/gpt-oss-20b", "judge": "openai/gpt-oss-20b"},
    "gemini": {"explain": "gemini-3.5-flash", "parse": "gemini-3.1-flash-lite", "judge": "gemini-3.8-flash"},
    "anthropic": {"explain": "claude-opus-5-5", "parse": "claude-opus-5-5", "judge": "claude-sonnet-5-5"},
    "openrouter": {"explain": "deepseek/deepseek-chat-v3.1:free", "parse": "deepseek/deepseek-chat-v3.1:free",
                   "judge": "meta-llama/llama-3.3-70b-instruct:free"},
    "deepseek": {"explain": "deepseek-chat", "parse": "deepseek-chat", "judge": "deepseek-reasoner"},
}
# Default (requests/min, tokens/min) per provider, from the free tiers we hit. Override with
# LLM_RPM_<PROVIDER> / LLM_TPM_<PROVIDER>; 0 means no limit.
LIMITS = {"groq": (30, 8000), "gemini": (10, 250_000), "anthropic": (50, 0), "openrouter": (20, 0), "deepseek": (0, 0)}
EXPECTED_OUTPUT_TOKENS = {"explain": 800, "parse": 200, "judge": 1500}  # measured: ~640 per explanation

# Models that accept the server-side refusal fallback (`fallbacks: "default"`) on the Claude API.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() not in ("0", "false", "no", "off", "")


def _has_key(provider: str) -> bool:
    if provider == "gemini":
        return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    return bool(os.environ.get(KEY_ENV.get(provider, "")))


def _env_chain() -> tuple[str, ...]:
    raw = os.environ.get("LLM_PROVIDERS") or os.environ.get("LLM_PROVIDER") or ""
    chain = [p.strip().lower() for p in raw.split(",") if p.strip()]
    fb = os.environ.get("LLM_FALLBACK_PROVIDER", "").strip().lower()
    if chain and fb and fb not in chain:
        chain.append(fb)
    return tuple(chain) or tuple(p for p in AUTO_ORDER if _has_key(p))


@dataclass(frozen=True)
class LLMSettings:
    providers: tuple[str, ...] = ()  # ordered chain; empty = LLM_PROVIDERS or every provider with a key
    provider: str = ""               # shorthand for a one-provider chain; set to the first provider after init
    model: str = ""                  # explain model for the first provider (else env / table)
    parse_model: str = ""
    judge_model: str = ""
    fallback_provider: str = ""      # appended to a one-provider chain
    explain_effort: str = field(default_factory=lambda: os.environ.get("LLM_EXPLAIN_EFFORT", "medium"))
    parse_effort: str = field(default_factory=lambda: os.environ.get("LLM_PARSE_EFFORT", "low"))
    enabled: bool = field(default_factory=lambda: _env_bool("LLM_ENABLED", True))
    use_cache: bool = field(default_factory=lambda: _env_bool("LLM_CACHE", True))
    server_fallbacks: bool = field(default_factory=lambda: _env_bool("LLM_SERVER_FALLBACKS", True))
    # Longest we wait for a provider's rate limit before trying the next one (raise it for batch evaluation).
    max_wait_s: float = field(default_factory=lambda: float(os.environ.get("LLM_MAX_WAIT_S", "20")))
    cache_dir: Path = field(default_factory=lambda: Path(os.environ.get("LLM_CACHE_DIR", BACKEND_DIR / ".cache/llm")))
    # Read-only caches checked after cache_dir: by default the committed eval/llm_cache, so organisers can
    # reproduce reported answers (and the demo) without API keys.
    read_cache_dirs: tuple[Path, ...] = field(default_factory=lambda: tuple(
        Path(d) for d in os.environ.get("LLM_CACHE_READ_DIRS", str(COMMITTED_CACHE)).split(os.pathsep) if d))
    log_path: Path = field(
        default_factory=lambda: Path(os.environ.get("LLM_LOG_PATH", BACKEND_DIR / ".cache/llm_calls.jsonl")))
    timeout_s: float = field(default_factory=lambda: float(os.environ.get("LLM_TIMEOUT_S", "30")))
    max_retries: int = 1

    def __post_init__(self) -> None:
        chain = self.providers
        if not chain and self.provider:
            chain = (self.provider,) + ((self.fallback_provider,) if self.fallback_provider else ())
        if not chain:
            chain = _env_chain()
        if chain == ("none",):  # cache-only: answer from caches, never call a provider
            chain = ()
        object.__setattr__(self, "providers", tuple(dict.fromkeys(p.strip().lower() for p in chain)))
        object.__setattr__(self, "provider", self.providers[0] if self.providers else "")

    def model_for(self, provider: str, role: str) -> str:
        env = os.environ.get(f"LLM_{role.upper()}_MODEL_{provider.upper()}")
        if env:
            return env
        if provider == self.provider:
            explicit = {"explain": self.model, "parse": self.parse_model, "judge": self.judge_model}[role]
            env_first = os.environ.get({"explain": "LLM_MODEL", "parse": "LLM_PARSE_MODEL",
                                        "judge": "LLM_JUDGE_MODEL"}[role])
            if explicit or env_first:
                return explicit or env_first
        return MODELS.get(provider, {}).get(role, "")


class LLMUnavailable(Exception):
    """No provider produced a usable structured answer. Fall back to templates."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass
class LLMResult(Generic[T]):
    parsed: T
    model: str
    cached: bool
    latency_ms: int
    usage: dict[str, Any]
    request_id: str | None = None
    provider: str = ""


def inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve $ref/$defs so providers with partial JSON-schema support accept the schema."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


# --- Rate limiting --------------------------------------------------------------------------------------------

class RateLimiter:
    """Sliding one-minute window of requests and tokens, shared by every client in the process."""

    def __init__(self, rpm: int, tpm: int):
        self.rpm, self.tpm = rpm, tpm
        self.events: deque[list[float]] = deque()  # [timestamp, tokens]
        self.lock = threading.Lock()

    def wait_time(self, tokens: float, now: float) -> float:
        while self.events and now - self.events[0][0] >= 60:
            self.events.popleft()
        wait = 0.0
        if self.rpm and len(self.events) >= self.rpm:
            wait = self.events[len(self.events) - self.rpm][0] + 60 - now
        if self.tpm:
            used = sum(e[1] for e in self.events)
            if used + tokens > self.tpm:
                freed = 0.0
                for ts, tok in self.events:
                    freed += tok
                    if used - freed + tokens <= self.tpm:
                        wait = max(wait, ts + 60 - now)
                        break
        return max(wait, 0.0)

    def acquire(self, tokens: float, max_wait: float) -> list[float] | None:
        """Reserve capacity, waiting up to max_wait seconds. None = would wait too long (try another provider)."""
        if self.tpm and tokens > self.tpm:
            return None
        deadline = time.monotonic() + max_wait
        while True:
            with self.lock:
                now = time.monotonic()
                wait = self.wait_time(tokens, now)
                if wait <= 0:
                    event = [now, float(tokens)]
                    self.events.append(event)
                    return event
            if now + wait > deadline:
                return None
            time.sleep(min(wait, 5.0))

    def settle(self, event: list[float], actual_tokens: float | None) -> None:
        if actual_tokens:
            with self.lock:
                event[1] = float(actual_tokens)


_LIMITERS: dict[tuple[str, str], RateLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


def limiter_for(provider: str, model: str) -> RateLimiter:
    with _LIMITERS_LOCK:
        key = (provider, model)
        if key not in _LIMITERS:
            rpm, tpm = LIMITS.get(provider, (0, 0))
            rpm = int(os.environ.get(f"LLM_RPM_{provider.upper()}", rpm))
            tpm = int(os.environ.get(f"LLM_TPM_{provider.upper()}", tpm))
            _LIMITERS[key] = RateLimiter(rpm, tpm)
        return _LIMITERS[key]


# --- Client ---------------------------------------------------------------------------------------------------

class LLMClient:
    def __init__(self, settings: LLMSettings | None = None, sdk_client: Any = None):
        self.settings = settings or LLMSettings()
        self._sdks: dict[str, Any] = {}
        if sdk_client is not None and self.settings.provider:  # tests inject a fake SDK for the first provider
            self._sdks[self.settings.provider] = sdk_client

    def sdk(self, provider: str) -> Any:
        if provider not in self._sdks:
            try:
                if provider in OPENAI_COMPAT:
                    import openai

                    base_url, key_env = OPENAI_COMPAT[provider]
                    self._sdks[provider] = openai.OpenAI(base_url=base_url, api_key=os.environ[key_env],
                                                         timeout=self.settings.timeout_s,
                                                         max_retries=self.settings.max_retries)
                elif provider == "gemini":
                    from google import genai

                    self._sdks[provider] = genai.Client(
                        api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
                elif provider == "anthropic":
                    import anthropic

                    self._sdks[provider] = anthropic.Anthropic(timeout=self.settings.timeout_s,
                                                               max_retries=self.settings.max_retries)
                else:
                    raise ValueError(f"unknown provider {provider!r}")
            except Exception as e:  # missing package or credentials
                raise LLMUnavailable("client_init", f"{provider}: {e}") from e
        return self._sdks[provider]

    # --- cache and log -------------------------------------------------------
    def _cache_key(self, provider: str, model: str, role: str, system: str, user: str,
                   schema: type[BaseModel]) -> str:
        blob = json.dumps({"p": provider, "m": model, "r": role, "s": system, "u": user,
                           "schema": schema.model_json_schema()}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    def _cache_get(self, key: str, schema: type[T]) -> T | None:
        if not self.settings.use_cache:
            return None
        for folder in (self.settings.cache_dir, *self.settings.read_cache_dirs):
            path = folder / f"{key}.json"
            if path.exists():
                try:
                    return schema.model_validate_json(path.read_text())
                except (ValidationError, OSError):
                    continue
        return None

    def _cache_put(self, key: str, value: BaseModel) -> None:
        if not self.settings.use_cache:
            return
        self.settings.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.settings.cache_dir / f"{key}.json").write_text(value.model_dump_json(indent=1))

    def _log(self, record: dict[str, Any]) -> None:
        try:
            self.settings.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.settings.log_path.open("a") as fh:
                fh.write(json.dumps({"ts": time.time(), **record}) + "\n")
        except OSError:
            pass

    def _fail(self, provider: str, purpose: str, model: str, reason: str, e: Exception | str) -> LLMUnavailable:
        self._log({"provider": provider, "purpose": purpose, "model": model, "cached": False, "outcome": reason,
                   "error": str(e)[:300]})
        return LLMUnavailable(reason, f"{provider}: {str(e)[:200]}")

    # --- call ----------------------------------------------------------------
    def structured(self, *, system: str, user: str, schema: type[T], role: str = "explain", max_tokens: int,
                   purpose: str) -> LLMResult[T]:
        if not self.settings.enabled:
            raise LLMUnavailable("disabled", "LLM_ENABLED=0 (template mode)")
        # Cache-only mode (no providers) still finds answers cached under any known provider's model.
        cache_chain = [(p, self.settings.model_for(p, role)) for p in (self.settings.providers or AUTO_ORDER)]
        for provider, model in cache_chain:  # any cached answer wins: demo runs never wait on a server
            hit = self._cache_get(self._cache_key(provider, model, role, system, user, schema), schema)
            if hit is not None:
                self._log({"provider": provider, "purpose": purpose, "model": model, "cached": True, "outcome": "ok"})
                return LLMResult(hit, model, True, 0, {}, provider=provider)

        # About 5 characters per token on our prompts (measured on Groq); slightly pessimistic.
        if not self.settings.providers:
            raise LLMUnavailable("no_provider", "cache-only mode, or no API key in .env and LLM_PROVIDERS is empty")
        chain = [(p, self.settings.model_for(p, role)) for p in self.settings.providers]
        estimate = (len(system) + len(user)) / 4.5 + EXPECTED_OUTPUT_TOKENS.get(role, 1000)
        failures: list[str] = []
        for provider, model in chain:
            if not model:
                failures.append(f"{provider}: no model for role {role}")
                continue
            limiter = limiter_for(provider, model)
            event = limiter.acquire(estimate, self.settings.max_wait_s)
            if event is None:
                failures.append(f"{provider}: rate limit (would wait over {self.settings.max_wait_s:.0f}s)")
                self._log({"provider": provider, "purpose": purpose, "model": model, "cached": False,
                           "outcome": "skipped_rate_limit"})
                continue
            call = {"gemini": self._call_gemini, "anthropic": self._call_anthropic}.get(provider,
                                                                                       self._call_openai_compat)
            t0 = time.perf_counter()
            try:
                parsed, served, usage, rid, stop = call(provider, system, user, schema, role, max_tokens, purpose,
                                                        model)
            except LLMUnavailable as e:
                failures.append(f"{provider}: {e.reason}")
                continue
            latency = int((time.perf_counter() - t0) * 1000)
            limiter.settle(event, (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))
            self._log({"provider": provider, "purpose": purpose, "model": served, "cached": False,
                       "latency_ms": latency, "usage": usage, "request_id": rid, "stop_reason": stop, "outcome": "ok"})
            self._cache_put(self._cache_key(provider, model, role, system, user, schema), parsed)
            return LLMResult(parsed, served, False, latency, usage, rid, provider)
        raise LLMUnavailable("all_providers_failed", "; ".join(failures))

    def _effort(self, role: str) -> str:
        return {"explain": self.settings.explain_effort, "parse": self.settings.parse_effort}.get(role, "medium")

    def _call_anthropic(self, provider, system, user, schema, role, max_tokens, purpose, model):
        import anthropic

        kwargs: dict[str, Any] = dict(
            model=model,
            max_tokens=max(max_tokens, 8000),  # thinking tokens count towards max_tokens on this API
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=schema,
            output_config={"effort": self._effort(role)},
        )
        sdk = self.sdk(provider)
        try:
            if self.settings.server_fallbacks and model in _FALLBACK_MODELS:
                resp = sdk.beta.messages.parse(**kwargs, betas=[_FALLBACK_BETA], fallbacks="default")
            else:
                resp = sdk.messages.parse(**kwargs)
        except anthropic.AuthenticationError as e:
            raise self._fail(provider, purpose, model, "auth", e)
        except anthropic.RateLimitError as e:
            raise self._fail(provider, purpose, model, "rate_limited", e)
        except anthropic.BadRequestError as e:
            raise self._fail(provider, purpose, model, "bad_request", e)
        except anthropic.APIStatusError as e:
            raise self._fail(provider, purpose, model, f"api_status_{e.status_code}", e)
        except anthropic.APIConnectionError as e:
            raise self._fail(provider, purpose, model, "connection", e)
        except ValidationError as e:
            raise self._fail(provider, purpose, model, "invalid_output", e)

        u = getattr(resp, "usage", None)
        usage = {"input_tokens": getattr(u, "input_tokens", None), "output_tokens": getattr(u, "output_tokens", None),
                 "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", None)} if u else {}
        if resp.stop_reason == "refusal":
            raise self._fail(provider, purpose, model, "refusal", str(getattr(resp, "stop_details", "")))
        if resp.stop_reason == "max_tokens":
            raise self._fail(provider, purpose, model, "max_tokens", "output cut off")
        parsed = getattr(resp, "parsed_output", None)
        if parsed is None:
            raise self._fail(provider, purpose, model, "invalid_output", "no parsed output")
        return parsed, getattr(resp, "model", model), usage, getattr(resp, "_request_id", None), resp.stop_reason

    def _call_openai_compat(self, provider, system, user, schema, role, max_tokens, purpose, model):
        """Groq / OpenRouter / DeepSeek via the OpenAI-style chat API."""
        import openai

        json_schema = inline_refs(schema.model_json_schema())
        extra: dict[str, Any] = {}
        if model.startswith("openai/gpt-oss"):  # reasoning model: keep thinking short for this task
            extra["reasoning_effort"] = "medium" if role == "judge" else "low"
        formats = [
            {"type": "json_schema", "json_schema": {"name": schema.__name__, "schema": json_schema, "strict": False}},
            {"type": "json_object"},  # some models only support plain JSON mode: the schema goes in the prompt
        ]
        sdk = self.sdk(provider)
        resp = None
        for i, fmt in enumerate(formats):
            sys_text = system if i == 0 else system + "\n\nReturn only JSON matching this JSON schema:\n" + \
                json.dumps(json_schema)
            try:
                resp = sdk.chat.completions.create(
                    model=model, messages=[{"role": "system", "content": sys_text}, {"role": "user", "content": user}],
                    response_format=fmt, max_tokens=max_tokens, temperature=0, **extra)
                break
            except openai.AuthenticationError as e:
                raise self._fail(provider, purpose, model, "auth", e)
            except openai.RateLimitError as e:
                raise self._fail(provider, purpose, model, "rate_limited", e)
            except openai.BadRequestError as e:
                if i == 0:
                    continue  # json_schema not supported by this model: try json_object
                raise self._fail(provider, purpose, model, "bad_request", e)
            except openai.APIStatusError as e:  # includes Groq 413 "request too large for tokens per minute"
                raise self._fail(provider, purpose, model, f"api_status_{e.status_code}", e)
            except openai.APIConnectionError as e:
                raise self._fail(provider, purpose, model, "connection", e)

        choice = resp.choices[0]
        u = resp.usage
        usage = {"input_tokens": getattr(u, "prompt_tokens", None),
                 "output_tokens": getattr(u, "completion_tokens", None)} if u else {}
        if choice.finish_reason == "length":
            raise self._fail(provider, purpose, model, "max_tokens", f"output cut off at {max_tokens} tokens")
        if choice.finish_reason == "content_filter":
            raise self._fail(provider, purpose, model, "refusal", "content_filter")
        try:
            parsed = schema.model_validate_json(choice.message.content or "")
        except ValidationError as e:
            raise self._fail(provider, purpose, model, "invalid_output", e)
        return parsed, resp.model or model, usage, resp.id, choice.finish_reason

    def _call_gemini(self, provider, system, user, schema, role, max_tokens, purpose, model):
        from google.genai import errors, types

        cfg: dict[str, Any] = dict(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=inline_refs(schema.model_json_schema()),
            max_output_tokens=max_tokens,
            temperature=0.0,
        )
        if model.startswith("gemini-3"):  # thinking counts towards output tokens and latency
            cfg["thinking_config"] = types.ThinkingConfig(thinking_level="LOW")
        config = types.GenerateContentConfig(**cfg)
        sdk = self.sdk(provider)
        resp = None
        for attempt in range(2):
            try:
                resp = sdk.models.generate_content(model=model, contents=user, config=config)
                break
            except errors.ClientError as e:
                reason = {401: "auth", 403: "auth", 404: "bad_model", 429: "rate_limited"}.get(e.code, "bad_request")
                raise self._fail(provider, purpose, model, reason, e)
            except errors.ServerError as e:  # 503 "overloaded" is common on the free tier: one short retry
                if attempt == 0:
                    time.sleep(3)
                    continue
                raise self._fail(provider, purpose, model, f"api_status_{e.code}", e)
            except Exception as e:  # network errors surface as httpx exceptions
                raise self._fail(provider, purpose, model, "connection", e)

        cand = (resp.candidates or [None])[0]
        finish = str(getattr(cand, "finish_reason", "") or "").split(".")[-1]
        um = resp.usage_metadata
        usage = {"input_tokens": getattr(um, "prompt_token_count", None),
                 "output_tokens": (getattr(um, "candidates_token_count", 0) or 0)
                 + (getattr(um, "thoughts_token_count", 0) or 0)} if um else {}
        if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"):
            raise self._fail(provider, purpose, model, "refusal", finish)
        if finish == "MAX_TOKENS":
            raise self._fail(provider, purpose, model, "max_tokens", f"output cut off at {max_tokens} tokens")
        text = resp.text
        if not text:
            raise self._fail(provider, purpose, model, "invalid_output", f"empty response ({finish})")
        try:
            parsed = schema.model_validate_json(text)
        except ValidationError as e:
            raise self._fail(provider, purpose, model, "invalid_output", e)
        return parsed, getattr(resp, "model_version", None) or model, usage, getattr(resp, "response_id", None), finish


_DEFAULT_CLIENT: LLMClient | None = None
_DEFAULT_LOCK = threading.Lock()


def get_client() -> LLMClient:
    """One shared client per process (shared SDK connections and rate limits)."""
    global _DEFAULT_CLIENT
    with _DEFAULT_LOCK:
        if _DEFAULT_CLIENT is None:
            _DEFAULT_CLIENT = LLMClient()
        return _DEFAULT_CLIENT


def status() -> dict[str, Any]:
    s = LLMSettings()
    return {"enabled": s.enabled, "providers": [
        {"provider": p, "key_set": _has_key(p), "models": {r: s.model_for(p, r) for r in ROLES},
         "limits_per_min": dict(zip(("requests", "tokens"), LIMITS.get(p, (0, 0))))} for p in s.providers]}


def _list_models(provider: str) -> None:
    client = LLMClient(LLMSettings(providers=(provider,)))
    if provider in OPENAI_COMPAT:
        for m in client.sdk(provider).models.list():
            print(m.id)
    elif provider == "gemini":
        for m in client.sdk(provider).models.list():
            if "generateContent" in (getattr(m, "supported_actions", None) or []):
                print(m.name)
    else:
        print("listing not supported for", provider)


if __name__ == "__main__":
    import sys

    if "--list-models" in sys.argv:
        idx = sys.argv.index("--provider") + 1 if "--provider" in sys.argv else None
        _list_models(sys.argv[idx] if idx else LLMSettings().provider)
    else:
        print(json.dumps(status(), indent=1))
