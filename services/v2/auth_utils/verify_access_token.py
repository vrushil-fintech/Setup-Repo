import jwt

from app.config import ALGORITHM, SECRET_KEY
from app.dependencies import logger

async def verify_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # No need to manually check expiration; it's handled by jwt.decode()
        email = payload.get("sub")
        if email is None:
            logger.error("Email not present in access token.")
            raise Exception("Email not present in access token.")
        
    except jwt.ExpiredSignatureErroratureError:
        logger.warning("Access token expired.")
        raise Exception("Token has expired")
    except Exception as e:
        logger.error("JWT Error: " + str(e))
        raise Exception("JWT Error")

    return email