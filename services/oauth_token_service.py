from datetime import datetime, timedelta, timezone
from typing import Dict
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET, GITHUB_TOKEN_URL
from app.dependencies import logger
from app.crud.github_oauth_token import create_or_update_oauth_token, get_oauth_token

async def refresh_github_token(token_dict: Dict, github_id: str, user_id: str, db_session: AsyncSession):
    """Refreshes a GitHub access token using the refresh token."""
    if not token_dict["refresh_token"]:
        logger.error("No OAuth refresh token found associated with user", extra={"user_id": user_id})
        return None  # Can't refresh without a refresh token

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            token_res = await client.post(
                GITHUB_TOKEN_URL,
                headers={"Accept": "application/json"},
                data={
                    "client_id": GITHUB_CLIENT_ID,
                    "client_secret": GITHUB_CLIENT_SECRET,
                    "refresh_token": token_dict["refresh_token"],
                    "grant_type": "refresh_token",
                },
            )
            token_res.raise_for_status()
            token_data = token_res.json()
    except httpx.HTTPStatusError as http_err:
        logger.error(f"GitHub API responded with an error while refreshing token: {http_err}", extra={"user_id": user_id})
        return None

    except Exception as e:
        logger.error(f"Error: {e}", extra={"user_id": user_id})
        return None

    new_token_dict = {}
    if token_data and "access_token" in token_data:
        new_token_dict["access_token"] = token_data["access_token"]
        new_token_dict["refresh_token"] = token_data.get("refresh_token", token_dict["refresh_token"])
        new_token_dict["access_expires_at"] = token_data.get("expires_in", 28800)
        new_token_dict["refresh_expires_at"] = token_data.get("refresh_token_expires_in", 15897600)
        await create_or_update_oauth_token(db_session=db_session, token_dict=new_token_dict, github_id=github_id)
        return new_token_dict
    else:
        logger.error("No access token found in GitHub API response", extra={"user_id": user_id})
        return None

async def get_github_access_token(user_id: str, github_id: int, db_session: AsyncSession):
    """Returns a valid GitHub access token, refreshing it if needed."""
    token_dict = await get_oauth_token(db_session=db_session, github_id=github_id)
    
    if not token_dict:
        logger.error("No OAuth token found associated with user", extra={"user_id": user_id})
        return None

    # Refresh if expired or close to expiration (buffer: 2 mins)
    if token_dict["access_expires_at"] < datetime.now(timezone.utc) + timedelta(minutes=5):
        logger.info("Refreshing OAuth token", extra={"user_id": user_id})
        return await refresh_github_token(token_dict, github_id, user_id, db_session)
    
    return token_dict
