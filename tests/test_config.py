import os

import pytest

from finals_agent.agent.llm import build_chat_model
from finals_agent.core.config import apply_langsmith_env, load_settings
from finals_agent.core.exceptions import ConfigurationError


def test_load_deepseek_settings_from_env_mapping():
    settings = load_settings(
        env={
            "LLM_PROVIDER": "deepseek",
            "LLM_MODEL": "deepseek-chat",
            "DEEPSEEK_API_KEY": "sk-test",
            "LLM_TEMPERATURE": "0.1",
            "MAX_SEARCH_RESULTS": "7",
        }
    )

    assert settings.model.provider == "deepseek"
    assert settings.model.model == "deepseek-chat"
    assert settings.model.api_key == "sk-test"
    assert settings.model.base_url == "https://api.deepseek.com"
    assert settings.model.temperature == 0.1
    assert settings.runtime.max_search_results == 7
    assert settings.embeddings.provider == "disabled"
    assert settings.embeddings.model == "BAAI/bge-small-zh-v1.5"
    assert settings.paths.memory_path.name == "memory.json"
    assert settings.paths.runs_path.name == "runs.json"
    assert settings.planner.provider == "rule"
    assert settings.planner.confidence_threshold == 0.80
    assert settings.language == "zh"


def test_loads_global_english_language():
    settings = load_settings(
        env={
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test",
            "APP_LANGUAGE": "en",
        }
    )

    assert settings.language == "en"


def test_openai_requires_api_key():
    with pytest.raises(ConfigurationError, match="Missing LLM API key"):
        load_settings(env={"LLM_PROVIDER": "openai"})


def test_custom_provider_requires_base_url():
    with pytest.raises(ConfigurationError, match="LLM_BASE_URL is required"):
        load_settings(env={"LLM_PROVIDER": "custom", "LLM_API_KEY": "not-needed"})


def test_invalid_temperature_is_rejected():
    with pytest.raises(ConfigurationError, match="LLM_TEMPERATURE must be between 0 and 2"):
        load_settings(
            env={
                "LLM_PROVIDER": "deepseek",
                "DEEPSEEK_API_KEY": "sk-test",
                "LLM_TEMPERATURE": "3",
            }
        )


def test_langsmith_tracing_requires_api_key():
    with pytest.raises(ConfigurationError, match="LANGSMITH_API_KEY is required"):
        load_settings(
            env={
                "LLM_PROVIDER": "deepseek",
                "DEEPSEEK_API_KEY": "sk-test",
                "LANGSMITH_TRACING": "true",
            }
        )


def test_apply_langsmith_env_sets_expected_variables(monkeypatch):
    settings = load_settings(
        env={
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test",
            "LANGSMITH_TRACING": "true",
            "LANGSMITH_API_KEY": "ls-test",
            "LANGSMITH_PROJECT": "finals-agent-test",
        }
    )

    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_PROJECT", raising=False)

    apply_langsmith_env(settings)

    try:
        assert os.environ["LANGSMITH_TRACING"] == "true"
        assert os.environ["LANGSMITH_API_KEY"] == "ls-test"
        assert os.environ["LANGSMITH_PROJECT"] == "finals-agent-test"
    finally:
        os.environ.pop("LANGSMITH_TRACING", None)
        os.environ.pop("LANGSMITH_API_KEY", None)
        os.environ.pop("LANGSMITH_PROJECT", None)


def test_load_local_embedding_settings_from_env_mapping():
    settings = load_settings(
        env={
            "LLM_PROVIDER": "deepseek",
            "LLM_MODEL": "deepseek-chat",
            "DEEPSEEK_API_KEY": "sk-test",
            "EMBEDDING_PROVIDER": "local",
            "EMBEDDING_MODEL": "BAAI/bge-m3",
            "EMBEDDING_DEVICE": "cpu",
        }
    )

    assert settings.embeddings.provider == "local"
    assert settings.embeddings.model == "BAAI/bge-m3"
    assert settings.embeddings.device == "cpu"


def test_embedding_settings_do_not_reuse_deepseek_api_key():
    settings = load_settings(
        env={
            "LLM_PROVIDER": "deepseek",
            "LLM_MODEL": "deepseek-chat",
            "DEEPSEEK_API_KEY": "sk-test",
            "EMBEDDING_PROVIDER": "disabled",
        }
    )

    assert settings.embeddings.provider == "disabled"
    assert settings.embeddings.model == "BAAI/bge-small-zh-v1.5"
    assert settings.embeddings.api_key is None
    assert settings.embeddings.base_url is None


def test_invalid_embedding_provider_is_rejected():
    with pytest.raises(ConfigurationError, match="Unsupported EMBEDDING_PROVIDER"):
        load_settings(
            env={
                "LLM_PROVIDER": "deepseek",
                "DEEPSEEK_API_KEY": "sk-test",
                "EMBEDDING_PROVIDER": "unsupported",
            }
        )


def test_deepseek_embedding_provider_is_rejected():
    with pytest.raises(ConfigurationError, match="Unsupported EMBEDDING_PROVIDER"):
        load_settings(
            env={
                "LLM_PROVIDER": "local",
                "LLM_BASE_URL": "http://localhost:5050/v1",
                "EMBEDDING_PROVIDER": "deepseek",
            }
        )


def test_chat_model_validation_is_independent_from_embedding_provider():
    settings = load_settings(
        env={
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test",
            "EMBEDDING_PROVIDER": "deepseek",
        },
        validate=False,
    )

    model = build_chat_model(settings)

    assert model.model_name == "deepseek-chat"


def test_load_vision_settings_from_env_mapping():
    settings = load_settings(
        env={
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test",
            "VISION_PROVIDER": "openai_compatible",
            "VISION_MODEL": "vision-model",
            "VISION_API_KEY": "vision-key",
            "VISION_BASE_URL": "https://vision.example/v1",
            "VISION_RENDER_DPI": "144",
        }
    )

    assert settings.vision.provider == "openai_compatible"
    assert settings.vision.model == "vision-model"
    assert settings.vision.api_key == "vision-key"
    assert settings.vision.base_url == "https://vision.example/v1"
    assert settings.vision.render_dpi == 144


def test_enabled_vision_requires_api_key():
    with pytest.raises(ConfigurationError, match="VISION_API_KEY"):
        load_settings(
            env={
                "LLM_PROVIDER": "deepseek",
                "DEEPSEEK_API_KEY": "sk-test",
                "VISION_PROVIDER": "openai_compatible",
                "VISION_MODEL": "vision-model",
                "VISION_BASE_URL": "https://vision.example/v1",
            }
        )


def test_load_planner_settings_from_env_mapping():
    settings = load_settings(
        env={
            "LLM_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test",
            "PLANNER_PROVIDER": "hybrid",
            "PLANNER_CONFIDENCE_THRESHOLD": "0.6",
        }
    )

    assert settings.planner.provider == "hybrid"
    assert settings.planner.confidence_threshold == 0.6


def test_invalid_planner_provider_is_rejected():
    with pytest.raises(ConfigurationError, match="Unsupported PLANNER_PROVIDER"):
        load_settings(
            env={
                "LLM_PROVIDER": "deepseek",
                "DEEPSEEK_API_KEY": "sk-test",
                "PLANNER_PROVIDER": "unsupported",
            }
        )


def test_invalid_planner_threshold_is_rejected():
    with pytest.raises(ConfigurationError, match="PLANNER_CONFIDENCE_THRESHOLD"):
        load_settings(
            env={
                "LLM_PROVIDER": "deepseek",
                "DEEPSEEK_API_KEY": "sk-test",
                "PLANNER_PROVIDER": "hybrid",
                "PLANNER_CONFIDENCE_THRESHOLD": "1.5",
            }
        )
