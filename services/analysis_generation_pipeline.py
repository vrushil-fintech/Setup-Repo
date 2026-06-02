from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from app.crud.github_repository import get_github_repository_on_fullname
from app.crud.github_user import get_github_id_from_user_id
from app.crud.organization import get_organization_id_from_name
from app.crud.usage import (
    get_tokens_usage_by_user_id_org_id,
    insert_usage,
    insert_characteristic_usage,
    upsert_tokens_usage_user_id_org_id,
)
from app.crud.mongo.analyses import insert_analysis_mongo
from app.database import AsyncSessionFactory
from app.services.cost_calculation_service import calculate_llm_cost
from app.services.order_handler_service import sync_order_status
from app.services.pr_review_services.hybrid_line_number_service import (
    char_issues_linenum_ext,
)
from app.services.github_app_email_utils import send_usage_email
from app.models import (
    CharAnalysisResponse,
    FactorAnalysisResponse,
    LLMUsage,
    ResponseClass,
)

from app.services.llm_endpoint_service import LLMRouterService
from app.config import (
    FACTORS_LIST,
    FRONTEND_URL,
    MAX_INPUT_TOKENS,
    MIN_INPUT_TOKENS,
    PAID_TOKENS_LIMIT,
    SMALL_LINES_TOKEN_LIMIT,
)
from app.services.calculate_tokens import calculate_tokens
from app.services.prompt_service import PromptService
from app.dependencies import logger
from app.services.websocket_manager import WebSocketManager
from app.services.language_ext_and_applicability_check import applicability_check
from app.services.md_to_json_service import md_to_json
from app.services.eventgrid_service import publish_event
from app.crud.users import get_user_by_id
from app.config import FREE_TOKENS_LIMIT
from app.crud.user_organization import get_user_org_row
from app.services.pr_review_pipeline import get_trial_reminder_config

async def handle_usage_and_trial_logic(
    user, 
    order_status: str, 
    tokens_usage: int, 
    token_limit: int,
    user_id: str,
    websocket_manager: WebSocketManager,
    analysis_platform: str = "website",
    organization_id: str | None = None,
) -> bool:
    """
    Handle trial logic for analysis generation pipeline.
    
    Args:
        user: User object
        order_status: Order status (active/inactive)
        tokens_usage: Current token usage
        token_limit: Token limit for user
        user_id: User ID
        websocket_manager: WebSocket manager for sending messages
        
    Returns:
        bool: True if analysis should continue, False if should stop
    """
    tokens_left = max(0, token_limit - tokens_usage)
    # percentage_remaining = max(0, int((tokens_left / token_limit) * 100))
    dashboard_link = f"{FRONTEND_URL}/dashboard"
    analysis_page_link = f"{FRONTEND_URL}/analysis"
    user_org_row = None
    if organization_id:
        async with AsyncSessionFactory() as db_session:
            try:
                user_org_row = await get_user_org_row(db_session, user_id=user_id, organization_id=organization_id)
            except Exception as e:
                logger.error(f"Error occurred while getting user org row {e}", extra={"user_id": user_id, "organization_id": organization_id})
                return False

    # Handle order status specific logic
    if order_status == "active":

        # Check if tokens are exhausted
        if not user.role and tokens_left == 0:
            if analysis_platform != "website":
                if user_org_row:
                        link_text = f" Upgrade by visiting: {dashboard_link}"
                else:
                    link_text = f" Upgrade by visiting: {analysis_page_link}"
            else:
                link_text = ""

            error_message = (
                "You have already exhausted your paid plan limit of 3 million tokens. "
                "Please upgrade your subscription to continue new analysis. "
                f"{link_text}"
            )
            await websocket_manager.send_error(
                user_id=user_id,
                status_code=422,
                error_message=error_message
            )
            return False
            
    else:
        try:
            if user.role:
                return True

            trial_start = (
                user_org_row.get("created_at") if user_org_row and user_org_row.get("created_at")
                else getattr(user, "created_at", None)
            )

            # If no created_at found anywhere → stop
            if not trial_start:
                if analysis_platform != "website":
                    # Check for organization mapping - use dashboard link if exists, otherwise analysis link
                    if user_org_row:
                        link_text = f" Upgrade by visiting: {dashboard_link}"
                    else:
                        link_text = f" Upgrade by visiting: {analysis_page_link}"
                else:
                    link_text = ""

                logger.error("User have already exhausted your 14 days trial period. Please upgrade your subscription to continue new analysis. ", extra={"user_id": user_id, "organization_id": organization_id})

                await websocket_manager.send_error(
                    user_id=user_id,
                    status_code=422,
                    error_message=(
                        "You have already exhausted your 14 days trial period. "
                        "Please upgrade your subscription to continue new analysis. "
                        f"{link_text}"
                    ),
                )

                return False

            if isinstance(trial_start, str):
                trial_start = datetime.fromisoformat(trial_start)
            if not trial_start.tzinfo:
                trial_start = trial_start.replace(tzinfo=timezone.utc)

            days_since_creation = (datetime.now(timezone.utc) - trial_start).days

        except Exception:
            logger.error("days since creation is none")
            days_since_creation = None
            return False

        if days_since_creation is not None:
            trial_cfg = get_trial_reminder_config(days_since_creation)

            if trial_cfg["message_type"] == "expired":
                if analysis_platform != "website":
                    # Check for organization mapping - use dashboard link if exists, otherwise analysis link
                    if user_org_row:
                        link_text = f" Upgrade by visiting: {dashboard_link}"
                    else:
                        link_text = f" Upgrade by visiting: {analysis_page_link}"
                else:
                    link_text = ""
                logger.info("User have already exhausted your 14 days trial period. Please upgrade your subscription to continue new analysis. ")
                await websocket_manager.send_error(
                    user_id=user_id,
                    status_code=422,
                    error_message=(
                        "You have already exhausted your 14 days trial period. "
                        "Please upgrade your subscription to continue new analysis. "
                        f"{link_text}"
                    ),
                )
                return False

    return True


async def analysis_generation_pipeline(
    factor: str,
    llm: str,
    model: str,
    user_id: str,
    analysis_code_content: str,
    file_name: str,
    temperature: float,
    websocket_manager: WebSocketManager,
    mongo_db: AsyncIOMotorClient,
    llm_service: LLMRouterService,
    context_code_content: str = "",
    analysis_platform: str = "website",
    organization_name: str = None,
    repo_name: str = None,
):
    req_start_time = datetime.now(timezone.utc)
    is_jsx_tsx=0
    extension = "." + file_name.split(".")[-1]
    if extension == ".jsx" or extension == ".tsx":
        is_jsx_tsx = 1
    else:
        is_jsx_tsx = 0

    if not 0.0 < temperature < 2.0:
        logger.warning(
            "Invalid temperature value: %s", temperature, extra={"user_id": user_id}
        )
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=422,
            error_message="Invalid temperature value. Temperature should be in the range 0 to 2.",
        )
        return

    if llm != "openai":
        logger.warning("Invalid LLM name: %s", llm, extra={"user_id": user_id})
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=422,
            error_message="LLM not found. Please provide a valid LLM name.",
        )
        return

    if model not in ["gpt-3.5-turbo-0125", "gpt-4-turbo-preview", "gpt-4o-mini", "gpt-5-mini"]:
        logger.warning("Invalid model name: %s", model, extra={"user_id": user_id})
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=422,
            error_message="Model not found. Please provide a valid model name.",
        )
        return

    if factor not in FACTORS_LIST:
        logger.warning("Invalid factor name: %s", factor, extra={"user_id": user_id})
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=422,
            error_message="Factor not found. Please provide a valid factor name.",
        )
        return

    organization_id = None
    
    async with AsyncSessionFactory() as db_session:
        try:
            user = await get_user_by_id(db_session, user_id)
            github_user_id = await get_github_id_from_user_id(db_session=db_session, user_id=user.userid)
            if github_user_id:
                if analysis_platform == "website":
                    logger.warning(
                        f"Github user detected doing analysis on website {user.userid}", extra={"user_id": user_id, "github_id": github_user_id}
                    )
                    await websocket_manager.send_error(
                        user_id=user.userid,
                        status_code=422,
                        error_message="**Analysis not supported on website for GitHub users.**\n Since you signed up using GitHub, please use the IDE Extension to run code analysis.\n Make sure you open a repository where our GitHub App is installed.",
                    )
                    return

                if organization_name and repo_name:
                    repo_full_name = organization_name + "/" + repo_name
                    repo_details = await get_github_repository_on_fullname(db_session=db_session, repo_full_name=repo_full_name)
                    if not repo_details:
                        logger.warning(f"Github repository not found: org_name {organization_name}, repo_name {repo_name}", extra={"user_id": user_id, "github_id": github_user_id})
                        await websocket_manager.send_error(
                            user_id=user.userid,
                            status_code=422,
                            error_message="CodeSherlock GitHub App is not installed in this repository. Analysis would be allowed once it is installed in this repository.",
                        )
                        return
                else:
                    logger.warning("No repositories detected in workspace", extra={"user_id": user_id, "github_id": github_user_id})
                    await websocket_manager.send_error(
                        user_id=user.userid,
                        status_code=422,
                        error_message="**No Git repository found in this workspace.**\n To run analysis, please open a GitHub repository in your IDE where our app is installed.",
                    )
                    return
        except Exception as e:
            logger.error(
                f"Error while retrieving user details. user_id: {user_id}. Error: {str(e)}",
                extra={"user_id": user_id}
            )
            await websocket_manager.send_error(
                user_id=user_id,
                status_code=422,  # before analysis error have uniform status_codes
                error_message="We ran into an issue while retrieving your details. Please try again later or contact support@codesherlock.ai.",
            )
            return

        if organization_name:
            try:
                organization_id = await get_organization_id_from_name(db_session=db_session, name=organization_name)
            except Exception as e:
                logger.error(
                    f"Error occurred while retrieving organization details. {str(e)}",
                    extra={"user_id": user_id, "error": str(e)},
                )
                # Log the error for debugging, optionally send a user-friendly message
                await websocket_manager.send_error(
                    user_id=user_id,
                    status_code=422,
                    error_message="We ran into an issue while retrieving your organization details. Please try again later or contact support@codesherlock.ai.",
                )
                return

        try:
            order_details = await sync_order_status(db_session=db_session, user_id=user_id, org_id=organization_id)
            order_status = order_details.get("status")

            tokens_usage = await get_tokens_usage_by_user_id_org_id(db_session, user_id, organization_id)
        except Exception as e:
            await db_session.rollback()
            logger.error(
                "We ran into an issue while retrieving your usage details.",
                extra={"user_id": user_id, "error": str(e)},
            )
            # Log the error for debugging, optionally send a user-friendly message
            await websocket_manager.send_error(
                user_id=user_id,
                status_code=422,
                error_message="We ran into an issue while retrieving your usage details. Please try again later or contact support@codesherlock.ai.",
            )
            return

    # Set token limit based on the order status
    if order_status == "active":
        token_limit = PAID_TOKENS_LIMIT
    else:
        token_limit = FREE_TOKENS_LIMIT

    # Use dynamic trial logic similar to PR pipeline
    should_continue = await handle_usage_and_trial_logic(
        user=user,
        order_status=order_status,
        tokens_usage=tokens_usage,
        token_limit=token_limit,
        user_id=user_id,
        websocket_manager=websocket_manager,
        analysis_platform=analysis_platform,
        organization_id=organization_id,
    )
    
    if not should_continue:
        return
    
    code_tokens = calculate_tokens(analysis_code_content)
    if factor != "power_analysis" and code_tokens < MIN_INPUT_TOKENS:
        logger.warning(
            "Code too small: %s tokens", code_tokens, extra={"user_id": user_id}
        )
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=422,
            error_message="The code snippet is too small for an analysis. We require at least 50 lines of code with sufficient logic so we can provide a meaningful analysis of your code.",
        )
        return

    elif code_tokens > MAX_INPUT_TOKENS:
        logger.warning(
            "Code too large: %s tokens", code_tokens, extra={"user_id": user_id}
        )
        await websocket_manager.send_error(
            user_id=user_id,
            status_code=422,
            error_message="Code too large. Please provide a smaller code.",
        )
        return

    prompt_service = PromptService()

    req_usage_data = {}

    if code_tokens > SMALL_LINES_TOKEN_LIMIT:
        applicability_usage_data = LLMUsage()
        if(factor in ["cwe", "soc2", "cwe_mitre", "cwe_kev"]):
            applicability_check_str = await prompt_service.get_prompt(
                "applicability_check_prompt_cwe_soc2", code=analysis_code_content, factor=factor
            )
        else:
            applicability_check_str = await prompt_service.get_prompt(
                "applicability_check_prompt", code=analysis_code_content, factor=factor
            )
        applicability_check_prompt = [
            {
                "role": "system",
                "content": "You are a senior software engineer who is great at analyzing and reviewing code.",
            },
            {"role": "user", "content": applicability_check_str},
        ]

        try:
            applicability_check_response = await applicability_check(
                prompt=applicability_check_prompt,
                file_name=file_name,
                llm_service=llm_service,
                usage_data=applicability_usage_data,
            )

            req_usage_data["applicability_check_" + factor] = applicability_usage_data
            applicability_usage_data.cost = calculate_llm_cost(applicability_usage_data, model)
            req_usage_data["applicability_check_" + factor] = applicability_usage_data

        except Exception as e:
            logger.error(
                "Error occurred while running applicability check for factor: %s, error: %s",
                factor,
                str(e),
                extra={"user_id": user_id},
            )

        # TODO: remove this log in prod
        logger.info(
            "Filtered chars: %s",
            applicability_check_response["filtered_chars"],
            extra={"user_id": user_id},
        )

    if factor not in ["power_analysis", "owasp"]:
        prompts_dict = await prompt_service.get_prompt(
            "factor_analysis_prompt",
            factor_name=factor,
            applicable_chars=applicability_check_response["filtered_chars"],
        )
    elif factor == "power_analysis":
        if is_jsx_tsx or code_tokens <= SMALL_LINES_TOKEN_LIMIT:
            logger.info("Running small file power analysis")
            prompts_dict = await prompt_service.get_prompt(
                "power_analysis_small_prompt",
                factor_name="power_analysis_small",
                context=context_code_content,
            )
        else :
            prompts_dict = await prompt_service.get_prompt(
                "power_analysis_prompt",
                factor_name=factor,
                context=context_code_content,
                applicable_chars=applicability_check_response["filtered_chars"],
            )
       
    elif factor == "owasp":
        prompts_dict = await prompt_service.get_prompt(
            "owasp_analysis_prompt",
            factor_name=factor,
            context=context_code_content,
            applicable_chars=applicability_check_response["filtered_chars"],
        )

    elif factor in ["cwe", "soc2", "cwe_mitre", "cwe_kev"]:
        filtered_chars = applicability_check_response["filtered_chars"]
        if filtered_chars  == []:
            logger.warning(
            "No relevant issues found for user_id: %s with factor: %s",
            user_id,
            factor,
            extra={"filtered_chars": filtered_chars},
        )
            await websocket_manager.send_error(
            user_id=user_id,
            status_code=422,
            error_message="We could not find any relevant issues in your code for the selected factor.",
            )
            await WebSocketManager.disconnect(user_id)
            return

        prompts_dict = await prompt_service.get_prompt(
            "cwe_analysis_prompt",
            factor_name=factor,
            context=context_code_content,
            applicable_chars=applicability_check_response["filtered_chars"],
        )


    ws_conn_err_flag = False  # Flag to track WebSocket connection errors
    if code_tokens > SMALL_LINES_TOKEN_LIMIT:
        code_language = applicability_check_response.get("language", None)
        code_language = code_language.lower() if code_language else None
    else:
        code_language = None

    char_analysis_response_list = []

    for index, (characteristic, char_prompt) in enumerate(prompts_dict.items()):
        # if websocket got disconnected in previous iteration, exit the loop
        if ws_conn_err_flag:
            break

        char_usage_data = LLMUsage()
        char_start_time = datetime.now(timezone.utc)
        char_response = ""

        prompt = [
            {
                "role": "system",
                "content": "You are a senior software engineer who is great at analyzing and reviewing code.",
            },
            {
                "role": "user",
                "content": "Code To Anlayze: "
                + "\n"
                + analysis_code_content
                + "\n"
                + char_prompt,
            },
        ]

        if factor != "owasp":
            char_heading = f"\n# {characteristic}\n"
            char_response += char_heading

        try:
            # generating md response
            async for chunk in llm_service.agenerate_streaming_response(
                prompt=prompt,
                model=model,
                usage_data=char_usage_data,
                temperature=temperature,
            ):
                char_response += chunk

            md_str_start_time = datetime.now(timezone.utc)

            # converting md to json
            char_response_json = md_to_json(char_response, file_name, factor)

            file_code = analysis_code_content
            char_response_linenum = char_issues_linenum_ext(
                char_response_json, file_code
            )

            md_str_end_time = datetime.now(timezone.utc)
            logger.info(
                "md to str conversion time: %s",
                str(md_str_end_time - md_str_start_time),
                extra={"user_id": user_id},
            )

            if char_response_json:
                ws_response = ResponseClass(
                    status_code=200,
                    content=FactorAnalysisResponse(
                        analysis=[
                            CharAnalysisResponse(**char) for char in char_response_linenum
                        ],
                        language=code_language,
                        analysis_type="structured",
                    ),
                )
                if not ws_conn_err_flag:
                    success = await websocket_manager.send_json(user_id, ws_response)
                    if not success:
                        ws_conn_err_flag = True

        except Exception as e:
            logger.error(
                "Error occured while generating response for characteristic: %s, error: %s",
                characteristic,
                str(e),
                extra={"user_id": user_id},
            )

            char_usage_data.llm_deployment = "N/A"

        char_end_time = datetime.now(timezone.utc)
        logger.info(
            "Characteristic - %s, completed in time: %s",
            characteristic,
            str(char_end_time - char_start_time),
            extra={"user_id": user_id},
        )

        if isinstance(char_response_json, list):
            char_analysis_response_list.extend(char_response_linenum)  # Unpack the list
        else:
            char_analysis_response_list.append(
                char_response_linenum
            )  # Append single object

        char_usage_data.cost = calculate_llm_cost(char_usage_data, model)
        req_usage_data[characteristic] = char_usage_data

    # END OF FOR LOOP OF CHARACTERISTICS

    # Calculate total tokens and total cost
    total_tokens = 0
    total_cost = 0.0

    for usage in req_usage_data.values():
        total_tokens += getattr(usage, "input_tokens", 0) + getattr(
            usage, "response_tokens", 0
        )
    total_cost += getattr(usage, "cost", 0.0)

    created_at = datetime.now(timezone.utc)

    async with AsyncSessionFactory() as db_session:
        try:
            analysis_id = await insert_analysis_mongo(
                mongo_db,
                user_id,
                char_analysis_response_list,
                factor,
                file_name,
                code_language,
                analysis_platform,
            )

            # Call the upsert function to record token usage
            await upsert_tokens_usage_user_id_org_id(
                db_session=db_session,
                user_id=user_id,
                tokens_used=total_tokens,
                cost=total_cost,
                organization_id=organization_id,
            )
            usage_ids = await insert_usage(
                db_session, req_usage_data, user_id, model, created_at, organization_id
            )
            await insert_characteristic_usage(
                db_session, req_usage_data, usage_ids, user_id, created_at, organization_id
            )
            await db_session.commit()

            if not ws_conn_err_flag:
                ws_response = ResponseClass(
                    status_code=200,
                    content=None,
                    analysis_id=analysis_id,
                    is_complete=True,
                )
                await websocket_manager.send_json(user_id, ws_response)
            await websocket_manager.disconnect(user_id)
        except Exception as e:
            if not ws_conn_err_flag:
                await websocket_manager.send_error(
                    user_id=user_id, status_code=503, error_message=str(e)
                )

        await publish_event(
            event_type="Analysis.Feedback",
            subject=f"Analysis_Feedback/{user.email}",
            data={"email": user.email, "name": user.name, "factor": factor},
        )

        try:
            tokens_usage_after_analysis = await get_tokens_usage_by_user_id_org_id(db_session, user_id, organization_id)
        except Exception as e:
            logger.error(f"Error occurred while getting tokens usage: {e}", extra={"user_id": user_id})
            tokens_usage_after_analysis = 0

    tokens_left_after_analysis = max(0, token_limit - tokens_usage_after_analysis)
    percentage_remaining_after_analysis = max(
        0, int((tokens_left_after_analysis / token_limit) * 100)
    )

    # Calculate initial percentage for threshold comparison
    tokens_left_initial = max(0, token_limit - tokens_usage)
    percentage_remaining = max(0, int((tokens_left_initial / token_limit) * 100))

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

    req_end_time = datetime.now(timezone.utc)
    logger.info(
        "Request completed in time: %s",
        str(req_end_time - req_start_time),
        extra={"user_id": user_id},
    )
    return