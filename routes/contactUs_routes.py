from fastapi import APIRouter, Form, HTTPException

from app.dependencies import logger
from ..services.send_contactUs import send_contact_us
from ..services.validate_email import is_valid_email

router = APIRouter()

@router.post("/contactus")
async def contactus_handler(name: str = Form(), email: str = Form(), message: str = Form()):
    if not await is_valid_email(email):
        logger.warning("Invalid email provided.", extra={"email": email})
        raise HTTPException(status_code=403, detail="Invalid email.")
    await send_contact_us(name,email,message)
    logger.info("Contaact us info sent.", extra={"email": email})
    return {"status_code": 200, "message": "Contact us info received", "email": email, "name": name}