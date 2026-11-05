from datetime import date, datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from geupsikdeul_backend.models.enums import PollStatus


class PollStatusFilter(StrEnum):
    open = "open"
    closed = "closed"
    all = "all"


class PollSummary(BaseModel):
    id: int
    title: str
    target_date: date
    opens_at: datetime
    closes_at: datetime
    status: PollStatus
    has_voted: bool
    total_votes: int


class PollOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    menu_name: str
    description: str | None
    image_url: str | None


class PollDetail(BaseModel):
    id: int
    title: str
    description: str | None
    target_date: date
    opens_at: datetime
    closes_at: datetime
    status: PollStatus
    has_voted: bool
    my_option_id: int | None
    options: list[PollOptionRead]


class VoteRequest(BaseModel):
    option_id: int


class VoteResponse(BaseModel):
    poll_id: int
    option_id: int
    voted_at: datetime


class OptionResult(BaseModel):
    option_id: int
    menu_name: str
    vote_count: int
    percentage: float
    is_winner: bool


class PollResult(BaseModel):
    poll_id: int
    title: str
    target_date: date
    closed_at: datetime
    total_votes: int
    results: list[OptionResult]


# ---- admin ----


class PollOptionCreate(BaseModel):
    menu_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=500)


class PollCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    target_date: date
    opens_at: AwareDatetime
    closes_at: AwareDatetime
    options: list[PollOptionCreate]


class PollUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    target_date: date | None = None
    opens_at: AwareDatetime | None = None
    closes_at: AwareDatetime | None = None
    options: list[PollOptionCreate] | None = None


class AdminPollRead(BaseModel):
    id: int
    title: str
    description: str | None
    target_date: date
    opens_at: datetime
    closes_at: datetime
    status: PollStatus
    is_published: bool
    total_votes: int
    created_at: datetime
    options: list[PollOptionRead]


class OptionCount(BaseModel):
    option_id: int
    menu_name: str
    vote_count: int


class GradeParticipation(BaseModel):
    grade: int
    voted: int
    eligible: int
    rate: float


class PollStats(BaseModel):
    poll_id: int
    total_votes: int
    eligible_students: int
    participation_rate: float
    by_option: list[OptionCount]
    by_grade: list[GradeParticipation]


class NonVoter(BaseModel):
    student_no: str
    name: str
    grade: int | None
    class_no: int | None


class NonVoterList(BaseModel):
    items: list[NonVoter]
    total: int
