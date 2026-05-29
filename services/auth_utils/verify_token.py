from datetime import datetime
import jwt

from app.config import ALGORITHM, SECRET_KEY
from app.dependencies import logger


async def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        expire = datetime.fromtimestamp(payload.get("exp")).timestamp()
        current_time = datetime.now().timestamp()
        if email is None:
            error_message = "Email not present in access token."
            logger.error(error_message)
            raise Exception(error_message)
        if expire < current_time:
            error_message = "Access token expired."
            logger.error(error_message)
            raise Exception(error_message)
        
    except:
        error_message = "JWT Error."
        logger.error(error_message)
        raise Exception(error_message)
    return email