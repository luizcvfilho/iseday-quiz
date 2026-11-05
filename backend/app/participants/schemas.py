from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class Registration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quiz_version_id: UUID
    school_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
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


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agrees_with_result: StrictBool
    chosen_course_id: UUID | None = None

    @model_validator(mode="after")
    def course_matches_agreement(self):
        if self.agrees_with_result and self.chosen_course_id is None:
            raise ValueError("Escolha um dos cursos sugeridos ao concordar com o resultado.")
        if not self.agrees_with_result and self.chosen_course_id is not None:
            raise ValueError("Não escolha um curso ao discordar do resultado.")
        return self


class PublicStatement(BaseModel):
    id: UUID
    display_order: int
    text: str


class QuizContent(BaseModel):
    id: UUID
    version_number: int
    event_name: str
    required_selection_count: int
    statements: list[PublicStatement]


class CurrentQuiz(QuizContent):
    privacy_notice_version: str
    privacy_notice_text: str


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


class FeedbackResult(BaseModel):
    participation_id: UUID
    status: Literal["completed"]
    completed_at: datetime
    agrees_with_result: bool
    chosen_course_id: UUID | None
    destination: str
    destination_instructions: str
    answered_at: datetime


class ParticipationResult(BaseModel):
    participation_id: UUID
    quiz_version_id: UUID
    status: Literal["submitted", "completed"]
    submitted_at: datetime
    statement_ids: list[UUID]
    areas: list[AreaResult]
    courses: list[CourseResult]
    feedback: FeedbackResult | None = None
