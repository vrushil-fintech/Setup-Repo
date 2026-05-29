import asyncio
from collections import defaultdict
from datetime import datetime, timezone
import uuid, time
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.crud.github_user import get_user_id_from_github_id
from app.crud.mongo.code_chunks import delete_code_chunks
from app.crud.organization import get_organization_id_from_github_id
from app.crud.user_organization import get_organization_id_for_user_id, get_user_org_row
from app.database import AsyncSessionFactory, get_mongo_db
from app.services.calculate_tokens import calculate_tokens
from app.services.check_code_file import is_code_file
import re, copy, json
from app.services.data import Factors
from typing import List, Dict, Optional
from dataclasses import dataclass
from app.services.check_valid_pr_line_numbers import (
    clean_raw_patch,
    validate_comment_line_numbers,
)
from app.services.cost_calculation_service import calculate_llm_cost
from app.services.installation_token_service import fetch_installation_token_installid
from app.services.json_to_md_service import (
    json_to_md_analysis,
    json_to_md_issue_color_formatted,
)
from app.services.order_handler_service import sync_order_status
from app.services.pr_config_utils import parse_yaml_file
from app.services.data import IMPACT_DUMMY_EXAMPLE
from app.services.pr_review_services.hybrid_line_number_service import (
    char_issues_linenum_ext,
)
from app.services.pr_review_services.pr_files_fetch_service import (
    parse_diff_to_file_objects,
)
from app.crud.analyses import insert_pr_analysis
from app.crud.users import get_user_by_id
from app.crud.analyses import insert_pr_analysis
from app.crud.usage import (
    get_tokens_usage_by_user_id_org_id,
    insert_characteristic_usage,
    insert_usage,
    upsert_tokens_usage_user_id_org_id,
)
from app.services.github_app_email_utils import send_usage_email
from app.services.pr_review_services.md_summary_service import (
    format_severity_characteristic_data,
)
from app.services.pr_review_services.pr_files_fetch_service import (
    fetch_new_version,
    trim_patch_before_hunks,
)
from app.api.pr_details import (
    get_pull_request_files,
    post_pull_request_comment,
    post_pull_request_line_comment,
    post_pull_request_status,
    delete_pull_request_comment,
    update_pull_request_comment,
    get_pull_request_diff,
    get_github_pr_data,
)
from app.api.github import get_github_repo_structure, get_github_files_content_batch
from app.services.rag_services.imports_line_direct_extraction import (
    extract_import_lines_from_pr_files_as_dict,
    detect_language_from_filename,
)
from app.services.prompt_service import PromptService
from app.services.llm_endpoint_service import get_router_service
from app.dependencies import logger
from app.services.md_to_json_service import md_to_json
from app.services.language_ext_and_applicability_check import (
    applicability_check,
    cwe_applicability_check,
    identify_missing_dependencies_llm_call,
    instruction_applicability_check,
    impact_based_characteristic_pick,
)
from app.models import (
    LLMUsage,
)
from app.config import (
    GITHUB_APP_ID,
    PAID_TOKENS_LIMIT,
    SMALL_LINES_TOKEN_LIMIT,
    FREE_TOKENS_LIMIT,
    MAX_INPUT_TOKENS,
    FRONTEND_URL,
    YAML_FILE_PATH,
    DEFAULT_LLM_MODEL,
)
from app.services.rag_services.chunking_pipeline import chunk_code_and_save_to_db
from app.services.rag_services.context_traversal_service import (
    build_adjacency,
    traverse_dependencies_and_retrieve_chunks,
)
from app.services.diagram_generation_service import (
    render_ascii_diagram,
    render_mermaid_diagram,
    extract_graph_spec_body,
    extract_mermaid_body,
    sanitize_mermaid_diagram,
)


def _duration_seconds(start_time: datetime, end_time: datetime) -> float:
    return round((end_time - start_time).total_seconds(), 3)


def get_trial_reminder_config(days_since_creation: int) -> dict:
    """
    Dynamic trial reminder configuration based on days since creation.
    Returns configuration for trial reminders without hardcoded if-else statements.

    Args:
        days_since_creation: Number of days since user account creation

    Returns:
        dict: Configuration containing should_send_email, days_remaining, message_type
    """
    trial_config = {
        "days_remaining": 0,
        "message_type": None,
        "email_days_remaining": 0,
    }

    # Trial expired (14+ days)
    if days_since_creation >= 14:
        trial_config.update(
            {"days_remaining": 0, "message_type": "expired", "email_days_remaining": 0}
        )
    # 12–13 days (2 days left)
    elif 12 <= days_since_creation <= 13:
        trial_config.update(
            {
                "days_remaining": 14 - days_since_creation,
                "message_type": "warning",
                "email_days_remaining": 14 - days_since_creation,
            }
        )
    # 7–8 days (7 days left)
    elif 7 <= days_since_creation <= 8:
        trial_config.update(
            {
                "days_remaining": 14 - days_since_creation,
                "message_type": "reminder",
                "email_days_remaining": 14 - days_since_creation,
            }
        )

    return trial_config


def get_trial_message(
    message_type: str, days_remaining: int, dashboard_link: str
) -> str:
    """
    Generate trial-related messages based on message type.

    Args:
        message_type: Type of message (expired, warning, reminder)
        days_remaining: Days remaining in trial
        dashboard_link: Link to user dashboard

    Returns:
        str: Formatted message for PR comment
    """
    messages = {
        "expired": (
            "**Your 14-day trial has expired!**\n\n"
            "You have already exhausted your 14th day trial period."
            " Please upgrade your subscription to continue new analysis.\n\n"
            f"Upgrade by visiting: [View Dashboard]({dashboard_link})"
        ),
        "warning": (
            f"**You're down to {days_remaining} days left in your trial!**\n\n"
            "Once the trial period is over, new analysis in-editor and PR analyses will pause."
            f"Unlock more power with the Standard Plan: [View Dashboard]({dashboard_link})"
        ),
        "reminder": (
            f"**You're down to {days_remaining} days left in your trial!**\n\n"
            "Once the trial period is over, new analysis in-editor and PR analyses will pause."
            f"Unlock more power with the Standard Plan: [View Dashboard]({dashboard_link})"
        ),
    }

    return messages.get(message_type, "")


async def handle_usage_and_trial_logic(
    user,
    github_username: str,
    order_status: str,
    tokens_usage: int,
    token_limit: int,
    repo_owner: dict,
    repo_data: dict,
    pr_details: dict,
    token: dict,
    dashboard_link: str,
    organization_id: str,
) -> tuple[bool, str]:
    """
    Handle usage percentage and trial logic dynamically based on order status.

    Args:
        user: User object
        github_username: GitHub username
        order_status: Order status (active/inactive)
        tokens_usage: Current token usage
        token_limit: Token limit for user
        repo_owner: Repository owner info
        repo_data: Repository data
        pr_details: PR details
        token: GitHub token
        dashboard_link: Dashboard link
        organization_id: Organization ID

    Returns:
        tuple: (should_continue_analysis, initial_message)
    """
    tokens_left = max(0, token_limit - tokens_usage)
    percentage_remaining = max(0, int((tokens_left / token_limit) * 100))
    initial_message = ""

    # Handle order status specific logic
    if order_status == "active":
        # For active orders, only show usage percentage warnings
        if not user.role and percentage_remaining <= 40:
            initial_message = (
                f"⚠️ **Your Codesherlock Usage!**\n\n"
                f"You're down to {tokens_left} tokens, (**{percentage_remaining}%**) of your allowance.\n\n"
                f"Once they're gone, new analysis in‑editor and PR analyses will pause.\n\n"
                f"You can upgrade your plan from here: [View Dashboard]({dashboard_link})."
            )

        # Check if tokens are exhausted
        if tokens_left == 0:
            await post_pull_request_comment(
                repo_owner["login"],
                repo_data["name"],
                pr_details["number"],
                (
                    f"⚠️ **Your Codesherlock Usage!**\n\n"
                    f"You're down to {tokens_left} tokens, (**{percentage_remaining}%**) of your allowance.\n\n"
                    f"To continue using CodeSherlock's analysis, please upgrade to a monthly subscription.\n\n"
                    f"You can upgrade your plan from here: [View Dashboard]({dashboard_link})."
                ),
                token["access_token"],
            )
            await send_usage_email(
                user.email,
                username=github_username,
                tokens_left=tokens_left,
                percentage_remaining=percentage_remaining,
            )

            return False, initial_message

    else:
        if user.role:
            return True, None
        # For inactive orders (trial users), handle trial logic
        async with AsyncSessionFactory() as db_session:
            try:
                user_org_row = await get_user_org_row(
                    db_session, user_id=user.userid, organization_id=organization_id
                )
            except Exception as e:
                logger.error(
                    f"Error fetching user_org_row: {e}",
                    extra={"user_id": user.userid, "organization_id": organization_id},
                )
                return False, None

        if user_org_row:
            if not user.role and user_org_row.get("created_at"):
                trial_start = user_org_row["created_at"]
                now = datetime.now(timezone.utc)
                days_since_creation = (now - trial_start).days
                logger.info(
                    f"User {user.userid} trial org days since creation: {days_since_creation}"
                )
            else:
                logger.info(
                    f"User {user.userid} trial org days since creation: {days_since_creation}"
                )
                days_since_creation = None
        else:
            # Fallback to original logic if no row found in user_organization
            if not user.role and hasattr(user, "created_at") and user.created_at:
                trial_start = user.created_at
                now = datetime.now(timezone.utc)
                days_since_creation = (now - trial_start).days
                logger.info(
                    f"User {user.userid} trial days since creation: {days_since_creation}"
                )
            else:
                days_since_creation = None
                logger.info(
                    f"User {user.userid} trial days since creation: {days_since_creation}"
                )

        # Proceed only if we have a valid trial start date
        if days_since_creation is not None:
            # Get dynamic trial configuration
            trial_config = get_trial_reminder_config(days_since_creation)

            message = get_trial_message(
                trial_config["message_type"],
                trial_config["days_remaining"],
                dashboard_link,
            )

            await post_pull_request_comment(
                repo_owner["login"],
                repo_data["name"],
                pr_details["number"],
                message,
                token["access_token"],
            )

            # If trial expired, stop analysis
            if trial_config["message_type"] == "expired":
                return False, initial_message

    return True, initial_message


async def process_pr_summary(pr_full_data, pr_file_details, model, factor: str = None):
    """
    Process the PR summary using LLM to generate a concise summary of the review findings.

    Args:
        pr_full_data (dict): Full PR data including title, body, author, labels, commits, and files changed.
        pr_file_details (list): List of file details with changes, additions, deletions, etc.

    Returns:
        dict: Dictionary containing the generated PR summary and usage data.
    """
    llm_service = get_router_service()
    prompt_service = PromptService()

    try:
        # Get the prompt for PR summary generation
        generate_pr_summary_prompt = await prompt_service.get_prompt(
            "generate_pr_summary",
            pr_full_data=pr_full_data,
            pr_file_details=pr_file_details,
        )

        # Create the prompt for LLM
        prompt = [
            {
                "role": "system",
                "content": "You are a senior software engineer who is great at analyzing and reviewing code. You excel at creating clear, concise summaries of pull requests that help reviewers understand the changes quickly.",
            },
            {
                "role": "user",
                "content": generate_pr_summary_prompt,
            },
        ]

        # Initialize usage tracking
        usage_data = LLMUsage()
        llm_response = ""

        # Generate the PR summary using LLM
        async for chunk in llm_service.agenerate_streaming_response(
            prompt=prompt,
            model=model,
            usage_data=usage_data,
        ):
            llm_response += chunk

        # Calculate cost
        usage_data.cost = calculate_llm_cost(usage_data=usage_data, model=model)

        # Return the summary with usage data
        return {
            "summary": llm_response,
            "usage_data": usage_data,
            "total_tokens": usage_data.input_tokens + usage_data.response_tokens,
            "total_cost": usage_data.cost,
        }

    except Exception as e:
        logger.error(
            f"Error processing PR summary: {e}",
            extra={"pr_number": pr_full_data.get("number", "unknown")},
        )
        return {"summary": "", "usage_data": None, "total_tokens": 0, "total_cost": 0.0}


async def process_pr_diagram(
    pr_summary: str, pr_file_details: list, model: str = DEFAULT_LLM_MODEL
):
    """
    Process the PR diagram generation using LLM to create a Graph-Spec JSON, then render as ASCII diagram.

    Args:
        pr_summary (str): The PR summary text to analyze for diagram generation.
        model (str): The LLM model to use for diagram generation.

    Returns:
        dict: Dictionary containing the generated ASCII diagram script and usage data.
    """
    llm_service = get_router_service()
    prompt_service = PromptService()

    try:
        # Get the prompt for PR diagram generation
        generate_pr_diagram_prompt = await prompt_service.get_prompt(
            "generate_pr_diagram",
            pr_summary=pr_summary,
            pr_file_details=pr_file_details,
        )

        # Create the prompt for LLM
        prompt = [
            {
                "role": "system",
                "content": "You are an expert at creating Graph-Spec JSON diagrams that depict code changes and architectural flows.",
            },
            {
                "role": "user",
                "content": f"{generate_pr_diagram_prompt}\n\nGenerate a Graph-Spec JSON diagram based on this PR summary.",
            },
        ]

        # Initialize usage tracking
        usage_data = LLMUsage()
        llm_response = ""

        # Generate the diagram using LLM
        async for chunk in llm_service.agenerate_streaming_response(
            prompt=prompt,
            model=model,
            usage_data=usage_data,
        ):
            llm_response += chunk

        # Calculate cost
        usage_data.cost = calculate_llm_cost(usage_data=usage_data, model=model)

        # Log the raw LLM response for debugging
        raw_response_length = len(llm_response.strip()) if llm_response else 0
        logger.info(
            f"Raw LLM diagram response length: {raw_response_length}",
            extra={"pr_summary_length": len(pr_summary) if pr_summary else 0},
        )

        # Log first 200 chars of raw response for debugging (if not empty)
        if llm_response.strip():
            preview = llm_response.strip()[:200]
            logger.info(
                f"Raw LLM diagram response preview: {preview}...",
                extra={"pr_summary_length": len(pr_summary) if pr_summary else 0},
            )

        # Extract and render Graph-Spec
        diagram_script = ""
        diagram_type = "Flow"  # Default diagram type
        if llm_response.strip():
            graph_spec = extract_graph_spec_body(llm_response)

            if graph_spec and graph_spec.get("nodes"):
                # Extract and format diagram type
                raw_diagram_type = graph_spec.get("diagram_type", "flow").lower()
                if raw_diagram_type in ["sequence", "sequencediagram"]:
                    diagram_type = "Sequence"
                elif raw_diagram_type in ["class", "classdiagram"]:
                    diagram_type = "Class"
                else:  # flow, flowchart, graph, or any other
                    diagram_type = "Flow"

                logger.info(
                    "Graph-Spec JSON extracted from LLM response",
                    extra={
                        "pr_summary_length": len(pr_summary) if pr_summary else 0,
                        "diagram_type": diagram_type,
                        "node_count": len(graph_spec.get("nodes", [])),
                        "edge_count": len(graph_spec.get("edges", [])),
                    },
                )

                # Render ASCII diagram from Graph-Spec
                ascii_diagram = render_ascii_diagram(graph_spec)

                # Render Mermaid diagram from Graph-Spec
                # mermaid_diagram = render_mermaid_diagram(graph_spec)

                if ascii_diagram and ascii_diagram.strip():
                    # Wrap in triple backticks for GitHub rendering
                    diagram_script = f"```text\n{ascii_diagram}\n```"

                    logger.info(
                        "ASCII diagram successfully rendered from Graph-Spec",
                        extra={
                            "pr_summary_length": len(pr_summary) if pr_summary else 0
                        },
                    )
                else:
                    # Explicitly ensure diagram_script is empty if rendering fails
                    diagram_script = ""
                    logger.warning(
                        "Failed to render ASCII diagram from Graph-Spec (empty result), skipping update",
                        extra={
                            "pr_summary_length": len(pr_summary) if pr_summary else 0
                        },
                    )
            else:
                logger.warning(
                    "No valid Graph-Spec JSON extracted from LLM response",
                    extra={
                        "pr_summary_length": len(pr_summary) if pr_summary else 0,
                        "full_llm_response": llm_response,  # Log full response for debugging
                    },
                )
        else:
            logger.warning(
                "LLM response is empty, no diagram generated",
                extra={"pr_summary_length": len(pr_summary) if pr_summary else 0},
            )

        return {
            "diagram": diagram_script,
            "diagram_type": diagram_type,
            "usage_data": usage_data,
            "total_tokens": usage_data.input_tokens + usage_data.response_tokens,
            "total_cost": usage_data.cost,
        }

    except Exception as e:
        logger.error(
            f"Error processing PR diagram: {e}",
            extra={"pr_summary_length": len(pr_summary) if pr_summary else 0},
            exc_info=True,
        )
        return {
            "diagram": "",
            "diagram_type": "Flow",
            "usage_data": None,
            "total_tokens": 0,
            "total_cost": 0.0,
        }


async def generate_and_update_diagram(
    pr_summary_text: str,
    pr_file_details: list,
    summary_comment_id,
    summary_body: str,
    repo_owner_login: str,
    repo_name: str,
    pr_number: int,
    access_token: str,
):
    try:
        logger.info(
            "Starting diagram generation",
            extra={
                "owner": repo_owner_login,
                "pr_number": pr_number,
                "comment_id": summary_comment_id,
            },
        )
        if not pr_summary_text:
            logger.warning(
                "PR summary is empty, skipping diagram generation",
                extra={"owner": repo_owner_login, "pr_number": pr_number},
            )
            return {"total_tokens": 0, "total_cost": 0.0}
        diagram_result = await process_pr_diagram(
            pr_summary=pr_summary_text,
            pr_file_details=pr_file_details,
            model=DEFAULT_LLM_MODEL,
        )
        diagram_script = diagram_result.get("diagram", "")
        logger.info(
            f"Diagram generation completed. Diagram length: {len(diagram_script) if diagram_script else 0}",
            extra={"owner": repo_owner_login, "pr_number": pr_number},
        )
        if diagram_script and summary_comment_id:
            updated_body = summary_body
            if diagram_script.strip():
                diagram_type = diagram_result.get("diagram_type", "Flow")
                updated_body += f"\n\n## {diagram_type} Diagram\n\n" + diagram_script
                logger.info(
                    f"Updating comment {summary_comment_id} with diagram",
                    extra={"owner": repo_owner_login, "pr_number": pr_number},
                )
                await update_pull_request_comment(
                    repo_owner_login,
                    repo_name,
                    summary_comment_id,
                    updated_body,
                    access_token,
                )
                logger.info(
                    "Diagram generated and comment updated successfully",
                    extra={"owner": repo_owner_login, "pr_number": pr_number},
                )
            else:
                logger.warning(
                    "Diagram script is empty after strip, skipping update",
                    extra={"owner": repo_owner_login, "pr_number": pr_number},
                )
            logger.info(
                f"Diagram generation used {diagram_result.get('total_tokens', 0)} tokens, cost: ${diagram_result.get('total_cost', 0.0)}",
                extra={"owner": repo_owner_login, "pr_number": pr_number},
            )
        else:
            logger.warning(
                f"No diagram generated or comment ID missing. Diagram: {bool(diagram_script)}, Comment ID: {summary_comment_id}",
                extra={"owner": repo_owner_login, "pr_number": pr_number},
            )
        return diagram_result
    except Exception as e:
        logger.error(
            f"Error generating or updating diagram: {str(e)}",
            extra={"owner": repo_owner_login, "pr_number": pr_number},
            exc_info=True,
        )
        return {"total_tokens": 0, "total_cost": 0.0}


async def process_file(
    file,
    factor: str,
    model: str,
    temperature: float,
    prompt_service: PromptService,
    mongo_db: AsyncIOMotorDatabase,
    github_login: str,
    repo_name: str,
    pr_number: int = None,
    commit_id: str = None,
    file_patch=None,
    pr_summary=None,
    preferred_characteristics: list = None,
    additional_instructions: list = [],
    adjacency: dict = None,
    file_imports_map: dict = None,
    max_depth: int = 2,
    impact_based_char_obj: dict = None,
):
    """
    Common file processing function that can be used for both PR and commit reviews.

    Args:
        file: File object with filename, status, new_content, patch
        factor: Analysis factor (e.g., 'power_analysis', 'owasp')
        prompt_service: PromptService instance
        mongo_db: MongoDB database instance
        github_login: GitHub username
        repo_name: Repository name
        pr_number: PR number (for PR reviews)
        commit_id: Commit hash (for commit reviews)
        file_patch: List of file patches (for PR reviews)
        preferred_characteristics: List of preferred characteristics (for PR reviews)
        additional_instructions: Additional instructions for analysis (for PR reviews)

    Returns:
        dict: Analysis results with file info, response, code language, and usage data
    """
    logger.info(f"Started processing file {file['filename']}")

    # Check for 'patch' in file object
    patch = file.get("patch")
    # Fallback: if patch is None or empty, look for it in file_patch list
    if not patch and file_patch:
        matched = next(
            (
                item.get("patch")
                for item in file_patch
                if item.get("filename") == file.get("filename")
            ),
            None,
        )
        patch = matched

    # If patch is still None or empty, exit early
    if not patch:
        logger.warning(
            f"No patch found for file {file.get('filename', 'unknown')}, skipping."
        )
        return

    req_usage_data = {}
    llm_service = get_router_service()
    try:
        cleaned_patch = clean_raw_patch(patch, file["filename"])
        if not cleaned_patch:
            return {
                "file": file,
                "response": "We are skipping the analysis for this file as there are no substantial changes.",
                "code_language": "",
            }
    except Exception as e:
        logger.error(
            f"Error occurred in cleaning raw patch: {str(e)}",
            extra={"patched_filename": file["filename"]},
        )
        cleaned_patch = patch

    is_jsx_tsx = 0
    extension = "." + file["filename"].split(".")[-1]
    if extension == ".jsx" or extension == ".tsx":
        is_jsx_tsx = 1
    else:
        is_jsx_tsx = 0

    # If the file is a JSX/TSX file, we can remove JSX elements
    # Uncomment the following lines if you want to enable JSX cleaning
    # This is currently disabled as per the original code

    # change here
    # try:
    #     cleaned_patch = remove_jsx_by_extension(cleaned_patch, file["filename"])

    #     if not cleaned_patch:
    #         return {
    #         "file": file,
    #         "response": "We are skipping the analysis for this file as there are no substantial changes.",
    #         "code_language": "",
    #     }

    # except Exception as e:
    #     logger.error(
    #     f"Error occurred in cleaning patch for jsx: {str(e)}",
    #     extra={"patched_filename": file["filename"]},
    # )
    #     cleaned_patch = patch

    # Step 1: always set code_to_analyze as the diff
    if file["status"] == "added" or file["status"] == "untracked":
        code_to_analyze = cleaned_patch
    elif file["status"] == "modified":
        code_to_analyze = patch
    else:
        code_to_analyze = ""

    # Step 2: start token count with diff
    diff_tokens = calculate_tokens(code_to_analyze)
    current_tokens = diff_tokens

    # If diff alone is too big, skip immediately
    if diff_tokens > MAX_INPUT_TOKENS:
        logger.warning(
            f"Skipping analysis for {file['filename']} — diff alone exceeds token limit ({diff_tokens}).",
            extra={
                "pr_number": pr_number,
                "commit_id": commit_id,
                "user_id": github_login,
                "repo_name": repo_name,
            },
        )
        return {
            "file": file,
            "response": f"Skipping analysis for {file['filename']} because the code changes are too large to process",
            "code_language": "",
        }

    if diff_tokens < SMALL_LINES_TOKEN_LIMIT and factor in [
        "owasp",
        "soc2",
        "cwe",
        "cwe_mitre",
        "cwe_kev",
    ]:
        logger.warning(
            f"Skipping {factor} analysis for {file['filename']} as it has too few lines.",
            extra={
                "pr_number": pr_number,
                "commit_id": commit_id,
                "user_id": github_login,
                "repo_name": repo_name,
            },
        )
        return {
            "file": file,
            "response": f"We are skipping the {factor} analysis for this file as there are no substantial changes.",
            "code_language": "",
        }

    # Step 3: build code_context with remaining budget
    code_context_parts: list[str] = []

    # Try adding new_content first if modified
    if file["status"] == "modified":
        new_content_text = (
            f"File: {file["filename"]}\n" f"Code Snippet:\n{file["new_content"]}\n"
        )
        new_content_tokens = calculate_tokens(new_content_text)
        if current_tokens + new_content_tokens <= MAX_INPUT_TOKENS:
            code_context_parts.append(new_content_text)
            current_tokens += new_content_tokens
        else:
            logger.warning(
                f"Skipping new_content for {file['filename']} due to token limit.",
                extra={
                    "pr_number": pr_number,
                    "commit_id": commit_id,
                    "user_id": github_login,
                    "repo_name": repo_name,
                },
            )

    context_chunks = []

    # Build context using dependency graph if provided; fallback to per-file import parse
    context_chunks = await traverse_dependencies_and_retrieve_chunks(
        mongo_db=mongo_db,
        file=file,
        adjacency=adjacency,
        file_imports_map=file_imports_map,
        max_depth=max_depth,
        pr_number=pr_number,
        commit_id=commit_id,
        user_id=github_login,
        repo_name=repo_name,
    )

    # Then add context chunks until limit is reached
    for chunk in context_chunks:
        chunk_text = (
            f"File: {chunk['file_path']}\n" f"Code Snippet:\n{chunk['code_snippet']}"
        )
        chunk_tokens = calculate_tokens(chunk_text)

        if current_tokens + chunk_tokens > MAX_INPUT_TOKENS:
            break

        code_context_parts.append(chunk_text)
        current_tokens += chunk_tokens

    # Step 4: finalize context
    code_context = "\n".join(code_context_parts)

    # Temporarily add impact-based characteristic to Factors for applicability check
    # Create a local copy of Factors to avoid modifying the global data
    local_factors = copy.deepcopy(Factors)

    if impact_based_char_obj and factor in local_factors:
        # Work on the local list only
        char_name = impact_based_char_obj.get("characteristic", "")
        existing_names = {
            obj.get("characteristic", "").lower() for obj in local_factors[factor]
        }

        if char_name.lower() not in existing_names:
            # Add the impact-based characteristic only to the local copy
            local_factors[factor].append(impact_based_char_obj)
            logger.info(
                f"Temporarily added impact-based characteristic '{char_name}' to local Factors for applicability check",
                extra={"patched_filename": file["filename"]},
            )

    if (is_jsx_tsx and factor == "power_analysis") or (
        diff_tokens <= SMALL_LINES_TOKEN_LIMIT and factor == "power_analysis"
    ):
        applicability_check_str = await prompt_service.get_prompt(
            "applicability_check_small_prompt", code=code_to_analyze, factor=factor
        )
    elif diff_tokens > SMALL_LINES_TOKEN_LIMIT and factor not in [
        "cwe",
        "soc2",
        "cwe_mitre",
        "cwe_kev",
    ]:
        applicability_check_str = await prompt_service.get_prompt(
            "applicability_check_prompt",
            code=code_to_analyze,
            factor=factor,
            local_factors=local_factors,
        )
    elif diff_tokens > SMALL_LINES_TOKEN_LIMIT and factor in [
        "cwe",
        "soc2",
        "cwe_mitre",
        "cwe_kev",
    ]:
        applicability_check_str = await prompt_service.get_prompt(
            "applicability_check_prompt_cwe_soc2", code=code_to_analyze, factor=factor
        )

    else:
        logger.warning(
            f"Invalid factor {factor} and/or code length {diff_tokens} for file {file['filename']}"
        )
        return {}

    applicability_check_prompt = [
        {
            "role": "system",
            "content": "You are a senior software engineer who is great at analyzing and reviewing code.",
        },
        {"role": "user", "content": applicability_check_str},
    ]
    applicability_usage_data = LLMUsage()
    applicability_check_response = {}
    llm_service = get_router_service()
    req_usage_data = {}

    try:
        applicability_start_time = datetime.now(timezone.utc)
        if factor in ["cwe_mitre", "cwe_kev"]:
            applicability_check_response = await cwe_applicability_check(
                prompt=applicability_check_prompt,
                file_name=file["filename"],
                llm_service=llm_service,
                usage_data=applicability_usage_data,
            )
        else:
            applicability_check_response = await applicability_check(
                prompt=applicability_check_prompt,
                file_name=file["filename"],
                llm_service=llm_service,
                usage_data=applicability_usage_data,
            )
        applicability_end_time = datetime.now(timezone.utc)
        logger.info(
            f"Applicability check completed in {applicability_end_time - applicability_start_time} for file {file['filename']}",
            extra={"patched_filename": file["filename"]},
        )

        applicability_usage_data.cost = calculate_llm_cost(
            applicability_usage_data, model
        )
        req_usage_data["applicability_check_" + factor] = applicability_usage_data

        if diff_tokens > SMALL_LINES_TOKEN_LIMIT:
            logger.info(
                "Filtered chars: %s",
                applicability_check_response.get("filtered_chars", []),
                extra={"patched_filename": file["filename"]},
            )

    except Exception as e:
        logger.error(
            "Error occurred while running applicability check for factor: %s, error: %s",
            factor,
            str(e),
        )

    # Build initial list of applicable characteristics
    filtered_chars = applicability_check_response.get("filtered_chars", []) or []

    filtered_instructions = ""

    if additional_instructions:
        applicability_check_prompt_add_inst_str = await prompt_service.get_prompt(
            "applicability_check_prompt_additional_instructions",
            code=code_to_analyze,
            additional_instructions=additional_instructions,
        )
        instruction_applicability_usage_data = LLMUsage()

        applicability_check_prompt_add_inst = [
            {
                "role": "system",
                "content": "You are a senior software engineer who is great at analyzing and reviewing code.",
            },
            {"role": "user", "content": applicability_check_prompt_add_inst_str},
        ]

        try:
            instruction_applicability_check_response = (
                await instruction_applicability_check(
                    prompt=applicability_check_prompt_add_inst,
                    file_name=file["filename"],
                    llm_service=llm_service,
                    usage_data=instruction_applicability_usage_data,
                )
            )

            instruction_applicability_usage_data.cost = calculate_llm_cost(
                instruction_applicability_usage_data, model
            )
            req_usage_data["applicability_check_instructions"] = (
                instruction_applicability_usage_data
            )

            logger.info(
                "Filtered instructions: %s",
                instruction_applicability_check_response.get(
                    "filtered_instructions", []
                ),
                extra={"patched_filename": file["filename"]},
            )

            filtered_instructions = "\n".join(
                instruction_applicability_check_response.get(
                    "filtered_instructions", []
                )
            )

        except Exception as e:
            logger.error(
                "Error occurred while running applicability check for additional instructions: error: %s",
                str(e),
            )
            filtered_instructions = ""

    # Log final characteristics that will be passed for analysis
    logger.info(
        "Final characteristics for analysis (applicability check): %s",
        filtered_chars,
        extra={"patched_filename": file["filename"]},
    )
    # Check if impact-based characteristic is in filtered_chars
    if impact_based_char_obj:
        impact_char_name = impact_based_char_obj.get("characteristic", "")
        if impact_char_name in filtered_chars:
            logger.info(
                f"Impact-based characteristic '{impact_char_name}' is applicable to this file",
                extra={"patched_filename": file["filename"]},
            )
        else:
            logger.info(
                f"Impact-based characteristic '{impact_char_name}' is not applicable to this file",
                extra={"patched_filename": file["filename"]},
            )

    if factor not in ["power_analysis", "owasp", "cwe", "cwe_mitre", "cwe_kev"]:
        prompts_dict = await prompt_service.get_prompt(
            "factor_analysis_prompt",
            factor_name=factor,
            applicable_chars=filtered_chars,
        )
    elif factor == "power_analysis":
        # Determine if is_jsx_tsx
        if is_jsx_tsx or diff_tokens <= SMALL_LINES_TOKEN_LIMIT:
            logger.info("Running small file power analysis")
            prompts_dict = await prompt_service.get_prompt(
                "power_analysis_small_prompt",
                factor_name="power_analysis_small",
                context=code_context,
                additional_instructions=filtered_instructions,
                pr_summary=pr_summary,
            )
        else:
            # filtered_chars contains all applicable characteristics (including impact-based if applicable)
            if filtered_chars and preferred_characteristics:
                filtered_chars = [
                    char
                    for char in filtered_chars
                    if char.lower() in preferred_characteristics
                ]

            if not filtered_chars and not filtered_instructions:
                return {
                    "file": file,
                    "response": f"We are skipping the analysis for this file as everything looks great.",
                    "code_language": "",
                }

            prompts_dict = await prompt_service.get_prompt(
                "power_analysis_prompt",
                factor_name=factor,
                context=code_context,
                applicable_chars=filtered_chars,
                additional_instructions=filtered_instructions,
                impact_based_characteristic=impact_based_char_obj,
                pr_summary=pr_summary,
            )

    elif factor == "owasp":
        prompts_dict = await prompt_service.get_prompt(
            "owasp_analysis_prompt",
            factor_name=factor,
            context=code_context,
            applicable_chars=filtered_chars,
            pr_summary=pr_summary,
        )

    elif factor in ["cwe", "cwe_mitre", "cwe_kev", "soc2"]:
        if not filtered_chars:
            return {
                "file": file,
                "response": f"We are skipping the analysis for this file as everything looks great.",
                "code_language": "",
            }
        logger.info(f"running {factor} analysis")

        prompts_dict = await prompt_service.get_prompt(
            "cwe_analysis_prompt",
            factor_name=factor,
            context=code_context,
            applicable_chars=filtered_chars,
            pr_summary=pr_summary,
        )

    pr_review_response = []  # Collect responses for each characteristic

    # Log all characteristics being processed (including impact-based)
    logger.info(
        f"Processing {len(prompts_dict)} characteristics for file {file['filename']}: {list(prompts_dict.keys())}",
        extra={"patched_filename": file["filename"]},
    )

    for index, (characteristic, char_prompt) in enumerate(prompts_dict.items()):
        char_usage_data = LLMUsage()
        char_response = ""
        llm_char_response = ""

        prompt = [
            {
                "role": "system",
                "content": "You are a senior software engineer who is great at analyzing and reviewing code.",
            },
            {
                "role": "user",
                "content": f"Code To Analyze:\n{code_to_analyze}\n{char_prompt}",
            },
        ]

        try:
            logger.info(
                f"Starting LLM call for characteristic '{characteristic}' (index {index + 1}/{len(prompts_dict)}) for file {file['filename']}",
                extra={
                    "patched_filename": file["filename"],
                    "characteristic": characteristic,
                },
            )

            if factor not in ["owasp", "cwe", "owasp", "cwe_mitre", "cwe_kev"]:
                char_heading = f"# {characteristic}\n\n"
                char_response += char_heading
            # Generating markdown response
            llm_start_time = datetime.now(timezone.utc)
            async for chunk in llm_service.agenerate_streaming_response(
                prompt=prompt,
                model=model,
                usage_data=char_usage_data,
                temperature=temperature,
            ):
                llm_char_response += chunk
            llm_end_time = datetime.now(timezone.utc)

            logger.info(
                f"LLM streaming completed for characteristic '{characteristic}' in {llm_end_time - llm_start_time}. Response length: {len(llm_char_response)} chars",
                extra={
                    "patched_filename": file["filename"],
                    "characteristic": characteristic,
                },
            )

            char_response += f"{llm_char_response}\n\n"

            logger.info(
                f"Starting md_to_json conversion for characteristic '{characteristic}'",
                extra={
                    "patched_filename": file["filename"],
                    "characteristic": characteristic,
                },
            )
            char_response_json = md_to_json(char_response, file["filename"], factor)

            logger.info(
                f"md_to_json completed for characteristic '{characteristic}'. Result type: {type(char_response_json)}, "
                f"Is dict: {isinstance(char_response_json, dict)}, Is list: {isinstance(char_response_json, list)}, "
                f"Is None: {char_response_json is None}",
                extra={
                    "patched_filename": file["filename"],
                    "characteristic": characteristic,
                },
            )

            # Check if this is the impact-based characteristic (if it was passed in)
            is_impact_based = (
                impact_based_char_obj
                and characteristic == impact_based_char_obj.get("characteristic")
            )
            if is_impact_based:
                # Log that we're processing the impact-based characteristic
                logger.info(
                    f"Processing impact-based characteristic '{characteristic}' for file {file['filename']}",
                    extra={"patched_filename": file["filename"]},
                )

            file_code = file["new_content"]

            # Ensure char_response_json is a list for char_issues_linenum_ext
            if char_response_json is None:
                logger.warning(
                    f"char_response_json is None for characteristic '{characteristic}', converting to empty list",
                    extra={
                        "patched_filename": file["filename"],
                        "characteristic": characteristic,
                    },
                )
                char_response_json = []
            elif isinstance(char_response_json, dict):
                logger.warning(
                    f"char_response_json is dict for characteristic '{characteristic}', converting to empty list",
                    extra={
                        "patched_filename": file["filename"],
                        "characteristic": characteristic,
                    },
                )
                char_response_json = []

            logger.info(
                f"Starting char_issues_linenum_ext for characteristic '{characteristic}'. "
                f"JSON data length: {len(char_response_json) if isinstance(char_response_json, list) else 'N/A'}, "
                f"File code length: {len(file_code) if file_code else 0} chars",
                extra={
                    "patched_filename": file["filename"],
                    "characteristic": characteristic,
                },
            )

            char_response_linenum = char_issues_linenum_ext(
                char_response_json, file_code
            )

            logger.info(
                f"char_issues_linenum_ext completed for characteristic '{characteristic}'. "
                f"Result length: {len(char_response_linenum) if isinstance(char_response_linenum, list) else 'N/A'}",
                extra={
                    "patched_filename": file["filename"],
                    "characteristic": characteristic,
                },
            )

            # Log if impact-based characteristic has no issues
            if is_impact_based:
                has_issues = any(
                    char.get("issue_items", []) for char in char_response_linenum
                )
                logger.info(
                    f"Impact-based characteristic '{characteristic}' has issues: {has_issues}. Response: {char_response_linenum}",
                    extra={"patched_filename": file["filename"]},
                )

            pr_review_response.extend(char_response_linenum)

            char_usage_data.cost = calculate_llm_cost(char_usage_data, model)
            req_usage_data[characteristic] = char_usage_data

            logger.info(
                f"Successfully completed processing characteristic '{characteristic}' (index {index + 1}/{len(prompts_dict)}) for file {file['filename']}",
                extra={
                    "patched_filename": file["filename"],
                    "characteristic": characteristic,
                },
            )

        except Exception as e:
            logger.error(
                f"Error processing characteristic '{characteristic}' (index {index + 1}/{len(prompts_dict)}) for file {file['filename']}: {e}",
                extra={
                    "patched_filename": file["filename"],
                    "characteristic": characteristic,
                },
                exc_info=True,
            )

    # Calculate total tokens and total cost
    total_tokens = 0
    total_cost = 0.0

    for usage in req_usage_data.values():
        total_tokens += getattr(usage, "input_tokens", 0) + getattr(
            usage, "response_tokens", 0
        )
        total_cost += getattr(usage, "cost", 0.0)

    return {
        "file": file,
        "response": pr_review_response,
        "code_language": applicability_check_response.get("language", ""),
        "usage_summary": {"total_tokens": total_tokens, "total_cost": total_cost},
        "req_usage_data": req_usage_data,
    }


async def pr_review_pipeline(pr_details, repo_data, installation_id, factor):
    model = DEFAULT_LLM_MODEL
    temperature = 0.9
    try:
        pr_process_start_time = datetime.now(timezone.utc)
        timing_metrics = {}
        repo_owner = repo_data.get("owner", {})
        github_username = pr_details.get("github_username")
        repo_owner_github_id = repo_data.get("owner", {}).get("id", None)
        repo_admin_username = repo_owner.get("login", "")

        async with AsyncSessionFactory() as db_session:
            try:
                # Get the stored GitHub installation token
                token = await fetch_installation_token_installid(
                    db_session, str(installation_id)
                )
                github_id = pr_details.get("github_user_id")
                user_id = await get_user_id_from_github_id(db_session, int(github_id))
                organization_details = await get_organization_id_from_github_id(
                    db_session=db_session,
                    platform_type_id=1,
                    platform_id=int(repo_owner_github_id),
                )
                
                matched_org_id = None
                if user_id is not None:
                    user_id = str(user_id)
                    user = await get_user_by_id(db_session, user_id)

                    # print(f"user {user}")
                    org_ids = await get_organization_id_for_user_id(
                        db_session=db_session, user_id=user_id
                    )

                    # print(f"org_ids {org_ids}")
                    for org_id, role in org_ids:
                        if organization_details["id"] == org_id:
                            matched_org_id = org_id

                            break
                            

                if user_id is None or matched_org_id is None:
                    signup_link = f"{FRONTEND_URL}/signup"
                    logger.warning(
                        "user id is None or install_id is None",
                        extra={"github_id": github_id, "install_id": installation_id},
                    )
                    await post_pull_request_comment(
                        repo_owner["login"],
                        repo_data["name"],
                        pr_details["number"],
                        f"We could not run your PR Review. We noticed that you are part of an Org. We require everyone who is part of an Org to SignUp via GitHub so we can track your individual usage and maximize on your usage capacity. Enroll into CodeSherlock system by signing up via GitHub using the [SignUp link]({signup_link}). Also, please note — every user pays for their own usage.",
                        token["access_token"],
                    )
                    return

                order_details = await sync_order_status(
                    db_session=db_session, user_id=user_id, org_id=matched_org_id
                )
                order_status = order_details.get("status")
                tokens_usage = await get_tokens_usage_by_user_id_org_id(
                    db_session=db_session,
                    user_id=user_id,
                    organization_id=matched_org_id,
                )

                await db_session.commit()

            except Exception as e:
                # print(f"derror {e}")
                await db_session.rollback()
                # Log the error for debugging, optionally send a user-friendly message
                logger.error(
                    f"Error occurred while retrieving usage details - {str(e)}",
                    extra={"user_id": user_id, "error": str(e)},
                )
                await post_pull_request_comment(
                    repo_owner["login"],
                    repo_data["name"],
                    pr_details["number"],
                    "We ran into an issue while retrieving your usage details. Please try again later or contact support@codesherlock.ai.",
                    token["access_token"],
                )
                return

        # Set token limit based on the order status
        if order_status == "active":
            token_limit = PAID_TOKENS_LIMIT
        else:
            token_limit = FREE_TOKENS_LIMIT

        # Use dynamic usage and trial logic based on order status
        dashboard_link = f"{FRONTEND_URL}/dashboard"
        should_continue, initial_message = await handle_usage_and_trial_logic(
            user=user,
            github_username=github_username,
            order_status=order_status,
            tokens_usage=tokens_usage,
            token_limit=token_limit,
            repo_owner=repo_owner,
            repo_data=repo_data,
            pr_details=pr_details,
            token=token,
            dashboard_link=dashboard_link,
            organization_id=matched_org_id,
        )

        if not should_continue:
            return


        pr_reviewers = [
            reviewer.get("login")
            for reviewer in pr_details.get("requested_reviewers", [])
        ]

        pr_details["reviewers"] = pr_reviewers

        codesherlock_config_file = {}
        codesherlock_config_file["filename"] = YAML_FILE_PATH
        file_content = await fetch_new_version(
            owner=repo_owner["login"],
            repo=repo_data["name"],
            filename=codesherlock_config_file["filename"],
            head_sha=pr_details["head_sha"],
            access_token=token["access_token"],
        )
        codesherlock_config_file["new_content"] = file_content["new_content"]
        pr_config = {}
        if codesherlock_config_file["new_content"]:
            try:
                pr_config = await parse_yaml_file(
                    codesherlock_config_file["new_content"]
                )
            except Exception as e:
                logger.error(
                    f"Error parsing codesherlock.yaml file: {str(e)}",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    },
                )

        if pr_config.get("target_branches") and pr_details.get(
            "base_branch"
        ) not in pr_config.get("target_branches"):
            logger.info(
                f"Skipping PR {pr_details['number']} because branch {pr_details.get('base_branch')} is not in the target branches {pr_config.get('target_branches')}",
                extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
            )

            await post_pull_request_status(
                repo_owner["login"],
                repo_data["name"],
                commit_sha=pr_details["head_sha"],
                state="success",
                description="CodeSherlock.AI has skipped the review.",
                access_token=token["access_token"],
            )
            return

        initial_comment_task = post_pull_request_comment(
            repo_owner["login"],
            repo_data["name"],
            pr_details["number"],
            "**CodeSherlock.AI** is currently reviewing the changes in this pull request.\n\n⏳ *Smaller PRs typically take 1–2 minutes, medium ones 3–4 minutes, and larger PRs may take up to 5–6 minutes.*",
            token["access_token"],
        )

        owasp_tip = (
            "### 💡 Tip\n"
            "Want to run additional checks on this PR?  \n"
            f"- Comment `@{GITHUB_APP_ID} analyze owasp` to trigger an **OWASP Top-10 security analysis**.  \n"
            f"- Comment `@{GITHUB_APP_ID} analyze cwe_mitre` to trigger a **CWE-MITRE mapping analysis**.  \n"
            f"- Comment `@{GITHUB_APP_ID} analyze cwe_kev` to trigger a **CWE-KEV (Known Exploited Vulnerabilities) analysis**.\n\n"
        )

        owasp_tip_task = post_pull_request_comment(
            repo_owner["login"],
            repo_data["name"],
            pr_details["number"],
            owasp_tip,
            token["access_token"],
        )

        status_task = post_pull_request_status(
            repo_owner["login"],
            repo_data["name"],
            commit_sha=pr_details["head_sha"],
            state="pending",
            description="CodeSherlock.AI is reviewing this PR... ",
            access_token=token["access_token"],
        )

        file_details_task = get_pull_request_files(
            repo_owner["login"],
            repo_data["name"],
            pr_details["number"],
            token["access_token"],
        )

        tasks = [
            initial_comment_task,
            owasp_tip_task,
            status_task,
            file_details_task,
        ]

        if initial_message:
            tasks.append(
                post_pull_request_comment(
                    repo_owner["login"],
                    repo_data["name"],
                    pr_details["number"],
                    initial_message,
                    token["access_token"],
                )
            )

        initial_comment_response, _, _, pr_file_details, *rest = await asyncio.gather(
            *tasks
        )

        file_patch = []

        # Check if any files are missing patches
        missing_patches = any(
            file.get("changes", 0) > 0 and not file.get("patch")
            for file in pr_file_details
        )

        if missing_patches:
            start_time = time.time()
            diff_patch = await get_pull_request_diff(
                repo_owner["login"],
                repo_data["name"],
                pr_details["number"],
                token["access_token"],
            )
            elapsed_time = time.time() - start_time
            logger.info(
                f"Time elapsed for get_pull_request_diff: {elapsed_time:.2f} seconds"
            )

            file_patch = parse_diff_to_file_objects(diff_patch)

            # Step 3: convert list to filename -> patch string map
            file_patch_map = {}

            for f in file_patch:
                raw_patch = f.get("patch")
                if not raw_patch:
                    continue

                # Clean and trim the patch
                patch = raw_patch.replace("\r", "").strip()
                patch = trim_patch_before_hunks(patch)

                file_patch_map[f["filename"]] = patch

            # Step 4: update missing patches
            for file in pr_file_details:
                if not file.get("patch") and file_patch_map.get(file["filename"]):
                    file["patch"] = file_patch_map[file["filename"]]

        initial_comment_id = initial_comment_response["id"]

        logger.info(
            "Starting to analyze files",
            extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
        )

        relevant_files = [
            file
            for file in pr_file_details
            if is_code_file(file["filename"])
            and file["status"] in ("added", "modified")
        ]
        pr_summary = {"summary": ""}
        diagram_task = None  # Initialize diagram_task
        repo_structure = []  # Initialize repo_structure

        # Extract ref for repository structure fetch
        # Priority: base_sha (commit SHA - most reliable) > base_branch (branch name)
        ref = pr_details.get("base_sha") or pr_details.get("base_branch")
        
        if not ref:
            logger.warning(
                "Missing both base_sha and base_branch in PR details - cannot fetch repository structure",
                extra={
                    "owner": repo_owner["login"],
                    "pr_number": pr_details.get("number"),
                    "available_fields": list(pr_details.keys())
                }
            )

        if factor not in {"owasp", "cwe_mitre", "cwe_kev"}:
            # Step: Fetch complete PR data and repo structure in parallel
            logger.info(
                "Phase 3: Fetching PR data and repository structure in parallel",
                extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
            )

            try:
                # Prepare tasks for parallel execution
                tasks = [
                    get_github_pr_data(
                        access_token=token["access_token"],
                        repository={
                            "owner": repo_owner["login"],
                            "name": repo_data["name"],
                            "platform_id": repo_owner_github_id,
                        },
                        pr_number=pr_details["number"],
                    )
                ]
                
                # Only fetch repo structure if we have a valid ref
                if ref:
                    tasks.append(
                        get_github_repo_structure(
                            access_token=token["access_token"],
                            owner=repo_owner["login"],
                            repo=repo_data["name"],
                            ref=ref,
                            user_id=str(user_id) if user_id else None,
                        )
                    )
                else:
                    logger.warning(
                        "Skipping repository structure fetch - no valid ref available",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                        }
                    )
                
                # Execute tasks in parallel
                results = await asyncio.gather(*tasks)
                pr_full_data = results[0]
                repo_structure = results[1] if len(results) > 1 else []
                logger.info(
                    f"Fetched PR data and {len(repo_structure)} files from repository structure",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    },
                )
            except HTTPException as e:
                logger.error(
                    f"Failed to fetch repository structure: {e.detail}",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                        "status_code": e.status_code,
                        "detail": e.detail,
                    },
                )
                repo_structure = []  # Continue without missing dependency detection
                logger.warning(
                    "Continuing PR review without missing dependency detection",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    },
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error fetching repository structure: {str(e)}",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    },
                    exc_info=True,
                )
                repo_structure = []  # Continue without missing dependency detection
                logger.warning(
                    "Continuing PR review without missing dependency detection",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    },
                )

            pr_summary = await process_pr_summary(
                pr_full_data=pr_full_data,
                pr_file_details=pr_file_details,
                model=DEFAULT_LLM_MODEL,
                factor=factor,
            )
        else:
            # For OWASP/CWE, only fetch repo structure (no PR summary needed)
            logger.info(
                "Phase 3: Fetching repository structure for OWASP/CWE analysis",
                extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
            )

            if not ref:
                logger.warning(
                    "Cannot fetch repository structure: missing both base_sha and base_branch",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    }
                )
                repo_structure = []
            else:
                try:
                    repo_structure = await get_github_repo_structure(
                        access_token=token["access_token"],
                        owner=repo_owner["login"],
                        repo=repo_data["name"],
                        ref=ref,
                        user_id=str(user_id) if user_id else None,
                    )
                    logger.info(
                        f"Fetched {len(repo_structure)} files from repository structure",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                        },
                    )
                except HTTPException as e:
                    logger.error(
                        f"Failed to fetch repository structure: {e.detail}",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                            "status_code": e.status_code,
                            "detail": e.detail,
                        },
                    )
                    repo_structure = []  # Continue without missing dependency detection
                    logger.warning(
                        "Continuing PR review without missing dependency detection",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                        },
                    )
                except Exception as e:
                    logger.error(
                        f"Unexpected error fetching repository structure: {str(e)}",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                        },
                        exc_info=True,
                    )
                    repo_structure = []  # Continue without missing dependency detection
                    logger.warning(
                        "Continuing PR review without missing dependency detection",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                        },
                    )

        summary_body = pr_summary.get("summary", "")

        # Post PR summary and get comment ID
        summary_comment_response = await post_pull_request_comment(
            repo_owner["login"],
            repo_data["name"],
            pr_details["number"],
            summary_body,
            token["access_token"],
        )
        summary_comment_id = summary_comment_response.get("id")

        # Generate and update diagram asynchronously
        diagram_task = asyncio.create_task(
            generate_and_update_diagram(
                pr_summary_text=pr_summary.get("summary", ""),
                pr_file_details=pr_file_details,
                summary_comment_id=summary_comment_id,
                summary_body=summary_body,
                repo_owner_login=repo_owner["login"],
                repo_name=repo_data["name"],
                pr_number=pr_details["number"],
                access_token=token["access_token"],
            )
        )
        logger.info(
            f"Diagram generation task created",
            extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
        )

        # Create impact-based characteristic ONCE at PR level (if applicable)
        impact_based_char_obj = None
        impact_usage_data = LLMUsage()
        if pr_summary and factor not in {"owasp", "cwe_mitre", "cwe_kev"}:
            try:
                prompt_service_temp = PromptService()
                impact_prompt_str = await prompt_service_temp.get_prompt(
                    "impact_based_characteristic_prompt",
                    factor_name=factor,
                    pr_summary=pr_summary["summary"],
                )
                impact_prompt = [
                    {
                        "role": "system",
                        "content": "You are a senior software engineer who creates new analysis characteristics based on PR Impact descriptions to cover issues not already addressed by existing characteristics.",
                    },
                    {"role": "user", "content": impact_prompt_str},
                ]

                llm_service_temp = get_router_service()
                impact_char_obj = await impact_based_characteristic_pick(
                    prompt=impact_prompt,
                    usage_data=impact_usage_data,
                    llm_service=llm_service_temp,
                )

                # If a new characteristic was created, check if it already exists
                if impact_char_obj:
                    char_name = impact_char_obj.get("characteristic", "")

                    # Check if it exists in the Factors list (to avoid duplicates)
                    from app.services.data import Factors as _FactorsData

                    factor_characteristics = _FactorsData.get(factor, [])
                    all_existing_names = {
                        obj.get("characteristic", "").lower()
                        for obj in factor_characteristics
                    }

                    if char_name.lower() not in all_existing_names:
                        # Add example field if missing (required for Factors structure)
                        if "example" not in impact_char_obj:
                            impact_char_obj["example"] = IMPACT_DUMMY_EXAMPLE

                        impact_based_char_obj = impact_char_obj
                        logger.info(
                            "New impact-based characteristic created at PR level: %s",
                            char_name,
                            extra={
                                "owner": repo_owner["login"],
                                "pr_number": pr_details["number"],
                            },
                        )
                        impact_usage_data.cost = calculate_llm_cost(
                            impact_usage_data, model
                        )
                    else:
                        logger.info(
                            "Impact-based characteristic '%s' already exists in Factors - skipping",
                            char_name,
                            extra={
                                "owner": repo_owner["login"],
                                "pr_number": pr_details["number"],
                            },
                        )
                else:
                    logger.info(
                        "No new impact-based characteristic needed",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                        },
                    )
            except Exception as e:
                logger.error(
                    "Error occurred while deriving characteristic from PR Impact: %s",
                    str(e),
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    },
                )

        # First, create a mapping of files to their fetch task
        fetch_tasks = [
            fetch_new_version(
                repo_owner["login"],
                repo_data["name"],
                file["filename"],
                pr_details["head_sha"],
                token["access_token"],
            )
            for file in relevant_files
        ]

        # Run all fetches concurrently
        new_contents = await asyncio.gather(*fetch_tasks)

        # Append the results back to the file objects
        for file, new_content in zip(relevant_files, new_contents):
            file["new_content"] = new_content["new_content"]

        # ============================================================================
        # PHASE 5: MISSING DEPENDENCY DETECTION
        # ============================================================================
        # Step 5.1: Extract import lines from all PR files
        logger.info(
            "Phase 5.1: Extracting import lines from PR files",
            extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
        )

        pr_imports_dict = {}
        try:
            pr_imports_dict = await extract_import_lines_from_pr_files_as_dict(
                pr_files=[
                    {
                        "path": file["filename"],
                        "content": file["new_content"],
                        "language": detect_language_from_filename(file["filename"])
                    }
                    for file in relevant_files
                ]
            )

            logger.info(
                f"Import extraction completed for {len(pr_imports_dict)} files",
                extra={
                    "owner": repo_owner["login"],
                    "pr_number": pr_details["number"],
                },
            )
        except Exception as e:
            logger.error(
                f"Error extracting imports from PR files: {str(e)}",
                extra={
                    "owner": repo_owner["login"],
                    "pr_number": pr_details["number"],
                },
                exc_info=True,
            )
            pr_imports_dict = {}  # Continue without missing dependency detection

        # Step 5.2: Identify missing dependencies via parallel LLM calls
        missing_file_paths = set()

        if pr_imports_dict and repo_structure:
            logger.info(
                "Phase 5.2: Identifying missing dependencies via LLM",
                extra={
                    "owner": repo_owner["login"],
                    "pr_number": pr_details["number"],
                },
            )

            # Prepare PromptService instance
            prompt_service = PromptService()

            # Prepare LLM service for missing dependency detection
            llm_service = get_router_service()

            # Prepare parallel LLM tasks for each file
            async def identify_missing_deps_for_file(file_data):
                """Helper to identify missing dependencies for a single file"""
                try:
                    file_path = file_data["file_path"]
                    import_lines = file_data.get("import_lines", [])

                    if not import_lines:
                        return []

                    # Get list of PR file paths
                    pr_file_paths = [f["filename"] for f in relevant_files]

                    # Step 1: Generate prompt
                    prompt_text = await prompt_service._identify_missing_dependencies_prompt(
                        file_path=file_path,
                        extracted_imports=file_data,  # Pass entire dict with file_path, language, import_lines
                        repo_structure=repo_structure,
                        pr_file_paths=pr_file_paths,
                    )

                    # Step 2: Call LLM with prompt (includes JSON parsing and validation)
                    missing_deps_result = await identify_missing_dependencies_llm_call(
                        prompt=prompt_text,
                        file_path=file_path,
                        llm_service=llm_service,
                    )

                    # Step 3: Extract missing files from LLM response
                    return missing_deps_result.get("missing_files", [])

                except Exception as e:
                    logger.error(
                        f"Error identifying missing deps for {file_data.get('file_path', 'unknown')}: {str(e)}",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                        },
                    )
                    return []

            # Run parallel LLM calls
            try:
                missing_deps_results = await asyncio.gather(
                    *[
                        identify_missing_deps_for_file(file_data)
                        for file_data in pr_imports_dict.values()
                    ],
                    return_exceptions=True,
                )

                # Collect all unique missing file paths
                for result in missing_deps_results:
                    if isinstance(result, list):
                        missing_file_paths.update(result)

                logger.info(
                    f"Identified {len(missing_file_paths)} missing dependency files",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                        "missing_files": list(missing_file_paths),
                    },
                )

            except Exception as e:
                logger.error(
                    f"Error during parallel missing dependency detection: {str(e)}",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    },
                    exc_info=True,
                )
        else:
            # Initialize PromptService even if we skip missing dependency detection
            prompt_service = PromptService()
            if not pr_imports_dict:
                logger.info(
                    "Skipping missing dependency detection - no imports extracted",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    },
                )
            if not repo_structure:
                logger.info(
                    "Skipping missing dependency detection - no repo structure available",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                    },
                )

        # Step 5.3: Fetch missing files in batch
        if missing_file_paths:
            logger.info(
                f"Phase 5.3: Fetching {len(missing_file_paths)} missing dependency files",
                extra={
                    "owner": repo_owner["login"],
                    "pr_number": pr_details["number"],
                    "requested_files": list(missing_file_paths),
                },
            )

            try:
                missing_files_content = await get_github_files_content_batch(
                    owner=repo_owner["login"],
                    repo=repo_data["name"],
                    file_paths=list(missing_file_paths),
                    ref=ref,  # ← ADDED: Use same ref as repo structure fetch
                    access_token=token["access_token"],
                )

                # Check for partial failures
                fetched_count = len(missing_files_content)
                requested_count = len(missing_file_paths)

                if fetched_count < requested_count:
                    failed_files = missing_file_paths - set(
                        missing_files_content.keys()
                    )
                    logger.warning(
                        f"Partial failure: Fetched {fetched_count}/{requested_count} missing dependency files",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                            "fetched_count": fetched_count,
                            "requested_count": requested_count,
                            "failed_files": list(failed_files),
                        },
                    )
                else:
                    logger.info(
                        f"Successfully fetched all {fetched_count} missing dependency files",
                        extra={
                            "owner": repo_owner["login"],
                            "pr_number": pr_details["number"],
                        },
                    )

                # Add missing files to relevant_files with status="context"
                for file_path, content in missing_files_content.items():
                    if content:  # Only add if content was successfully fetched
                        relevant_files.append(
                            {
                                "filename": file_path,
                                "status": "context",  # Special status for missing dependency files
                                "new_content": content,
                                "patch": None,  # No patch for context files
                                "additions": 0,
                                "deletions": 0,
                                "changes": 0,
                            }
                        )

                logger.info(
                    f"Added {len(missing_files_content)} missing dependency files to context",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                        "added_files": list(missing_files_content.keys()),
                    },
                )

            except Exception as e:
                logger.error(
                    f"Error fetching missing dependency files: {str(e)}",
                    extra={
                        "owner": repo_owner["login"],
                        "pr_number": pr_details["number"],
                        "requested_count": len(missing_file_paths),
                    },
                    exc_info=True,
                )
        else:
            logger.info(
                "No missing dependency files identified",
                extra={
                    "owner": repo_owner["login"],
                    "pr_number": pr_details["number"],
                },
            )

        # Continue with existing flow (prompt_service already initialized above)
        # Note: prompt_service is initialized in Phase 5 above

        preferred_characteristics = pr_config.get("preferred_characteristics", [])

        additional_instructions = pr_config.get("additional_instructions", [])

        mongo_db = get_mongo_db()
        chunking_start_time = datetime.now(timezone.utc)
        # Chunk code files and save to db
        try:
            for file in relevant_files:
                chunk_ids = await chunk_code_and_save_to_db(
                    file["new_content"],
                    mongo_db,
                    repo_owner["login"],
                    file["filename"],
                    repo_data["name"],
                    pr_details["number"],
                )
                if not chunk_ids:
                    logger.warning(f"No chunks inserted for file {file['filename']}")

        except Exception as e:
            logger.error(f"Error occured while creating context {e}")

        chunking_end_time = datetime.now(timezone.utc)
        timing_metrics["chunking_seconds"] = _duration_seconds(
            chunking_start_time, chunking_end_time
        )

        # After chunking, parse all files to build dependency graph (adjacency list)
        adjacency_start_time = datetime.now(timezone.utc)
        adjacency, file_imports_map = await build_adjacency(relevant_files)
        adjacency_end_time = datetime.now(timezone.utc)
        timing_metrics["adjacency_build_seconds"] = _duration_seconds(
            adjacency_start_time, adjacency_end_time
        )

        # Process each file with its corresponding old version, passing adjacency and max_depth
        file_processing_start_time = datetime.now(timezone.utc)
        results = await asyncio.gather(
            *[
                process_file(
                    file=file,
                    factor=factor,
                    model=model,
                    temperature=temperature,
                    prompt_service=prompt_service,
                    mongo_db=mongo_db,
                    github_login=repo_owner["login"],
                    repo_name=repo_data["name"],
                    pr_number=pr_details["number"],
                    file_patch=file_patch,
                    pr_summary=pr_summary["summary"],
                    preferred_characteristics=preferred_characteristics,
                    additional_instructions=additional_instructions,
                    adjacency=adjacency,
                    file_imports_map=file_imports_map,
                    max_depth=pr_config.get("max_depth", 2),
                    impact_based_char_obj=impact_based_char_obj,
                )
                for file in relevant_files
            ]
        )
        file_processing_end_time = datetime.now(timezone.utc)
        timing_metrics["file_processing_seconds"] = _duration_seconds(
            file_processing_start_time, file_processing_end_time
        )

        pr_review_summary = ""
        pr_review_full = ""
        pr_review_line_comments = []

        logger.info(
            "All files analyzed. Constructing markdown..",
            extra={"sender": github_username, "pr_number": pr_details["number"]},
        )
        markdown_build_start_time = datetime.now(timezone.utc)
        try:
            for result in results:
                if result:
                    response = result.get("response", [])
                    file = result.get("file", {})
                    code_language = result["code_language"]

                    # Constructing the Full Review markdown
                    if response:
                        pr_review_summary += f"## File Name: {file['filename']}\n\n"
                        pr_review_full += f"## File Name: {file['filename']}\n\n"
                        if type(response) == str:
                            pr_review_summary += f"{response}\n\n"
                            pr_review_full += f"{response}\n\n"
                            continue

                        # file_markdown = json_to_md_analysis(response, code_language)
                        # if file_markdown:
                        #     pr_review_full += (
                        #         f"## File Name: {file['filename']}\n\n{file_markdown}\n\n"
                        #     )

                        file_characteristic_data = defaultdict(dict)
                        valid_response = []

                        # Constructing line comments markdown
                        file_line_comments = {
                            "filename": file["filename"],
                            "line_comments": [],
                        }
                        # Track impact-based characteristic name if available
                        # We need to identify it from the response data or pass it through
                        # For now, we'll check if characteristic has a specific marker or handle empty issue_items differently

                        for char_el in response:
                            if not char_el:
                                continue

                            issue_items = char_el.get("issue_items", [])
                            valid_issue_items = []
                            characteristic_name = char_el.get("characteristic", "")

                            for issue_item in issue_items:
                                issue_markdown = json_to_md_issue_color_formatted(
                                    issue_item,
                                    code_language,
                                    characteristic_name,
                                )
                                if not issue_markdown:
                                    continue

                                line_comment = {
                                    "start_line": issue_item.get("start_line"),
                                    "end_line": issue_item.get("end_line"),
                                    "comment": issue_markdown,
                                    "valid": True,
                                }
                                if line_comment.get("start_line"):
                                    file_line_comments["line_comments"].append(
                                        line_comment
                                    )

                                    validate_comment_line_numbers(
                                        file["patch"],
                                        file["filename"],
                                        line_comment,
                                    )
                                    if line_comment["valid"]:
                                        valid_issue_items.append(issue_item)

                                        file_characteristic_data[characteristic_name][
                                            issue_item["severity"]
                                        ] = (
                                            file_characteristic_data[
                                                characteristic_name
                                            ].get(issue_item["severity"], 0)
                                            + 1
                                        )

                            # Include characteristic even if no valid issue items (for impact-based characteristics)
                            # We check if it's likely an impact-based characteristic by checking if it has description but no issues
                            # This is a heuristic - ideally we'd pass a flag, but this works for now
                            is_likely_impact_based = (
                                not valid_issue_items
                                and char_el.get("description_of_characteristic")
                                and len(issue_items)
                                == 0  # Had no issues at all, not just invalid ones
                            )

                            if valid_issue_items or is_likely_impact_based:
                                valid_char_el = {
                                    **char_el,
                                    "issue_items": valid_issue_items,
                                }
                                valid_response.append(valid_char_el)

                                # Log if we're including an impact-based characteristic with no issues
                                if is_likely_impact_based:
                                    logger.info(
                                        f"Including impact-based characteristic '{characteristic_name}' with no issues in output",
                                        extra={"patched_filename": file["filename"]},
                                    )

                        pr_review_line_comments.append(file_line_comments)
                        pr_review_summary += await format_severity_characteristic_data(
                            file_characteristic_data
                        )
                        pr_review_full += json_to_md_analysis(
                            valid_response, code_language
                        )

        except Exception as e:
            logger.error(
                f"Error occured while md construction:{str(e)}",
                extra={"sender": github_username, "pr_number": pr_details["number"]},
            )
        finally:
            markdown_build_end_time = datetime.now(timezone.utc)
            timing_metrics["markdown_build_seconds"] = _duration_seconds(
                markdown_build_start_time, markdown_build_end_time
            )

        if pr_review_summary:
            logger.info(
                "Final response markdown generated and posting...",
                extra={"sender": github_username, "pr_number": pr_details["number"]},
            )
            await post_pull_request_comment(
                repo_owner["login"],
                repo_data["name"],
                pr_details["number"],
                pr_review_summary,
                token["access_token"],
            )

        for file_line_comment in pr_review_line_comments:
            try:
                filename = file_line_comment["filename"]
                line_comments = file_line_comment["line_comments"]
                file = next(
                    (f for f in relevant_files if f["filename"] == filename), None
                )
                # Check for 'patch' in file object
                patch = file.get("patch")
                # Fallback: if patch is None or empty, look for it in file_patch list
                if not patch and file_patch:
                    matched = next(
                        (
                            item.get("patch")
                            for item in file_patch
                            if item.get("filename") == file.get("filename")
                        ),
                        None,
                    )
                    patch = matched
                patch = patch.replace("\r", "").strip()
                patch = trim_patch_before_hunks(patch)

            except Exception as e:
                logger.error(
                    f"Error occured while validating line numbers: {str(e)}",
                    extra={
                        "sender": github_username,
                        "pr_number": pr_details["number"],
                    },
                )
                continue

            for line_comment in line_comments:
                if line_comment["valid"]:
                    logger.info(
                        f"Posting comment at {line_comment['start_line']}-{line_comment['end_line']} in file {filename}..."
                    )
                    try:
                        await post_pull_request_line_comment(
                            owner=repo_owner["login"],
                            repo=repo_data["name"],
                            pr_number=pr_details["number"],
                            body=line_comment["comment"],
                            commit_id=pr_details["head_sha"],
                            path=filename,
                            start_line=line_comment["start_line"],
                            end_line=line_comment["end_line"],
                            access_token=token["access_token"],
                        )
                    except Exception as e:
                        logger.error(
                            f"Error occurred while posting line comment at lines {line_comment['start_line']}-{line_comment['end_line']}: {str(e)}"
                        )

        if pr_details["reviewers"]:
            reviewer_comment = "**CodeSherlock.AI** has completed its review. ✅"
            for reviewer in pr_details["reviewers"]:
                reviewer_comment = f"@{reviewer} {reviewer_comment}"

            logger.info("Posting Reviewer comment")
            await post_pull_request_comment(
                repo_owner["login"],
                repo_data["name"],
                pr_details["number"],
                reviewer_comment,
                token["access_token"],
            )

        await post_pull_request_status(
            repo_owner["login"],
            repo_data["name"],
            commit_sha=pr_details["head_sha"],
            state="success",
            description="CodeSherlock.AI has completed the review. PR is ready for merge.",
            access_token=token["access_token"],
        )

        await delete_pull_request_comment(
            repo_owner["login"],
            repo_data["name"],
            initial_comment_id,
            token["access_token"],
        )

        if pr_review_full:
            if pr_summary and isinstance(pr_summary, dict):
                summary_text = pr_summary.get("summary", "")
                if summary_text:
                    pr_review_full = summary_text + "\n\n" + pr_review_full

        # Wait for diagram generation task to complete (if it was created)
        diagram_result = {"total_tokens": 0, "total_cost": 0.0}
        try:
            logger.info(
                "Waiting for diagram generation task to complete...",
                extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
            )
            diagram_result = await diagram_task  # Get the return value
            logger.info(
                f"Diagram generation task completed. Tokens: {diagram_result.get('total_tokens', 0)}, Cost: ${diagram_result.get('total_cost', 0.0)}",
                extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
            )
        except Exception as e:
            logger.error(
                f"Error waiting for diagram task: {str(e)}",
                extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
                exc_info=True,
            )
            diagram_result = {"total_tokens": 0, "total_cost": 0.0}

        # Calculate total token usage and cost
        total_tokens_used = sum(
            result.get("usage_summary", {}).get("total_tokens", 0)
            for result in results
            if result
        )
        total_tokens_used += pr_summary.get("total_tokens", 0)
        total_tokens_used += diagram_result.get("total_tokens", 0)
        total_tokens_used += impact_usage_data.total_tokens

        total_cost = sum(
            result.get("usage_summary", {}).get("total_cost", 0)
            for result in results
            if result
        )
        total_cost += pr_summary.get("total_cost", 0)
        total_cost += diagram_result.get("total_cost", 0.0)
        total_cost += impact_usage_data.cost

        tokens_usage_after_analysis = 0

        async with AsyncSessionFactory() as db_session:
            try:
                if pr_review_full:
                    analysisid = str(uuid.uuid4())  # Generate a UUID string
                    await insert_pr_analysis(
                        db_session=db_session,
                        user_id=user_id,
                        content=pr_review_full,
                        factor=factor,
                        language=results[0].get("code_language", "unknown"),
                        pr_number=pr_details["number"],
                        repo_name=repo_data["name"],
                        repo_owner=repo_admin_username,
                        analysisid=analysisid,
                    )

                # Call the upsert function to record token usage
                await upsert_tokens_usage_user_id_org_id(
                    db_session=db_session,
                    user_id=user_id,
                    organization_id=matched_org_id,
                    tokens_used=total_tokens_used,
                    cost=total_cost,
                )
                created_at = datetime.now(timezone.utc)

                for result in results:
                    req_usage_data = (
                        result.get("req_usage_data", None) if result else None
                    )
                    if req_usage_data:
                        usage_ids = await insert_usage(
                            db_session=db_session,
                            usage_data=req_usage_data,
                            user_id=user_id,
                            model=model,
                            created_at=created_at,
                            organization_id=matched_org_id,
                        )

                        await insert_characteristic_usage(
                            db_session=db_session,
                            usage_data=req_usage_data,
                            usage_ids=usage_ids,
                            user_id=user_id,
                            created_at=created_at,
                            organization_id=matched_org_id,
                        )

                    await db_session.commit()

                    tokens_usage_after_analysis = (
                        await get_tokens_usage_by_user_id_org_id(
                            db_session, user_id, matched_org_id
                        )
                    )
            except Exception as e:
                await db_session.rollback()
                logger.error(
                    f"Error while saving PR analysis: {str(e)}",
                    extra={
                        "sender": github_username,
                        "pr_number": pr_details["number"],
                    },
                )
                tokens_usage_after_analysis = 0

        tokens_left_after_analysis = max(0, token_limit - tokens_usage_after_analysis)
        percentage_remaining_after_analysis = max(
            0, int((tokens_left_after_analysis / token_limit) * 100)
        )

        # Calculate initial percentage for threshold comparison
        tokens_left_initial = max(0, token_limit - tokens_usage)
        percentage_remaining_initial = max(
            0, int((tokens_left_initial / token_limit) * 100)
        )

        if order_status == "active" and not user.role:
            thresholds = [40, 20, 10, 0]
            crossed_thresholds = [
                t
                for t in thresholds
                if percentage_remaining_initial
                >= t
                >= percentage_remaining_after_analysis
            ]

            if crossed_thresholds:
                await send_usage_email(
                    user.email,
                    username=github_username,
                    tokens_left=tokens_left_after_analysis,
                    percentage_remaining=percentage_remaining_after_analysis,
                )

        delete_count = await delete_code_chunks(
            mongo_db=mongo_db,
            user_id=github_username,
            repo_name=repo_data["name"],
            pr_number=pr_details["number"],
        )
        logger.info(
            f"{delete_count} code chunks deleted for PR: {pr_details['number']}",
            extra={"owner": repo_owner["login"], "pr_number": pr_details["number"]},
        )

        total_complete_time = datetime.now(timezone.utc)
        timing_metrics["total_pipeline_seconds"] = _duration_seconds(
            pr_process_start_time, total_complete_time
        )
        logger.info(
            "PR review pipeline timing metrics",
            extra={
                "user_id": user_id,
                "pr_number": pr_details["number"],
                "repo_name": repo_data["name"],
                "files_analyzed_count": len(relevant_files),
                **timing_metrics,
            },
        )

        return results

    except Exception as e:
        logger.exception(
            f"Error occurred while processing PR: {str(e)}",
            extra={"user_id": user_id, "org_id": matched_org_id},
        )