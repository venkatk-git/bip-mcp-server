from pydantic import BaseModel
from typing import Optional

class BipSessionData(BaseModel):
    bip_session_cookie: str
    xsrf_token_cookie: str
    wiki_user_name_cookie: Optional[str] = None
    wiki_user_id_cookie: Optional[str] = None