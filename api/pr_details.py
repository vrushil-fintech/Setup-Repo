from fastapi import HTTPException
import httpx
from app.dependencies import logger


def handle_http_error(e, repo, path, head_sha):
    if e.response.status_code == 404:
        logger.warning(
            f"GitHub API returned 404 for repo '{repo}', path '{path}', ref '{head_sha}'. "
            f"Response: {e.response.text}",
            extra={"repo": repo, "path": path, "head_sha": head_sha},
        )
        return None
    else:
        logger.error(
            f"GitHub API request failed for repo '{repo}', path '{path}', ref '{head_sha}'. "
            f"Status: {e.response.status_code}, Response: {e.response.text}",
            extra={"repo": repo, "path": path, "head_sha": head_sha},
        )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Failed to fetch PR files. GitHub responded with {e.response.status_code}: {e.response.text}",
        )

async def get_pull_request_details(
    access_token: str,
    owner: str = None,
    repo: str = None,
    pull_number: int = None,
    pr_url: str = None,
):
    if pr_url:
        url = pr_url
    elif owner and repo and pull_number:
        url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}"
    else:
        raise ValueError("Either pr_url or (owner, repo, pull_number) must be provided")

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {access_token}",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GitHub API request failed: {str(e)}",
                extra={"url": url},
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to fetch PR details.",
            )
        except Exception as e:
            logger.error(
                f"Unexpected error: {str(e)}",
                extra={"url": url},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble retrieving PR details. Please try again later.",
            )


async def get_pull_request_files(
    owner: str, repo: str, pull_number: int, access_token: str
):
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/files"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {access_token}",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "GitHub API request failed",
                extra={
                    "repo": repo,
                    "pull_number": pull_number,
                    "status_code": e.response.status_code,
                    "response_text": e.response.text,
                },
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to fetch PR files. GitHub responded with {e.response.status_code}.",
            )
        except Exception as e:
            logger.error(
                "Unexpected error while fetching PR files",
                extra={"repo": repo, "pull_number": pull_number},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble retrieving PR files. Please try again later.",
            )


async def get_pull_request_files_older_version(
    owner: str, repo: str, path: str, base_sha: str, access_token: str
):
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={base_sha}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {access_token}",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GitHub API request failed for repo '{repo}', path '{path}', ref '{base_sha}'. "
                f"Status: {e.response.status_code}, Response: {e.response.text}",
                extra={"repo": repo, "path": path, "base_sha": base_sha},
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to fetch PR files. GitHub responded with {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while fetching PR files for repo '{repo}', path '{path}', ref '{base_sha}'",
                extra={"repo": repo, "path": path, "base_sha": base_sha},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble retrieving PR files. Please try again later.",
            )


async def get_pull_request_files_new_version(
    owner: str, repo: str, path: str, head_sha: str, access_token: str
):
    if not all([owner, repo, path, head_sha, access_token]):
        raise ValueError("All parameters must be non-empty: owner, repo, path, head_sha, access_token.")

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={head_sha}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {access_token}",
    }

    timeout = httpx.Timeout(30.0)  # Set timeout to 30 seconds

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except httpx.HTTPStatusError as e:
            return handle_http_error(e, repo, path, head_sha)
        except Exception as e:
            logger.exception(
                f"Unexpected error while fetching PR files for repo '{repo}', path '{path}', ref '{head_sha}'",
                extra={"repo": repo, "path": path, "head_sha": head_sha},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble retrieving PR files. Please try again later.",
            )


async def post_pull_request_comment(
    owner: str, repo: str, pr_number: int, comment: str, access_token: str
):
    """
    Posts a comment on a pull request conversation.

    :param owner: Repository owner.
    :param repo: Repository name.
    :param pr_number: Pull request number.
    :param comment: The comment text.
    :param access_token: GitHub personal access token for authentication.
    :return: JSON response from GitHub API.
    """
    # Validate that comment is not empty, None, or just whitespace
    if not comment or not comment.strip():
        logger.warning(
            f"Skipping empty comment for repo '{repo}', PR #{pr_number}",
            extra={"repo": repo, "pr_number": pr_number},
        )
        return None
    
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{pr_number}/comments"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {access_token}",
    }
    data = {"body": comment}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GitHub API request failed for repo '{repo}', PR #{pr_number}. "
                f"Status: {e.response.status_code}, Response: {e.response.text}",
                extra={"repo": repo, "pr_number": pr_number},
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to post comment. GitHub responded with {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while posting a comment to PR #{pr_number} in repo '{repo}': {str(e)}",
                extra={"repo": repo, "pr_number": pr_number},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble posting the comment. Please try again later.",
            )

async def update_pull_request_comment(
    owner: str, repo: str, comment_id: int, comment: str, access_token: str
):
    """
    Updates an existing comment on a pull request conversation.

    :param owner: Repository owner.
    :param repo: Repository name.
    :param comment_id: The ID of the comment to be updated.
    :param comment: The updated comment text.
    :param access_token: GitHub personal access token for authentication.
    :return: JSON response from GitHub API.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment_id}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {access_token}",
    }
    data = {"body": comment}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.patch(url, json=data, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GitHub API request failed for updating comment {comment_id} in repo '{repo}'. "
                f"Status: {e.response.status_code}, Response: {e.response.text}",
                extra={"repo": repo, "comment_id": comment_id},
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to update comment. GitHub responded with {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while updating comment {comment_id} in repo '{repo}': {str(e)}",
                extra={"repo": repo, "comment_id": comment_id},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble updating the comment. Please try again later.",
            )

async def delete_pull_request_comment(
    owner: str, repo: str, comment_id: int, access_token: str
):
    """
    Deletes a comment from a pull request conversation.

    :param owner: Repository owner.
    :param repo: Repository name.
    :param comment_id: The ID of the comment to be deleted.
    :param access_token: GitHub personal access token for authentication.
    :return: None if successful, raises an exception otherwise.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/comments/{comment_id}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {access_token}",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.delete(url, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses
            logger.info(
                f"Successfully deleted comment {comment_id} from repo '{repo}'."
            )
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Failed to delete comment {comment_id} in repo '{repo}'. "
                f"Status: {e.response.status_code}, Response: {e.response.text}",
                extra={"repo": repo, "comment_id": comment_id},
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to delete comment. GitHub responded with {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while deleting comment {comment_id} in repo '{repo}'",
                extra={"repo": repo, "comment_id": comment_id},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble deleting the comment. Please try again later.",
            )


async def post_pull_request_status(
    owner: str,
    repo: str,
    commit_sha: str,
    state: str,
    description: str,
    access_token: str,
    target_url: str = None,
):
    """
    Posts a status check on a pull request's latest commit.

    :param owner: Repository owner.
    :param repo: Repository name.
    :param commit_sha: SHA of the latest commit in the PR.
    :param state: Status state ('pending', 'success', 'failure', 'error').
    :param description: Short message describing the status.
    :param access_token: GitHub personal access token for authentication.
    :param target_url: Optional link to analysis results or logs.
    :return: JSON response from GitHub API.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/statuses/{commit_sha}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {access_token}",
    }

    data = {
        "state": state,  # Options: 'pending', 'success', 'failure', 'error'
        "description": description,
        "context": "CodeSherlock.AI",
    }

    if target_url:
        data["target_url"] = target_url  # Optional link to analysis results

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GitHub API request failed for repo '{repo}', commit '{commit_sha}'. "
                f"Status: {e.response.status_code}, Response: {e.response.text}",
                extra={"repo": repo, "commit_sha": commit_sha},
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to post status. GitHub responded with {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while posting status to commit '{commit_sha}' in repo '{repo}'",
                extra={"repo": repo, "commit_sha": commit_sha},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble posting the status. Please try again later.",
            )


async def post_pull_request_line_comment(
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    commit_id: str,
    path: str,
    start_line: int,
    end_line: int,  # Optional support for multi-line comments
    access_token: str,
):
    """
    Posts a comment on a specific line (or range of lines) in a pull request diff.

    :param owner: Repository owner.
    :param repo: Repository name.
    :param pr_number: Pull request number.
    :param body: The comment text.
    :param commit_id: The latest commit SHA on the PR (usually the head SHA).
    :param path: The file path in the PR.
    :param start_line: The line number to comment on (in the diff).
    :param end_line: Optional starting line for a multi-line comment.
    :param access_token: GitHub personal access token.
    :return: JSON response from GitHub API.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/comments"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {access_token}",
    }

    # Standard line comment
    data = {
        "body": body,
        "commit_id": commit_id,
        "path": path,
        "side": "RIGHT",  # "RIGHT" = new version, "LEFT" = old
        "line": end_line,
    }

    # If it's a multi-line comment
    if end_line and start_line != end_line:
        data["start_line"] = start_line
        data["start_side"] = "RIGHT"

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, json=data, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GitHub API request failed for line comment on PR #{pr_number}. "
                f"Status: {e.response.status_code}, Response: {e.response.text}",
                extra={
                    "repo": repo,
                    "pr_number": pr_number,
                    "file": path,
                    "line": end_line,
                },
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to post line comment. GitHub responded with {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while posting line comment to PR #{pr_number}",
                extra={"repo": repo, "pr_number": pr_number, "file": path},
            )
            raise HTTPException(
                status_code=503,
                detail="Unexpected error occurred while posting line comment.",
            )


async def get_pull_request_diff(
    owner: str, repo: str, pr_number: int, access_token: str
) -> str:
    """
    Fetches the raw diff for a pull request using GitHub's .diff endpoint.

    This endpoint returns the complete diff for a PR and works for files of any size,
    unlike the REST API which may omit patches for large files.

    :param owner: Repository owner.
    :param repo: Repository name.
    :param pr_number: Pull request number.
    :param access_token: GitHub personal access token for authentication.
    :return: Raw diff text from GitHub.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}.diff"
    headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3.diff",
    }

    # Try different header combinations
    # headers_options = [
    #     {"Authorization": f"Bearer {installation_token}"},
    #     {"Authorization": f"Bearer {installation_token}", "Accept": "application/vnd.github.v3.diff"},
    #     {"Authorization": f"token {installation_token}"},  # Old format
    # ]

    async with httpx.AsyncClient(
        timeout=120.0
    ) as client:  # Longer timeout for large diffs
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            return response.text
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GitHub diff request failed for repo '{repo}', PR #{pr_number}. "
                f"Status: {e.response.status_code}, Response: {e.response.text}",
                extra={"repo": repo, "pr_number": pr_number},
            )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Failed to fetch PR diff. GitHub responded with {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            logger.error(
                f"Unexpected error while fetching diff for PR #{pr_number} in repo '{repo}': {str(e)}",
                extra={"repo": repo, "pr_number": pr_number, "error": str(e)},
            )
            raise HTTPException(
                status_code=503,
                detail="We're having trouble fetching the PR diff. Please try again later.",
            )


async def get_github_pr_data(access_token: str, repository: dict, pr_number: int) -> dict[str, any]:
    """
    Fetches pull request details and commits from GitHub.
    Handles pagination for commits.
    """
    base_url = f"https://api.github.com/repos/{repository['owner']}/{repository['name']}/pulls/{pr_number}"
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1. PR details
            pr_response = await client.get(base_url, headers=headers)
            pr_response.raise_for_status()
            pr_data = pr_response.json()

            logger.info(
                f"GitHub PR API (Details) Response code: {pr_response.status_code}",
                extra={"repository_id": repository["platform_id"], "pr_number": pr_number},
            )

            # 2. PR commits (with pagination)
            commits_data = []
            page = 1
            while True:
                response = await client.get(f"{base_url}/commits?per_page=100&page={page}", headers=headers)
                response.raise_for_status()
                data = response.json()
                if not data:
                    break
                commits_data.extend(data)
                page += 1

            logger.info(
                f"GitHub PR API (Commits) Total: {len(commits_data)}",
                extra={"repository_id": repository["platform_id"], "pr_number": pr_number},
            )

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            logger.error(
                f"Installation token expired: {e}",
                extra={"repository_id": repository["platform_id"], "pr_number": pr_number},
            )
            raise HTTPException(status_code=401, detail="Installation token expired.")
        else:
            logger.error(
                f"Error occurred while fetching PR data: {e}",
                extra={"repository_id": repository["platform_id"], "pr_number": pr_number},
            )
            raise HTTPException(status_code=503, detail="Error occurred while fetching PR data.")

    # Structure the data for downstream AI processing
    return {
        "title": pr_data.get("title"),
        "description": pr_data.get("body"),
        "author": pr_data.get("user", {}).get("login"),
        "labels": [label.get("name") for label in pr_data.get("labels", [])],
        "commits": [
            {
                "sha": commit.get("sha"),
                "message": commit.get("commit", {}).get("message"),
                "author": commit.get("commit", {}).get("author", {}),
            }
            for commit in commits_data
        ],
    }