"""Runtime configuration: where the database and the evidence folder live.

Both paths can be overridden with environment variables so the platform can
point at a dedicated evidence folder (e.g. a shared drive) without code changes:

    QDB_MRM_DB            path to the SQLite database file
    QDB_MRM_EVIDENCE_DIR  path to the dedicated evidence folder

Defaults keep everything inside the project's data/ folder.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
SEED_DIR = DATA_DIR / "seed"


def db_path() -> Path:
    return Path(os.environ.get("QDB_MRM_DB", DATA_DIR / "qdb_mrm.db"))


def evidence_dir() -> Path:
    return Path(os.environ.get("QDB_MRM_EVIDENCE_DIR", DATA_DIR / "evidence"))
