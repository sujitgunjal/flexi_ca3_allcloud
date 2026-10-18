import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3:8b",
)

OLLAMA_API_BASE = os.getenv(
    "OLLAMA_API_BASE",
    "http://localhost:11434",
)

# Model that writes user-facing replies for the local routing tier.
LOCAL_RESPONSE_MODEL = os.getenv(
    "LOCAL_RESPONSE_MODEL",
    "openai/gpt-oss-20b",
)

CHEAP_MODEL = os.getenv(
    "CHEAP_MODEL",
    "nvidia/nemotron-3.5-lightning-30b-a3b",
)

STRONG_MODEL = os.getenv(
    "STRONG_MODEL",
    "nvidia/nemotron-3-ultra-550b-a55b",
)

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")

NVIDIA_API_BASE = os.getenv(
    "NVIDIA_API_BASE",
    "https://integrate.api.nvidia.com/v1",
)

PROVIDER_TIMEOUT_SECONDS = float(
    os.getenv("PROVIDER_TIMEOUT_SECONDS", "8")
)

# Local inference can take longer than the remote provider deadline, especially
# when Ollama is loading a model. Keep it bounded without sharing the cloud SLA.
OLLAMA_TIMEOUT_SECONDS = float(
    os.getenv("OLLAMA_TIMEOUT_SECONDS", "30")
)

# Redis is an optional response cache. The application continues without it.
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))
REDIS_TTL = int(os.getenv("REDIS_TTL", "3600"))
# Minimum cosine similarity required before a cached answer can be reused.
SEMANTIC_CACHE_THRESHOLD = float(os.getenv("SEMANTIC_CACHE_THRESHOLD", "0.86"))
SEMANTIC_CACHE_MAX_CANDIDATES = int(os.getenv("SEMANTIC_CACHE_MAX_CANDIDATES", "200"))

# Embedding provider for context ranking and the semantic cache.
# voyage is the deployed default. ollama remains available.
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "voyage").strip().lower() or "voyage"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30"))
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
VOYAGE_API_BASE = os.getenv("VOYAGE_API_BASE", "https://api.voyageai.com/v1").rstrip("/")
VOYAGE_EMBEDDING_MODEL = os.getenv("VOYAGE_EMBEDDING_MODEL", "voyage-4-lite")
CONTEXT_TOKEN_LIMITS = {
    "low": int(os.getenv("CONTEXT_TOKEN_LIMIT_LOW", "80")),
    "medium": int(os.getenv("CONTEXT_TOKEN_LIMIT_MEDIUM", "240")),
    "high": int(os.getenv("CONTEXT_TOKEN_LIMIT_HIGH", "800")),
}
CONTEXT_MESSAGE_CAPS = {
    "low": int(os.getenv("CONTEXT_MESSAGE_CAP_LOW", "2")),
    "medium": int(os.getenv("CONTEXT_MESSAGE_CAP_MEDIUM", "4")),
    "high": int(os.getenv("CONTEXT_MESSAGE_CAP_HIGH", "8")),
}
