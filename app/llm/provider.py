"""LLM provider abstraction.

Every agent that needs to call a language model goes through
``get_llm()`` — no agent imports ``openai``/``anthropic`` directly. This
keeps the whole system runnable offline (``LLM_PROVIDER=dummy``) and makes
swapping providers a one-line env change.

The dummy provider is not a toy stub that returns fixed text: it performs
deterministic *extractive* synthesis over whatever context it is given
(keyword-overlap sentence ranking), so the rest of the pipeline (RAG,
diagnosis, validation) can be exercised end-to-end, and its behavior
tested, without any API key or network access.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import get_settings


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str


class BaseLLM(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int | None = None) -> LLMResponse: ...


def _estimate_tokens(text: str) -> int:
    """Cheap, provider-agnostic token estimate (~4 chars/token)."""
    return max(1, len(text) // 4)


class DummyLLM(BaseLLM):
    """Deterministic, offline, extractive "LLM".

    Given a system prompt (used only for logging/inspection here) and a
    user prompt that embeds retrieved context, it scores each sentence in
    the context by keyword overlap with the query and returns the
    top-scoring sentences as the "generated" answer. This is intentionally
    simple and inspectable — it exists so the multi-agent pipeline has a
    real, deterministic generation step to test against without needing
    an API key.
    """

    model_name = "dummy-extractive-v1"

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> LLMResponse:
        query, context = self._split_prompt(user)
        sentences = self._split_sentences(context)
        query_terms = self._terms(query)

        scored = []
        for sent in sentences:
            terms = self._terms(sent)
            overlap = len(query_terms & terms)
            if overlap:
                scored.append((overlap, sent))
        scored.sort(key=lambda x: x[0], reverse=True)

        top = [s for _, s in scored[:4]]
        if not top:
            answer = (
                "I could not find directly relevant information in the retrieved "
                "context to answer this confidently."
            )
        else:
            answer = " ".join(top)

        return LLMResponse(
            text=answer,
            input_tokens=_estimate_tokens(system + user),
            output_tokens=_estimate_tokens(answer),
            model=self.model_name,
        )

    @staticmethod
    def _split_prompt(user: str) -> tuple[str, str]:
        """Expect the convention 'QUERY: ...\\n\\nCONTEXT:\\n...' used by
        callers in this codebase; fall back gracefully otherwise."""
        if "CONTEXT:" in user:
            query_part, context_part = user.split("CONTEXT:", 1)
            return query_part.replace("QUERY:", "").strip(), context_part.strip()
        return user, user

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


class OpenAILLM(BaseLLM):
    """Real OpenAI-compatible provider. Requires network + LLM_API_KEY."""

    def __init__(self, model: str, api_key: str):
        if not api_key:
            raise RuntimeError(
                "LLM_PROVIDER=openai requires LLM_API_KEY to be set in .env"
            )
        self.model = model
        self.api_key = api_key

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> LLMResponse:
        import httpx

        settings = get_settings()
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens or settings.llm_max_tokens,
                "temperature": settings.llm_temperature,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            input_tokens=usage.get("prompt_tokens", _estimate_tokens(system + user)),
            output_tokens=usage.get("completion_tokens", _estimate_tokens(text)),
            model=self.model,
        )


class AnthropicLLM(BaseLLM):
    """Real Anthropic provider. Requires network + LLM_API_KEY."""

    def __init__(self, model: str, api_key: str):
        if not api_key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic requires LLM_API_KEY to be set in .env"
            )
        self.model = model
        self.api_key = api_key

    def complete(self, system: str, user: str, max_tokens: int | None = None) -> LLMResponse:
        import httpx

        settings = get_settings()
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": self.model,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "max_tokens": max_tokens or settings.llm_max_tokens,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        text = "".join(block.get("text", "") for block in data.get("content", []))
        usage = data.get("usage", {})
        return LLMResponse(
            text=text,
            input_tokens=usage.get("input_tokens", _estimate_tokens(system + user)),
            output_tokens=usage.get("output_tokens", _estimate_tokens(text)),
            model=self.model,
        )


def get_llm() -> BaseLLM:
    settings = get_settings()
    if settings.llm_provider == "dummy":
        return DummyLLM()
    if settings.llm_provider == "openai":
        return OpenAILLM(settings.llm_model, settings.llm_api_key)
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(settings.llm_model, settings.llm_api_key)
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider}")
