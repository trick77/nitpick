"""Metric views over retained PR review data

Revision ID: 004
Revises: 003
Create Date: 2026-04-24

Four views, one question each:
    v_reviewer_precision  — how useful is the LLM review?        (higher = better)
    v_lead_time           — DORA lead-time for changes
    v_activity_weekly     — SPACE Activity: PRs / runs per author per week
    v_cost_by_model       — LLM token spend per model per week
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reviewer precision = 1 - disagree_rate. Positive framing.
    # feedback_events only holds "negative" (disagree) rows today,
    # so COUNT(*) = disagreed.
    op.execute("""
        CREATE VIEW v_reviewer_precision AS
        WITH posted AS (
            SELECT
                rs.project_key,
                rs.repo_slug,
                DATE_TRUNC('week', rs.created_at) AS week,
                SUM(rs.findings_posted) AS n_posted
            FROM review_statistics rs
            LEFT JOIN pr_reviews pr
                ON pr.project_key = rs.project_key
               AND pr.repo_slug   = rs.repo_slug
               AND pr.pr_id       = rs.pr_id
            WHERE pr.deleted_at IS NULL OR pr.id IS NULL
            GROUP BY rs.project_key, rs.repo_slug, DATE_TRUNC('week', rs.created_at)
        ),
        disagreed AS (
            SELECT
                fe.project_key,
                fe.repo_slug,
                DATE_TRUNC('week', fe.created_at) AS week,
                COUNT(*) AS n_disagreed
            FROM feedback_events fe
            LEFT JOIN pr_reviews pr
                ON pr.project_key = fe.project_key
               AND pr.repo_slug   = fe.repo_slug
               AND pr.pr_id       = fe.pr_id
            WHERE fe.classification = 'negative'
              AND (pr.deleted_at IS NULL OR pr.id IS NULL)
            GROUP BY fe.project_key, fe.repo_slug, DATE_TRUNC('week', fe.created_at)
        )
        SELECT
            p.project_key,
            p.repo_slug,
            p.week,
            p.n_posted,
            COALESCE(d.n_disagreed, 0) AS n_disagreed,
            CASE
                WHEN p.n_posted > 0 THEN
                    ROUND(1 - COALESCE(d.n_disagreed, 0)::numeric / p.n_posted, 3)
                ELSE NULL
            END AS precision
        FROM posted p
        LEFT JOIN disagreed d
            ON d.project_key = p.project_key
           AND d.repo_slug   = p.repo_slug
           AND d.week        = p.week
    """)

    # Activity per author per week — PRs observed and review runs.
    op.execute("""
        CREATE VIEW v_activity_weekly AS
        SELECT
            rs.author,
            DATE_TRUNC('week', rs.created_at) AS week,
            COUNT(DISTINCT (rs.project_key, rs.repo_slug, rs.pr_id)) AS prs,
            COUNT(*) AS review_runs
        FROM review_statistics rs
        LEFT JOIN pr_reviews pr
            ON pr.project_key = rs.project_key
           AND pr.repo_slug   = rs.repo_slug
           AND pr.pr_id       = rs.pr_id
        WHERE rs.author IS NOT NULL
          AND (pr.deleted_at IS NULL OR pr.id IS NULL)
        GROUP BY rs.author, DATE_TRUNC('week', rs.created_at)
    """)

    # LLM cost per model per week.
    op.execute("""
        CREATE VIEW v_cost_by_model AS
        SELECT
            rs.model_name,
            DATE_TRUNC('week', rs.created_at) AS week,
            COUNT(*)                      AS runs,
            SUM(rs.prompt_tokens)         AS prompt_tokens,
            SUM(rs.completion_tokens)     AS completion_tokens,
            SUM(rs.prompt_tokens + rs.completion_tokens) AS total_tokens,
            AVG(rs.elapsed_seconds)       AS avg_elapsed_seconds
        FROM review_statistics rs
        WHERE rs.model_name IS NOT NULL
        GROUP BY rs.model_name, DATE_TRUNC('week', rs.created_at)
    """)

    # Lead-time per merged PR (DORA).
    op.execute("""
        CREATE VIEW v_lead_time AS
        SELECT
            project_key,
            repo_slug,
            pr_id,
            author,
            opened_at,
            merged_at,
            EXTRACT(EPOCH FROM (merged_at - opened_at))::bigint AS lead_time_seconds
        FROM pr_reviews
        WHERE merged_at IS NOT NULL
          AND opened_at IS NOT NULL
          AND deleted_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_lead_time")
    op.execute("DROP VIEW IF EXISTS v_cost_by_model")
    op.execute("DROP VIEW IF EXISTS v_activity_weekly")
    op.execute("DROP VIEW IF EXISTS v_reviewer_precision")
