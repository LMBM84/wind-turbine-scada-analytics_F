"""
Central application settings — loaded from environment variables / .env file.
All services import from here to ensure a single source of truth.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────
    app_name: str = "Wind Turbine SCADA Analytics"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # ── Database ─────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://scada:scada@localhost:5432/scada_db"
    database_url_sync: str = "postgresql://scada:scada@localhost:5432/scada_db"

    # ── Kafka / Redpanda ─────────────────────────────────────
    kafka_brokers: str = "localhost:9092"
    kafka_topic_scada_raw: str = "scada.raw.10min"
    kafka_topic_anomalies: str = "scada.anomalies"
    kafka_topic_cms: str = "cms.vibration"
    kafka_consumer_group: str = "scada-analytics-v2"

    # ── Redis ────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── MinIO ────────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_raw: str = "scada-raw"
    minio_bucket_models: str = "scada-models"

    # ── MLflow ───────────────────────────────────────────────
    mlflow_tracking_uri: str = "http://localhost:5001"
    mlflow_experiment_name: str = "wind-turbine-anomaly"

    # ── Security ─────────────────────────────────────────────
    secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    cors_origins: str = "http://localhost:5173"

    # ── External Data ────────────────────────────────────────
    kelmarsh_zenodo_url: str = (
        "https://zenodo.org/record/5841834/files/Kelmarsh_SCADA_2016-2021_R0.zip"
    )
    openmeteo_api_url: str = "https://api.open-meteo.com/v1/forecast"

    # ── Celery ───────────────────────────────────────────────
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    @field_validator("cors_origins")
    @classmethod
    def parse_cors(cls, v: str) -> List[str]:
        return [origin.strip() for origin in v.split(",")]

    @property
    def kafka_brokers_list(self) -> List[str]:
        return [b.strip() for b in self.kafka_brokers.split(",")]


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()


settings = get_settings()
