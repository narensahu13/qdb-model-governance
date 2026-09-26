"""One-shot migration: MMC/NMMC/VAL/VRQ/VFI → MC/VAL/FND.

Maps:
  MMC + NMMC → MC (materiality field preserved)
  VAL + VRQ  → VAL (VRQ becomes Ad-hoc nature)
  VFI        → FND

Also rewrites evidence linked_ids and thread response_ids.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TYPE_MAP = {
    "MMC": ("MC", "Material"),
    "NMMC": ("MC", "Non-material"),
    "VAL": ("VAL", None),
    "VRQ": ("VAL", None),
    "VFI": ("FND", None),
    # Already-migrated / identity
    "MC": ("MC", None),
    "FND": ("FND", None),
}


def _rewrite_id(old_id: str, id_map: dict[str, str]) -> str:
    if old_id in id_map:
        return id_map[old_id]
    # Thread response ids: PREFIX-NNN-Rk
    for old, new in id_map.items():
        if old_id.startswith(old + "-R"):
            return new + old_id[len(old):]
    return old_id


def migrate() -> None:
    req_path = DATA / "validation_requests.json"
    requests = json.loads(req_path.read_text(encoding="utf-8"))

    # First pass: assign new ids
    counters = {"MC": 0, "VAL": 0, "FND": 0}
    # Preserve VAL numbering where type stays VAL; allocate MC/FND by old numeric suffix when possible
    id_map: dict[str, str] = {}
    migrated: list[dict] = []

    # Pre-scan VAL max so VRQ gets next number
    for r in requests:
        if r["type"] == "VAL":
            try:
                counters["VAL"] = max(counters["VAL"], int(r["request_id"].split("-")[-1]))
            except ValueError:
                pass

    for r in requests:
        old_type = r["type"]
        old_id = r["request_id"]
        new_type, default_mat = TYPE_MAP[old_type]

        if old_type == "VAL":
            new_id = old_id  # keep VAL-NNN
        elif old_type in ("MMC", "NMMC", "MC"):
            try:
                num = int(old_id.split("-")[-1])
            except ValueError:
                counters["MC"] += 1
                num = counters["MC"]
            counters["MC"] = max(counters["MC"], num)
            new_id = f"MC-{num:03d}"
        elif old_type in ("VFI", "FND"):
            try:
                num = int(old_id.split("-")[-1])
            except ValueError:
                counters["FND"] += 1
                num = counters["FND"]
            counters["FND"] = max(counters["FND"], num)
            new_id = f"FND-{num:03d}"
        elif old_type == "VRQ":
            counters["VAL"] += 1
            new_id = f"VAL-{counters['VAL']:03d}"
        else:
            raise ValueError(f"Unknown type {old_type}")

        id_map[old_id] = new_id

        materiality = r.get("materiality")
        if materiality is None and default_mat:
            materiality = default_mat
        elif old_type == "MMC":
            materiality = "Material"
        elif old_type == "NMMC":
            materiality = "Non-material"

        subtype = r.get("validation_subtype")
        if old_type == "VRQ" and not subtype:
            subtype = "Ad-hoc"

        thread = []
        for entry in r.get("thread") or []:
            e = dict(entry)
            rid = e.get("response_id") or ""
            if rid.startswith(old_id):
                e["response_id"] = new_id + rid[len(old_id):]
            elif rid:
                e["response_id"] = _rewrite_id(rid, {old_id: new_id})
            thread.append(e)

        new_rec = {
            **{k: v for k, v in r.items() if k not in ("request_id", "type", "thread", "materiality", "validation_subtype")},
            "request_id": new_id,
            "type": new_type,
            "materiality": materiality,
            "validation_subtype": subtype,
            "thread": thread,
        }
        # Preserve prior id as legacy hint when renamed
        if old_id != new_id and not new_rec.get("legacy_id"):
            new_rec["legacy_id"] = old_id
        migrated.append(new_rec)

    type_order = {"MC": 0, "VAL": 1, "FND": 2}
    migrated.sort(key=lambda r: (type_order.get(r["type"], 9), r["request_id"]))

    req_path.write_text(json.dumps(migrated, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Evidence linked_ids
    ev_path = DATA / "evidence.json"
    evidence = json.loads(ev_path.read_text(encoding="utf-8"))
    for e in evidence:
        e["linked_id"] = _rewrite_id(e.get("linked_id") or "", id_map)
    ev_path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    from collections import Counter
    counts = Counter(r["type"] for r in migrated)
    print(f"Migrated {len(migrated)} requests -> {dict(counts)}")
    print(f"ID remaps: { {k: v for k, v in id_map.items() if k != v} }")
    print(f"Updated {len(evidence)} evidence rows")


if __name__ == "__main__":
    migrate()
