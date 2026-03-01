from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from examples.claim_processing.claim_processing_common import evaluate_all_claims, to_pretty_json


def main() -> None:
    results = [evaluation.to_dict() for evaluation in evaluate_all_claims()]
    counts = {"approved": 0, "denied": 0, "continue_arbitration": 0}
    for result in results:
        counts[result["decision"]] = counts.get(result["decision"], 0) + 1

    print("=== Decision Summary ===")
    print(to_pretty_json(counts))

    print("\n=== Claim Results ===")
    for result in results:
        print(to_pretty_json(result))


if __name__ == "__main__":
    main()
