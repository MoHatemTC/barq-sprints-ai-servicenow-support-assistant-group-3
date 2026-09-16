"""
Structural verification of the S2.3 tool definitions.

Runs fully offline — no credentials, no network — so it works in CI and
for reviewers who don't have instance access.

Asserts:
  * exactly four tools are exported,
  * each has a name, purpose description, and args schema,
  * repeatable tools say so; terminal tools say they end the run,
  * no tool schema exposes a resolve/close/reassign field,
  * the client's field guard blocks every forbidden write.

Run with: python PoCs/verify_tools.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from tools.agent_tools import AGENT_TOOLS, REPEATABLE_TOOLS, TERMINAL_TOOLS  # noqa: E402
from servicenow.client import (  # noqa: E402
    ServiceNowClient,
    ForbiddenFieldError,
    BLOCKED_INCIDENT_FIELDS,
    ALLOWED_INCIDENT_FIELDS,
)

FORBIDDEN_SCHEMA_FIELDS = {
    "state", "incident_state", "close_code", "close_notes",
    "resolution_code", "assignment_group", "assigned_to", "active",
}


def main() -> None:
    print("Tool inventory")
    assert len(AGENT_TOOLS) == 4, f"Expected 4 tools, found {len(AGENT_TOOLS)}"
    assert len(REPEATABLE_TOOLS) == 2 and len(TERMINAL_TOOLS) == 2

    for tool in AGENT_TOOLS:
        schema_fields = set(tool.args_schema.model_fields)
        print(f"  {tool.name:<24} schema={sorted(schema_fields)}")

        assert tool.description.strip(), f"{tool.name} has no description"

        leaked = schema_fields & FORBIDDEN_SCHEMA_FIELDS
        assert not leaked, f"{tool.name} exposes forbidden input field(s): {sorted(leaked)}"

        desc = tool.description.lower()
        if tool in REPEATABLE_TOOLS:
            assert "repeatedly" in desc and "without ending the run" in desc, (
                f"{tool.name} must state it is repeatable and does not end the run"
            )
        else:
            assert "ends the run" in desc, f"{tool.name} must state it ends the run"

    print("\nField guard")
    print(f"  allowed: {sorted(ALLOWED_INCIDENT_FIELDS)}")

    # Build a client without touching the network or real credentials.
    guard = ServiceNowClient.__new__(ServiceNowClient)

    for field in sorted(BLOCKED_INCIDENT_FIELDS):
        try:
            ServiceNowClient.update_incident(guard, "dummy", {field: "x"})
        except ForbiddenFieldError:
            pass
        else:
            raise AssertionError(f"'{field}' was not blocked by the guard")
    print(f"  blocked: all {len(BLOCKED_INCIDENT_FIELDS)} forbidden fields rejected")

    try:
        ServiceNowClient.update_incident(guard, "dummy", {"some_random_field": "x"})
    except ForbiddenFieldError:
        print("  blocked: unknown fields rejected by allow-list")
    else:
        raise AssertionError("Unknown field was not blocked")

    print("\nDefault write safety (no network, no credentials needed)")
    guard.live_writes = False  # this is the default from SERVICENOW_LIVE_WRITES
    result = ServiceNowClient.update_incident(guard, "dummy", {"work_notes": "test"})
    assert result.get("dry_run") is True, "Expected a dry-run result when live_writes is False"
    print("  OK — with live_writes=False, an allowed write is validated but never sent")

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
