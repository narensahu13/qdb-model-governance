"""Rebuild the database and evidence folder from data/seed/.

Use after editing the seed JSON files, or to discard all changes made in the
app. This deletes the current database and evidence folder.

Run from the project root:  python scripts/reset_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import repository  # noqa: E402

if __name__ == "__main__":
    repository.reset_db()
    ok, _ = repository.verify_audit_chain()
    print(f"Database rebuilt at {config.db_path()} "
          f"({len(repository.list_models())} models; audit chain {'OK' if ok else 'BROKEN'}).")
    print(f"Evidence folder: {config.evidence_dir()}")
