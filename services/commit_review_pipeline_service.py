from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from app.crud.mongo.code_chunks import delete_code_chunks
from app.services.commit_review_pipeline import commit_review_pipeline
from app.services.websocket_manager import WebSocketManager
from app.models import ResponseClass
from app.dependencies import logger
from app.config import (
    DEFAULT_LLM_MODEL,
    FACTORS_LIST,
    PAID_TOKENS_LIMIT,
    FREE_TOKENS_LIMIT,
)
from app.database import AsyncSessionFactory
from app.crud.users import get_user_by_id
from app.crud.organization import get_organization_id_from_name
from app.crud.usage import (
    get_tokens_usage_by_user_id_org_id,
    insert_characteristic_usage,
    insert_usage,
    upsert_tokens_usage_user_id_org_id,
)
from app.crud.github_user import get_github_id_from_user_id
from app.crud.github_repository import get_github_repository_on_fullname
from app.config import FRONTEND_URL
from app.services.order_handler_service import sync_order_status
from app.services.github_app_email_utils import send_usage_email
from app.services.analysis_generation_pipeline import handle_usage_and_trial_logic
            

async def commit_review_pipeline_service(
    files: list,
    repo_name: str,
    commit_id: str,
    username: str,
    factor: str,
    user_id: str,
    websocket_manager: WebSocketManager,
    mongo_db: AsyncIOMotorClient,
    organization_name: str = None,
):
    """
    Commit review pipeline service that works with WebSocket for real-time updates.
    Similar to analysis_generation_pipeline but for commit reviews.
    """
    req_start_time = datetime.now(timezone.utc)
    
    logger.info(
        f"Starting commit review pipeline service",
        extra={
            "user_id": user_id,
            "commit_id": commit_id,
            "repo_name": repo_name,
            "factor": factor,
            "file_count": len(files),
            "organization_name": organization_name
        }
    )

    model = DEFAULT_LLM_MODEL
    
    try:
        logger.info(f"Validating factor: {factor}", extra={"user_id": user_id, "factor": factor})
        if factor not in FACTORS_LIST:
            logger.warning("Invalid factor: %s", factor, extra={"user_id": user_id})
            await websocket_manager.send_error(
                user_id=user_id,
                status_code=422,
                error_message="Invalid factor. Please provide a valid factor.",
            )
            return

        logger.info(f"Factor validation successful", extra={"user_id": user_id, "factor": factor})

        # -------- Pre-checks and usage retrieval (transactional) --------
        async with AsyncSessionFactory() as db_session:
            try:
                # User
                logger.info(f"Retrieving user details", extra={"user_id": user_id})
                user = await get_user_by_id(db_session, user_id)
                if not user:
                    logger.error(f"User not found", extra={"user_id": user_id})
                    await websocket_manager.send_error(
                        user_id=user_id,
                        status_code=404,
                        error_message="User not found.",
                    )
                    return

                logger.info(f"User details retrieved successfully", extra={"user_id": user_id, "user_role": user.role})

                # GitHub user and repository validation
                try:
                    github_user_id = await get_github_id_from_user_id(db_session=db_session, user_id=user.userid)
                    if github_user_id:
                        logger.info(f"GitHub user detected for commit review", extra={"user_id": user_id, "github_id": github_user_id})
                        
                        if organization_name and repo_name:
                            repo_full_name = organization_name + "/" + repo_name
                            repo_details = await get_github_repository_on_fullname(db_session=db_session, repo_full_name=repo_full_name)
                            if not repo_details:
                                logger.warning(f"GitHub repository not found: org_name {organization_name}, repo_name {repo_name}", extra={"user_id": user_id, "github_id": github_user_id})
                                await websocket_manager.send_error(
                                    user_id=user.userid,
                                    status_code=422,
                                    error_message="CodeSherlock GitHub App is not installed in this repository. Commit review would be allowed once it is installed in this repository.",
                                )
                                return
                        else:
                            logger.warning("No repository information provided for GitHub user", extra={"user_id": user_id, "github_id": github_user_id})
                            await websocket_manager.send_error(
                                user_id=user.userid,
                                status_code=422,
                                error_message="**No Git repository information found.**\n To run commit review, please provide valid organization and repository names.",
                            )
                            return
                except Exception as e:
                    logger.error(
                        f"Error while retrieving GitHub user details. user_id: {user_id}. Error: {str(e)}",
                        extra={"user_id": user_id}
                    )
                    logger.info(f"Continuing with commit review without GitHub validation", extra={"user_id": user_id})

                # Organization (optional)
                organization_id = None
                if organization_name:
                    logger.info(f"Retrieving organization details for: {organization_name}", extra={"user_id": user_id, "organization_name": organization_name})
                    try:
                        organization_id = await get_organization_id_from_name(db_session=db_session, name=organization_name)
                        logger.info(f"Organization ID retrieved: {organization_id}", extra={"user_id": user_id, "organization_id": organization_id})
                    except Exception as e:
                        logger.error(
                            f"Error occurred while retrieving organization details. {str(e)}",
                            extra={"user_id": user_id, "error": str(e)},
                        )
                        await websocket_manager.send_error(
                            user_id=user_id,
                            status_code=422,
                            error_message="We ran into an issue while retrieving your organization details. Please try again later or contact support@codesherlock.ai.",
                        )
                        return
                else:
                    logger.info(f"No organization name provided, using personal account", extra={"user_id": user_id})

                # Usage and order status
                logger.info(f"Checking usage limits for user", extra={"user_id": user_id, "organization_id": organization_id})
                try:
                    order_details = await sync_order_status(db_session=db_session, user_id=user_id, org_id=organization_id)
                    order_status = order_details.get("status")

                    tokens_usage = await get_tokens_usage_by_user_id_org_id(db_session, user_id, organization_id)
                except Exception as e:
                    logger.error(
                        "We ran into an issue while retrieving your usage details.",
                        extra={"user_id": user_id, "error": str(e)},
                    )
                    await websocket_manager.send_error(
                        user_id=user_id,
                        status_code=422,
                        error_message="We ran into an issue while retrieving your usage details. Please try again later or contact support@codesherlock.ai.",
                    )
                    return

                await db_session.commit()
            except Exception as e:
                await db_session.rollback()
                logger.error(
                    f"Error occurred during pre-checks: {str(e)}",
                    extra={"user_id": user_id},
                )
                await websocket_manager.send_error(
                    user_id=user_id,
                    status_code=500,
                    error_message="An internal error occurred before running the analysis.",
                )
                return

        # Token gates
        if order_status == "active":
            token_limit = PAID_TOKENS_LIMIT
        else:
            token_limit = FREE_TOKENS_LIMIT

        tokens_left = max(0, token_limit - tokens_usage)
        percentage_remaining = max(0, int((tokens_left / token_limit) * 100))

        # Use same trial logic as analysis_generation_pipeline
        should_continue = await handle_usage_and_trial_logic(
            user=user,
            order_status=order_status,
            tokens_usage=tokens_usage,
            token_limit=token_limit,
            user_id=user_id,
            websocket_manager=websocket_manager,
            analysis_platform="ide",
            organization_id=organization_id,
        )
        
        if not should_continue:
            return

        # Run the commit review pipeline
        logger.info(
            f"Starting commit review pipeline execution",
            extra={
                "user_id": user_id,
                "commit_id": commit_id,
                "factor": factor,
                "file_count": len(files)
            }
        )
        
        result = await commit_review_pipeline(
            files=files,
            repo_name=repo_name,
            commit_id=commit_id,
            username=username,
            factor=factor,
            websocket_manager=websocket_manager,
            user_id=user_id,
        )

        if not result:
            logger.error(f"Commit review pipeline returned no result", extra={"user_id": user_id, "commit_id": commit_id})
            await websocket_manager.send_error(
                user_id=user_id,
                status_code=500,
                error_message="Failed to generate commit review analysis.",
            )
            return

        logger.info(f"Commit review pipeline completed successfully", extra={"user_id": user_id, "commit_id": commit_id})

        # Calculate total usage from results
        logger.info(f"Calculating total usage from pipeline results", extra={"user_id": user_id})
        total_tokens_used = 0
        total_cost = 0.0
        
        for file_result in result.get("results", []):
            if file_result and "usage_summary" in file_result:
                total_tokens_used += file_result["usage_summary"]["total_tokens"]
                total_cost += file_result["usage_summary"]["total_cost"]

        logger.info(
            f"Usage calculation completed - total tokens: {total_tokens_used}, total cost: {total_cost}",
            extra={
                "user_id": user_id,
                "total_tokens_used": total_tokens_used,
                "total_cost": total_cost
            }
        )

        # -------- Post-usage update and notifications (transactional) --------
        async with AsyncSessionFactory() as db_session:
            try:
                if organization_id:
                    logger.info(f"Updating usage in database for organization", extra={"user_id": user_id, "organization_id": organization_id})
                    await upsert_tokens_usage_user_id_org_id(
                        db_session=db_session,
                        user_id=user_id,
                        organization_id=organization_id,
                        tokens_used=total_tokens_used,
                        cost=total_cost,
                    )
                else:
                    logger.info(f"Updating usage in database for personal account", extra={"user_id": user_id})
                    await upsert_tokens_usage_user_id_org_id(
                        db_session=db_session,
                        user_id=user_id,
                        organization_id=None,
                        tokens_used=total_tokens_used,
                        cost=total_cost,
                    )
                created_at = datetime.now(timezone.utc)

                for file_result in result.get("results", []):
                    req_usage_data = file_result.get("req_usage_data", None) if file_result else None
                    if req_usage_data:
                        usage_ids = await insert_usage(
                            db_session=db_session,
                            usage_data=req_usage_data,
                            user_id=user_id,
                            model=model,
                            created_at=created_at,
                            organization_id = organization_id,
                        )

                        await insert_characteristic_usage(
                            db_session=db_session,
                            usage_data=req_usage_data,
                            usage_ids=usage_ids,
                            user_id=user_id,
                            created_at=created_at,
                            organization_id = organization_id,
                        )


                await db_session.commit()

                # Recompute tokens after analysis for email gating
                tokens_usage_after_analysis = await get_tokens_usage_by_user_id_org_id(db_session, user_id, organization_id)

            except Exception as e:
                await db_session.rollback()
                logger.error(
                    f"Error while recording token usage: {str(e)}",
                    extra={"user_id": user_id},
                )
                tokens_usage_after_analysis = 0

        total_time = datetime.now(timezone.utc) - req_start_time
        logger.info(
            f"Commit review completed in {total_time}",
            extra={"user_id": user_id, "commit_id": commit_id, "factor": factor}
        )
        completion_response = ResponseClass(
            status_code=200,
            content=None,
            is_complete=True,
        )
        await websocket_manager.send_json(user_id, completion_response)
        await websocket_manager.disconnect(user_id)

        tokens_left_after_analysis = max(0, token_limit - tokens_usage_after_analysis)
        percentage_remaining_after_analysis = max(
            0, int((tokens_left_after_analysis / token_limit) * 100)
        )

        if order_status == "active" and not user.role:
            thresholds = [40, 20, 10, 0]
            crossed_thresholds = [
                t
                for t in thresholds
                if percentage_remaining >= t >= percentage_remaining_after_analysis
            ]

            if crossed_thresholds:
                await send_usage_email(
                    user.email,
                    username=user.name,
                    tokens_left=tokens_left_after_analysis,
                    percentage_remaining=percentage_remaining_after_analysis,
                )
        
        delete_count = await delete_code_chunks(
            mongo_db=mongo_db, user_id=username, repo_name=repo_name, commit_id=commit_id
        )
        logger.info(
            f"{delete_count} code chunks deleted for commit: {commit_id}",
            extra={"user_id": user_id, "repo_name": repo_name},
        )

    except Exception as e:
        logger.error(
            f"Error in commit review pipeline service: {str(e)}",
            extra={"user_id": user_id, "commit_id": commit_id}
        )
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=500,
            error_message="An error occurred during commit review analysis.",
        )
