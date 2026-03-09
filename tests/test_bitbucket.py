import httpx
import pytest
import respx

from app.bitbucket import BitbucketClient
from app.config import BitbucketConfig
from app.models import ReviewFinding

BASE_URL = "https://bitbucket.company.com"


@pytest.fixture
def bb_config():
    return BitbucketConfig(
        base_url=BASE_URL,
        token="test-token",
        webhook_secret="test-secret",
    )


@pytest.fixture
def client(bb_config):
    return BitbucketClient(bb_config)


class TestBitbucketClient:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_pr_diff(self, client):
        diff_text = "diff --git a/file.py b/file.py\n+hello\n"
        respx.get(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/pull-requests/1/diff"
        ).mock(return_value=httpx.Response(200, text=diff_text))

        result = await client.fetch_pr_diff("PROJ", "my-repo", 1)
        assert result == diff_text
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_file_content(self, client):
        content = "print('hello')\n"
        respx.get(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/browse/src/main.py"
        ).mock(return_value=httpx.Response(200, text=content))

        result = await client.fetch_file_content("PROJ", "my-repo", "abc123", "src/main.py")
        assert result == content
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_inline_comment(self, client):
        respx.post(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/pull-requests/1/comments"
        ).mock(return_value=httpx.Response(201, json={"id": 1}))

        finding = ReviewFinding(
            file="src/main.py", line=10, severity="error", comment="Bug here"
        )
        await client.post_inline_comment("PROJ", "my-repo", 1, finding, "abc123")
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_post_pr_comment(self, client):
        respx.post(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/pull-requests/1/comments"
        ).mock(return_value=httpx.Response(201, json={"id": 2}))

        await client.post_pr_comment("PROJ", "my-repo", 1, "Review summary")
        await client.close()
