import logging
from dataclasses import dataclass, field

import httpx

from app.config import JiraConfig

logger = logging.getLogger(__name__)


@dataclass
class JiraTicket:
    key: str
    title: str
    description: str | None
    labels: list[str]
    acceptance_criteria: str | None
    subtasks: list[str] = field(default_factory=list)
    url: str = ""

    MAX_DESCRIPTION_LENGTH = 5000


class JiraClient:
    def __init__(self, config: JiraConfig):
        self.config = config
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {config.token}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )

    async def fetch_ticket(self, ticket_id: str) -> JiraTicket | None:
        url = (
            f"{self.config.base_url.rstrip('/')}/rest/api/2/issue/{ticket_id}"
            f"?fields=summary,description,labels,subtasks,customfield_10004"
        )
        try:
            response = await self.client.get(url)
            if response.status_code == 404:
                logger.info("Jira ticket %s not found", ticket_id)
                return None
            response.raise_for_status()
        except httpx.ConnectError:
            logger.warning("Failed to connect to Jira for ticket %s", ticket_id)
            return None
        except httpx.HTTPStatusError:
            logger.warning("Jira API error for ticket %s", ticket_id, exc_info=True)
            return None

        data = response.json()
        fields = data.get("fields", {})

        description = fields.get("description")
        if description and len(description) > JiraTicket.MAX_DESCRIPTION_LENGTH:
            description = description[:JiraTicket.MAX_DESCRIPTION_LENGTH] + "..."

        subtasks_raw = fields.get("subtasks", [])
        subtasks = [
            f"{st['key']}: {st.get('fields', {}).get('summary', '')}"
            for st in subtasks_raw
            if isinstance(st, dict) and "key" in st
        ]

        acceptance_criteria = fields.get("customfield_10004")
        if acceptance_criteria and not isinstance(acceptance_criteria, str):
            acceptance_criteria = None

        browse_url = f"{self.config.base_url.rstrip('/')}/browse/{data.get('key', ticket_id)}"

        return JiraTicket(
            key=data.get("key", ticket_id),
            title=fields.get("summary", ""),
            description=description,
            labels=fields.get("labels", []),
            acceptance_criteria=acceptance_criteria,
            subtasks=subtasks,
            url=browse_url,
        )

    async def close(self):
        await self.client.aclose()
