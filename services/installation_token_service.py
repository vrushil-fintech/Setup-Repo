import time

import httpx
import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import PRIVATE_KEY_PATH, GITHUB_CLIENT_ID
from app.crud.github_installation import get_github_installation_token, update_github_installation_token
from app.dependencies import logger

async def fetch_installation_token_installid(db_session: AsyncSession, installation_id: str = None, organization_id: str = None):
    if not organization_id and not installation_id:
        logger.error("organization_id or installation_id is required")
        return None
    if organization_id:
        token = await get_github_installation_token(db_session=db_session, organization_id=organization_id)
    else:
        token = await get_github_installation_token(db_session=db_session, installation_id=int(installation_id))

    if not token:
        token_dict = await regenerate_installation_token(db_session, installation_id)
        token = token_dict

    return token

async def regenerate_installation_token(db_session: AsyncSession, installation_id: str):
    try:
        # Load your GitHub App's private key
        with open(PRIVATE_KEY_PATH, "r") as f:
            private_key = f.read()
        # Create the JWT payload
        payload = {
            "iat": int(time.time()) - 60,  # Issued at time (To protect against clock drift, 60 seconds in the past)
            "exp": int(time.time()) + 480,  # Expiration (max 10 min)
            "iss": GITHUB_CLIENT_ID  # App ID
        }

        # Generate JWT
        jwt_token = jwt.encode(payload, private_key, algorithm="RS256")

    except Exception as e:
        logger.error(f"Error occurred while generating JWT: {e}")
        raise Exception("Failed to generate JWT")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            token_res = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {jwt_token}"},
            )
            token_data = token_res.json()
        except httpx.HTTPStatusError as http_err:
            logger.error(f"GitHub API responded with an error: {http_err}")
            raise Exception("Failed to fetch installation token")
        except Exception as e:
            logger.error(f"Unexpected error while fetching token: {e}")
            raise Exception("Unexpected error occurred")

    token_dict = {
        "access_token": token_data["token"],
        "expires_at": token_data["expires_at"]
    }
    try:
        await update_github_installation_token(db_session, int(installation_id), token_dict["access_token"], token_dict["expires_at"])
        await db_session.commit()
    except Exception as e:
        await db_session.rollback()
        logger.error(f"Database error occured while updating installation token: {e}", extra={"installation_id": installation_id})
        return None

    return token_dict