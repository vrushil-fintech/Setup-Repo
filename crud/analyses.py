from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import logger


async def insert_analysis(
    db_session: AsyncSession,
    user_id: str,
    content: str,
    factor: str,
    file_name: str,
    language: str,
):
    created_at = datetime.now(timezone.utc)

    sql_query = text(
        """
INSERT INTO codesherlock.analyses (userid, analysis, factor_name, created_at, feedback, file_name, language)
VALUES (:userid, :analysis, :factor_name, :created_at, :feedback, :file_name, :language)
RETURNING analysisid;
    """
    )
    try:
        db_result = await db_session.execute(
            sql_query,
            {
                "userid": user_id,
                "analysis": content,
                "factor_name": factor,
                "created_at": created_at,
                "feedback": "Not Responded",
                "file_name": file_name,
                "language": language,
            },
        )
        analysis_id = db_result.fetchone()[0]
        logger.info(
            "Analysis inserted in history.",
            extra={"user_id": str(user_id), "analysis_id": str(analysis_id)},
        )
        return analysis_id

        # update the exception to http exception
    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Error inserting analysis in history: %s",
            str(e),
            extra={"user_id": str(user_id)},
        )
        raise Exception(
            "We're having trouble saving your analysis. Please try again later."
        )


async def get_history(db_session: AsyncSession, user_id: str, limit: int = 5):
    sql_query = text(
        """
SELECT analysisid, factor_name, created_at, file_name
FROM codesherlock.analyses
WHERE userid = :userid
ORDER BY created_at DESC
LIMIT :limit;
    """
    )
    try:
        db_result = await db_session.execute(
            sql_query, {"userid": user_id, "limit": limit}
        )
        results = list(db_result.fetchall())
        logger.info("History retrieved for user", extra={"user_id": str(user_id)})
        analysis_history_list = []
        for item in results:
            analysisid, factor_name, created_at, file_name = item
            analysis_history_list.append(
                {
                    "id": analysisid,
                    "factor": factor_name,
                    "created_at": created_at,
                    "file_name": file_name,
                }
            )
        return analysis_history_list
    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Error fetching history for user: %s",
            str(e),
            extra={"user_id": str(user_id)},
        )
        raise Exception(
            "We're having trouble loading your history. Please try again later."
        )


async def get_pr_history(db_session: AsyncSession, user_id: str, limit: int = 5):
    sql_query = text(
        """
SELECT analysisid, factor_name, created_at, pr_number, repo_name
FROM codesherlock.pr_analyses
WHERE userid = :userid
ORDER BY created_at DESC
LIMIT :limit;
        """
    )
    try:
        db_result = await db_session.execute(
            sql_query, {"userid": user_id, "limit": limit}
        )
        results = list(db_result.fetchall())
        logger.info("PR history retrieved for user", extra={"user_id": str(user_id)})

        pr_history_list = []
        for item in results:
            analysisid, factor_name, created_at, pr_number, repo_name = item
            pr_history_list.append(
                {
                    "id": analysisid,
                    "factor": factor_name,
                    "created_at": created_at,
                    "pr_number": pr_number,
                    "repo_name": repo_name,
                }
            )
        return pr_history_list

    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Error fetching PR history for user: %s",
            str(e),
            extra={"user_id": str(user_id)},
        )
        raise Exception(
            "We're having trouble loading your PR history. Please try again later."
        )


async def get_analysis(db_session: AsyncSession, user_id: str, analysis_id: int):
    sql_query = text(
        """
SELECT factor_name, analysis, file_name, created_at, feedback
FROM codesherlock.analyses
WHERE userid = :userid AND analysisid = :analysisid
    """
    )
    try:
        db_result = await db_session.execute(
            sql_query, {"userid": user_id, "analysisid": analysis_id}
        )
        result = db_result.fetchone()
        if not result:
            logger.warning(
                "Analysis not found in PostgreSQL.",
                extra={"user_id": str(user_id), "analysis_id": str(analysis_id)},
            )
            return None

        logger.info(
            "Analysis %s retrieved for user",
            str(analysis_id),
            extra={"user_id": str(user_id)},
        )
        factor_name, analysis, file_name, created_at, feedback = result
        analysis_result = {
            "user_id": user_id,
            "factor": factor_name,
            "created_at": created_at,
            "analysis": analysis,
            "file_name": file_name,
            "feedback": feedback,
        }
        return analysis_result
    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Error fetching analysis %s for user: %s",
            str(analysis_id),
            str(e),
            extra={"user_id": str(user_id)},
        )
        raise Exception(
            "We're having trouble loading your analysis. Please try again later."
        )


async def get_pr_analysis(db_session: AsyncSession, user_id: str, analysis_id: int):
    sql_query = text(
        """
        SELECT factor_name, analysis, pr_number, repo_name, created_at
        FROM codesherlock.pr_analyses
        WHERE analysisid = :analysisid AND userid = :userid
        """
    )
    try:
        db_result = await db_session.execute(
            sql_query, {"analysisid": analysis_id, "userid": user_id}
        )
        result = db_result.fetchone()
        if not result:
            logger.warning(
                "PR Analysis not found in PostgreSQL.",
                extra={"user_id": str(user_id), "analysis_id": str(analysis_id)},
            )
            return None

        logger.info(
            "PR Analysis %s retrieved successfully",
            str(analysis_id),
            extra={"user_id": str(user_id)},
        )
        factor_name, analysis, pr_number, repo_name, created_at = result
        analysis_result = {
            "factor": factor_name,
            "created_at": created_at,
            "analysis": analysis,
            "pr_number": pr_number,
            "repo_name": repo_name,
        }
        return analysis_result

    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Error fetching PR analysis %s: %s",
            str(analysis_id),
            str(e),
            extra={"user_id": str(user_id)},
        )
        raise Exception(
            "We're having trouble loading this PR analysis. Please try again later."
        )


async def insert_pr_analysis(
    db_session: AsyncSession,
    user_id: str,
    content: str,
    factor: str,
    language: str,
    pr_number: int,
    repo_name: str,
    repo_owner: str,
    analysisid: str,
):
    created_at = datetime.now(timezone.utc)

    sql_query = text(
        """
        INSERT INTO codesherlock.pr_analyses (
            userid, analysisid, analysis, factor_name, created_at, 
            language, pr_number, repo_name, repo_owner
        )
        VALUES (
            :userid, :analysisid, :analysis, :factor_name, :created_at, 
            :language, :pr_number, :repo_name, :repo_owner
        )
        RETURNING analysisid;
    """
    )
    try:
        db_result = await db_session.execute(
            sql_query,
            {
                "userid": user_id,
                "analysis": content,
                "factor_name": factor,
                "created_at": created_at,
                "language": language,
                "pr_number": pr_number,
                "repo_name": repo_name,
                "repo_owner": repo_owner,
                "analysisid": analysisid,
            },
        )
        analysis_id = db_result.fetchone()[0]
        logger.info(
            "PR Analysis inserted in history.",
            extra={"user_id": str(user_id), "analysis_id": str(analysis_id)},
        )
        return analysis_id
    except Exception as e:
        await db_session.rollback()
        logger.error(
            "Error inserting PR analysis in history: %s",
            str(e),
            extra={"user_id": str(user_id)},
        )
        raise Exception(
            "We're having trouble saving your PR analysis. Please try again later."
        )
