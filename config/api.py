from ninja import NinjaAPI

from apps.commercial.api import router as commercial_router

api = NinjaAPI(
    title="SolAI ERP API",
    version="1.0.0",
    description="API for B2B multi-tenant ERP system",
)

api.add_router("/partners", commercial_router, tags=["Partners"])
