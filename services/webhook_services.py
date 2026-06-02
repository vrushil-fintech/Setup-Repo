import hmac
from fastapi import Request, HTTPException
import hashlib
from app.config import GITHUB_WEBHOOK_SECRET
from app.dependencies import logger


async def verify_signature(request: Request):
    """Verify GitHub webhook signature."""
    signature = request.headers.get("X-Hub-Signature-256")
    if not signature:
        logger.warning("Missing X-Hub-Signature-256 header.")
        raise HTTPException(status_code=401, detail="Missing signature")

    body = await request.body()
    expected_signature = (
        "sha256="
        + hmac.new(GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    )

    # Use `hmac.compare_digest` to prevent timing attacks
    if not hmac.compare_digest(signature, expected_signature):
        logger.warning("Invalid signature. Possible attack detected!")
        raise HTTPException(status_code=401, detail="Invalid signature")

    return
