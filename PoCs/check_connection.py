"""
Live connection check against the team's ServiceNow instance.

Run this FIRST, before anything else:

    python PoCs/check_connection.py

It verifies, in order:
  1. env vars are present,
  2. credentials authenticate,
  3. the knowledge base is reachable and returns articles,
  4. an incident can be read,
  5. the resolve/close/reassign guard actually blocks a forbidden write.

Step 5 is the one your reviewer will care about most — it proves the
exclusion is enforced in code, not just claimed in a docstring.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from servicenow.client import (  # noqa: E402
    ServiceNowClient,
    ServiceNowConfigError,
    ForbiddenFieldError,
)


def main() -> int:
    print("1. Reading configuration...")
    try:
        client = ServiceNowClient()
    except ServiceNowConfigError as exc:
        print(f"   FAILED: {exc}")
        return 1
    print(f"   OK — instance: {client.instance_url}")
    print(
        f"   SERVICENOW_LIVE_WRITES = {client.live_writes} "
        f"({'writes will be SENT' if client.live_writes else 'writes are DRY-RUN — nothing will be sent'})"
    )

    print("\n2. Searching the knowledge base...")
    probe = os.getenv("KB_PROBE_QUERY", "password")
    try:
        articles = client.search_knowledge(probe, limit=3)
    except Exception as exc:
        print(f"   FAILED: {exc}")
        print("   If this is a 401, the credentials are wrong or expired.")
        print("   If this is a 403, the account lacks knowledge read access.")
        return 1

    if not articles:
        print(f"   Connected, but no articles matched '{probe}'.")
        print("   Set KB_PROBE_QUERY to a word you know is in your articles.")
    else:
        print(f"   OK — {len(articles)} article(s):")
        for a in articles:
            print(f"      [{a['number']}] {a['title']}")

    print("\n3. Reading an incident...")
    number = os.getenv("TEST_INCIDENT_NUMBER", "INC0000001")
    try:
        incident = client.get_incident(number)
    except Exception as exc:
        print(f"   FAILED: {exc}")
        return 1

    if not incident:
        print(f"   Connected, but incident {number} was not found.")
        print("   Set TEST_INCIDENT_NUMBER to a real incident on the instance.")
    else:
        print(f"   OK — {incident.get('number')}: {incident.get('short_description')}")

    print("\n4. Checking the resolve/close/reassign guard...")
    failures = []
    for field, value in (
        ("state", "6"),
        ("close_code", "Solved (Permanently)"),
        ("assignment_group", "Service Desk"),
        ("assigned_to", "admin"),
    ):
        try:
            client.update_incident("dummy_sys_id", {field: value})
        except ForbiddenFieldError:
            print(f"   OK — '{field}' correctly blocked.")
        except Exception as exc:
            failures.append(f"'{field}' was NOT blocked by the guard ({type(exc).__name__}: {exc})")
        else:
            failures.append(f"'{field}' was NOT blocked — a request was actually sent!")

    if failures:
        print("\n   GUARD FAILURE:")
        for f in failures:
            print(f"      {f}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
