from enum import Enum
from typing import Optional

from pydantic import BaseModel


class InputType(Enum):
    WEBSITE = "website"
    TEXT = "text"
    CLINIC_NOTES = "clinic_notes"


class LegalDocument(BaseModel):
    content: str
    source: Optional[str] = None
    type: InputType
