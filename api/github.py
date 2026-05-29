from typing import Dict, List, Optional, Tuple
from fastapi import HTTPException
import httpx
import base64
import asyncio
from app.dependencies import logger


async def get_installation_repositories(access_token: str):
    result_data = None
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            result = await client.get(
                "https://api.github.com/installation/repositories",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            result.raise_for_status()
            result_data = result.json()
        except httpx.HTTPStatusError as e:
            # If unauthorized, regenerate the token and retry once
            if e.response.status_code == 401:
                logger.error(f"Installation token expired: {e}")
                raise HTTPException(
                    status_code=401, detail="Installation token expired."
                )
            else:
                logger.error(
                    f"Error occurred while fetching repositories: {e}",
                )
                raise HTTPException(status_code=503, detail=str(e))

    logger.info(f"GitHub Repositories API Response code: {result.status_code}")
    return [
        {
            "name": repo["name"],
            "full_name": repo["full_name"],
            "id": repo["id"],
            "html_url": repo["html_url"],
        }
        for repo in result_data.get("repositories", [])
    ]


async def get_github_organizations(access_token: str, user_id: str):
    orgs_url = "https://api.github.com/user/memberships/orgs"
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            orgs_res = await client.get(
                orgs_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            orgs_res.raise_for_status()
            orgs_data = orgs_res.json()
            logger.info(
                f"GitHub Organizations API Response code: {orgs_res.status_code}",
                extra={"user_id": user_id},
            )
            return orgs_data
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error while fetching orgs: {e.response.status_code} - {e.response.text}",
                extra={"user_id": user_id},
            )
            return None
        except httpx.RequestError as e:
            logger.error(
                f"Request error while fetching orgs: {str(e)}",
                extra={"user_id": user_id},
            )
            return None


async def get_github_organization_members(access_token: str, organization: Dict):
    org_members = []
    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            result = await client.get(
                f"https://api.github.com/orgs/{organization["name"]}/members?filter=all&role=admin",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            result.raise_for_status()
            result_data = result.json()
            org_members.extend(
                {"id": member.get("id"), "login": member.get("login"), "role": "admin"}
                for member in result_data
            )
            logger.info(
                f"GitHub Organization Members API (Admin) Response code: {result.status_code}",
                extra={"organization_id": organization["platform_id"]},
            )

        except httpx.HTTPStatusError as e:
            # If unauthorized, regenerate the token and retry once
            if e.response.status_code == 401:
                logger.error(
                    f"Installation token expired: {e}",
                    extra={"organization_id": organization["platform_id"]},
                )
                raise HTTPException(
                    status_code=401, detail="Installation token expired."
                )
            else:
                logger.error(
                    f"Error occurred while fetching org members: {e}",
                    extra={"organization_id": organization["platform_id"]},
                )
                raise HTTPException(
                    status_code=503, detail="Error occurred while fetching org members."
                )

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            result = await client.get(
                f"https://api.github.com/orgs/{organization["name"]}/members?filter=all&role=member",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            result.raise_for_status()
            result_data = result.json()
            org_members.extend(
                {"id": member.get("id"), "login": member.get("login"), "role": "member"}
                for member in result_data
            )
            logger.info(
                f"GitHub Organization Members API (Member) Response code: {result.status_code}",
                extra={"organization_id": organization["platform_id"]},
            )

        except httpx.HTTPStatusError as e:
            # If unauthorized, regenerate the token and retry once
            if e.response.status_code == 401:
                logger.error(
                    f"Installation token expired: {e}",
                    extra={"organization_id": organization["platform_id"]},
                )
                raise HTTPException(
                    status_code=401, detail="Installation token expired."
                )
            else:
                logger.error(
                    f"Error occurred while fetching org members: {e}",
                    extra={"organization_id": organization["platform_id"]},
                )
                raise HTTPException(
                    status_code=503, detail="Error occurred while fetching org members."
                )

    return org_members


async def get_github_repo_structure(
    access_token: str,
    owner: str,
    repo: str,
    ref: str,
    user_id: str | None = None,
) -> List[Dict]:
    """
    Fetch full GitHub repository structure using Git Trees API.

    Returns:
        List of dicts with:
        - path: Full path to file/directory
        - type: 'blob' (file) or 'tree' (directory)

    Raises:
        HTTPException: 401 (unauthorized), 404 (not found),
                      413 (tree truncated), 503 (API error)
    """

    if not access_token:
        raise HTTPException(status_code=401, detail="GitHub access token missing")

    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{ref}?recursive=1"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            # Check if tree was truncated (GitHub limit: 100,000 entries)
            if data.get("truncated", False):
                tree_size = len(data.get("tree", []))
                logger.warning(
                    "GitHub Repo Tree was truncated (>100k items)",
                    extra={
                        "owner": owner,
                        "repo": repo,
                        "ref": ref,
                        "items_count": tree_size,
                    },
                )
                raise HTTPException(
                    status_code=413,
                    detail=f"Repository too large - tree truncated at {tree_size} items",
                )

            logger.info(
                f"GitHub Repo Tree API call successful - Status: {response.status_code}",
                extra={
                    "owner": owner,
                    "repo": repo,
                    "ref": ref,
                    "user_id": user_id,
                    "items_count": len(data.get("tree", [])),
                    "status_code": response.status_code,
                },
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "GitHub Repo Tree API HTTP error",
                extra={
                    "status_code": e.response.status_code,
                    "response": e.response.text,
                    "owner": owner,
                    "repo": repo,
                    "ref": ref,
                    "user_id": user_id,
                },
            )

            if e.response.status_code == 401:
                raise HTTPException(
                    status_code=401,
                    detail="GitHub token expired or unauthorized",
                )
            elif e.response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail="Repository or ref not found",
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail="GitHub API error while fetching repository structure",
                )

        except httpx.RequestError as e:
            logger.error(
                "GitHub Repo Tree API request error",
                extra={
                    "error": str(e),
                    "owner": owner,
                    "repo": repo,
                    "ref": ref,
                    "user_id": user_id,
                },
            )
            raise HTTPException(
                status_code=503,
                detail="Network error while contacting GitHub",
            )

    # Parse tree
    repo_items: List[Dict] = []

    for item in data.get("tree", []):
        path = item.get("path")
        item_type = item.get("type")

        # Optional: Extract file name for future reference
        # file_name = path.split("/")[-1] if (item_type == "blob" and path) else None

        repo_items.append(
            {
                "path": path,
                "type": item_type,
                # "file_name": file_name,
                # "sha": item.get("sha"),   # Git SHA for caching/version tracking
                # "size": item.get("size"), # File size in bytes
            }
        )

    return repo_items


async def get_github_files_content_batch(
    owner: str,
    repo: str,
    file_paths: List[str],
    ref: str,
    access_token: str,
) -> Dict[str, str]:
    """
    Fetches the content of multiple files from GitHub in parallel.

    Args:
        owner: Repository owner
        repo: Repository name
        file_paths: List of file paths to fetch
        ref: The branch, tag or commit SHA to fetch from
        access_token: GitHub access token

    Returns:
        A dictionary mapping file paths to their raw string content.
        Files that fail to fetch are omitted from the dictionary.
    """
    if not file_paths:
        return {}

    # Limit maximum parallel requests to avoid hitting rate limits or crashing
    MAX_CONCURRENT_REQUESTS = 20
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }

    async def fetch_file(
        client: httpx.AsyncClient, path: str
    ) -> Tuple[str, Optional[str]]:
        async with semaphore:
            url = (
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={ref}"
            )
            try:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                content_b64 = data.get("content", "")
                if not content_b64:
                    logger.warning(
                        f"Empty content for {path}",
                        extra={
                            "owner": owner,
                            "repo": repo,
                            "path": path,
                            "ref": ref,
                        },
                    )
                    return path, None

                # GitHub returns content with newlines, remove them before b64 decoding
                content = base64.b64decode(content_b64.replace("\n", "")).decode(
                    "utf-8"
                )
                return path, content

            except httpx.HTTPStatusError as e:
                # Specific HTTP error handling
                status_code = e.response.status_code
                
                if status_code == 401:
                    logger.error(
                        f"Unauthorized access to {path} (token expired or invalid)",
                        extra={
                            "owner": owner,
                            "repo": repo,
                            "path": path,
                            "ref": ref,
                            "status_code": status_code,
                        },
                    )
                elif status_code == 403:
                    logger.error(
                        f"Forbidden access to {path} (insufficient permissions)",
                        extra={
                            "owner": owner,
                            "repo": repo,
                            "path": path,
                            "ref": ref,
                            "status_code": status_code,
                        },
                    )
                elif status_code == 404:
                    logger.warning(
                        f"File not found: {path}",
                        extra={
                            "owner": owner,
                            "repo": repo,
                            "path": path,
                            "ref": ref,
                            "status_code": status_code,
                        },
                    )
                else:
                    logger.error(
                        f"HTTP error fetching {path}: {status_code}",
                        extra={
                            "owner": owner,
                            "repo": repo,
                            "path": path,
                            "ref": ref,
                            "status_code": status_code,
                            "response": e.response.text[:200] if e.response.text else "",
                        },
                    )
                return path, None
            
            except UnicodeDecodeError as e:
                # Binary file or encoding issue
                logger.warning(
                    f"Encoding error for {path} (likely binary file or non-UTF8)",
                    extra={
                        "owner": owner,
                        "repo": repo,
                        "path": path,
                        "ref": ref,
                        "error_type": "UnicodeDecodeError",
                        "encoding": "utf-8",
                    },
                )
                return path, None
            
            except httpx.RequestError as e:
                # Network/connection error
                logger.error(
                    f"Network error fetching {path}: {str(e)}",
                    extra={
                        "owner": owner,
                        "repo": repo,
                        "path": path,
                        "ref": ref,
                        "error_type": type(e).__name__,
                    },
                )
                return path, None
            
            except Exception as e:
                # Catch-all for unexpected errors
                logger.error(
                    f"Unexpected error fetching {path}: {str(e)}",
                    extra={
                        "owner": owner,
                        "repo": repo,
                        "path": path,
                        "ref": ref,
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                return path, None

    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [fetch_file(client, path) for path in file_paths]
        results = await asyncio.gather(*tasks)

    # Filter out None results (failures) and build the final dictionary
    return {path: content for path, content in results if content is not None}
