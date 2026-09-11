from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel, ConfigDict

app = FastAPI(title="ServiceNow Incident Webhook")


class IncidentPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_sys_id: str
    number: str
    short_description: str
    description: str


def process_incident(payload: IncidentPayload) -> None:
    # Put the heavier processing here.
    # Example: call Gemini, make the agentic decision, then update
    # the same ServiceNow incident.
    print(f"Processing incident {payload.number} ({payload.incident_sys_id})")


@app.post("/webhook", status_code=202)
async def webhook(payload: IncidentPayload, background_tasks: BackgroundTasks):
    # FastAPI/Pydantic validates the payload before this function runs.
    # Invalid/malformed requests automatically receive HTTP 422.
    background_tasks.add_task(process_incident, payload)

    return {
        "status": "accepted",
        "incident_sys_id": payload.incident_sys_id,
        "number": payload.number,
    }
