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
    Stores BIP session cookies into the server-side session.
    """
    session_data_dict = session_data.model_dump()
    request.session['bip_session_data'] = session_data_dict

    # Log the received data to the console for verification
    print("--- Received BIP Session Data (now in server session) ---")
    print(session_data_dict)
    print("---------------------------------")

    return {"message": "BIP session data received and stored in server session successfully."}

@router.get("/session/bip/test", summary="Test retrieval of stored BIP session data")
async def test_get_bip_session_data(request: Request):
    """
    Test endpoint to retrieve the BIP session data from the server-side session.
    """
    bip_data = request.session.get('bip_session_data')
    if not bip_data:
        raise HTTPException(status_code=404, detail="BIP session data not found in server session.")
    return {"bip_session_data": bip_data}
