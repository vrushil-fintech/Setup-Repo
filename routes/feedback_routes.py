from bson import ObjectId
from sqlalchemy.ext.asyncio import AsyncSession
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Form, HTTPException, Request, Depends

from app.middleware.cookie_verification import cookie_verification
from app.database import get_db, get_mongo_db
from app.crud.feedback import update_feedback
from app.crud.mongo.feedback import update_feedback_mongo

router = APIRouter()


@router.post("/feedback")
async def feedback_handler(
    request: Request,
    user_id: str = Form(),
    analysis_id: str = Form(),
    feedback: str = Form(),
    email: str = Depends(cookie_verification),
    db_session: AsyncSession = Depends(get_db),
    mongo_db: AsyncIOMotorDatabase = Depends(get_mongo_db),
):
    try:
        if ObjectId.is_valid(analysis_id):
            await update_feedback_mongo(mongo_db, user_id, analysis_id, feedback)
        else:
            await update_feedback(db_session, user_id, int(analysis_id), feedback)
            await db_session.commit()

    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

    return {"message": "Feedback updated"}


# @router.post("/feedbacks/item")
# async def create_feedback(
#     request: Request,
#     analysis_id: int = Form(),
#     sequence_no: str = Form(),
#     feedback: str = Form(),
#     email: str = Depends(cookie_verification)
# ):
#     feedback_datetime = datetime.now(timezone.utc)
#     with connection.cursor() as cur:
#         try:
#             cur.execute(
#                 """
#                 SELECT sequence_no, feedback FROM codesherlock.feedbacks
#                 WHERE analysisid = %s AND sequence_no = %s;
#                 """,
#                 (analysis_id,sequence_no)
#             )
#             results = cur.fetchall()
#             if results:
#                 try:
#                     cur.execute(
#                      """
#                       UPDATE codesherlock.feedbacks
#                       SET feedback_datetime = %s, feedback = %s
#                        WHERE analysisid = %s AND sequence_no = %s
#                      """,
#                         (feedback_datetime, feedback, analysis_id, sequence_no)
#                     )
#                     connection.commit()
#                     logger.info("Feedback updated for analysis id %s, sequence no %s by user %s.", analysis_id, sequence_no, email)
#                     return f"Feedback created for analysis id: {analysis_id}, sequence number {sequence_no}."
#                 except Exception as e:
#                     logger.error("Error updating feedback for analysis id %s, sequence no %s: %s.", analysis_id, sequence_no, str(e), extra={"user_id": str(email)})
#                     raise HTTPException(
#                     status_code=500, detail="Error updating feedback."
#                     )
#             cur.execute(
#              """
#              INSERT INTO codesherlock.feedbacks (feedback_datetime, analysisid, sequence_no, feedback)
#              VALUES (%s, %s, %s, %s)                """,
#              (feedback_datetime, analysis_id, sequence_no, feedback)
#             )
#             connection.commit()
#             logger.info("Feedback created for analysis id %s sequence number %s.", analysis_id, sequence_no, extra={"user_id": str(email)})
#             return f"Feedback created for analysis id: {analysis_id}, sequence number {sequence_no}."
#         except Exception as e:
#             logger.error("Error creating feedback for analysis id %s sequence number : %s.", analysis_id,sequence_no , str(e), extra={"user_id": str(email)})
#             raise HTTPException(
#                 status_code=500, detail="Error creating feedback."
#             )

# @router.get("/feedback/item/{analysis_id}")
# async def read_feedback(analysis_id: int, email: str = Depends(cookie_verification)):
#     with connection.cursor() as cur:
#         try:
#             cur.execute(
#                 """
#                 SELECT sequence_no, feedback FROM codesherlock.feedbacks
#                 WHERE analysisid = %s;
#                 """,
#                 (analysis_id,)
#             )
#             results = cur.fetchall()
#             if not results:
#                 return "Feedback not found"
#             feedback_dict = {result[0]: result[1] for result in results}
#             logger.info("Feedback read for analysis id %s by user %s.", analysis_id, email)
#             return feedback_dict
#         except Exception as e:
#             print("Error reading feedback for analysis id %s: %s.", analysis_id, str(e))
#             raise HTTPException(
#                 status_code=500, detail="Error reading feedback."
#             )
