import asyncio
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List

from app.dependencies import logger
from app.services.language_ext_and_applicability_check import identify_missing_dependencies_llm_call
from app.services.rag_services.imports_line_direct_extraction import extract_import_lines_from_pr_files_as_dict
from app.services.rag_services.imports_line_direct_extraction.import_line_service import detect_language_from_filename
from app.services.prompt_service import PromptService
from app.services.llm_endpoint_service import get_router_service, LLMRouterService

router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────────────

class CommitFile(BaseModel):
    filename: str
    status: str          # "added" | "modified" | "untracked"
    new_content: str


class MissingDependenciesRequest(BaseModel):
    repo_structure: List[str]   # All file paths in the local repo
    files: List[CommitFile]     # Commit files to analyse for missing imports


class MissingDependenciesResponse(BaseModel):
    status: int           # 0 = missing files found, 1 = nothing missing
    missing_files: List[str]


# ── Route ──────────────────────────────────────────────────────────────────────

@router.post("/missing-dependencies", response_model=MissingDependenciesResponse)
async def identify_missing_dependencies(
    payload: MissingDependenciesRequest,
    llm_service: LLMRouterService = Depends(get_router_service),
) -> MissingDependenciesResponse:
    """
    Given a list of commit/PR files and the full repo file structure, identify
    any internal files that are imported by the commit files but are NOT
    included in the commit (i.e. missing context dependencies).

    The check is done per-file in parallel (mirrors the PR review pipeline's
    Phase 5.1 / 5.2 logic) and the results are aggregated into a single
    deduplicated list.

    Returns:
        status=0 with missing_files list when missing deps are found.
        status=1 with empty list when all imports are accounted for.
    """
    repo_structure = payload.repo_structure
    files = payload.files
    commit_file_paths = [f.filename for f in files]

    # ── Step 1: Extract import lines from each commit file (parallel) ──────────
    logger.info(
        "Missing-deps check: extracting import lines",
        extra={"file_count": len(files)},
    )

    try:
        imports_dict = await extract_import_lines_from_pr_files_as_dict(
            pr_files=[
                {
                    "path": f.filename,
                    "content": f.new_content,
                    "language": detect_language_from_filename(f.filename),
                }
                for f in files
            ]
        )
    except Exception as exc:
        logger.error(f"Import extraction failed: {exc}", exc_info=True)
        imports_dict = {}

    if not imports_dict:
        return MissingDependenciesResponse(status=1, missing_files=[])

    # ── Step 2: Per-file LLM call to identify missing deps (parallel) ──────────
    prompt_service = PromptService()

    async def _identify_for_file(file_data: dict) -> List[str]:
        """Run a single LLM call for one file's imports."""
        try:
            file_path = file_data["file_path"]
            if not file_data.get("import_lines"):
                return []

            prompt_text = await prompt_service._identify_missing_dependencies_prompt(
                file_path=file_path,
                extracted_imports=file_data,   # dict with file_path, language, import_lines
                repo_structure=repo_structure,
                pr_file_paths=commit_file_paths,
            )

            result = await identify_missing_dependencies_llm_call(
                prompt=prompt_text,
                file_path=file_path,
                llm_service=llm_service,
            )
            return result.get("missing_files", [])

        except Exception as exc:
            logger.error(
                f"Missing-deps LLM call failed for {file_data.get('file_path', '?')}: {exc}",
                exc_info=True,
            )
            return []

    logger.info(
        "Missing-deps check: running parallel LLM calls",
        extra={"file_count": len(imports_dict)},
    )

    per_file_results = await asyncio.gather(
        *[_identify_for_file(file_data) for file_data in imports_dict.values()],
        return_exceptions=True,
    )

    # ── Step 3: Aggregate and deduplicate ─────────────────────────────────────
    all_missing: set[str] = set()
    for result in per_file_results:
        if isinstance(result, Exception):
            continue
        all_missing.update(result)

    # Exclude files that are already part of the commit
    all_missing -= set(commit_file_paths)

    if not all_missing:
        return MissingDependenciesResponse(status=1, missing_files=[])

    return MissingDependenciesResponse(
        status=0,
        missing_files=sorted(all_missing),
    )
