import logging

from app.bitbucket import BitbucketClient
from app.copilot import CopilotClient
from app.models import ReviewFinding, WebhookPayload

logger = logging.getLogger(__name__)


class Reviewer:
    def __init__(
        self,
        bitbucket: BitbucketClient,
        copilot: CopilotClient,
        allowed_authors: list[str],
    ):
        self.bitbucket = bitbucket
        self.copilot = copilot
        self.allowed_authors = allowed_authors

    def is_author_allowed(self, author_name: str) -> bool:
        return author_name in self.allowed_authors

    async def review_pull_request(self, payload: WebhookPayload) -> None:
        pr = payload.pullRequest
        author_name = pr.author.user.name
        pr_id = pr.id

        project_key, repo_slug = self._extract_project_repo(payload)
        if not project_key or not repo_slug:
            logger.error("Could not extract project/repo from webhook payload")
            return

        if not self.is_author_allowed(author_name):
            logger.info(
                "Skipping PR %d by %s (not in allowed authors)", pr_id, author_name
            )
            return

        logger.info("Starting review of PR %d by %s", pr_id, author_name)

        diff = await self.bitbucket.fetch_pr_diff(project_key, repo_slug, pr_id)
        if not diff.strip():
            logger.info("PR %d has empty diff, skipping", pr_id)
            return

        findings = await self.copilot.review_diff(diff)
        logger.info("Found %d issues in PR %d", len(findings), pr_id)

        to_commit = pr.fromRef.latestCommit or ""

        for finding in findings:
            try:
                await self.bitbucket.post_inline_comment(
                    project_key, repo_slug, pr_id, finding, to_commit
                )
            except Exception:
                logger.error(
                    "Failed to post inline comment on %s:%d",
                    finding.file,
                    finding.line,
                    exc_info=True,
                )

        summary = self._build_summary(findings)
        try:
            await self.bitbucket.post_pr_comment(
                project_key, repo_slug, pr_id, summary
            )
        except Exception:
            logger.error("Failed to post summary comment", exc_info=True)

    def _extract_project_repo(
        self, payload: WebhookPayload
    ) -> tuple[str, str]:
        pr = payload.pullRequest
        # Bitbucket Server webhooks nest repository under fromRef/toRef
        ref = pr.toRef
        if ref.repository:
            return ref.repository.project.key, ref.repository.slug
        ref = pr.fromRef
        if ref.repository:
            return ref.repository.project.key, ref.repository.slug
        return ("", "")

    def _build_summary(self, findings: list[ReviewFinding]) -> str:
        if not findings:
            return "**AI Review:** No issues found."

        counts = {"error": 0, "warning": 0, "info": 0}
        for f in findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1

        parts = []
        if counts["error"]:
            parts.append(f"{counts['error']} error(s)")
        if counts["warning"]:
            parts.append(f"{counts['warning']} warning(s)")
        if counts["info"]:
            parts.append(f"{counts['info']} info")

        return f"**AI Review:** {len(findings)} issue(s) found — {', '.join(parts)}"
