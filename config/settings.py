"""Centralized, environment-driven configuration. Nothing sensitive is hardcoded here."""
import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    classifier_model: str = field(default_factory=lambda: os.getenv("CLASSIFIER_MODEL", "gpt-4o-mini"))
    summary_model: str = field(default_factory=lambda: os.getenv("SUMMARY_MODEL", "gpt-4o-mini"))
    model_temperature: float = field(default_factory=lambda: float(os.getenv("MODEL_TEMPERATURE", "0")))
    max_feedback_length: int = field(default_factory=lambda: int(os.getenv("MAX_FEEDBACK_LENGTH", "4000")))
    theme_cluster_distance_threshold: float = field(
        default_factory=lambda: float(os.getenv("THEME_CLUSTER_DISTANCE_THRESHOLD", "0.35"))
    )
    chroma_persist_dir: str = field(default_factory=lambda: os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"))
    top_theme_count: int = field(default_factory=lambda: int(os.getenv("TOP_THEME_COUNT", "8")))
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "./pulseai.db"))


def get_settings() -> Settings:
    return Settings()
