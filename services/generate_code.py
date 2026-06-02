from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import  RANDOM_CODE_MIN, RANDOM_CODE_MAX
import random

from app.config import OTP_EXPIRE_MINUTES
from app.crud.codes import create_code


async def generate_code(db_session: AsyncSession, email: str, code_type: str):
    code = str(random.randint(RANDOM_CODE_MIN, RANDOM_CODE_MAX))
    creation_time = datetime.now(timezone.utc)
    expiry_time = creation_time + timedelta(minutes=OTP_EXPIRE_MINUTES)
    await create_code(db_session, email, code, creation_time, expiry_time, "Valid")
    await db_session.commit()
    return code
