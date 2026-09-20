"""CLI:  python -m support_agent <scenario>   (see mock_data.SCENARIOS)"""

from __future__ import annotations

import argparse
import json

from .agent import generate_recommendation
from .mock_data import SCENARIOS


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the grounded support agent on a mock scenario.")
    parser.add_argument("scenario", choices=sorted(SCENARIOS), help="mock scenario to run")
    parser.add_argument("--json", action="store_true", help="print the full AgentResult as JSON")
    args = parser.parse_args()

    sc = SCENARIOS[args.scenario]
    result = generate_recommendation(
        sc["incident"],
        sc["chunks"],
        short_circuit_on_empty=sc.get("short_circuit_on_empty", True),
    )
    if args.json:
        print(json.dumps(result.__dict__, indent=2, default=str))
    else:
        print(f"[{result.status}] {sc['title']}\n")
        print(result.text)
        if result.decline_reason:
            print(f"\n(decline_reason: {result.decline_reason})")


if __name__ == "__main__":
    main()
