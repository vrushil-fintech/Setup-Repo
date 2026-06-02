from app.database import AsyncSessionFactory
from app.services.send_code import send_code
from app.services.generate_code import generate_code
from app.dependencies import logger
from sqlalchemy.exc import SQLAlchemyError


async def generate_and_send_code(email: str):
    async with AsyncSessionFactory() as db_session:
        try:
            code = await generate_code(db_session, email, "auth")
            await db_session.commit()
            await send_code(email, code, "auth")
        except SQLAlchemyError as sqle:
            await db_session.rollback()
            logger.error(f"Database error during code generation for {email}: {sqle}")
        except Exception as e:
            logger.error(
                f"Unexpected error during code generation or email send for {email}: {e}"
            )
