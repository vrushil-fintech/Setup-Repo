from datetime import datetime, timedelta, timezone
from typing import Dict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.dependencies import logger

async def create_or_update_oauth_token(db_session: AsyncSession, github_id: int, token_dict: Dict):
    access_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=token_dict["access_expires_at"]
    )
    refresh_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=token_dict["refresh_expires_at"]
    )
    sql_query = text(
        """
INSERT INTO codesherlock.github_oauth_token (github_id, access_token, access_expires_at, refresh_token, refresh_expires_at)
VALUES (:github_id, :access_token, :access_expires_at, :refresh_token, :refresh_expires_at)
ON CONFLICT (github_id) 
DO UPDATE SET 
    access_token = EXCLUDED.access_token,
    access_expires_at = EXCLUDED.access_expires_at,
    refresh_token = EXCLUDED.refresh_token,
    refresh_expires_at = EXCLUDED.refresh_expires_at;
    """
    )
    try:
        await db_session.execute(
            sql_query,
            {
                "github_id": github_id,
                "access_token": token_dict["access_token"],
                "access_expires_at": access_expires_at,
                "refresh_token": token_dict["refresh_token"],
                "refresh_expires_at": refresh_expires_at,
            },
        )
        logger.info(f"Github Oauth token created or updated", extra={"github_id": github_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred {e}", extra={"github_id": github_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )
    
    return

async def get_oauth_token(db_session: AsyncSession, github_id: int):
    sql_query = text(
        """
SELECT access_token, access_expires_at, refresh_token, refresh_expires_at FROM codesherlock.github_oauth_token
WHERE github_id = :github_id;
    """
    )
    try:
        db_result = await db_session.execute(sql_query, {"github_id": github_id})
        result = db_result.fetchone()
        logger.info(f"Github Oauth token retrieved", extra={"github_id": github_id})
        if result:
            return {
                "access_token": result[0],
                "refresh_token": result[1],
                "access_expires_at": result[2],
                "refresh_expires_at": result[3],
            }
        return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"github_id": github_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble verifying your session. Please try again later.",
        )
