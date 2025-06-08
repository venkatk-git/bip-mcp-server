# packages/mcp-server/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    # Application settings
    APP_NAME: str = "MCP-Enabled AI Assistant for BIP Portal"
    DEBUG: bool = False
    ROOT_PATH: str = "" # For deployments behind a reverse proxy, e.g. /api/v1

    # BIP OAuth2 Configuration (!!! REPLACE WITH ACTUAL VALUES FROM BIP !!!)
    BIP_CLIENT_ID: str = "YOUR_BIP_CLIENT_ID"
    BIP_CLIENT_SECRET: str = "YOUR_BIP_CLIENT_SECRET"
    BIP_AUTHORIZATION_URL: str = "https://bip.portal.example.com/oauth/authorize"
    BIP_TOKEN_URL: str = "https://bip.portal.example.com/oauth/token"
    BIP_USERINFO_URL: str = "https://bip.portal.example.com/oauth/userinfo" # If BIP provides user info endpoint
    BIP_REDIRECT_URI: str = "http://localhost:8000/auth/callback" # Must match registered redirect URI
    BIP_SCOPES: str = "openid profile email read:academic_data" # Example scopes

    # Session Middleware Secret Key (generate a random string for this)
    # openssl rand -hex 32
    SESSION_SECRET_KEY: str = "YOUR_VERY_SECRET_RANDOM_STRING_FOR_SESSIONS"

    # AI Model API Key
    GOOGLE_API_KEY: str = "" # Will be loaded from .env

    # For .env file loading
    # Construct an absolute path to the .env file relative to this config.py file
    # This assumes .env is in the same directory as config.py (which is packages/mcp_server)
    _env_file_path = os.path.join(os.path.dirname(__file__), ".env")
    print(f"DEBUG config.py: Attempting to load .env file from: '{_env_file_path}'")
    model_config = SettingsConfigDict(env_file=_env_file_path, env_file_encoding='utf-8', extra='ignore')

settings = Settings()
print(f"DEBUG config.py: Loaded GOOGLE_API_KEY = '{settings.GOOGLE_API_KEY}' after Settings() instantiation")

# Example .env file (create this in packages/mcp-server/.env)
"""
# packages/mcp-server/.env
BIP_CLIENT_ID="your_actual_client_id_from_bip"
BIP_CLIENT_SECRET="your_actual_client_secret_from_bip"
BIP_AUTHORIZATION_URL="https://actual_bip_auth_url.com/authorize"
BIP_TOKEN_URL="https://actual_bip_token_url.com/token"
BIP_USERINFO_URL="https://actual_bip_userinfo_url.com/userinfo"
BIP_REDIRECT_URI="http://localhost:8000/auth/callback" # Ensure this matches dev & prod setup
BIP_SCOPES="openid profile read:marks read:attendance"
SESSION_SECRET_KEY="a_very_strong_random_secret_key_here"
DEBUG=True
"""
