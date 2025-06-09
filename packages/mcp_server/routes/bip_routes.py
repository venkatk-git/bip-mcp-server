# packages/mcp-server/routes/bip_routes.py
from fastapi import APIRouter, Request, HTTPException, Depends
from ..models.bip_models import BipSessionData

router = APIRouter()

# WARNING: This is a temporary, in-memory storage for demonstration purposes only.
# It is NOT suitable for production as it's not thread-safe and will be lost on restart.
LATEST_BIP_SESSION_DATA = None

@router.post("/session/bip", summary="Receive BIP session data from extension")
async def receive_bip_session_data(
    request: Request,
    session_data: BipSessionData,
):
    """
    Stores BIP session cookies into a global variable for testing.
    """
    global LATEST_BIP_SESSION_DATA
    session_data_dict = session_data.model_dump()
    LATEST_BIP_SESSION_DATA = session_data_dict

    # Log the received data to the console for verification
    print("--- Received BIP Session Data ---")
    print(session_data_dict)
    print("---------------------------------")

    return {"message": "BIP session data received and stored successfully."}

@router.get("/session/bip/test", summary="Test retrieval of stored BIP session data")
async def test_get_bip_session_data(request: Request):
    """
    Test endpoint to retrieve the most recently received BIP session data.
    """
    if not LATEST_BIP_SESSION_DATA:
        raise HTTPException(status_code=404, detail="BIP session data not found in MCP session.")
    return {"bip_session_data": LATEST_BIP_SESSION_DATA}
