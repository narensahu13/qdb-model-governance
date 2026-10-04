"""SQLite persistence for the governance platform.

This module has no Streamlit dependency, so it can be unit-tested and reused
by scripts. Every table holds one JSON document per record plus the columns
needed for filtering; the application reads and writes whole documents.

The audit log is the control that matters most to an auditor, so it is:
  * append-only — database triggers reject any UPDATE or DELETE;
  * hash-chained — each event stores the SHA-256 of the previous event's hash
    plus its own content, so an edit made outside the application (e.g. with
    a SQLite browser, after dropping the triggers) breaks the chain and
    `verify_audit_chain()` reports the first broken event.

The database is created and seeded from data/seed/ on first use.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import config

SCHEMA_VERSION = "6"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    name TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    doc  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS models (
    model_id TEXT PRIMARY KEY,
    doc      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
    request_id TEXT PRIMARY KEY,
    model_id   TEXT NOT NULL,
    type       TEXT NOT NULL,
    status     TEXT NOT NULL,
    doc        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_requests_model ON requests(model_id);
CREATE TABLE IF NOT EXISTS evidence (
    evidence_id TEXT PRIMARY KEY,
    model_id    TEXT NOT NULL,
    sha256      TEXT NOT NULL,
    doc         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_evidence_model ON evidence(model_id);
CREATE TABLE IF NOT EXISTS tools (
    tool_id TEXT PRIMARY KEY,
    doc     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kmpis (
    kmpi_id  TEXT PRIMARY KEY,
    model_id TEXT NOT NULL,
    doc      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_kmpis_model ON kmpis(model_id);
CREATE TABLE IF NOT EXISTS kmpi_returns (
    model_id TEXT NOT NULL,
    period   TEXT NOT NULL,
    status   TEXT NOT NULL,
    doc      TEXT NOT NULL,
    PRIMARY KEY (model_id, period)
);
CREATE TABLE IF NOT EXISTS audit_log (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    user        TEXT NOT NULL,
    role        TEXT NOT NULL,
    action      TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    details     TEXT NOT NULL,
    before      TEXT,
    after       TEXT,
    prev_hash   TEXT NOT NULL,
    hash        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_model ON audit_log(model_id);
CREATE TRIGGER IF NOT EXISTS audit_log_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only');
END;
"""

GENESIS_HASH = "0" * 64

AUDIT_FIELDS = (
    "timestamp", "user", "role", "action", "entity_type",
    "entity_id", "model_id", "details", "before", "after",
)


# ---------------------------------------------------------------- connection
def _connect() -> sqlite3.Connection:
    path = config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def tx():
    """One transaction: commits on success, rolls back on any exception."""
    ensure_db()
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _is_seeded(conn: sqlite3.Connection) -> bool:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'seeded_at'").fetchone()
    except sqlite3.OperationalError:
        return False
    return row is not None


_ready: set[str] = set()


def ensure_db() -> None:
    """Create the schema and seed it on first use (idempotent)."""
    key = str(config.db_path())
    if key in _ready and config.db_path().exists():
        return
    conn = _connect()
    try:
        if _is_seeded(conn):
            version = _stored_version(conn)
            if version == SCHEMA_VERSION:
                _ready.add(key)
                return
            conn.close()
            _backup_and_reset(version)
            conn = _connect()
        conn.executescript(SCHEMA)
        _seed(conn, config.SEED_DIR)
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (SCHEMA_VERSION,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('seeded_at', ?)",
            (datetime.now().isoformat(timespec="seconds"),),
        )
        conn.commit()
        _ready.add(key)
    finally:
        conn.close()


def reset_db() -> None:
    """Delete the database and the evidence folder, then reseed from data/seed/."""
    path = config.db_path()
    _ready.discard(str(path))
    if path.exists():
        path.unlink()
    ev = config.evidence_dir()
    if ev.exists():
        shutil.rmtree(ev)
    ensure_db()


# ---------------------------------------------------------------- hashing
def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(obj) -> str:
    """Stable serialisation for hashing (sorted keys)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _dump(obj) -> str:
    """Storage serialisation: keeps key order (e.g. the documentation checklist)."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _event_hash(prev_hash: str, event: dict) -> str:
    payload = {k: event.get(k) for k in AUDIT_FIELDS}
    return sha256_bytes((prev_hash + _canonical(payload)).encode("utf-8"))


# ---------------------------------------------------------------- seed
def _seed(conn: sqlite3.Connection, seed_dir: Path) -> None:
    def load(name):
        with open(seed_dir / name, encoding="utf-8") as f:
            return json.load(f)

    for u in load("users.json"):
        conn.execute(
            "INSERT INTO users(name, role, doc) VALUES (?, ?, ?)",
            (u["name"], u["role"], _dump(u)),
        )
    for m in load("models.json"):
        conn.execute(
            "INSERT INTO models(model_id, doc) VALUES (?, ?)",
            (m["model_id"], _dump(m)),
        )
    for r in load("validation_requests.json"):
        conn.execute(
            "INSERT INTO requests(request_id, model_id, type, status, doc) VALUES (?, ?, ?, ?, ?)",
            (r["request_id"], r["model_id"], r["type"], r["status"], _dump(r)),
        )

    # Evidence: copy seed files into the evidence folder and hash them.
    ev_root = config.evidence_dir()
    for e in load("evidence.json"):
        src = seed_dir / "evidence" / e["stored_path"]
        dst = ev_root / e["stored_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        e = {**e, "sha256": sha256_bytes(dst.read_bytes())}
        conn.execute(
            "INSERT INTO evidence(evidence_id, model_id, sha256, doc) VALUES (?, ?, ?, ?)",
            (e["evidence_id"], e["model_id"], e["sha256"], _dump(e)),
        )

    for k in load("kmpis.json"):
        put_kmpi(conn, k)
    for r in load("kmpi_returns.json"):
        put_kmpi_return(conn, r)

    for t in load("tools.json"):
        conn.execute("INSERT INTO tools(tool_id, doc) VALUES (?, ?)", (t["tool_id"], _dump(t)))

    for ev in sorted(load("audit_log.json"), key=lambda e: e["timestamp"]):
        _append_audit(conn, ev)


# ---------------------------------------------------------------- upgrades
def _stored_version(conn) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
    return row["value"] if row else "1"


def _backup_and_reset(old_version: str) -> Path:
    """A database from an older schema is kept as a backup and rebuilt from seed
    (v3 renumbered the models; v5 replaced monitoring with KMPIs and the CRO
    approval with owner and sponsor approvals; v6 simplified KMPIs to pass/fail
    and added annual confirmation and decommissioning)."""
    path = config.db_path()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = path.with_name(f"{path.stem}.v{old_version}-backup-{stamp}{path.suffix}")
    shutil.move(str(path), backup)
    ev = config.evidence_dir()
    if ev.exists():
        shutil.move(str(ev), ev.with_name(f"{ev.name}.v{old_version}-backup-{stamp}"))
    return backup


# ---------------------------------------------------------------- documents
def _docs(conn, sql: str, params=()) -> list[dict]:
    return [json.loads(r["doc"]) for r in conn.execute(sql, params).fetchall()]


def list_users() -> list[dict]:
    with tx() as conn:
        return _docs(conn, "SELECT doc FROM users ORDER BY rowid")


def list_models() -> list[dict]:
    with tx() as conn:
        return _docs(conn, "SELECT doc FROM models ORDER BY model_id")


def put_user(conn, user: dict) -> None:
    conn.execute(
        "INSERT INTO users(name, role, doc) VALUES (?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET role = excluded.role, doc = excluded.doc",
        (user["name"], user["role"], _dump(user)),
    )


def delete_user(conn, name: str) -> None:
    conn.execute("DELETE FROM users WHERE name = ?", (name,))


def list_users_conn(conn) -> list[dict]:
    return _docs(conn, "SELECT doc FROM users ORDER BY rowid")


def delete_model(conn, model_id: str) -> None:
    conn.execute("DELETE FROM models WHERE model_id = ?", (model_id,))


def list_requests_conn(conn) -> list[dict]:
    return _docs(conn, "SELECT doc FROM requests ORDER BY request_id")


def list_tools_conn(conn) -> list[dict]:
    return _docs(conn, "SELECT doc FROM tools ORDER BY tool_id")


def update_evidence(conn, ev: dict) -> None:
    conn.execute("UPDATE evidence SET model_id = ?, doc = ? WHERE evidence_id = ?",
                 (ev["model_id"], _dump(ev), ev["evidence_id"]))


def db_bytes() -> bytes:
    """A consistent copy of the database file (for backup download)."""
    ensure_db()
    src = sqlite3.connect(config.db_path())
    dst = sqlite3.connect(":memory:")
    src.backup(dst)
    src.close()
    data = dst.serialize()
    dst.close()
    return bytes(data)


def list_models_conn(conn) -> list[dict]:
    return _docs(conn, "SELECT doc FROM models ORDER BY model_id")


def get_model(model_id: str, conn=None) -> dict | None:
    if conn is None:
        with tx() as c:
            return get_model(model_id, c)
    rows = _docs(conn, "SELECT doc FROM models WHERE model_id = ?", (model_id,))
    return rows[0] if rows else None


def put_model(conn, model: dict) -> None:
    conn.execute(
        "INSERT INTO models(model_id, doc) VALUES (?, ?) "
        "ON CONFLICT(model_id) DO UPDATE SET doc = excluded.doc",
        (model["model_id"], _dump(model)),
    )


def list_requests(model_id: str | None = None) -> list[dict]:
    with tx() as conn:
        if model_id:
            return _docs(
                conn, "SELECT doc FROM requests WHERE model_id = ? ORDER BY request_id",
                (model_id,),
            )
        return _docs(conn, "SELECT doc FROM requests ORDER BY request_id")


def get_request(request_id: str, conn=None) -> dict | None:
    if conn is None:
        with tx() as c:
            return get_request(request_id, c)
    rows = _docs(conn, "SELECT doc FROM requests WHERE request_id = ?", (request_id,))
    return rows[0] if rows else None


def put_request(conn, req: dict) -> None:
    conn.execute(
        "INSERT INTO requests(request_id, model_id, type, status, doc) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(request_id) DO UPDATE SET model_id = excluded.model_id, "
        "type = excluded.type, status = excluded.status, doc = excluded.doc",
        (req["request_id"], req["model_id"], req["type"], req["status"], _dump(req)),
    )


def request_ids(conn, rtype: str) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT request_id FROM requests WHERE type = ?", (rtype,),
    ).fetchall()]


def list_evidence() -> list[dict]:
    with tx() as conn:
        return _docs(conn, "SELECT doc FROM evidence ORDER BY evidence_id")


def list_evidence_conn(conn) -> list[dict]:
    return _docs(conn, "SELECT doc FROM evidence ORDER BY evidence_id")


def evidence_ids(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT evidence_id FROM evidence").fetchall()]


def put_evidence(conn, ev: dict) -> None:
    conn.execute(
        "INSERT INTO evidence(evidence_id, model_id, sha256, doc) VALUES (?, ?, ?, ?)",
        (ev["evidence_id"], ev["model_id"], ev["sha256"], _dump(ev)),
    )


def list_tools() -> list[dict]:
    with tx() as conn:
        return _docs(conn, "SELECT doc FROM tools ORDER BY tool_id")


def tool_ids(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT tool_id FROM tools").fetchall()]


def model_ids(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT model_id FROM models").fetchall()]


def put_tool(conn, tool: dict) -> None:
    conn.execute(
        "INSERT INTO tools(tool_id, doc) VALUES (?, ?) "
        "ON CONFLICT(tool_id) DO UPDATE SET doc = excluded.doc",
        (tool["tool_id"], _dump(tool)),
    )


# ---------------------------------------------------------------- KMPIs
def list_kmpis(conn=None) -> list[dict]:
    if conn is None:
        with tx() as c:
            return list_kmpis(c)
    return _docs(conn, "SELECT doc FROM kmpis ORDER BY kmpi_id")


def put_kmpi(conn, k: dict) -> None:
    conn.execute(
        "INSERT INTO kmpis(kmpi_id, model_id, doc) VALUES (?, ?, ?) "
        "ON CONFLICT(kmpi_id) DO UPDATE SET model_id = excluded.model_id, doc = excluded.doc",
        (k["kmpi_id"], k["model_id"], _dump(k)),
    )


def kmpi_ids(conn) -> list[str]:
    return [r[0] for r in conn.execute("SELECT kmpi_id FROM kmpis").fetchall()]


def list_kmpi_returns(conn=None) -> list[dict]:
    if conn is None:
        with tx() as c:
            return list_kmpi_returns(c)
    return _docs(conn, "SELECT doc FROM kmpi_returns ORDER BY model_id, period")


def get_kmpi_return(conn, model_id: str, period: str) -> dict | None:
    rows = _docs(conn, "SELECT doc FROM kmpi_returns WHERE model_id = ? AND period = ?",
                 (model_id, period))
    return rows[0] if rows else None


def put_kmpi_return(conn, r: dict) -> None:
    conn.execute(
        "INSERT INTO kmpi_returns(model_id, period, status, doc) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(model_id, period) DO UPDATE SET status = excluded.status, doc = excluded.doc",
        (r["model_id"], r["period"], r["status"], _dump(r)),
    )


def rename_model_in_kmpis(conn, old_id: str, new_id: str) -> None:
    for k in list_kmpis(conn):
        if k["model_id"] == old_id:
            put_kmpi(conn, {**k, "model_id": new_id})
    for r in list_kmpi_returns(conn):
        if r["model_id"] == old_id:
            conn.execute("DELETE FROM kmpi_returns WHERE model_id = ? AND period = ?", (old_id, r["period"]))
            put_kmpi_return(conn, {**r, "model_id": new_id})


# ---------------------------------------------------------------- audit log
def _append_audit(conn, event: dict) -> dict:
    row = conn.execute("SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash = row["hash"] if row else GENESIS_HASH
    ev = {k: event.get(k) for k in AUDIT_FIELDS}
    for k in ("before", "after"):
        if ev[k] is not None and not isinstance(ev[k], str):
            ev[k] = _canonical(ev[k])
    for k in ("user", "role", "action", "entity_type", "entity_id", "model_id", "details"):
        ev[k] = ev[k] or ""
    ev["hash"] = _event_hash(prev_hash, ev)
    ev["prev_hash"] = prev_hash
    conn.execute(
        "INSERT INTO audit_log(timestamp, user, role, action, entity_type, entity_id, "
        "model_id, details, before, after, prev_hash, hash) "
        "VALUES (:timestamp, :user, :role, :action, :entity_type, :entity_id, "
        ":model_id, :details, :before, :after, :prev_hash, :hash)",
        ev,
    )
    return ev


def append_audit(conn, event: dict) -> dict:
    """Append one event inside the caller's transaction."""
    return _append_audit(conn, event)


def list_audit(model_id: str | None = None) -> list[dict]:
    with tx() as conn:
        if model_id:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE model_id = ? ORDER BY seq", (model_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
    return [dict(r) for r in rows]


def verify_audit_chain() -> tuple[bool, int | None]:
    """Recompute the hash chain. Returns (ok, first_broken_seq)."""
    prev = GENESIS_HASH
    for ev in list_audit():
        if ev["prev_hash"] != prev or _event_hash(prev, ev) != ev["hash"]:
            return False, ev["seq"]
        prev = ev["hash"]
    return True, None
