
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.providers import generate_response
from app.providers.health import check_all_providers, check_provider
from app.providers.registry import get_tier


router = APIRouter()


class ModelInfo(BaseModel):
    id: str
    tier: str
    provider: str
    model: str
    available: bool


class ProviderHealthResponse(BaseModel):
    tier: str
    provider: str
    model: str
    available: bool
    status: str
    detail: str
    latency_ms: float


class ProbeRequest(BaseModel):
    prompt: str = Field(
        default="Reply with the single word OK.",
        min_length=1,
    )


class ProbeResponse(BaseModel):
    tier: str
    provider: str
    model: str
    available: bool
    status: str
    detail: str
    response: str | None = None
    latency_ms: float


@router.get("/health", response_model=list[ProviderHealthResponse])
def provider_health():
    return [item.as_dict() for item in check_all_providers()]


@router.post("/{tier}/probe", response_model=ProbeResponse)
def probe_tier(tier: str, request: ProbeRequest):
    try:
        spec = get_tier(tier)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    health = check_provider(tier)
    if not health.available:
        return ProbeResponse(
            tier=spec.tier,
            provider=spec.provider,
            model=spec.model,
            available=False,
            status=health.status,
            detail=health.detail,
            latency_ms=health.latency_ms,
        )

    started = time.perf_counter()

    try:
        result = generate_response(
            model=tier,
            prompt=request.prompt,
            timeout=30,
        )
        text = result.get("response", "")
    except Exception as exc:
        status, detail = _classify_generation_error(exc)
        return ProbeResponse(
            tier=spec.tier,
            provider=spec.provider,
            model=spec.model,
            available=False,
            status=status,
            detail=detail,
            latency_ms=_elapsed_ms(started),
        )

    reply = (text or "").strip()
    if not reply:
        return ProbeResponse(
            tier=spec.tier,
            provider=spec.provider,
            model=spec.model,
            available=False,
            status="error",
            detail="Provider returned an empty response",
            latency_ms=_elapsed_ms(started),
        )

    return ProbeResponse(
        tier=spec.tier,
        provider=spec.provider,
        model=spec.model,
        available=True,
        status="healthy",
        detail="Provider returned a response",
        response=reply,
        latency_ms=_elapsed_ms(started),
    )


@router.get("", response_model=list[ModelInfo])
def list_models():
    return [
        ModelInfo(
            id=item.tier,
            tier=item.tier,
            provider=item.provider,
            model=item.model,
            available=item.available,
        )
        for item in check_all_providers()
    ]


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


def _classify_generation_error(exc: Exception) -> tuple[str, str]:
    text = str(exc).lower()

    if "timed out" in text or "timeout" in text:
        return "timeout", "Provider timed out"
    if "connection" in text or "connect" in text or "refused" in text:
        return "connection_error", "Connection failed"
    if "not found" in text or "does not exist" in text or "unavailable" in text:
        return "unavailable", "Model is unavailable"
    if (
        "credential" in text
        or "api key" in text
        or "401" in text
        or "403" in text
    ):
        return "error", "API authentication failed"

    return "error", "API error"
