from fastapi import HTTPException, Request, Form
from app.dependencies import logger


async def get_user_id(request: Request, user_id: str = Form(None)) -> str:
    """
    Dependency to retrieve user_id from either:
    - request.state.user_id (if authenticated via API key)
    - Form data (if authenticated via cookie/token)
    
    Args:
        request: FastAPI Request object
        user_id: Optional user_id from form data
    
    Returns:
        user_id string
    
    Raises:
        HTTPException: If user_id cannot be determined
    """
    # Check if user_id is in request state (API key authentication)
    if hasattr(request.state, "user_id"):
        logger.debug("Retrieved user_id from request state (API key auth)", extra={"user_id": request.state.user_id})
        return request.state.user_id
    
    # Otherwise, expect it from form data (cookie/token authentication)
    if user_id is None:
        logger.warning("user_id not found in request state or form data")
        raise HTTPException(
            status_code=400,
            detail="user_id is required in form data for cookie/token authentication"
        )
    
    logger.debug("Retrieved user_id from form data (cookie/token auth)", extra={"user_id": user_id})
    return user_id


async def get_username(request: Request, username: str = Form(None)) -> str:
    """
    Dependency to retrieve username from either:
    - request.state.username (if authenticated via API key)
    - Form data (if authenticated via cookie/token)
    
    Args:
        request: FastAPI Request object
        username: Optional username from form data
    
    Returns:
        username string
    
    Raises:
        HTTPException: If username cannot be determined
    """
    # Check if username is in request state (API key authentication)
    if hasattr(request.state, "username"):
        logger.debug("Retrieved username from request state (API key auth)", extra={"username": request.state.username})
        return request.state.username
    
    # Otherwise, expect it from form data (cookie/token authentication)
    if username is None:
        logger.warning("username not found in request state or form data")
        raise HTTPException(
            status_code=400,
            detail="username is required in form data for cookie/token authentication"
        )
    
    logger.debug("Retrieved username from form data (cookie/token auth)", extra={"username": username})
    return username
