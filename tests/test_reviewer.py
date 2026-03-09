from unittest.mock import AsyncMock

import pytest

from app.models import ReviewFinding, WebhookPayload
from app.reviewer import Reviewer


def _make_payload(author: str = "jan.username") -> WebhookPayload:
    return WebhookPayload(**{
        "eventKey": "pr:opened",
        "pullRequest": {
            "id": 42,
            "title": "Test PR",
            "fromRef": {
                "id": "refs/heads/feature",
                "displayId": "feature",
                "latestCommit": "abc123",
                "repository": {"slug": "my-repo", "project": {"key": "PROJ"}},
            },
            "toRef": {
                "id": "refs/heads/main",
                "displayId": "main",
                "latestCommit": "def456",
                "repository": {"slug": "my-repo", "project": {"key": "PROJ"}},
            },
            "author": {"user": {"name": author}},
        },
    })


def _make_real_payload() -> WebhookPayload:
    """Build a WebhookPayload from a real-world Bitbucket Server webhook (anonymized)."""
    return WebhookPayload(**{
        "eventKey": "pr:opened",
        "date": "2025-06-17T06:55:51+0000",
        "actor": {
            "name": "username",
            "emailAddress": "user@example.com",
            "active": True,
            "displayName": "Nit Pick",
            "id": 12345,
            "slug": "username",
            "type": "NORMAL",
            "links": {
                "self": [{"href": "https://bitbucket.example.com/users/username"}]
            },
        },
        "pullRequest": {
            "id": 1,
            "version": 0,
            "title": "test nitpick",
            "state": "OPEN",
            "open": True,
            "closed": False,
            "createdDate": 1750143351522,
            "updatedDate": 1750143351522,
            "fromRef": {
                "id": "refs/heads/test-branch",
                "displayId": "test-branch",
                "latestCommit": "d596f83abcdef1234567890abcdef1234567890ab",
                "repository": {
                    "slug": "test",
                    "id": 999,
                    "name": "test",
                    "description": "test repo for nitpick",
                    "hierarchyId": "abc123def456",
                    "scmId": "git",
                    "state": "AVAILABLE",
                    "statusMessage": "Available",
                    "forkable": True,
                    "project": {
                        "key": "~USERNAME",
                        "id": 100,
                        "name": "Nit Pick",
                        "description": "Personal project of Nit Pick",
                        "public": False,
                        "type": "PERSONAL",
                        "owner": {
                            "name": "username",
                            "emailAddress": "user@example.com",
                            "active": True,
                            "displayName": "Nit Pick",
                            "id": 12345,
                            "slug": "username",
                            "type": "NORMAL",
                            "links": {
                                "self": [{"href": "https://bitbucket.example.com/users/username"}]
                            },
                        },
                        "links": {
                            "self": [{"href": "https://bitbucket.example.com/users/username"}]
                        },
                    },
                    "public": False,
                    "archived": False,
                    "links": {
                        "clone": [
                            {"href": "https://bitbucket.example.com/scm/~username/test.git", "name": "http"},
                            {"href": "ssh://git@bitbucket.example.com:7999/~username/test.git", "name": "ssh"},
                        ],
                        "self": [{"href": "https://bitbucket.example.com/users/username/repos/test/browse"}],
                    },
                },
            },
            "toRef": {
                "id": "refs/heads/master",
                "displayId": "master",
                "latestCommit": "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4",
                "repository": {
                    "slug": "test",
                    "id": 999,
                    "name": "test",
                    "description": "test repo for nitpick",
                    "hierarchyId": "abc123def456",
                    "scmId": "git",
                    "state": "AVAILABLE",
                    "statusMessage": "Available",
                    "forkable": True,
                    "project": {
                        "key": "~USERNAME",
                        "id": 100,
                        "name": "Nit Pick",
                        "description": "Personal project of Nit Pick",
                        "public": False,
                        "type": "PERSONAL",
                        "owner": {
                            "name": "username",
                            "emailAddress": "user@example.com",
                            "active": True,
                            "displayName": "Nit Pick",
                            "id": 12345,
                            "slug": "username",
                            "type": "NORMAL",
                            "links": {
                                "self": [{"href": "https://bitbucket.example.com/users/username"}]
                            },
                        },
                        "links": {
                            "self": [{"href": "https://bitbucket.example.com/users/username"}]
                        },
                    },
                    "public": False,
                    "archived": False,
                    "links": {
                        "clone": [
                            {"href": "https://bitbucket.example.com/scm/~username/test.git", "name": "http"},
                            {"href": "ssh://git@bitbucket.example.com:7999/~username/test.git", "name": "ssh"},
                        ],
                        "self": [{"href": "https://bitbucket.example.com/users/username/repos/test/browse"}],
                    },
                },
            },
            "locked": False,
            "author": {
                "user": {
                    "name": "username",
                    "emailAddress": "user@example.com",
                    "active": True,
                    "displayName": "Nit Pick",
                    "id": 12345,
                    "slug": "username",
                    "type": "NORMAL",
                    "links": {
                        "self": [{"href": "https://bitbucket.example.com/users/username"}]
                    },
                },
                "role": "AUTHOR",
                "approved": False,
                "status": "UNAPPROVED",
            },
            "reviewers": [],
            "participants": [],
            "links": {
                "self": [{"href": "https://bitbucket.example.com/users/username/repos/test/pull-requests/1"}]
            },
        },
    })


@pytest.fixture
def mock_bitbucket():
    client = AsyncMock()
    client.fetch_pr_diff = AsyncMock(return_value="diff --git a/file.py b/file.py\n+hello\n")
    client.post_inline_comment = AsyncMock()
    client.post_pr_comment = AsyncMock()
    return client


@pytest.fixture
def mock_copilot():
    client = AsyncMock()
    client.review_diff = AsyncMock(return_value=[
        ReviewFinding(file="file.py", line=1, severity="warning", comment="Test issue"),
    ])
    return client


@pytest.fixture
def reviewer(mock_bitbucket, mock_copilot):
    return Reviewer(mock_bitbucket, mock_copilot, allowed_authors=["jan.username"])


class TestReviewer:
    @pytest.mark.asyncio
    async def test_review_allowed_author(self, reviewer, mock_bitbucket, mock_copilot):
        payload = _make_payload("jan.username")
        await reviewer.review_pull_request(payload)

        mock_bitbucket.fetch_pr_diff.assert_called_once_with("PROJ", "my-repo", 42)
        mock_copilot.review_diff.assert_called_once()
        mock_bitbucket.post_inline_comment.assert_called_once()
        mock_bitbucket.post_pr_comment.assert_called_once()

        summary_text = mock_bitbucket.post_pr_comment.call_args[0][3]
        assert "1 issue(s) found" in summary_text

    @pytest.mark.asyncio
    async def test_skip_disallowed_author(self, reviewer, mock_bitbucket, mock_copilot):
        payload = _make_payload("other.user")
        await reviewer.review_pull_request(payload)

        mock_bitbucket.fetch_pr_diff.assert_not_called()
        mock_copilot.review_diff.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_empty_diff(self, reviewer, mock_bitbucket, mock_copilot):
        mock_bitbucket.fetch_pr_diff.return_value = "   \n"
        payload = _make_payload("jan.username")
        await reviewer.review_pull_request(payload)

        mock_copilot.review_diff.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_findings(self, reviewer, mock_bitbucket, mock_copilot):
        mock_copilot.review_diff.return_value = []
        payload = _make_payload("jan.username")
        await reviewer.review_pull_request(payload)

        mock_bitbucket.post_inline_comment.assert_not_called()
        summary_text = mock_bitbucket.post_pr_comment.call_args[0][3]
        assert "No issues found" in summary_text

    def test_is_author_allowed(self, reviewer):
        assert reviewer.is_author_allowed("jan.username") is True
        assert reviewer.is_author_allowed("other.user") is False

    def test_build_summary_mixed(self, reviewer):
        findings = [
            ReviewFinding(file="a.py", line=1, severity="error", comment="err"),
            ReviewFinding(file="b.py", line=2, severity="warning", comment="warn"),
            ReviewFinding(file="c.py", line=3, severity="info", comment="info"),
        ]
        summary = reviewer._build_summary(findings)
        assert "3 issue(s) found" in summary
        assert "1 error(s)" in summary
        assert "1 warning(s)" in summary
        assert "1 info" in summary

    def test_build_summary_empty(self, reviewer):
        assert "No issues found" in reviewer._build_summary([])

    @pytest.mark.asyncio
    async def test_review_real_webhook_payload(self, mock_bitbucket, mock_copilot):
        payload = _make_real_payload()
        reviewer = Reviewer(mock_bitbucket, mock_copilot, allowed_authors=["username"])
        await reviewer.review_pull_request(payload)

        mock_bitbucket.fetch_pr_diff.assert_called_once_with("~USERNAME", "test", 1)
        mock_copilot.review_diff.assert_called_once()
        mock_bitbucket.post_inline_comment.assert_called_once()
        mock_bitbucket.post_pr_comment.assert_called_once()
