# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "httpx",
#     "pydantic-settings",
#     "redis",
#     "celery",
# ]
# ///
import os
import sys
import time
from pathlib import Path

# Add src to sys.path so barq_support is importable
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from barq_support.settings import get_settings
from barq_support.servicenow import ServiceNowClient

def main():
    settings = get_settings()
    client = ServiceNowClient(settings)
    
    print("=" * 60)
    print("1. Creating test incident in ServiceNow...")
    print("=" * 60)
    
    payload = {
        "short_description": "E2E Test: Outlook disconnected from server",
        "description": "User Outlook client reports disconnected status. Cannot send or receive emails.",
        "category": "software",
        "urgency": "3",
        "impact": "3",
    }
    
    res = client._request("POST", "/api/now/table/incident", json=payload)
    incident = res.get("result", {})
    sys_id = incident.get("sys_id")
    number = incident.get("number")
    
    if not sys_id:
        print("Failed to create incident:", res)
        sys.exit(1)
        
    print(f"Incident created successfully:")
    print(f"  Number: {number}")
    print(f"  sys_id: {sys_id}")
    print("\nWaiting for ServiceNow Business Rule -> ngrok -> FastAPI -> Celery -> Agent -> ServiceNow writeback...")
    
    # Poll ServiceNow for up to 90 seconds
    ai_fields = [
        "x_2215697_ai_ser_0_ai_status",
        "x_2215697_ai_ser_0_ai_processed",
        "x_2215697_ai_ser_0_human_review_required",
        "x_2215697_ai_ser_0_ai_confidence",
        "x_2215697_ai_ser_0_ai_suggested_response",
    ]
    sysparm_fields = "number,sys_id,category,active," + ",".join(ai_fields)
    
    max_wait = 90
    interval = 5
    elapsed = 0
    completed = False
    last_status = None
    
    while elapsed < max_wait:
        time.sleep(interval)
        elapsed += interval
        
        inc_data = client._request(
            "GET",
            f"/api/now/table/incident/{sys_id}",
            params={"sysparm_fields": sysparm_fields},
        ).get("result", {})
        
        current_status = inc_data.get("x_2215697_ai_ser_0_ai_status") or "(empty)"
        processed = inc_data.get("x_2215697_ai_ser_0_ai_processed")
        
        if current_status != last_status:
            print(f"[{elapsed}s] Incident status changed: ai_status='{current_status}', ai_processed='{processed}'")
            last_status = current_status
        else:
            print(f"[{elapsed}s] Current status: ai_status='{current_status}', ai_processed='{processed}'")
            
        if processed in [True, "true", "1"] or current_status in ["suggested", "escalated"]:
            completed = True
            print("\n" + "=" * 60)
            print("END-TO-END PROCESSING COMPLETED!")
            print("=" * 60)
            for f in ai_fields:
                print(f"  {f}: {inc_data.get(f)}")
            break
            
    if not completed:
        print("\nTimed out waiting for incident to be processed.")
        print(f"Final state: {inc_data}")
        sys.exit(1)

if __name__ == "__main__":
    main()
