"""Standalone LEYRA cloud application; does not alter the LM Arena bridge app."""
from fastapi import FastAPI

from .api import initialize_services, router
from ..leyra_gateway import router as provider_gateway_router

app = FastAPI(
    title="LEYRA IA Cloud",
    version="0.1.0",
    description="Cloud core and provider gateway for LEYRA IA.",
)


@app.on_event("startup")
async def startup() -> None:
    initialize_services(app)


app.include_router(router)
app.include_router(provider_gateway_router)


@app.get("/")
async def root():
    return {"service": "LEYRA IA Cloud", "docs": "/docs", "health": "/leyra/core/health"}
