"""Structural tests for alembic migrations. No live DB — files parsed as text."""
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_VERSIONS = Path("alembic/versions")


def test_migration_chain_is_linear_and_reaches_004():
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revs = [(r.revision, r.down_revision) for r in script.walk_revisions()]
    # Newest first from walk_revisions
    chain = [r for r, _ in revs]
    assert chain == ["004", "003", "002", "001"]
    # Down-chain links match
    assert dict(revs) == {"004": "003", "003": "002", "002": "001", "001": None}


def test_004_creates_four_metric_views():
    text = (_VERSIONS / "004_metric_views.py").read_text()
    for view in (
        "v_reviewer_precision",
        "v_activity_weekly",
        "v_cost_by_model",
        "v_lead_time",
    ):
        assert f"CREATE VIEW {view}" in text, f"missing CREATE VIEW {view}"


def test_004_downgrade_drops_every_view_it_creates():
    text = (_VERSIONS / "004_metric_views.py").read_text()
    for view in (
        "v_reviewer_precision",
        "v_activity_weekly",
        "v_cost_by_model",
        "v_lead_time",
    ):
        assert f"DROP VIEW IF EXISTS {view}" in text, f"missing DROP for {view}"


def test_004_excludes_deleted_prs_from_all_non_lead_time_views():
    text = (_VERSIONS / "004_metric_views.py").read_text()
    # reviewer_precision, activity, and cost-indirect all exclude deleted PRs
    # via the `pr.deleted_at IS NULL` filter. Cost-by-model reads only
    # review_statistics (no pr_reviews join), so it's excluded from this check.
    assert text.count("pr.deleted_at IS NULL") >= 3


def test_004_lead_time_requires_merged_and_opened_at():
    text = (_VERSIONS / "004_metric_views.py").read_text()
    # v_lead_time filters rows that have both timestamps
    assert "merged_at IS NOT NULL" in text
    assert "opened_at IS NOT NULL" in text


def test_004_precision_buckets_disagrees_by_finding_posted_week():
    """Both CTEs must bucket by review_findings.created_at — otherwise a
    finding posted in week N and disagreed in week N+1 splits across rows
    and a quiet week shows precision_score < 0."""
    text = (_VERSIONS / "004_metric_views.py").read_text()
    # disagreed CTE joins via review_findings.bitbucket_comment_id
    assert "rf.bitbucket_comment_id = fe.bitbucket_comment_id" in text
    # both CTEs bucket by the same source column
    assert text.count("DATE_TRUNC('week', rf.created_at)") >= 4  # 2 per CTE (SELECT + GROUP BY)
    # the old per-feedback-event bucketing must be gone
    assert "DATE_TRUNC('week', fe.created_at)" not in text


def test_004_precision_score_cast_to_float8():
    """asyncpg returns NUMERIC as Decimal; cast in SQL avoids per-FastAPI-version drift."""
    text = (_VERSIONS / "004_metric_views.py").read_text()
    assert "::float8" in text


def test_004_creates_lead_time_supporting_index():
    text = (_VERSIONS / "004_metric_views.py").read_text()
    assert "CREATE INDEX idx_pr_reviews_lead_time" in text
    assert "DROP INDEX IF EXISTS idx_pr_reviews_lead_time" in text


def test_003_adds_lifecycle_columns():
    text = (_VERSIONS / "003_pr_lifecycle_timestamps.py").read_text()
    for col in ("opened_at", "merged_at", "deleted_at"):
        assert f"ADD COLUMN {col} TIMESTAMPTZ" in text
