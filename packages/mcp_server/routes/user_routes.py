from fastapi import APIRouter

router = APIRouter()

@router.get("/")
async def get_user_info():
    return {"info": "user placeholder"}
