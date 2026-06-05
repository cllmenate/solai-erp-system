from ninja import NinjaAPI

from apps.assets.api import router as assets_router
from apps.commercial.api import router as commercial_router

api = NinjaAPI(
    title="SolAI ERP API",
    version="1.0.0",
    description="API for B2B multi-tenant ERP system",
)

api.add_router("/partners", commercial_router, tags=["Partners"])
api.add_router("/assets", assets_router, tags=["Assets"])

