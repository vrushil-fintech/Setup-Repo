from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import logger
import secrets
import string


def generate_api_key_secret(length: int = 32) -> str:
    """
    Generate a random secret string for API key.
    
    Args:
        length: Length of the secret string (default: 32)
    
    Returns:
        Random string containing numbers and upper/lower case letters
    """
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def create_mcp_api_key(
    db_session: AsyncSession,
    user_id: str,
    expires_at: str = None
):
    """
    Create a new MCP API key for a user.
    
    Args:
        db_session: Database session
        user_id: UUID of the user
        expires_at: Optional expiration timestamp
    
    Returns:
        The generated API key in format cs_mcp_<secret>
    """
    # Generate the secret part
    secret = generate_api_key_secret(32)
    api_key = f"cs_mcp_{secret}"
    
    sql_query = text("""
        INSERT INTO codesherlock.mcp_api_key (user_id, api_key, expires_at)
        VALUES (:user_id, :api_key, :expires_at)
        RETURNING id, created_at
    """)
    
    try:
        result = await db_session.execute(sql_query, {
            "user_id": user_id,
            "api_key": api_key,
            "expires_at": expires_at
        })
        row = result.fetchone()
        
        if row is None:
            logger.error("Failed to create MCP API key", extra={"user_id": user_id})
            raise HTTPException(
                status_code=503,
                detail="We're having trouble creating your API key. Please try again later."
            )
        
        logger.info("MCP API key created", extra={"user_id": user_id, "api_key_id": row[0]})
        
        return {
            "api_key": api_key,
            "created_at": row[1],
            "expires_at": expires_at
        }
        
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred while creating MCP API key: {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble creating your API key. Please try again later."
        )


async def get_mcp_api_key(db_session: AsyncSession, user_id: str):
    """
    Get the MCP API key for a user.
    
    Args:
        db_session: Database session
        user_id: UUID of the user
    
    Returns:
        The API key for the user (excluding revoked keys), or None if no key exists
    """
    sql_query = text("""
        SELECT 
            api_key,
            created_at,
            expires_at
        FROM codesherlock.mcp_api_key
        WHERE user_id = :user_id AND revoked = FALSE
        ORDER BY created_at DESC
        LIMIT 1
    """)
    
    try:
        result = await db_session.execute(sql_query, {"user_id": user_id})
        row = result.fetchone()
        
        if row is None:
            logger.info("No MCP API key found", extra={"user_id": user_id})
            return None
        
        api_key_data = {
            "api_key": row[0],
            "created_at": row[1],
            "expires_at": row[2]
        }
        
        logger.info("Retrieved MCP API key", extra={"user_id": user_id})
        return api_key_data
        
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred while fetching MCP API key: {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble fetching your API key. Please try again later."
        )

async def get_user_id_from_mcp_api_key(db_session: AsyncSession, api_key: str):
    sql_query = text("""
        SELECT user_id
        FROM codesherlock.mcp_api_key
        WHERE api_key = :api_key AND revoked = FALSE
        LIMIT 1
    """)
    
    try:
        result = await db_session.execute(sql_query, {"api_key": api_key})
        row = result.fetchone()
        
        if row is None:
            logger.warning("Invalid or revoked MCP API key provided", extra={"api_key": api_key})
            return None
        
        user_id = str(row[0])
        logger.info("Retrieved MCP API key", extra={"user_id": user_id})
        return user_id
        
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred while fetching MCP API key: {e}", extra={"api_key": api_key})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble fetching your API key. Please try again later."
        )


async def revoke_mcp_api_keys(db_session: AsyncSession, user_id: str):
    """
    Revoke all active MCP API keys for a user.
    
    Args:
        db_session: Database session
        user_id: UUID of the user
    
    Returns:
        Number of keys revoked
    """
    sql_query = text("""
        UPDATE codesherlock.mcp_api_key
        SET revoked = TRUE
        WHERE user_id = :user_id AND revoked = FALSE
    """)
    
    try:
        result = await db_session.execute(sql_query, {"user_id": user_id})
        rows_affected = result.rowcount
        
        logger.info(f"Revoked {rows_affected} MCP API key(s)", extra={"user_id": user_id})
        return
        
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occurred while revoking MCP API keys: {e}", extra={"user_id": user_id})
        raise HTTPException(
            status_code=503,
            detail="We're having trouble revoking your API keys. Please try again later."
        )
