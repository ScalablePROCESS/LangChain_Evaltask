"""
Endpoints de suivi des coûts LLM par tenant.

Permet à chaque plateforme EvalTask de consulter sa consommation
(tokens, coût USD), son budget, et l'historique des appels.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.jwt_auth import TenantInfo, verify_tenant_token
from app.config import Settings, get_settings
from app.cost.tracker import CostTracker

logger = logging.getLogger(__name__)
router = APIRouter(tags=["costs"])


# ─── Modèles ───


class CostSummaryResponse(BaseModel):
    tenant_id: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    request_count: int
    budget_threshold_usd: float
    budget_exceeded: bool


class DailyBreakdownItem(BaseModel):
    date: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    request_count: int


class DailyBreakdownResponse(BaseModel):
    tenant_id: str
    days: list[DailyBreakdownItem]


class LogEntry(BaseModel):
    request_id: str | None
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    timestamp: float


class LogsResponse(BaseModel):
    tenant_id: str
    logs: list[LogEntry]


class BudgetStatusResponse(BaseModel):
    tenant_id: str
    total_cost_usd: float
    budget_threshold_usd: float
    exceeded: bool
    remaining_usd: float


class SetBudgetRequest(BaseModel):
    tenant_id: str
    budget_usd: float


class SetBudgetResponse(BaseModel):
    status: str
    tenant_id: str
    budget_usd: float


class ModelPricingResponse(BaseModel):
    models: dict[str, dict[str, float]]


# ─── Endpoints ───


@router.get("/api/v1/costs/{tenant_id}", response_model=CostSummaryResponse)
async def get_cost_summary(
    tenant_id: str,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> CostSummaryResponse:
    """Résumé des coûts LLM pour un tenant."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    tracker = CostTracker.get_instance(settings)
    summary = tracker.get_summary(tenant_id)

    return CostSummaryResponse(**summary)


@router.get("/api/v1/costs/{tenant_id}/daily", response_model=DailyBreakdownResponse)
async def get_daily_breakdown(
    tenant_id: str,
    days: int = 7,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> DailyBreakdownResponse:
    """Consommation jour par jour pour un tenant."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    if days < 1 or days > 90:
        raise HTTPException(status_code=422, detail="days doit être entre 1 et 90.")

    tracker = CostTracker.get_instance(settings)
    breakdown = tracker.get_daily_breakdown(tenant_id, days)

    return DailyBreakdownResponse(
        tenant_id=tenant_id,
        days=[DailyBreakdownItem(**day) for day in breakdown],
    )


@router.get("/api/v1/costs/{tenant_id}/logs", response_model=LogsResponse)
async def get_cost_logs(
    tenant_id: str,
    limit: int = 20,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> LogsResponse:
    """Derniers appels LLM logged pour un tenant."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit doit être entre 1 et 100.")

    tracker = CostTracker.get_instance(settings)
    logs = tracker.get_recent_logs(tenant_id, limit)

    return LogsResponse(
        tenant_id=tenant_id,
        logs=[LogEntry(**log) for log in logs],
    )


@router.get("/api/v1/costs/{tenant_id}/budget", response_model=BudgetStatusResponse)
async def get_budget_status(
    tenant_id: str,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> BudgetStatusResponse:
    """Vérifie le statut du budget d'un tenant."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    tracker = CostTracker.get_instance(settings)
    budget = tracker.check_budget(tenant_id)

    return BudgetStatusResponse(**budget)


@router.put("/api/v1/costs/{tenant_id}/budget", response_model=SetBudgetResponse)
async def set_tenant_budget(
    tenant_id: str,
    request: SetBudgetRequest,
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> SetBudgetResponse:
    """Définit le budget personnalisé d'un tenant (admin seulement)."""
    if tenant.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch.")

    if tenant.tenant_id != "admin" and tenant.tenant_id != "default":
        raise HTTPException(status_code=403, detail="Réservé à l'admin.")

    if request.budget_usd < 0:
        raise HTTPException(status_code=422, detail="Le budget doit être positif.")

    tracker = CostTracker.get_instance(settings)
    tracker.set_tenant_budget(request.tenant_id, request.budget_usd)

    return SetBudgetResponse(
        status="ok",
        tenant_id=request.tenant_id,
        budget_usd=request.budget_usd,
    )


@router.get("/api/v1/costs/pricing/models", response_model=ModelPricingResponse)
async def get_model_pricing(
    tenant: TenantInfo = Depends(verify_tenant_token),
    settings: Settings = Depends(get_settings),
) -> ModelPricingResponse:
    """Retourne les tarifs des modèles supportés (USD pour 1M tokens)."""
    from app.cost.tracker import MODEL_PRICING

    return ModelPricingResponse(models=MODEL_PRICING)
