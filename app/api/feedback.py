"""
Endpoints de feedback utilisateur sur les réponses de l'assistant.

Permet aux utilisateurs de donner un thumbs up/down et un commentaire.
Les données sont stockées dans Redis pour analyse qualité.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.jwt_auth import TenantInfo, verify_tenant_token
from app.config import Settings, get_settings
from app.feedback.store import FeedbackStore

logger = logging.getLogger(__name__)
router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    tenant_id: str
    request_id: str
    rating: str = Field(..., description="'up' ou 'down'")
    comment: str | None = Field(None, max_length=1000)
    user_id: str | None = None
    message: str | None = Field(None, description="Message utilisateur (pour contexte, tronqué)")
    reply: str | None = Field(None, description="Réponse de l'IA (pour contexte, tronqué)")
    model_used: str | None = None


class FeedbackResponse(BaseModel):
    status: str
    rating: str


class FeedbackStatsResponse(BaseModel):
    tenant_id: str
    thumbs_up: int
    thumbs_down: int
    total: int
    satisfaction_rate_pct: float


class FeedbackEntry(BaseModel):
    request_id: str
    rating: str
    comment: str | None
    user_id: str | None
    message_preview: str | None
    reply_preview: str | None
    model_used: str | None
    timestamp: float


class FeedbackListResponse(BaseModel):
    tenant_id: str
    feedbacks: list[FeedbackEntry]


@router.post("/api/v1/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> FeedbackResponse:
    """Enregistre un feedback utilisateur sur une réponse de l'assistant."""
    if tenant.tenant_id != request.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    if request.rating not in ("up", "down"):
        raise HTTPException(status_code=422, detail="rating doit être 'up' ou 'down'.")

    store = FeedbackStore.get_instance(settings)
    result = store.record_feedback(
        tenant_id=request.tenant_id,
        request_id=request.request_id,
        rating=request.rating,
        comment=request.comment,
        user_id=request.user_id,
        message=request.message,
        reply=request.reply,
        model_used=request.model_used,
    )

    return FeedbackResponse(status=result["status"], rating=result["rating"])


@router.get("/api/v1/feedback/{tenant_id}/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    tenant_id: str,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> FeedbackStatsResponse:
    """Statistiques de feedback pour un tenant."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    store = FeedbackStore.get_instance(settings)
    stats = store.get_stats(tenant_id)

    return FeedbackStatsResponse(**stats)


@router.get("/api/v1/feedback/{tenant_id}/recent", response_model=FeedbackListResponse)
async def get_recent_feedbacks(
    tenant_id: str,
    limit: int = 20,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> FeedbackListResponse:
    """Derniers feedbacks d'un tenant."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit doit être entre 1 et 100.")

    store = FeedbackStore.get_instance(settings)
    feedbacks = store.get_recent(tenant_id, limit)

    return FeedbackListResponse(
        tenant_id=tenant_id,
        feedbacks=[FeedbackEntry(**f) for f in feedbacks],
    )
