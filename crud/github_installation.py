from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.dependencies import logger

async def create_github_installation(db_session: AsyncSession, organization_id: str, installation_id: int, access_token: str, expires_at: str):
    access_expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    is_active = True
    sql_query = text(
        """
INSERT INTO codesherlock.github_installation (organization_id, installation_id, access_token, access_expires_at, is_active)
VALUES (:organization_id, :installation_id, :access_token, :access_expires_at, :is_active);
"""
    )
    try:
        await db_session.execute(sql_query, {
            "organization_id": organization_id,
            "installation_id": installation_id,
            "access_token": access_token,
            "access_expires_at": access_expires_at,
            "is_active": is_active
        })
        logger.info(f"Successfully inserted github installation details", extra={"organization_id": organization_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"organization_id": organization_id})
        raise HTTPException(status_code=503, detail="We're having trouble processing your request. Please try again later.")

    return

async def get_github_installation(db_session: AsyncSession, organization_id: str):
    sql_query = text(
        """
SELECT installation_id FROM codesherlock.github_installation
WHERE organization_id = :organization_id AND is_active = TRUE
ORDER BY created_at DESC
LIMIT 1;
"""
    )
    try:
        db_result = await db_session.execute(sql_query, {
            "organization_id": organization_id,
        })
        result = db_result.fetchone()
        logger.info(f"Successfully retrieved github installation id", extra={"organization_id": organization_id})
        if result:
            return result[0]
        return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"organization_id": organization_id})
        raise HTTPException(status_code=503, detail="We're having trouble processing your request. Please try again later.")

async def get_github_organization_id_from_installation_id(db_session: AsyncSession, installation_id: int):
    sql_query = text(
        """
SELECT organization_id FROM codesherlock.github_installation
WHERE installation_id = :installation_id AND is_active = TRUE
ORDER BY created_at DESC
LIMIT 1;
"""
    )
    try:
        db_result = await db_session.execute(sql_query, {
            "installation_id": installation_id,
        })
        result = db_result.fetchone()
        logger.info(f"Successfully retrieved github organization id", extra={"installation_id": installation_id})
        if result:
            return result[0]
        return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"installation_id": installation_id})
        raise HTTPException(status_code=503, detail="We're having trouble processing your request. Please try again later.")

async def get_github_installation_token(db_session: AsyncSession, installation_id: int = None, organization_id: str = None):
    if not organization_id and not installation_id:
        raise HTTPException(status_code=400, detail="organization_id or installation_id is required")
    
    if not installation_id:
        installation_id = await get_github_installation(db_session, organization_id)

    sql_query = text(
        """
SELECT access_token, access_expires_at
FROM codesherlock.github_installation
WHERE installation_id = :installation_id 
  AND is_active = TRUE 
  AND access_expires_at > NOW() + INTERVAL '5 minutes'
ORDER BY created_at DESC
LIMIT 1;
"""
    )
    try:
        db_result = await db_session.execute(sql_query, {
            "installation_id": installation_id,
        })
        result = db_result.fetchone()
        logger.info(f"Successfully retrieved github installation token", extra={"installation_id": installation_id})
        if result:
            return {
                "access_token": result[0],
                "access_expires_at": result[1]
            }
        else:
            return None
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"installation_id": installation_id})
        raise HTTPException(status_code=503, detail="We're having trouble processing your request. Please try again later.")

async def update_github_installation_token(db_session: AsyncSession, installation_id: int, access_token: str, expires_at: str):
    access_expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    sql_query = text(
        """
UPDATE codesherlock.github_installation
SET access_token = :access_token, access_expires_at = :access_expires_at
WHERE installation_id = :installation_id;
"""
    )
    try:
        await db_session.execute(sql_query, {
            "installation_id": installation_id,
            "access_token": access_token,
            "access_expires_at": access_expires_at,
        })
        logger.info(f"Successfully updated github installation token details", extra={"installation_id": installation_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"installation_id": installation_id})
        raise HTTPException(status_code=503, detail="We're having trouble processing your request. Please try again later.")

    return

async def delete_github_installation(db_session: AsyncSession, installation_id: int):
    sql_query = text(
        """
UPDATE codesherlock.github_installation
SET is_active = FALSE
WHERE installation_id = :installation_id;
"""
    )
    try:
        await db_session.execute(sql_query, {"installation_id": installation_id})
        logger.info(f"Successfully revoked installation", extra={"installation_id": installation_id})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"installation_id": installation_id})
        raise HTTPException(status_code=503, detail="We're having trouble processing your request. Please try again later.")

    return
