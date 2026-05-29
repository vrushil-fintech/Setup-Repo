import asyncio
import uuid
import httpx
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import (
    COOKIE_EXPIRE_SECONDS,
    COOKIE_DOMAIN,
    COOKIE_SAMESITE,
    FRONTEND_URL,
    GITHUB_APP_INSTALL_URL,
    GITHUB_AUTH_URL,
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    GITHUB_TOKEN_URL,
    GITHUB_USER_API_URL,
)
from app.crud.github_installation import get_github_organization_id_from_installation_id
from app.crud.github_user import create_github_user, get_github_id_from_user_id
from app.crud.user_organization import get_organization_id_for_user_id
from app.dependencies import logger
from app.database import get_db
from app.crud.users import get_user_by_id, insert_user, get_user
from app.crud.github_oauth_token import create_or_update_oauth_token
from app.services.github_auth_utils.active_installations import sync_installations
from app.services.oauth_token_service import get_github_access_token
from app.services.auth_utils.create_token import create_token

router = APIRouter()


@router.get("/auth/github")
def login_with_github():
    """Redirects the user to GitHub for authorization"""
    github_redirect_url = (
        f"{GITHUB_AUTH_URL}?client_id={GITHUB_CLIENT_ID}&scope=read:org%20user:email"
    )
    return RedirectResponse(url=github_redirect_url)


@router.get("/auth/github/callback")
async def github_callback(
    request: Request, response: Response, db_session: AsyncSession = Depends(get_db)
):
    """Handles GitHub OAuth callback and sets a secure cookie"""
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    async with httpx.AsyncClient(timeout=60.0) as client:
        token_res = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
            },
        )
        token_data = token_res.json()

    if "access_token" not in token_data:
        logger.error("Failed to retrieve Github Oauth access token")
        return RedirectResponse(url=f"{FRONTEND_URL}/dashboard")

    access_token = token_data["access_token"]
    access_expires_at = token_data["expires_in"]
    refresh_token = token_data["refresh_token"]
    refresh_expires_at = token_data["refresh_token_expires_in"]

    token_dict = {
        "access_token": access_token,
        "access_expires_at": access_expires_at,
        "refresh_token": refresh_token,
        "refresh_expires_at": refresh_expires_at,
    }

    # rate_limit_url = "https://api.github.com/rate_limit"
    # async with httpx.AsyncClient() as client:
    #     rate_res = await client.get(rate_limit_url, headers={"Authorization": f"Bearer {access_token}"})
    #     print(rate_res.json())  # Check if you've hit a limit

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            user_res = await client.get(
                GITHUB_USER_API_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
            user_res.raise_for_status()  # Raise an error if request failed
            user_data = user_res.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard")
        except httpx.RequestError as e:
            logger.error(f"Request error: {str(e)}")
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard")

    github_id = user_data["id"]
    github_username = user_data["login"]
    github_company = user_data["company"]

    # extract user email
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            user_res = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            user_res.raise_for_status()  # Raise an error if request failed
            user_data = user_res.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error: {e.response.status_code} - {e.response.text}",
                extra={"github_id": github_id},
            )
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard")
        except httpx.RequestError as e:
            logger.error(f"Request error: {str(e)}", extra={"github_id": github_id})
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard")

    github_email = user_data[0]["email"]

    user = await get_user(db_session, github_email)

    if not user:
        userid = str(uuid.uuid4())
        await insert_user(
            db_session,
            userid,
            github_username,
            github_email,
            "hashed_password",
            github_company,
        )
        user = await get_user(db_session, github_email)

    github_user_id = await get_github_id_from_user_id(db_session, user.userid)
    if not github_user_id:
        logger.info("Creating new github user...", extra={"github_id": github_id})
        await create_github_user(db_session, user.userid, github_id, github_username)
    
    await create_or_update_oauth_token(db_session, github_id, token_dict)
    await db_session.commit()

    user_org_data = await sync_installations(db_session, user.userid)
    organization_details = await get_organization_id_for_user_id(db_session, user.userid)
    logger.info("Installations and Orgs Synced...", extra={"github_id": github_id})

    if user_org_data or organization_details:
        session_access_token = await create_token({"sub": github_email})
        response = RedirectResponse(url=f"{FRONTEND_URL}/dashboard")
        response.set_cookie(
            key="access_token",
            value=session_access_token,
            httponly=True,  # Prevents frontend JavaScript from accessing it
            secure=True,  # Send only over HTTPS
            samesite=COOKIE_SAMESITE,  # Adjust depending on frontend/backend domains
            domain=COOKIE_DOMAIN,
            max_age=COOKIE_EXPIRE_SECONDS,
        )

        return response  # Redirects with a cookie

    # No installation exists for the user
    else:
        logger.info("no installation id found for user", extra={"user_id": user.userid})
        install_url = f"{GITHUB_APP_INSTALL_URL}?state={user.userid}"
        return RedirectResponse(url=install_url)


@router.get("/github/setup")
async def github_setup(request: Request, db_session: AsyncSession = Depends(get_db)):
    """Setup URL - redirects after installation GitHub App setup"""
    user_id = request.query_params.get("state", None)
    installation_id = request.query_params.get("installation_id", None)
    # Default URL
    redirect_url = f"{FRONTEND_URL}/dashboard"
    if not user_id:
        logger.warning(
            "No userid found in Setup URL", extra={"installation_id": installation_id}
        )

    if installation_id is None:
        redirect_url = f"{FRONTEND_URL}/dashboard?requested=true"

    else:
        try:
            retries = 0
            max_retries = 3
            delay = 5
            org_id = None
            while retries < max_retries:
                org_id = await get_github_organization_id_from_installation_id(
                    db_session, int(installation_id)
                )
                if org_id is not None:
                    break
                retries += 1
                await asyncio.sleep(delay)

            redirect_url = f"{FRONTEND_URL}/dashboard?organization_id={org_id}"

        except Exception as e:
            logger.error(
                f"Error while getting org id from installation id: {str(e)}",
                extra={"installation_id": installation_id},
            )
            redirect_url = f"{FRONTEND_URL}/dashboard"

    response = RedirectResponse(url=f"{redirect_url}")

    if user_id:
        user = await get_user_by_id(db_session, user_id)
        session_access_token = await create_token({"sub": user.email})
        response.set_cookie(
            key="access_token",
            value=session_access_token,
            httponly=True,
            secure=True,
            samesite=COOKIE_SAMESITE,
            domain=COOKIE_DOMAIN,
            max_age=COOKIE_EXPIRE_SECONDS,
        )

    return response


@router.get("/get_github_token/{user_id}/{github_id}")
async def refresh_github_token_handler(
    user_id: str, github_id: int, db_session: AsyncSession = Depends(get_db)
):
    response = await get_github_access_token(user_id, github_id, db_session)
    await db_session.commit()
    return response
