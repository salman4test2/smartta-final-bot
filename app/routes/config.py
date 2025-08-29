from fastapi import APIRouter

from ..config import get_config, reload_config

router = APIRouter(tags=["config"])

@router.get("/health")
async def health():
    """Health check endpoint returning system status and configuration"""
    cfg = get_config()
    return {"status": "ok", "model": cfg.get("model"), "db": "ok"}

@router.post("/config/reload")
async def config_reload():
    """Reload configuration from disk"""
    cfg = reload_config()
    return {"ok": True, "model": cfg.get("model")}
