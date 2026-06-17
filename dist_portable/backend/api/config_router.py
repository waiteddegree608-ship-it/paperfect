from fastapi import APIRouter, Request
from backend.core.config import load_config, save_config

router = APIRouter()

@router.get("/api/config")
async def get_config():
    return load_config()

@router.post("/api/config")
async def update_config(req: Request):
    data = await req.json()
    save_config(data)
    return {"status": "success"}
