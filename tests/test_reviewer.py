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
