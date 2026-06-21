from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nba2k_editor.models.data_model import EditorDataModel


def main() -> int:
    model = EditorDataModel(target_executable="NBA2K26.exe")
    print("attach", model.attach(), model.last_status)
    for domain, limit in (("Teams", 8), ("Staff", 8), ("Stadiums", 8), ("Jerseys", 8), ("Shoes", 8), ("Players", 3)):
        try:
            base = model.domain_base(domain)
            stride = model.domain_stride(domain)
            items = model.scan_records(domain, limit=limit)
            print(domain, "base", hex(base), "stride", stride, "count", len(items))
            print([(item.index, hex(item.address), item.label) for item in items])
        except Exception as exc:
            print(domain, "ERR", type(exc).__name__, exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
