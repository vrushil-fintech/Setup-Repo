from datetime import datetime, timezone, timedelta
import jwt

from app.config import ALGORITHM, SECRET_KEY, COOKIE_EXPIRE_SECONDS


async def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(seconds=COOKIE_EXPIRE_SECONDS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt