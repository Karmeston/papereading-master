from __future__ import annotations

from finals_agent.core.config import ModelSettings, Settings, apply_langsmith_env, load_settings


def build_chat_model(settings: Settings | ModelSettings | None = None):
    """Create the chat model used by the agent.

    Kept in one place so you can swap DeepSeek, OpenAI, or a local
    OpenAI-compatible model without changing the agent and tools.
    """
    from langchain_openai import ChatOpenAI

    settings = settings or load_settings(validate=False)
    if isinstance(settings, Settings):
        settings.model.validate()
        settings.langsmith.validate()
        apply_langsmith_env(settings)
        model_settings = settings.model
    else:
        settings.validate()
        model_settings = settings

    return ChatOpenAI(
        model=model_settings.model,
        api_key=model_settings.api_key,
        base_url=model_settings.base_url,
        temperature=model_settings.temperature,
    )
