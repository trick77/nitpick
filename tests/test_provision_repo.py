import json
from pathlib import Path

import httpx
import pytest
import respx

from app.bitbucket import BitbucketClient
from app.config import REQUIRED_WEBHOOK_EVENTS, BitbucketConfig
from scripts.provision_repo import (
    DEFAULT_WEBHOOK_NAME,
    RepoSpec,
    WebhookProvisioner,
    load_provision_input,
    main,
    resolve_secrets,
)

BASE_URL = "https://bitbucket.company.com"
WEBHOOK_URL = "https://noergler.internal/webhook"


@pytest.fixture
def bb_config():
    return BitbucketConfig(
        base_url=BASE_URL,
        token="test-token",
        webhook_secret="test-secret",
        username="bot",
    )


@pytest.fixture
def client(bb_config):
    c = BitbucketClient(bb_config)
    yield c


@pytest.fixture
def provisioner(client):
    return WebhookProvisioner(
        client,
        webhook_url=WEBHOOK_URL,
        webhook_secret="whsec",
        webhook_name=DEFAULT_WEBHOOK_NAME,
    )


@pytest.fixture
def spec():
    return RepoSpec(project="PROJ", repo="my-repo")


# --------------------------------------------------------------------------- #
# JSON config validation
# --------------------------------------------------------------------------- #

class TestLoadProvisionInput:
    def _write(self, tmp_path: Path, data) -> Path:
        p = tmp_path / "config.json"
        p.write_text(json.dumps(data))
        return p

    def test_valid_config(self, tmp_path):
        path = self._write(tmp_path, {
            "bitbucket_url": "https://bb.example.com",
            "webhook_url": "https://noergler/webhook",
            "repos": [
                {"project": "A", "repo": "one"},
                {"project": "A", "repo": "two"},
            ],
        })
        result = load_provision_input(path)
        assert result.bitbucket_url == "https://bb.example.com"
        assert result.webhook_url == "https://noergler/webhook"
        assert [r.key for r in result.repos] == ["A/one", "A/two"]

    def test_strips_trailing_slash_on_bitbucket_url(self, tmp_path):
        path = self._write(tmp_path, {
            "bitbucket_url": "https://bb.example.com/",
            "webhook_url": "https://x/webhook",
            "repos": [{"project": "A", "repo": "one"}],
        })
        assert load_provision_input(path).bitbucket_url == "https://bb.example.com"

    def test_rejects_http_bitbucket_url(self, tmp_path):
        path = self._write(tmp_path, {
            "bitbucket_url": "http://bb",
            "webhook_url": "https://x/webhook",
            "repos": [{"project": "A", "repo": "one"}],
        })
        with pytest.raises(SystemExit, match="bitbucket_url"):
            load_provision_input(path)

    def test_rejects_missing_webhook_url(self, tmp_path):
        path = self._write(tmp_path, {
            "bitbucket_url": "https://bb",
            "repos": [{"project": "A", "repo": "one"}],
        })
        with pytest.raises(SystemExit, match="webhook_url"):
            load_provision_input(path)

    def test_rejects_empty_repos(self, tmp_path):
        path = self._write(tmp_path, {
            "bitbucket_url": "https://bb",
            "webhook_url": "https://x/webhook",
            "repos": [],
        })
        with pytest.raises(SystemExit, match="repos"):
            load_provision_input(path)

    def test_rejects_duplicate_repos(self, tmp_path):
        path = self._write(tmp_path, {
            "bitbucket_url": "https://bb",
            "webhook_url": "https://x/webhook",
            "repos": [
                {"project": "A", "repo": "one"},
                {"project": "A", "repo": "one"},
            ],
        })
        with pytest.raises(SystemExit, match="duplicate"):
            load_provision_input(path)

    def test_rejects_missing_repo_field(self, tmp_path):
        path = self._write(tmp_path, {
            "bitbucket_url": "https://bb",
            "webhook_url": "https://x/webhook",
            "repos": [{"project": "A"}],
        })
        with pytest.raises(SystemExit, match="repo"):
            load_provision_input(path)


# --------------------------------------------------------------------------- #
# resolve_secrets
# --------------------------------------------------------------------------- #

class TestResolveSecrets:
    def test_env_vars_win(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BITBUCKET_TOKEN", "from-env")
        monkeypatch.setenv("BITBUCKET_WEBHOOK_SECRET", "sec-env")
        monkeypatch.chdir(tmp_path)
        token, secret = resolve_secrets(None)
        assert (token, secret) == ("from-env", "sec-env")

    def test_env_file_fallback(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
        monkeypatch.delenv("BITBUCKET_WEBHOOK_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        env_file = tmp_path / "extra.env"
        env_file.write_text(
            'BITBUCKET_TOKEN="file-token"\nBITBUCKET_WEBHOOK_SECRET=file-secret\n# ignored\n'
        )
        token, secret = resolve_secrets(env_file)
        assert (token, secret) == ("file-token", "file-secret")

    def test_cwd_dotenv_used(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
        monkeypatch.delenv("BITBUCKET_WEBHOOK_SECRET", raising=False)
        (tmp_path / ".env").write_text(
            "BITBUCKET_TOKEN=cwd-token\nBITBUCKET_WEBHOOK_SECRET=cwd-secret\n"
        )
        monkeypatch.chdir(tmp_path)
        token, secret = resolve_secrets(None)
        assert (token, secret) == ("cwd-token", "cwd-secret")

    def test_missing_secrets_exits(self, monkeypatch, tmp_path):
        monkeypatch.delenv("BITBUCKET_TOKEN", raising=False)
        monkeypatch.delenv("BITBUCKET_WEBHOOK_SECRET", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            resolve_secrets(None)


# --------------------------------------------------------------------------- #
# WebhookProvisioner
# --------------------------------------------------------------------------- #

class TestVerifyPermissions:
    @pytest.mark.asyncio
    @respx.mock
    async def test_ok(self, provisioner, spec, client):
        respx.get(f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo").mock(
            return_value=httpx.Response(200, json={"slug": "my-repo"})
        )
        respx.get(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/pull-requests"
        ).mock(return_value=httpx.Response(200, json={"values": []}))
        await provisioner.verify_permissions(spec)
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_403_raises(self, provisioner, spec, client):
        respx.get(f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo").mock(
            return_value=httpx.Response(403, text="Forbidden")
        )
        with pytest.raises(httpx.HTTPStatusError):
            await provisioner.verify_permissions(spec)
        await client.close()


class TestUpsertWebhook:
    @pytest.mark.asyncio
    @respx.mock
    async def test_creates_when_absent(self, provisioner, spec, client):
        respx.get(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks"
        ).mock(return_value=httpx.Response(200, json={"values": [], "isLastPage": True}))
        create = respx.post(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks"
        ).mock(return_value=httpx.Response(200, json={"id": 42}))

        webhook_id, diff = await provisioner.upsert_webhook(spec)

        assert webhook_id == 42
        assert diff == ["create"]
        body = json.loads(create.calls[0].request.content)
        assert body["name"] == DEFAULT_WEBHOOK_NAME
        assert body["url"] == WEBHOOK_URL
        assert set(body["events"]) == set(REQUIRED_WEBHOOK_EVENTS)
        assert body["configuration"]["secret"] == "whsec"
        assert body["active"] is True
        assert body["sslVerificationRequired"] is True
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_op_when_up_to_date(self, provisioner, spec, client):
        respx.get(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks"
        ).mock(return_value=httpx.Response(200, json={
            "values": [{
                "id": 7,
                "name": DEFAULT_WEBHOOK_NAME,
                "url": WEBHOOK_URL,
                "events": list(REQUIRED_WEBHOOK_EVENTS),
                "active": True,
                "configuration": {"secret": "hidden"},
            }],
            "isLastPage": True,
        }))

        webhook_id, diff = await provisioner.upsert_webhook(spec)
        assert webhook_id == 7
        assert diff == []
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_updates_on_drift(self, provisioner, spec, client):
        respx.get(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks"
        ).mock(return_value=httpx.Response(200, json={
            "values": [{
                "id": 7,
                "name": DEFAULT_WEBHOOK_NAME,
                "url": "https://stale.example/webhook",
                "events": ["pr:opened"],  # missing events
                "active": True,
                "configuration": {"secret": "x"},
            }],
            "isLastPage": True,
        }))
        put = respx.put(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks/7"
        ).mock(return_value=httpx.Response(200, json={"id": 7}))

        webhook_id, diff = await provisioner.upsert_webhook(spec)
        assert webhook_id == 7
        assert any("url" in d for d in diff)
        assert any("events" in d for d in diff)
        assert put.called
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_dry_run_skips_writes(self, client, spec):
        p = WebhookProvisioner(
            client, webhook_url=WEBHOOK_URL, webhook_secret="whsec", dry_run=True,
        )
        respx.get(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks"
        ).mock(return_value=httpx.Response(200, json={"values": [], "isLastPage": True}))
        post_route = respx.post(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks"
        ).mock(return_value=httpx.Response(200, json={"id": 1}))

        webhook_id, diff = await p.upsert_webhook(spec)
        assert webhook_id == -1
        assert diff == ["create"]
        assert not post_route.called
        await client.close()


class TestTestWebhook:
    @pytest.mark.asyncio
    @respx.mock
    async def test_success_returns_200(self, provisioner, spec, client):
        respx.post(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks/7/test"
        ).mock(return_value=httpx.Response(200, json={"statusCode": 200}))
        assert await provisioner.test_webhook(spec, 7) == 200
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_downstream_401_reported(self, provisioner, spec, client):
        respx.post(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks/7/test"
        ).mock(return_value=httpx.Response(200, json={"statusCode": 401}))
        assert await provisioner.test_webhook(spec, 7) == 401
        await client.close()

    @pytest.mark.asyncio
    @respx.mock
    async def test_bitbucket_side_failure(self, provisioner, spec, client):
        respx.post(
            f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/my-repo/webhooks/7/test"
        ).mock(return_value=httpx.Response(500, text="boom"))
        assert await provisioner.test_webhook(spec, 7) == 500
        await client.close()


# --------------------------------------------------------------------------- #
# End-to-end via main()
# --------------------------------------------------------------------------- #

class TestMain:
    def test_multi_repo_mixed_results(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "bitbucket_url": BASE_URL,
            "webhook_url": WEBHOOK_URL,
            "repos": [
                {"project": "PROJ", "repo": "good"},
                {"project": "PROJ", "repo": "bad"},
            ],
        }))
        monkeypatch.setenv("BITBUCKET_TOKEN", "t")
        monkeypatch.setenv("BITBUCKET_WEBHOOK_SECRET", "s")
        monkeypatch.chdir(tmp_path)

        with respx.mock(assert_all_called=False) as mock:
            # good repo
            mock.get(f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/good").mock(
                return_value=httpx.Response(200, json={})
            )
            mock.get(
                f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/good/pull-requests"
            ).mock(return_value=httpx.Response(200, json={"values": []}))
            mock.get(
                f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/good/webhooks"
            ).mock(return_value=httpx.Response(200, json={"values": [], "isLastPage": True}))
            mock.post(
                f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/good/webhooks"
            ).mock(return_value=httpx.Response(200, json={"id": 1}))
            mock.post(
                f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/good/webhooks/1/test"
            ).mock(return_value=httpx.Response(200, json={"statusCode": 200}))
            # bad repo — permission failure
            mock.get(f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/bad").mock(
                return_value=httpx.Response(404, text="no repo")
            )

            rc = main([str(cfg)])

        assert rc == 1  # one failure → non-zero exit

    def test_dry_run_issues_no_writes(self, tmp_path, monkeypatch):
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "bitbucket_url": BASE_URL,
            "webhook_url": WEBHOOK_URL,
            "repos": [{"project": "PROJ", "repo": "r"}],
        }))
        monkeypatch.setenv("BITBUCKET_TOKEN", "t")
        monkeypatch.setenv("BITBUCKET_WEBHOOK_SECRET", "s")
        monkeypatch.chdir(tmp_path)

        with respx.mock(assert_all_called=False) as mock:
            mock.get(f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/r").mock(
                return_value=httpx.Response(200, json={})
            )
            mock.get(
                f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/r/pull-requests"
            ).mock(return_value=httpx.Response(200, json={"values": []}))
            mock.get(
                f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/r/webhooks"
            ).mock(return_value=httpx.Response(200, json={"values": [], "isLastPage": True}))
            create_route = mock.post(
                f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/r/webhooks"
            ).mock(return_value=httpx.Response(200, json={"id": 1}))
            test_route = mock.post(
                f"{BASE_URL}/rest/api/1.0/projects/PROJ/repos/r/webhooks/1/test"
            ).mock(return_value=httpx.Response(200, json={"statusCode": 200}))

            rc = main([str(cfg), "--dry-run"])

        assert rc == 0
        assert not create_route.called
        assert not test_route.called
