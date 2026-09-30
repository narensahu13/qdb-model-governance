import sqlite3

import pytest

import config
import repository


def test_seed_loaded():
    assert len(repository.list_models()) == 17
    assert repository.verify_audit_chain() == (True, None)


def test_audit_log_is_append_only():
    conn = sqlite3.connect(config.db_path())
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE audit_log SET details = 'x' WHERE seq = 1")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_log")
    conn.close()


def test_tampering_breaks_the_hash_chain():
    conn = sqlite3.connect(config.db_path())
    conn.execute("DROP TRIGGER audit_log_no_update")
    conn.execute("UPDATE audit_log SET details = 'rewritten' WHERE seq = 7")
    conn.commit()
    conn.close()
    assert repository.verify_audit_chain() == (False, 7)


def test_seed_evidence_is_hashed():
    for ev in repository.list_evidence():
        data = (config.evidence_dir() / ev["stored_path"]).read_bytes()
        assert repository.sha256_bytes(data) == ev["sha256"]
