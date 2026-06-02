import base64, re, httpx
from app.api.pr_details import (
    get_pull_request_files_new_version,
    get_pull_request_files_older_version,
)
from app.dependencies import logger


async def fetch_old_version(
    owner: str, repo: str, file: str, base_sha: str, access_token: str
):
    """Fetch the old version content of a modified file."""
    if file["status"] != "modified":
        return {**file, "old_content": None}  # Skip fetching for non-modified files

    try:
        old_version_content = await get_pull_request_files_older_version(
            owner,
            repo,
            file["filename"],
            base_sha,  # Pass the base commit SHA
            access_token,
        )

        # Extract file content (GitHub API returns base64-encoded content)
        file_content = base64.b64decode(old_version_content.get("content", "")).decode(
            "utf-8"
        )

        return {**file, "old_content": file_content}

    except Exception as e:
        logger.error(
            f"Failed to fetch old version for {file['filename']}",
            extra={"patched_filename": file["filename"], "error": str(e)},
        )
        return {**file, "old_content": None}  # Handle failure gracefully


async def fetch_new_version(
    owner: str, repo: str, filename: str, head_sha: str, access_token: str
):
    """Fetch the new version content of a modified file."""
    if not access_token or len(access_token.strip()) == 0:
        logger.error("Invalid access token provided.")
        return {"new_content": None}

    try:
        new_version_content = await get_pull_request_files_new_version(
            owner,
            repo,
            filename,
            head_sha,  # Pass the head commit SHA
            access_token,
        )

        if not new_version_content:
            logger.warning(f"File content not found: {filename}", extra={"patched_filename": filename, "owner": owner, "repo": repo})
            return {"new_content": None}

        # Extract file content (GitHub API returns base64-encoded content)
        file_content = base64.b64decode(new_version_content.get("content", "")).decode(
            "utf-8"
        )

        return {"new_content": file_content}
    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error occurred while fetching new version for {filename}: {e}",
            extra={"patched_filename": filename, "status_code": e.response.status_code, "owner": owner, "repo": repo}
        )
        return {"new_content": None} 

    except Exception as e:
        logger.error(
            f"Unexpected error while fetching new versionfor {filename}",
            extra={"patched_filename": filename, "error": str(e)},
        )
        return {"new_content": None} 

def parse_diff_to_file_objects(diff_text: str) -> list[dict]:
    """
    Parses a raw GitHub diff response into an array of objects with filename and patch.

    :param diff_text: Raw diff text from GitHub's .diff endpoint
    :return: List of dictionaries, each with 'filename' and 'patch' keys
    """
    if not diff_text:
        return []

    result = []

    # Split the diff by the standard diff file header
    # Each file section starts with "diff --git"
    file_sections = diff_text.split("diff --git ")

    # Skip the first empty element from the split
    if file_sections and not file_sections[0].strip():
        file_sections = file_sections[1:]

    for section in file_sections:
        if not section.strip():
            continue

        lines = section.split("\n")

        # Extract filename from diff line like: diff --git a/foo b/bar (1).cs
        file_path_line = lines[0].strip()

        # Match pattern like: a/old_filename b/new_filename (handles spaces and parens)
        match = re.match(r'^a/(.+) b/(.+)$', file_path_line)
        if match:
            filename = match.group(2).strip()
        else:
            filename = "unknown_file"

        # Find the start of the actual patch content (first @@ line)
        patch_start_index = -1
        for i, line in enumerate(lines):
            if line.startswith("@@"):
                patch_start_index = i
                break

        # Handle special cases like binary files or new/deleted files
        status = "modified"  # Default status
        if "Binary files" in "\n".join(lines[:5]):
            status = "binary"
            patch = None
        elif patch_start_index == -1:
            # No patch found, could be a rename without changes or other special case
            patch = ""
        else:
            # Extract the patch content including the @@ line
            patch = "\n".join(
                ["diff --git " + file_path_line]
                + lines[1:patch_start_index]
                + lines[patch_start_index:]
            )

        # Determine file status from diff headers
        if any(line.startswith("new file mode") for line in lines[:5]):
            status = "added"
        elif any(line.startswith("deleted file mode") for line in lines[:5]):
            status = "removed"
        elif any(line.startswith("rename ") for line in lines[:5]):
            status = "renamed"

        result.append({"filename": filename, "status": status, "patch": patch})

    return result


def trim_patch_before_hunks(patch_text: str) -> str:
    """
    Removes all lines before the first hunk (starting with '@@').
    """
    lines = patch_text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("@@"):
            return "\n".join(lines[i:])
    return ""  # If no hunk found, return empty
