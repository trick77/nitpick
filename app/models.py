from pydantic import BaseModel


class PullRequestProject(BaseModel):
    key: str


class PullRequestRepository(BaseModel):
    slug: str
    project: PullRequestProject


class PullRequestRef(BaseModel):
    id: str
    displayId: str
    latestCommit: str | None = None
    repository: PullRequestRepository | None = None


class PullRequestUser(BaseModel):
    name: str
    slug: str | None = None
    displayName: str | None = None


class PullRequestParticipant(BaseModel):
    user: PullRequestUser


class PullRequest(BaseModel):
    id: int
    title: str
    fromRef: PullRequestRef
    toRef: PullRequestRef
    author: PullRequestParticipant


class WebhookPayload(BaseModel):
    eventKey: str
    pullRequest: PullRequest
    actor: PullRequestUser | None = None


class ReviewFinding(BaseModel):
    file: str
    line: int
    severity: str  # "error", "warning", "info"
    comment: str
