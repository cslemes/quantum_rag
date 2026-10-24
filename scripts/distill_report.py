"""Print (and save) the report of a pilot directory: python scripts/distill_report.py DIR"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qcagent.distill.report import pilot_report


def main() -> int:
    out_dir = Path(sys.argv[1])
    report = pilot_report(out_dir)
    (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
