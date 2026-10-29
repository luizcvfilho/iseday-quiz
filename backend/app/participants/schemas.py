from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_version_id: UUID
    school_id: UUID
    full_name: Name
    phone: Annotated[str, StringConstraints(pattern=r"^\+55[1-9][0-9][0-9]{8,9}$")]
    email: Annotated[EmailStr, Field(max_length=254)]
    privacy_notice_version: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement_ids: list[UUID] = Field(min_length=25, max_length=25)

    @field_validator("statement_ids")
    @classmethod
    def unique_statements(cls, values):
        if len(set(values)) != 25:
            raise ValueError("As 25 afirmativas devem ser únicas.")
        return values


class PublicStatement(BaseModel):
    id: UUID
    display_order: int
    text: str


class CurrentQuiz(BaseModel):
    id: UUID
    version_number: int
    event_name: str
    required_selection_count: int
    privacy_notice_version: str
    privacy_notice_text: str
    statements: list[PublicStatement]


class PublicSchool(BaseModel):
    id: UUID
    name: str
    city: str | None
    state_code: str | None


class ParticipationSession(BaseModel):
    id: UUID
    quiz_version_id: UUID
    status: Literal["draft", "submitted", "completed"]
    access_expires_at: datetime


class AreaResult(BaseModel):
    id: UUID
    name: str
    score: int
    is_winner: bool


class CourseResult(BaseModel):
    id: UUID
    area_id: UUID
    name: str
    score: int
    is_recommended: bool


class ParticipationResult(BaseModel):
    participation_id: UUID
    quiz_version_id: UUID
    status: Literal["submitted", "completed"]
    submitted_at: datetime
    statement_ids: list[UUID]
    areas: list[AreaResult]
    courses: list[CourseResult]
