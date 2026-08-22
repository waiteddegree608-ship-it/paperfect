from fastapi import APIRouter, Request
from backend.core.config import load_config, save_config

router = APIRouter()

@router.get("/api/config")
async def get_config():
    return load_config()

@router.post("/api/config")
async def update_config(req: Request):
    # save_config() already only persists *_API_KEY fields — this is a
    # pre-configured commercial build, so the base URL and model are fixed
    # and customers may only ever supply their own API key.
    data = await req.json()
    save_config(data)
    return {"status": "success"}
