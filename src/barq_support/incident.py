from typing import Any

from pydantic import BaseModel, Field, model_validator


class IncidentEvent(BaseModel):
    sys_id: str = Field(default="", min_length=1)

    @model_validator(mode="before")
    @classmethod
    def populate_sys_id(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("sys_id"):
                if data.get("incident_sys_id"):
                    data["sys_id"] = data["incident_sys_id"]
                elif data.get("event_id"):
                    data["sys_id"] = data["event_id"]
        return data



class IncidentContext(BaseModel):
    number: str
    sys_id: str
    short_description: str
    description: str
    category: str