from datetime import date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, model_validator

from app.participants.schemas import ParticipationResult, PublicStatement


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[EmailStr, Field(max_length=254)]
    password: Annotated[str, StringConstraints(min_length=1, max_length=1024)]


class AdminIdentity(BaseModel):
    id: UUID
    name: str
    email: str
    expires_at: datetime


class Filters(BaseModel):
    q: str = Field(default="", max_length=200)
    school_id: UUID | None = None
    quiz_version_id: UUID | None = None
    status: Literal["draft", "submitted", "completed"] | None = None
    area_id: UUID | None = None
    course_id: UUID | None = None
    agreement: Literal["yes", "no", "pending"] | None = None
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def valid_period(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("A data inicial deve ser anterior ou igual à data final.")
        if self.date_to == date.max:
            raise ValueError("Data final fora do intervalo permitido.")
        return self


class NamedItem(BaseModel):
    id: UUID
    name: str


class PageFilters(Filters):
    page: int = Field(default=1, ge=1, le=1000000)
    page_size: int = Field(default=20, ge=1, le=100)


class VersionItem(NamedItem):
    version_number: int


class CatalogItem(NamedItem):
    quiz_version_id: UUID


class Options(BaseModel):
    schools: list[NamedItem]
    versions: list[VersionItem]
    areas: list[CatalogItem]
    courses: list[CatalogItem]


class ParticipationRow(BaseModel):
    id: UUID
    full_name: str
    school: NamedItem
    quiz_version_id: UUID
    version_number: int
    status: Literal["draft", "submitted", "completed"]
    started_at: datetime
    submitted_at: datetime | None
    completed_at: datetime | None
    agrees_with_result: bool | None
    winning_areas: list[NamedItem] = Field(default_factory=list)
    recommended_courses: list[NamedItem] = Field(default_factory=list)


class ParticipationPage(BaseModel):
    items: list[ParticipationRow]
    total: int
    page: int
    page_size: int


class ParticipationDetail(ParticipationRow):
    email: str
    phone: str
    event_name: str
    privacy_notice_version: str
    selections: list[PublicStatement]
    result: ParticipationResult | None


class CountItem(NamedItem):
    count: int
    version_number: int | None = None


class Summary(BaseModel):
    total: int
    draft: int
    submitted: int
    completed: int
    agreed: int
    disagreed: int
    agreement_rate: float | None
    schools: list[CountItem]
    areas: list[CountItem]
    courses: list[CountItem]
