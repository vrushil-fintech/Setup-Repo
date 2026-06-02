from app.crud.mcp_api_key import get_user_id_from_mcp_api_key
from fastapi import HTTPException, Request

from ..services.auth_utils.verify_token import verify_token
from ..services.v2.auth_utils.verify_access_token import verify_access_token
from app.dependencies import logger
from app.database import AsyncSessionFactory
from app.crud.users import get_user_by_id

timed_out_exception = HTTPException(
            status_code=401,
            detail="Session timed out. Please login again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def cookie_verification(request: Request):
    token = request.cookies.get("access_token")
    if token is None:
        logger.warning("Access token not found in cookies")
        raise timed_out_exception

    try:
        email = await verify_token(token)
    except:
        logger.warning("Access token verification failed")
        raise timed_out_exception

    return email

async def token_verification(request: Request):
    auth_header = request.headers.get("Authorization")
    if auth_header is None:
        logger.warning("Access token not found in headers")
        raise timed_out_exception
    
    access_token = request.headers.get("Authorization")[7:].strip()

    try:
        email = await verify_access_token(access_token)
        logger.info("Access token verified")
    except:
        logger.warning("Access token verification failed")
        raise timed_out_exception

    return email

async def cookie_or_token_verification(request: Request):
    token = request.cookies.get("access_token")
    if token is not None:
        return await cookie_verification(request)
    else:
        return await token_verification(request)


async def api_key_verification(request: Request):
    """
    Verify MCP API key from X-CS-MCP-API-Key header.
    Returns tuple (user_id, username) if valid, raises HTTPException otherwise.
    """
    
    api_key = request.headers.get("X-CS-MCP-API-Key")
    if api_key is None:
        logger.warning("MCP API key not found in headers")
        raise HTTPException(
            status_code=401,
            detail=(
                "API key missing. Authentication is required.\n\n"
                "To get an API key:\n"
                "1. Visit https://codesherlock.ai and sign up or log in.\n"
                "2. Navigate to the MCP API Keys page: https://codesherlock.ai/mcp-api-key.\n"
                "3. Generate or copy your API key.\n\n"
                "Usage instructions:\n"
                "See the MCP integration guide at https://codesherlock.ai/docs/mcp.\n\n"
                "If you followed these steps and still face issues, contact support at support@codesherlock.ai."
            ),
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    async with AsyncSessionFactory() as db_session:
        user_id = await get_user_id_from_mcp_api_key(db_session, api_key)
        
        if user_id is None:
            logger.warning("Invalid or revoked MCP API key provided")
            raise HTTPException(
                status_code=401,
                detail=(
                    "Invalid or revoked API key.\n\n"
                    "Please verify that you are using an active API key from your account.\n\n"
                    "To check or generate a key:\n"
                    "1. Visit https://test.codesherlock.ai and sign up or log in.\n"
                    "2. Go to the MCP API Keys page: https://test.codesherlock.ai/mcp/api/key\n"
                    "3. Generate a new key if your existing one is revoked or expired.\n\n"
                    "Usage instructions:\n"
                    "See the MCP integration guide at https://test.codesherlock.ai/mcp/setup/guide.\n\n"
                    "If the problem persists after following these steps, contact support at support@codesherlock.ai."
                ),
                headers={"WWW-Authenticate": "ApiKey"},
            )
        
        # Fetch user object to get username
        user = await get_user_by_id(db_session, user_id)
        
        if user is None:
            logger.error("User not found for valid API key", extra={"user_id": user_id})
            raise HTTPException(
                status_code=401,
                detail="User account not found.",
            )
    
    logger.info("MCP API key verified successfully", extra={"user_id": user_id, "username": user.name})
    return (user_id, user.name)


async def cookie_token_or_api_key_verification(request: Request):
    """
    Try cookie/token verification first, fall back to API key if those fail.
    Returns tuple: (auth_method, identifier, username)
    - auth_method: "cookie_token" or "api_key"
    - identifier: email (for cookie/token) or user_id (for API key)
    - username: username (for API key) or None (for cookie/token)
    """
    token = request.cookies.get("access_token")
    auth_header = request.headers.get("Authorization")
    
    # If cookie or auth header exists, try those first
    if token is not None or auth_header is not None:
        email = await cookie_or_token_verification(request)
        return ("cookie_token", email, None)
    else:
        # No cookie or token, try API key
        user_id, username = await api_key_verification(request)
        return ("api_key", user_id, username)
