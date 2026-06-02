from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.cookie_verification import cookie_token_or_api_key_verification
from app.dependencies import logger

class AuthenticationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
           
        if not request.url.path.startswith("/v2") or "/v2/auth" in request.url.path or "/v2/plans" in request.url.path:
            return await call_next(request)

        try:
            # Try cookie/token verification first, then API key
            auth_method, identifier, username = await cookie_token_or_api_key_verification(request)
            
            # Only store user_id and username in request state for API key authentication
            if auth_method == "api_key":
                request.state.user_id = identifier
                request.state.username = username
                logger.debug(f"Stored user_id and username in request state", extra={"user_id": identifier, "username": username})
            
            return await call_next(request)
        except HTTPException as e:
            # Handle HTTPException and re-raise it because Starlette's Middleware class doesn't raise it directly
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )

        except Exception as e:
            # Handle any unexpected errors
            logger.error("Authentication middleware error: %s", str(e))
            return JSONResponse(
                status_code=503,
                content={"detail": "We're having trouble authenticating you. Please try again later."}
            )