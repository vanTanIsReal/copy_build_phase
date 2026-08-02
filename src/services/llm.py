from langchain_groq import ChatGroq

from src.config import get_settings


def get_llm() -> ChatGroq:
    settings = get_settings()
    return ChatGroq(
        model=settings.model_name,
        api_key=settings.groq_api_key,
        temperature=settings.llm_temperature,
    )
