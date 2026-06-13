from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

from finals_agent.core.exceptions import ConfigurationError


def _application_home() -> Path:
    configured = os.environ.get("PAPER_AGENT_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    if getattr(sys, "frozen", False):
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
        return base / "PapereadingMasterBeta"
    return Path(__file__).resolve().parents[3]


PROJECT_ROOT = _application_home()
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
INDEX_PATH = DATA_DIR / "index.json"
MEMORY_PATH = DATA_DIR / "memory.json"
RUNS_PATH = DATA_DIR / "runs.json"
READING_STATE_PATH = DATA_DIR / "reading_state.json"
RESEARCH_TASKS_PATH = DATA_DIR / "research_tasks.json"
RESEARCH_ATTACHMENTS_DIR = DATA_DIR / "research_attachments"

SUPPORTED_LLM_PROVIDERS = {"deepseek", "openai", "custom", "local"}
SUPPORTED_EMBEDDING_PROVIDERS = {"disabled", "local"}
SUPPORTED_VISION_PROVIDERS = {"disabled", "openai_compatible"}
SUPPORTED_PLANNER_PROVIDERS = {"rule", "hybrid", "llm"}
SUPPORTED_APP_LANGUAGES = {"zh", "en"}


@dataclass(frozen=True)
class ModelSettings:
    provider: str
    model: str
    api_key: str | None
    base_url: str | None
    temperature: float

    def validate(self) -> None:
        if self.provider not in SUPPORTED_LLM_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_LLM_PROVIDERS))
            raise ConfigurationError(f"Unsupported LLM_PROVIDER '{self.provider}'. Allowed values: {allowed}.")
        if not self.model:
            raise ConfigurationError("LLM_MODEL cannot be empty.")
        if not 0 <= self.temperature <= 2:
            raise ConfigurationError("LLM_TEMPERATURE must be between 0 and 2.")
        if self.provider in {"deepseek", "openai"} and not self.api_key:
            raise ConfigurationError(
                "Missing LLM API key. Set DEEPSEEK_API_KEY or OPENAI_API_KEY in .env."
            )
        if self.provider in {"custom", "local"} and not self.base_url:
            raise ConfigurationError("LLM_BASE_URL is required when LLM_PROVIDER is custom or local.")


@dataclass(frozen=True)
class PathSettings:
    project_root: Path
    data_dir: Path
    raw_data_dir: Path
    index_path: Path
    memory_path: Path
    runs_path: Path
    reading_state_path: Path


@dataclass(frozen=True)
class LangSmithSettings:
    tracing: bool
    api_key: str | None
    project: str

    def validate(self) -> None:
        if self.tracing and not self.api_key:
            raise ConfigurationError("LANGSMITH_API_KEY is required when LANGSMITH_TRACING=true.")


@dataclass(frozen=True)
class RuntimeSettings:
    debug: bool
    max_search_results: int

    def validate(self) -> None:
        if self.max_search_results < 1:
            raise ConfigurationError("MAX_SEARCH_RESULTS must be at least 1.")


@dataclass(frozen=True)
class PlannerSettings:
    provider: str
    confidence_threshold: float

    def validate(self) -> None:
        if self.provider not in SUPPORTED_PLANNER_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_PLANNER_PROVIDERS))
            raise ConfigurationError(f"Unsupported PLANNER_PROVIDER '{self.provider}'. Allowed values: {allowed}.")
        if not 0 <= self.confidence_threshold <= 1:
            raise ConfigurationError("PLANNER_CONFIDENCE_THRESHOLD must be between 0 and 1.")


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    model: str
    device: str | None
    api_key: str | None = None
    base_url: str | None = None

    def validate(self) -> None:
        if self.provider not in SUPPORTED_EMBEDDING_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_EMBEDDING_PROVIDERS))
            raise ConfigurationError(f"Unsupported EMBEDDING_PROVIDER '{self.provider}'. Allowed values: {allowed}.")
        if self.provider == "local" and not self.model:
            raise ConfigurationError("EMBEDDING_MODEL cannot be empty when EMBEDDING_PROVIDER=local.")


@dataclass(frozen=True)
class VisionSettings:
    provider: str
    model: str | None
    api_key: str | None
    base_url: str | None
    render_dpi: int
    timeout_seconds: int

    def validate(self) -> None:
        if self.provider not in SUPPORTED_VISION_PROVIDERS:
            allowed = ", ".join(sorted(SUPPORTED_VISION_PROVIDERS))
            raise ConfigurationError(f"Unsupported VISION_PROVIDER '{self.provider}'. Allowed values: {allowed}.")
        if self.provider == "disabled":
            return
        if not self.model:
            raise ConfigurationError("VISION_MODEL cannot be empty when VISION_PROVIDER is enabled.")
        if not self.api_key:
            raise ConfigurationError("VISION_API_KEY is required when VISION_PROVIDER is enabled.")
        if not self.base_url:
            raise ConfigurationError("VISION_BASE_URL is required when VISION_PROVIDER is enabled.")
        if self.render_dpi < 72:
            raise ConfigurationError("VISION_RENDER_DPI must be at least 72.")
        if self.timeout_seconds < 1:
            raise ConfigurationError("VISION_TIMEOUT_SECONDS must be at least 1.")


@dataclass(frozen=True)
class Settings:
    model: ModelSettings
    paths: PathSettings
    langsmith: LangSmithSettings
    runtime: RuntimeSettings
    planner: PlannerSettings
    embeddings: EmbeddingSettings
    vision: VisionSettings
    language: str

    @property
    def llm_provider(self) -> str:
        return self.model.provider

    @property
    def llm_model(self) -> str:
        return self.model.model

    @property
    def llm_base_url(self) -> str | None:
        return self.model.base_url

    @property
    def llm_api_key(self) -> str | None:
        return self.model.api_key

    @property
    def temperature(self) -> float:
        return self.model.temperature

    def validate(self) -> None:
        self.model.validate()
        self.langsmith.validate()
        self.runtime.validate()
        self.planner.validate()
        self.embeddings.validate()
        self.vision.validate()
        if self.language not in SUPPORTED_APP_LANGUAGES:
            allowed = ", ".join(sorted(SUPPORTED_APP_LANGUAGES))
            raise ConfigurationError(f"Unsupported APP_LANGUAGE '{self.language}'. Allowed values: {allowed}.")


def load_settings(
    env_file: Path | None = PROJECT_ROOT / ".env",
    env: Mapping[str, str] | None = None,
    validate: bool = True,
) -> Settings:
    if env is None:
        if env_file:
            load_dotenv(env_file)
        env = os.environ

    settings = Settings(
        model=_load_model_settings(env),
        paths=PathSettings(
            project_root=PROJECT_ROOT,
            data_dir=DATA_DIR,
            raw_data_dir=RAW_DATA_DIR,
            index_path=INDEX_PATH,
            memory_path=MEMORY_PATH,
            runs_path=RUNS_PATH,
            reading_state_path=READING_STATE_PATH,
        ),
        langsmith=LangSmithSettings(
            tracing=_as_bool(env.get("LANGSMITH_TRACING"), default=False),
            api_key=_blank_to_none(env.get("LANGSMITH_API_KEY")),
            project=env.get("LANGSMITH_PROJECT", "paper-agent"),
        ),
        runtime=RuntimeSettings(
            debug=_as_bool(env.get("FINALS_AGENT_DEBUG"), default=False),
            max_search_results=_as_int(env.get("MAX_SEARCH_RESULTS"), default=5, name="MAX_SEARCH_RESULTS"),
        ),
        planner=PlannerSettings(
            provider=env.get("PLANNER_PROVIDER", "rule").lower(),
            confidence_threshold=_as_float(
                env.get("PLANNER_CONFIDENCE_THRESHOLD"),
                default=0.80,
                name="PLANNER_CONFIDENCE_THRESHOLD",
            ),
        ),
        embeddings=EmbeddingSettings(
            provider=env.get("EMBEDDING_PROVIDER", "disabled").lower(),
            model=_embedding_model(env),
            device=_blank_to_none(env.get("EMBEDDING_DEVICE")),
            api_key=_blank_to_none(env.get("EMBEDDING_API_KEY")),
            base_url=_blank_to_none(env.get("EMBEDDING_BASE_URL")),
        ),
        vision=VisionSettings(
            provider=env.get("VISION_PROVIDER", "disabled").lower(),
            model=_blank_to_none(env.get("VISION_MODEL")),
            api_key=_blank_to_none(env.get("VISION_API_KEY")),
            base_url=_blank_to_none(env.get("VISION_BASE_URL")),
            render_dpi=_as_int(env.get("VISION_RENDER_DPI"), default=180, name="VISION_RENDER_DPI"),
            timeout_seconds=_as_int(env.get("VISION_TIMEOUT_SECONDS"), default=60, name="VISION_TIMEOUT_SECONDS"),
        ),
        language=normalize_app_language(env.get("APP_LANGUAGE")),
    )
    if validate:
        settings.validate()
    return settings


def normalize_app_language(value: str | None) -> str:
    normalized = str(value or "zh").strip().lower()
    aliases = {
        "zh-cn": "zh",
        "zh_cn": "zh",
        "chinese": "zh",
        "中文": "zh",
        "en-us": "en",
        "en_us": "en",
        "english": "en",
        "英文": "en",
    }
    return aliases.get(normalized, normalized)


def response_language_instruction(language: str | None = None) -> str:
    target = normalize_app_language(language or os.environ.get("APP_LANGUAGE"))
    if target == "en":
        return (
            "Global output language: English. Write every user-visible explanation, heading, summary, "
            "clarification, and error-facing model response in English, regardless of the source language. "
            "Keep citations, code, formulas, file paths, and proper nouns unchanged."
        )
    return (
        "全局输出语言：中文。所有面向用户的解释、标题、总结、澄清和模型回答必须使用中文，"
        "不受原文语言影响；引用、代码、公式、文件路径和专有名词保持原样。"
    )


def ensure_data_dirs(paths: PathSettings | None = None) -> None:
    paths = paths or load_settings(validate=False).paths
    for folder in ["papers", "documents", "code", "related_work", "supplements", "notes"]:
        (paths.raw_data_dir / folder).mkdir(parents=True, exist_ok=True)
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    paths.memory_path.parent.mkdir(parents=True, exist_ok=True)
    paths.runs_path.parent.mkdir(parents=True, exist_ok=True)
    paths.reading_state_path.parent.mkdir(parents=True, exist_ok=True)
    RESEARCH_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


def apply_langsmith_env(settings: Settings) -> None:
    if not settings.langsmith.tracing:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith.project
    if settings.langsmith.api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith.api_key


def _load_model_settings(env: Mapping[str, str]) -> ModelSettings:
    provider = env.get("LLM_PROVIDER", "deepseek").lower()

    if provider == "deepseek":
        model = env.get("LLM_MODEL", "deepseek-chat")
        base_url = env.get("LLM_BASE_URL", "https://api.deepseek.com")
        api_key = _blank_to_none(env.get("DEEPSEEK_API_KEY"))
    elif provider == "openai":
        model = env.get("LLM_MODEL", "gpt-4.1-mini")
        base_url = _blank_to_none(env.get("LLM_BASE_URL"))
        api_key = _blank_to_none(env.get("OPENAI_API_KEY"))
    elif provider == "local":
        model = env.get("LLM_MODEL", "minimind")
        base_url = env.get("LLM_BASE_URL", "http://localhost:5050/v1")
        api_key = env.get("LLM_API_KEY", "not-needed")
    else:
        model = env.get("LLM_MODEL", "custom-model")
        base_url = _blank_to_none(env.get("LLM_BASE_URL"))
        api_key = env.get("LLM_API_KEY", "not-needed")

    return ModelSettings(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=_as_float(env.get("LLM_TEMPERATURE"), default=0.2, name="LLM_TEMPERATURE"),
    )


def _embedding_model(env: Mapping[str, str]) -> str:
    return env.get("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")


def _blank_to_none(value: str | None) -> str | None:
    if value is None or value.strip() == "":
        return None
    return value


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(value: str | None, default: float, name: str) -> float:
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number.") from exc


def _as_int(value: str | None, default: int, name: str) -> int:
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer.") from exc
