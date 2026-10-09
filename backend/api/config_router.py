from fastapi import APIRouter, Request, HTTPException
from backend.core.config import load_config, save_config

router = APIRouter()

@router.get("/api/config")
async def get_config():
    return load_config(for_settings=True)

@router.post("/api/config")
async def update_config(req: Request):
    data = await req.json()
    try:
        save_config(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "success"}
