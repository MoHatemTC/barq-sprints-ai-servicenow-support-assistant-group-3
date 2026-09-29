import hashlib, hmac, json, requests

SECRET = "rLeYeCqHjkeDTHNtOpLYJgoWhyhgPDUq"
url = "http://localhost:8000/api/v1/events/servicenow"

payload = {
    "incident_sys_id": "bbc2e7c32fcf4b102e0e5b707fa4e3a3",
    "number": "INC0010032",
}
body = json.dumps(payload).encode("utf-8")
sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()

resp = requests.post(
    url,
    data=body,
    headers={"Content-Type": "application/json", "X-Signature": sig},
)
print(resp.status_code, resp.json())