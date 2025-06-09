# packages/mcp-server/main.py
import sys
import os

# --- Start: Keep this sys.path modification for now during debugging ---
# This assumes main.py is in packages/mcp-server/
# We want to add the 'packages' directory's parent to sys.path,
# which is the project root.
PACKAGE_PARENT = '..'
SCRIPT_DIR = os.path.dirname(os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(__file__))))
PROJECT_ROOT = os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT, PACKAGE_PARENT))
if PROJECT_ROOT not in sys.path:
    print(f"App Factory: Temporarily adding to sys.path: {PROJECT_ROOT}")
    sys.path.insert(0, PROJECT_ROOT)
# --- End: sys.path modification ---


from fastapi import FastAPI, Request # Keep Request if used in root endpoint
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware

# Use absolute imports now that we've tried to manage sys.path
# These must be correct based on your actual file structure under project_root/packages/mcp_server/
try:
    from packages.mcp_server.config import settings
    from packages.mcp_server.routes import auth_routes, user_routes, bip_routes, assistant_routes
except ImportError as e:
    print(f"Error during imports in main.py: {e}")
    print(f"Current sys.path: {sys.path}")
    raise


def create_app() -> FastAPI:
    print("create_app() called.")
    current_app = FastAPI(
        title=settings.APP_NAME,
        debug=settings.DEBUG,
        root_path=settings.ROOT_PATH
    )

    # Add CORS middleware
    current_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Allows all origins
        allow_credentials=True,
        allow_methods=["*"],  # Allows all methods
        allow_headers=["*"],  # Allows all headers
    )

    current_app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET_KEY,
    )

    @current_app.get("/")
    async def read_root():
        return {"message": f"Welcome to {settings.APP_NAME} from App Factory"}

    current_app.include_router(auth_routes.router, prefix="/auth", tags=["Authentication"])
    current_app.include_router(user_routes.router, prefix="/users", tags=["User"])
    current_app.include_router(bip_routes.router, prefix="/bip", tags=["BIP Integration"])
    current_app.include_router(assistant_routes.router, prefix="/assistant", tags=["AI Assistant"])
    
    print("App configured in create_app().")
    return current_app

# If you still want to be able to run this file directly for some reason (not with uvicorn app string)
# you might have an `app = create_app()` here, but uvicorn will use the factory.

app = create_app()
