# packages/mcp-server/routes/bip_routes.py
from fastapi import APIRouter, Request, HTTPException, Depends
from ..models.bip_models import BipSessionData

router = APIRouter()

@router.post("/session/bip", summary="Receive BIP session data from extension")
async def receive_bip_session_data(
    request: Request,
    session_data: BipSessionData,
):
    """
    Stores BIP session cookies into the MCP server's session
    for the currently authenticated MCP user.
    """
    # For now, we store it directly in the FastAPI session.
    # Ensure SessionMiddleware is active in main.py
    request.session['bip_session_data'] = session_data.model_dump() # Store as dict

    return {"message": "BIP session data received and stored successfully."}

@router.get("/session/bip/test", summary="Test retrieval of stored BIP session data")
async def test_get_bip_session_data(request: Request):
    """
    Test endpoint to see if BIP session data is in the MCP session.
    """
    bip_data = request.session.get('bip_session_data')
    if not bip_data:
        raise HTTPException(status_code=404, detail="BIP session data not found in MCP session.")
    return {"bip_session_data": bip_data}
