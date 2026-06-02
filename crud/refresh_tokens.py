from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.dependencies import logger


async def create_refresh_token(
    db_session: AsyncSession,
    refresh_token: str,
    userid: str,
    expires_at: str,
    ip_address: str = None,
    ):
    expires_at = datetime.fromisoformat(expires_at)
    sql_query = text("""
INSERT INTO codesherlock.refresh_tokens(token, userid, expires_at, ip_address)
VALUES (:token, :userid, :expires_at, :ip_address);
    """)
    try:
        await db_session.execute(sql_query, {"token": refresh_token, "userid": userid, "expires_at": expires_at, "ip_address": ip_address})
        logger.info(f"Successfully created and inserted refresh token", extra={"userid": userid})
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured: {e}", extra={"userid": userid})
        raise HTTPException(status_code=503, detail="We're having trouble processing your request. Please try again later.")

async def get_refresh_token(db_session: AsyncSession, refresh_token: str, userid: str):
    sql_query = text("""
SELECT userid FROM codesherlock.refresh_tokens
WHERE token = :token AND userid = :userid AND revoked = FALSE AND expires_at > NOW()
LIMIT 1;
    """)
    try:
        db_result = await db_session.execute(sql_query, {"token": refresh_token, "userid": userid})
        result = db_result.fetchone()
        logger.info(f"Refresh token retrieved", extra={"userid": userid})
        return result
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured {e}", extra={"userid": userid})
        raise HTTPException(status_code=503, detail="We're having trouble verifying your session. Please try again later.")

async def revoke_refresh_token(db_session: AsyncSession, userid: str, refresh_token: str):
    sql_query = text("""
UPDATE codesherlock.refresh_tokens
SET revoked = TRUE
WHERE userid = :userid AND token = :token
RETURNING token;
    """)
    try:
        db_result = await db_session.execute(sql_query, {"token": refresh_token, "userid": userid})
        result = db_result.fetchone()

        if result is None:
            logger.warning(f"No matching refresh token found to revoke", extra={"userid": userid})
            raise HTTPException(status_code=404, detail="We're having trouble logging you out. Please try again.")
        
        logger.info(f"Refresh token revoked", extra={"userid": userid})

    except HTTPException as e:
        # Re-raise the HTTPException (404) without catching it here
        raise e
    
    except Exception as e:
        # Handle other exceptions (e.g., database errors)
        await db_session.rollback()
        logger.error(f"Database error occurred {e}", extra={"userid": userid})
        raise HTTPException(status_code=503, detail="We're having trouble verifying your session. Please try again later.")