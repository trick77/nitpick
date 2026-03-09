import logging

import httpx

from app.config import BitbucketConfig
from app.models import ReviewFinding

logger = logging.getLogger(__name__)


class BitbucketClient:
    def __init__(self, config: BitbucketConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.base_url,
            headers={
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def close(self):
        await self.client.aclose()

    async def fetch_pr_diff(self, project: str, repo: str, pr_id: int) -> str:
        url = f"/rest/api/1.0/projects/{project}/repos/{repo}/pull-requests/{pr_id}/diff"
        response = await self.client.get(
            url, headers={"Accept": "text/plain"}
        )
        response.raise_for_status()
        return response.text

    async def fetch_file_content(
        self, project: str, repo: str, commit: str, path: str
    ) -> str:
        url = f"/rest/api/1.0/projects/{project}/repos/{repo}/browse/{path}"
        response = await self.client.get(
            url,
            params={"at": commit},
            headers={"Accept": "text/plain"},
        )
        response.raise_for_status()
        return response.text

    async def post_inline_comment(
        self,
        project: str,
        repo: str,
        pr_id: int,
        finding: ReviewFinding,
        to_commit: str,
    ) -> None:
        url = f"/rest/api/1.0/projects/{project}/repos/{repo}/pull-requests/{pr_id}/comments"
        payload = {
            "text": f"**[{finding.severity.upper()}]** {finding.comment}",
            "anchor": {
                "path": finding.file,
                "line": finding.line,
                "lineType": "ADDED",
                "diffType": "EFFECTIVE",
            },
        }
        response = await self.client.post(url, json=payload)
        response.raise_for_status()
        logger.info("Posted inline comment on %s:%d", finding.file, finding.line)

    async def post_pr_comment(
        self, project: str, repo: str, pr_id: int, text: str
    ) -> None:
        url = f"/rest/api/1.0/projects/{project}/repos/{repo}/pull-requests/{pr_id}/comments"
        response = await self.client.post(url, json={"text": text})
        response.raise_for_status()
        logger.info("Posted summary comment on PR %d", pr_id)
