from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Instructions = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SchoolInput(Input):
    name: Name
    city: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    state_code: Annotated[str, StringConstraints(pattern=r"^([A-Z]{2})?$")] = ""
    is_active: bool = Field(default=True, strict=True)


class SchoolItem(SchoolInput):
    id: UUID


class NewVersion(Input):
    event_name: Name
    source_version_id: UUID | None = None


class Destination(Input):
    destination: Name
    destination_instructions: Instructions


class AreaInput(Destination):
    id: UUID


class CourseInput(Input):
    id: UUID
    destination: Name | None = None
    destination_instructions: Instructions | None = None

    @model_validator(mode="after")
    def destination_pair(self):
        if (self.destination is None) != (self.destination_instructions is None):
            raise ValueError("Informe o destino e as instruções juntos, ou deixe ambos vazios.")
        return self


class WeightInput(Input):
    course_id: UUID
    weight: int = Field(strict=True, ge=1, le=32767)


class StatementInput(Input):
    id: UUID | None = None
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    courses: list[WeightInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique_courses(self):
        if len({link.course_id for link in self.courses}) != len(self.courses):
            raise ValueError("Cada curso deve aparecer uma única vez por afirmativa.")
        return self


class VersionInput(Input):
    expected_revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    event_name: Name
    psychology_destination: Name
    psychology_instructions: Instructions
    areas: list[AreaInput] = Field(max_length=100)
    courses: list[CourseInput] = Field(max_length=500)
    statements: list[StatementInput] = Field(max_length=1000)

    @model_validator(mode="after")
    def unique_statements(self):
        ids = [s.id for s in self.statements if s.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("Cada afirmativa deve aparecer uma única vez.")
        texts = [" ".join(s.text.split()).casefold() for s in self.statements]
        if len(texts) != len(set(texts)):
            raise ValueError("Há afirmativas com textos repetidos. Revise o catálogo.")
        return self


class AreaItem(AreaInput):
    name: str


class CourseItem(CourseInput):
    name: str
    area_id: UUID


class VersionItem(BaseModel):
    id: UUID
    event_name: str
    version_number: int
    status: Literal["draft", "published", "archived"]
    created_at: datetime
    statement_count: int


class WeightItem(WeightInput):
    course: str


class StatementItem(BaseModel):
    id: UUID
    number: int
    text: str
    courses: list[WeightItem]


class VersionDetail(VersionItem):
    revision: str
    psychology_destination: str
    psychology_instructions: str
    areas: list[AreaItem]
    courses: list[CourseItem]
    review_notes: list[str]
    statements: list[StatementItem]


class PublishVersion(Input):
    reviewed: bool = Field(strict=True)
    expected_published_id: UUID | None
    expected_revision: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def reviewed_content(self):
        if not self.reviewed:
            raise ValueError("Confirme a revisão institucional antes de publicar.")
        return self
