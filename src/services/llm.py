import logging
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

from src.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMResult:
    message: Any
    provider: str
    model: str


class AllLLMProvidersFailedError(RuntimeError):
    pass


def _build_llm(provider: str, model: str) -> BaseChatModel:
    settings = get_settings()
    if provider == "groq":
        return ChatGroq(model=model, api_key=settings.groq_api_key, temperature=settings.llm_temperature)
    if provider == "openai":
        kwargs = {"model": model, "api_key": settings.openai_api_key}
        if not model.startswith("o"):
            kwargs["temperature"] = settings.llm_temperature
        return ChatOpenAI(**kwargs)
    return ChatGoogleGenerativeAI(
        model=model, google_api_key=settings.google_api_key, temperature=settings.llm_temperature
    )


def _candidates() -> list[tuple[str, str]]:
    settings = get_settings()
    keys = {
        "google": settings.google_api_key,
        "openai": settings.openai_api_key,
        "groq": settings.groq_api_key,
    }
    defaults = {
        "openai": ["gpt-4o-mini", "o4-mini"],
        "google": ["gemini-2.5-flash", "gemini-2.5-flash-lite"],
        "groq": ["openai/gpt-oss-20b", "llama-3.1-8b-instant"],
    }
    ordered = [(settings.llm_provider, settings.model_name)]
    for provider in ("openai", "google", "groq"):
        ordered.extend((provider, model) for model in defaults[provider])
    result: list[tuple[str, str]] = []
    for candidate in ordered:
        if keys.get(candidate[0]) and candidate not in result:
            result.append(candidate)
    return result


def get_llm() -> BaseChatModel:
    """Return the configured model. Kept for compatibility; new calls should use invoke_with_fallback."""
    settings = get_settings()
    return _build_llm(settings.llm_provider, settings.model_name)


async def invoke_with_fallback(prompt: Any, *, tools: list | None = None) -> LLMResult:
    candidates = _candidates()
    if not candidates:
        raise AllLLMProvidersFailedError(
            "No AI provider is configured. Set GOOGLE_API_KEY, OPENAI_API_KEY, or GROQ_API_KEY."
        )
    failures: list[str] = []
    for provider, model in candidates:
        try:
            llm = _build_llm(provider, model)
            runnable = llm.bind_tools(tools) if tools else llm
            return LLMResult(message=await runnable.ainvoke(prompt), provider=provider, model=model)
        except Exception as exc:  # noqa: BLE001 - a failed provider is exactly what fallback handles
            logger.warning("AI provider failed; trying fallback (%s/%s): %s", provider, model, exc)
            failures.append(f"{provider}/{model}: {type(exc).__name__}")
    raise AllLLMProvidersFailedError("All configured AI providers failed (" + ", ".join(failures) + ").")
