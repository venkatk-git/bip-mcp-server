from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_auth_status():
    return {"status": "auth placeholder"}
