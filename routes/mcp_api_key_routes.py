from app.middleware.cookie_verification import cookie_verification
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.dependencies import logger
from app.database import get_db
from app.crud.mcp_api_key import create_mcp_api_key, get_mcp_api_key, revoke_mcp_api_keys

router = APIRouter()


class ApiKeyResponse(BaseModel):
    api_key: str
    created_at: datetime
    expires_at: Optional[datetime]


@router.post("/mcp-api-key", response_model=ApiKeyResponse)
async def create_api_key_handler(
    user_id: str = Form(),
    db_session: AsyncSession = Depends(get_db),
    email: str = Depends(cookie_verification),
):
    """
    Get or create an MCP API key for a user.
    
    If the user already has an API key, returns the existing one.
    Otherwise, creates a new API key in the format: cs_mcp_<secret>
    where <secret> is a 32-character random string.
    """
    try:
        # First check if user already has an API key
        existing_key = await get_mcp_api_key(db_session, user_id)
        
        if existing_key is not None:
            logger.info("Returning existing MCP API key", extra={"user_id": user_id})
            return ApiKeyResponse(
                api_key=existing_key["api_key"],
                created_at=existing_key["created_at"],
                expires_at=existing_key["expires_at"]
            )
        
        # No existing key, create a new one
        api_key_data = await create_mcp_api_key(
            db_session,
            user_id,
            None
        )
        await db_session.commit()
        
        return ApiKeyResponse(
            api_key=api_key_data["api_key"],
            created_at=api_key_data["created_at"],
            expires_at=api_key_data["expires_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error creating MCP API key: {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble creating your API key. Please try again later."
        )


@router.get("/mcp-api-key/{user_id}", response_model=ApiKeyResponse)
async def get_api_key_handler(
    user_id: str,
    db_session: AsyncSession = Depends(get_db),
    email: str = Depends(cookie_verification),
):
    """
    Get the MCP API key for a user.
    
    Returns the active (non-revoked) API key for the specified user.
    """
    try:
        api_key = await get_mcp_api_key(db_session, user_id)
        
        if api_key is None:
            logger.warning("No MCP API key found for user", extra={"user_id": user_id})
            raise HTTPException(
                status_code=404,
                detail="No API key found for this user."
            )
        
        logger.info("Retrieved MCP API key", extra={"user_id": user_id})
        
        return ApiKeyResponse(
            api_key=api_key["api_key"],
            created_at=api_key["created_at"],
            expires_at=api_key["expires_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving MCP API key: {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble fetching your API key. Please try again later."
        )


@router.post("/mcp-api-key/regenerate", response_model=ApiKeyResponse)
async def regenerate_api_key_handler(
    user_id: str = Form(),
    db_session: AsyncSession = Depends(get_db),
    email: str = Depends(cookie_verification),
):
    """
    Regenerate the MCP API key for a user.
    
    Revokes the existing API key (if present) and creates a new one.
    The new API key will be in the format: cs_mcp_<secret>
    where <secret> is a 32-character random string.
    """
    try:
        # Revoke existing API keys
        await revoke_mcp_api_keys(db_session, user_id)
        
        # Create a new API key
        api_key_data = await create_mcp_api_key(
            db_session,
            user_id,
            None
        )
        await db_session.commit()
        
        logger.info("MCP API key regenerated successfully", extra={"user_id": user_id})
        
        return ApiKeyResponse(
            api_key=api_key_data["api_key"],
            created_at=api_key_data["created_at"],
            expires_at=api_key_data["expires_at"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Error regenerating MCP API key: {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble regenerating your API key. Please try again later."
        )
