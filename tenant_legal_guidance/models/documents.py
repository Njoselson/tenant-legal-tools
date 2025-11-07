from enum import Enum

from pydantic import BaseModel


class InputType(Enum):
    WEBSITE = "website"
    TEXT = "text"
    CLINIC_NOTES = "clinic_notes"


class LegalDocument(BaseModel):
    content: str
    source: str | None = None
    type: InputType
