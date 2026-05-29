from app.models import User
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Form, HTTPException, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.codes import get_code, update_code
from app.crud.users import insert_user, get_user, get_user_by_id
from app.services.v2.auth_utils.generate_access_token import generate_access_token
from app.services.v2.auth_utils.generate_refresh_token import generate_refresh_token
from app.services.v2.auth_utils.verify_refresh_token import verify_refresh_token
from app.crud.refresh_tokens import revoke_refresh_token
from app.services.validate_email import is_valid_email
from app.dependencies import logger
from app.database import get_db
from app.services.eventgrid_service import publish_event
from app.services.otp_util import generate_and_send_code


router = APIRouter()


@router.post("/auth/login")
async def login_handler(
    background_tasks: BackgroundTasks,
    email: str = Form(),
    db_session: AsyncSession = Depends(get_db),
):
    email = email.lower()
    if not await is_valid_email(email):
        logger.warning("Invalid email provided.", extra={"email": email})
        raise HTTPException(status_code=403, detail="Invalid email.")

    user = await get_user(db_session, email)
    if user is None:
        logger.warning("Login attempt with non-existing email", extra={"email": email})
        raise HTTPException(
            status_code=400, detail="Email does not exist. Please sign up."
        )

    background_tasks.add_task(generate_and_send_code, email)
    logger.info("Authentication code sent", extra={"email": email})

    return {"status_code": 200, "message": "Code sent", "email": email}


@router.post("/auth/login/validate")
async def login_validate_handler(
    request: Request,
    email: str = Form(),
    code: str = Form(),
    db_session: AsyncSession = Depends(get_db),
):
    email = email.lower()
    if not await is_valid_email(email):
        logger.warning("Invalid email provided.", extra={"email": email})
        raise HTTPException(status_code=403, detail="Invalid email.")

    if len(code) != 6:
        logger.warning("Invalid code provided.", extra={"email": email, "code": code})
        raise HTTPException(status_code=403, detail="Invalid code.")

    result = await get_code(db_session, email, code)
    if result is None:
        logger.warning("Invalid code provided.", extra={"email": email})
        raise HTTPException(status_code=403, detail="Invalid code.")

    await update_code(db_session, email, code, "Used")

    logger.info("User logged in", extra={"email": email})
    user = await get_user(db_session, email)

    # Generate access token and get expiration time
    access_token, access_token_expiration = await generate_access_token(
        {"sub": user.userid}
    )
    ip_address = request.client.host
    refresh_token = await generate_refresh_token(db_session, user.userid, ip_address)
    await db_session.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_token_expiration": access_token_expiration.isoformat(),
        "user": user,
    }


@router.post("/auth/signup")
async def signup_handler(
    background_tasks: BackgroundTasks,
    email: str = Form(),
    name: str = Form(),
    organization: str = Form(default=None),
    db_session: AsyncSession = Depends(get_db),
):
    email = email.lower()
    if not await is_valid_email(email):
        logger.warning("Invalid email provided.", extra={"email": email})
        raise HTTPException(status_code=403, detail="Invalid email.")

    # Check if the email already exists
    user = await get_user(db_session, email)
    if user:
        logger.warning("Signup attempt with existing email.", extra={"email": email})
        raise HTTPException(status_code=409, detail="Email already exists.")

    # Generate verification code
    background_tasks.add_task(generate_and_send_code, email)
    logger.info("Verification code sent.", extra={"email": email})

    return {
        "status_code": 200,
        "message": "Code sent",
        "email": email,
        "name": name,
        "organization": organization,
    }


@router.post("/auth/signup/validate")
async def signup_validate_handler(
    request: Request,
    email: str = Form(),
    code: str = Form(),
    name: str = Form(),
    organization: str = Form(default=None),
    db_session: AsyncSession = Depends(get_db),
):
    email = email.lower()
    if not await is_valid_email(email):
        logger.warning("Invalid email provided.", extra={"email": email})
        raise HTTPException(status_code=403, detail="Invalid email.")

    if len(code) != 4:
        logger.warning("Invalid code provided.", extra={"email": email, "code": code})
        raise HTTPException(status_code=403, detail="Invalid code.")

    result = await get_code(db_session, email, code)
    if result is None:
        logger.warning("Invalid code provided.", extra={"email": email})
        raise HTTPException(status_code=403, detail="Invalid code.")

    # Mark the code as used
    await update_code(db_session, email, code, "Used")

    # Create a new user
    user_id = str(uuid.uuid4())
    hashed_password = "hashed_password"  # Temporary placeholder for password
    await insert_user(db_session, user_id, name, email, hashed_password, organization)

    # Commit the database transaction
    await db_session.commit()

    # Generate access and refresh tokens
    access_token, access_token_expiration = await generate_access_token(
        {"sub": user_id}
    )
    ip_address = request.client.host
    refresh_token = await generate_refresh_token(db_session, user_id, ip_address)
    await db_session.commit()

    # Log the signup event
    await publish_event(
        event_type="User.SignUp",
        subject=f"signup/{email}",
        data={"email": email, "name": name, "organization": organization},
    )
    logger.info("User created and logged in", extra={"email": email})

    # Fetch the newly created user
    user = await get_user(db_session, email)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_token_expiration": access_token_expiration.isoformat(),
        "user": user,
    }


@router.post("/auth/refresh")
async def refresh_handler(
    refresh_token: str = Form(),
    email: str = Form(),
    db_session: AsyncSession = Depends(get_db),
):
    email = email.lower()
    user = await get_user(db_session, email)
    result = await verify_refresh_token(db_session, refresh_token, user.userid)
    if result:
        access_token, access_token_expiration = await generate_access_token(
            {"sub": user.userid}
        )
        logger.info("New access token generated", extra={"email": email})
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_token_expiration": access_token_expiration.isoformat(),
        }

    logger.warning("Refresh token expired or invalid.", extra={"email": email})
    raise HTTPException(status_code=401, detail="Refresh token expired or invalid.")


@router.post("/auth/logout")
async def logout_handler(
    user_id: str = Form(),
    refresh_token: str = Form(),
    db_session: AsyncSession = Depends(get_db),
):

    # Revoke all refresh tokens associated with the user_id
    await revoke_refresh_token(db_session, user_id, refresh_token)
    await db_session.commit()

    # Log the logout action
    logger.info(
        "User logged out", extra={"user_id": user_id, "refresh_token": refresh_token}
    )

    return {"message": "Logged out successfully"}

@router.post("/secure_route")
async def secure_route_handler(request: Request, db_session: AsyncSession = Depends(get_db)) -> User:
    """
    Secure route that requires API key authentication.
    Uses user_id from request.state (set by middleware during API key verification).
    """
    # Check if user_id is in request.state (API key authentication)
    user_id = getattr(request.state, "user_id", None)
    
    if not user_id:
        logger.error("User ID not found in request state - API key authentication required")
        raise HTTPException(
            status_code=401, 
            detail="Authentication required. Please provide a valid API key."
        )
    
    # Fetch user by ID
    user = await get_user_by_id(db_session, user_id)
    if user is None:
        logger.error("User not found for authenticated user_id", extra={"user_id": user_id})
        raise HTTPException(status_code=404, detail="User not found.")
    
    logger.info("User retrieved for secure route via API key", extra={"user_id": user.userid})
    return user
