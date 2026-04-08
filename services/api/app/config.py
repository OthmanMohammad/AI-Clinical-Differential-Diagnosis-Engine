"""Application configuration — single source of truth via environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Environment
    environment: Literal["production", "development"] = "development"

    # API
    api_key: str = "change-me-to-a-real-secret"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Neo4j
    neo4j_uri: str = "neo4j://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "medical_entities"

    # LLM providers
    groq_api_key: str = ""
    cerebras_api_key: str = ""

    # Langfuse
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Voyage AI (optional — production embeddings)
    voyage_api_key: str = ""

    # Rate limiting
    rate_limit_per_minute: int = 10

    # Timeouts (seconds)
    neo4j_query_timeout: int = 5
    llm_timeout: int = 10
    request_timeout: int = 30

    # Embedding model
    @property
    def embedding_model(self) -> str:
        if self.environment == "production":
            return "BAAI/bge-micro-v2"
        return "BAAI/bge-small-en-v1.5"

    # LLM fallback chain
    @property
    def llm_fallbacks(self) -> list[str]:
        models = [
            "groq/llama-3.3-70b-versatile",
            "cerebras/llama-3.3-70b",
            "groq/llama-3.1-8b-instant",
        ]
        if self.environment == "development":
            models.append("ollama/llama3.1:8b")
        return models

    @property
    def primary_llm(self) -> str:
        return self.llm_fallbacks[0]

    @property
    def fallback_llms(self) -> list[str]:
        return self.llm_fallbacks[1:]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
