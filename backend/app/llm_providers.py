"""Multi-provider LLM layer: OpenAI primary, with automatic fallback to
Anthropic (Claude) and then Google (Gemini) if the primary errors out
(rate limit, outage, missing/invalid key, etc).

This is what lets the demo keep working even if one provider's key is
missing or its API is having a bad day — genuinely useful for a live demo,
and a real pattern for production resilience/cost-routing.

Model names are read from env so they can be bumped without touching code.
Defaults below were verified 2026-09-14: OpenAI's via web search (no
OPENAI_API_KEY was available to check live), Google's via live calls (both
`models.list()` and an actual `invoke()`), Anthropic's from this session's
own model-ID context. This space moves fast — our OLD default
(gemini-2.0-flash) had already been fully removed from Google's API by the
time this was checked — so re-verify before a demo rather than trusting
these indefinitely.

Deliberately pinned, not "-latest" aliases: `gemini-flash-latest` currently
resolves to a newer Gemini generation that returns `.content` as a list of
structured blocks (text + a reasoning signature) instead of a plain string —
confirmed live. That's a silent breaking change for any code (ours included)
that expects `message.content` to be `str`. Google's own "-latest" alias
moving to a shape-incompatible model without a version bump is exactly the
kind of "still resolves, still technically works, but breaks your app
anyway" failure mode worth pinning against.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()

PROVIDER_STATUS = {
    "openai": bool(os.getenv("OPENAI_API_KEY")),
    "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
    "google": bool(os.getenv("GOOGLE_API_KEY")),
}


# Each provider SDK retries transient errors (rate limits, timeouts) with
# its own backoff by default — which can mean a single failing provider
# hangs for 30-60+ seconds before we ever get the exception that would let
# FallbackLLM move on. That's fine for a background job, not for a live
# demo. Capping retries and per-call timeout here makes a bad provider fail
# fast enough that the fallback chain actually feels instant.
_MAX_RETRIES = 1
_TIMEOUT_SECONDS = 20


def _build_candidates(temperature: float):
    """Return chat models for every provider that has a key set, in
    priority order: OpenAI -> Anthropic -> Google."""
    candidates = []

    if PROVIDER_STATUS["openai"]:
        from langchain_openai import ChatOpenAI

        candidates.append(
            (
                "openai",
                ChatOpenAI(
                    model=os.getenv("OPENAI_MODEL", "gpt-5.4-mini"),
                    temperature=temperature,
                    max_retries=_MAX_RETRIES,
                    timeout=_TIMEOUT_SECONDS,
                ),
            )
        )

    if PROVIDER_STATUS["anthropic"]:
        from langchain_anthropic import ChatAnthropic

        candidates.append(
            (
                "anthropic",
                ChatAnthropic(
                    model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
                    temperature=temperature,
                    max_retries=_MAX_RETRIES,
                    timeout=_TIMEOUT_SECONDS,
                ),
            )
        )

    if PROVIDER_STATUS["google"]:
        from langchain_google_genai import ChatGoogleGenerativeAI

        candidates.append(
            (
                "google",
                ChatGoogleGenerativeAI(
                    model=os.getenv("GOOGLE_MODEL", "gemini-2.5-flash"),
                    temperature=temperature,
                    max_retries=_MAX_RETRIES,
                    timeout=_TIMEOUT_SECONDS,
                ),
            )
        )

    if not candidates:
        raise RuntimeError(
            "No LLM provider is configured. Set at least one of OPENAI_API_KEY, "
            "ANTHROPIC_API_KEY, GOOGLE_API_KEY in backend/.env"
        )
    return candidates


class FallbackLLM:
    """Tries each prepared (provider_name, runnable) pair in order and
    remembers which provider actually served the last call, so callers/UI
    can show it (e.g. "answered via Anthropic" after an OpenAI outage).

    Doing our own try/except loop instead of LangChain's `.with_fallbacks()`
    is the only way to observe *which* provider won without extra plumbing —
    `with_fallbacks()` hides that by design.
    """

    def __init__(self, prepared: list[tuple[str, object]]):
        self._prepared = prepared
        self.last_provider: str | None = None

    def invoke(self, *args, **kwargs):
        last_err: Exception | None = None
        for name, model in self._prepared:
            try:
                result = model.invoke(*args, **kwargs)
                self.last_provider = name
                return result
            except Exception as e:  # noqa: BLE001 - deliberately broad: try next provider
                last_err = e
                continue
        raise RuntimeError(f"All configured LLM providers failed. Last error: {last_err}") from last_err


def get_llm(temperature: float = 0, tools: list | None = None, structured_schema=None) -> FallbackLLM:
    """Build a FallbackLLM that tries providers in order: OpenAI -> Anthropic
    -> Google. Tool-binding / structured output is applied to *each*
    provider's model individually first, so a fallback still has the right
    shape.
    """
    candidates = _build_candidates(temperature)
    prepared = []
    for name, model in candidates:
        m = model
        if tools:
            m = m.bind_tools(tools)
        if structured_schema:
            m = m.with_structured_output(structured_schema)
        prepared.append((name, m))

    return FallbackLLM(prepared)


@lru_cache
def configured_providers() -> tuple[str, ...]:
    return tuple(name for name, ok in PROVIDER_STATUS.items() if ok)
