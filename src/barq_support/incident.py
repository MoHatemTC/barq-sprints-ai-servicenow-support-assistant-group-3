from pydantic import BaseModel, Field


class IncidentEvent(BaseModel):
    sys_id: str = Field(..., min_length=1)


class IncidentContext(BaseModel):
    number: str
    sys_id: str
    short_description: str
    description: str
    category: str