from fastapi import APIRouter

from app.api.v1.endpoints import (
    ai_insights,
    auth,
    dashboard,
    documents,
    email_integrations,
    expenses,
    external_platforms,
    jobs,
    locations,
    pipeboard_integrations,
    pnl,
    pushops_integrations,
    reconciliation,
    reviews,
    tenants,
    toast_integrations,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(locations.router, prefix="/locations", tags=["locations"])
api_router.include_router(documents.router, prefix="/documents", tags=["documents"])
api_router.include_router(expenses.router, prefix="/expenses", tags=["expenses"])
api_router.include_router(reconciliation.router, prefix="/reconciliation", tags=["reconciliation"])
api_router.include_router(pnl.router, prefix="/pnl", tags=["pnl"])
api_router.include_router(ai_insights.router, prefix="/ai/insights", tags=["ai-insights"])
api_router.include_router(external_platforms.router, prefix="/external", tags=["external-platforms"])
api_router.include_router(toast_integrations.router, prefix="/integrations/toast", tags=["toast"])
api_router.include_router(pushops_integrations.router, prefix="/integrations/pushops", tags=["pushops"])
api_router.include_router(pipeboard_integrations.router, prefix="/integrations/pipeboard", tags=["pipeboard"])
api_router.include_router(email_integrations.router, prefix="/integrations", tags=["email-drive"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
