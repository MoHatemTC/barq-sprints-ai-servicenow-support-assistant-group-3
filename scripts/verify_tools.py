"""
Structural verification of the S2.3 tool definitions.

Runs fully offline — no credentials, no network, no ContextVar setup —
so any teammate (including S2.4 agent-loop work) can run it immediately.

Asserts:
  * exactly four tools are exported,
  * each has a name, purpose description, and args schema,
  * repeatable tools say so; terminal tools say they end the run,
  * no tool's input schema could carry a resolve/close/reassign field,
  * each tool can be invoked directly with a sample payload (mocked body).

Run with: python scripts/verify_tools.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from barq_support.agent.tools import AGENT_TOOLS, REPEATABLE_TOOLS, TERMINAL_TOOLS  # noqa: E402

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

    print("\nMock invocations (no network, no credentials)")
    print(" ", AGENT_TOOLS[0].invoke({"query": "VPN not connecting"}))
    print(" ", AGENT_TOOLS[1].invoke({"note_text": "Checked KB, found 2 candidate articles."}))
    print(
        " ",
        AGENT_TOOLS[2].invoke(
            {
                "resolution_procedure": "Restart the VPN client and re-authenticate.",
                "knowledge_article_references": ["KB0012345"],
            }
        ),
    )
    print(" ", AGENT_TOOLS[3].invoke({"handoff_reason": "No matching KB article found."}))

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
