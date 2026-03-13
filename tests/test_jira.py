import httpx
import pytest
import respx

from app.config import JiraConfig
from app.jira import JiraClient, JiraTicket


@pytest.fixture
def jira_config():
    return JiraConfig(base_url="https://jira.example.com", token="test-token")


@pytest.fixture
def jira_client(jira_config):
    return JiraClient(jira_config)


def _jira_response(
    key="SEP-22888",
    summary="Config security for intranet",
    description="Implement security config",
    labels=None,
    acceptance_criteria=None,
    subtasks=None,
):
    fields = {
        "summary": summary,
        "description": description,
        "labels": labels or [],
        "subtasks": subtasks or [],
    }
    if acceptance_criteria is not None:
        fields["customfield_10004"] = acceptance_criteria
    return {"key": key, "fields": fields}


class TestFetchTicket:
    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_ticket_success(self, jira_client):
        respx.get("https://jira.example.com/rest/api/2/issue/SEP-22888").mock(
            return_value=httpx.Response(
                200,
                json=_jira_response(
                    labels=["security", "backend"],
                    acceptance_criteria="Must pass security scan",
                    subtasks=[
                        {"key": "SEP-22889", "fields": {"summary": "Implement auth filter"}},
                        {"key": "SEP-22890", "fields": {"summary": "Add config endpoint"}},
                    ],
                ),
            )
        )

        ticket = await jira_client.fetch_ticket("SEP-22888")

        assert ticket is not None
        assert ticket.key == "SEP-22888"
        assert ticket.title == "Config security for intranet"
        assert ticket.description == "Implement security config"
        assert ticket.labels == ["security", "backend"]
        assert ticket.acceptance_criteria == "Must pass security scan"
        assert len(ticket.subtasks) == 2
        assert ticket.subtasks[0] == "SEP-22889: Implement auth filter"
        assert ticket.url == "https://jira.example.com/browse/SEP-22888"

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_ticket_not_found(self, jira_client):
        respx.get("https://jira.example.com/rest/api/2/issue/NOPE-999").mock(
            return_value=httpx.Response(404)
        )

        ticket = await jira_client.fetch_ticket("NOPE-999")
        assert ticket is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_ticket_connection_error(self, jira_client):
        respx.get("https://jira.example.com/rest/api/2/issue/SEP-123").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )

        ticket = await jira_client.fetch_ticket("SEP-123")
        assert ticket is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_ticket_truncates_description(self, jira_client):
        long_desc = "x" * 6000
        respx.get("https://jira.example.com/rest/api/2/issue/SEP-1").mock(
            return_value=httpx.Response(
                200,
                json=_jira_response(key="SEP-1", description=long_desc),
            )
        )

        ticket = await jira_client.fetch_ticket("SEP-1")

        assert ticket is not None
        assert len(ticket.description) == JiraTicket.MAX_DESCRIPTION_LENGTH + 3  # +3 for "..."
        assert ticket.description.endswith("...")

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_ticket_no_description(self, jira_client):
        respx.get("https://jira.example.com/rest/api/2/issue/SEP-2").mock(
            return_value=httpx.Response(
                200,
                json=_jira_response(key="SEP-2", description=None),
            )
        )

        ticket = await jira_client.fetch_ticket("SEP-2")

        assert ticket is not None
        assert ticket.description is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_fetch_ticket_non_string_acceptance_criteria(self, jira_client):
        resp = _jira_response(key="SEP-3")
        resp["fields"]["customfield_10004"] = {"some": "object"}
        respx.get("https://jira.example.com/rest/api/2/issue/SEP-3").mock(
            return_value=httpx.Response(200, json=resp)
        )

        ticket = await jira_client.fetch_ticket("SEP-3")

        assert ticket is not None
        assert ticket.acceptance_criteria is None
