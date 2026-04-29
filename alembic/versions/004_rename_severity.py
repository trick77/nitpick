"""Rename severity values: critical -> issue, important -> suggestion

Revision ID: 004
Revises: 003
Create Date: 2026-04-29

Aligns the stored vocabulary with the user-facing labels (`Issue` /
`Suggestion`) so there's a single set of terms end-to-end.

- review_findings.severity: backfill 'critical' -> 'issue', 'important' -> 'suggestion'
- feedback_events.severity: same backfill
- review_statistics.critical_count    -> issue_count
- review_statistics.important_count   -> suggestion_count

Views in 002_metrics_and_lifecycle.py do not reference these columns or
severity literals, so no view rebuild is required.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE review_findings SET severity = 'issue' WHERE severity = 'critical'")
    op.execute("UPDATE review_findings SET severity = 'suggestion' WHERE severity = 'important'")
    op.execute("UPDATE feedback_events SET severity = 'issue' WHERE severity = 'critical'")
    op.execute("UPDATE feedback_events SET severity = 'suggestion' WHERE severity = 'important'")
    op.execute("ALTER TABLE review_statistics RENAME COLUMN critical_count TO issue_count")
    op.execute("ALTER TABLE review_statistics RENAME COLUMN important_count TO suggestion_count")


def downgrade() -> None:
    op.execute("ALTER TABLE review_statistics RENAME COLUMN suggestion_count TO important_count")
    op.execute("ALTER TABLE review_statistics RENAME COLUMN issue_count TO critical_count")
    op.execute("UPDATE feedback_events SET severity = 'important' WHERE severity = 'suggestion'")
    op.execute("UPDATE feedback_events SET severity = 'critical' WHERE severity = 'issue'")
    op.execute("UPDATE review_findings SET severity = 'important' WHERE severity = 'suggestion'")
    op.execute("UPDATE review_findings SET severity = 'critical' WHERE severity = 'issue'")
