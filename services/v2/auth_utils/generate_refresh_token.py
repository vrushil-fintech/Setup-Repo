from datetime import datetime, timezone, timedelta
import random
import string
from app.crud.refresh_tokens import create_refresh_token
from app.config import REFRESH_TOKEN_EXPIRE_DAYS

async def generate_refresh_token(db_session, userid: str, ip_address: str = None, length=32):
    chars = string.ascii_lowercase + string.ascii_uppercase + string.digits
    refresh_token = ''.join(random.SystemRandom().choices(chars, k=length))
    # expires_at = datetime.now(timezone.utc) + timedelta(days=15)
    expires_at = str(datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))

    await create_refresh_token(db_session, refresh_token, userid, expires_at, ip_address)
    return refresh_token
