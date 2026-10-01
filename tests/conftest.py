"""Every test runs against a fresh copy of the pilot seed in a temp folder."""

import sys
from pathlib import Path

import pytest
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import repository  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("QDB_MRM_DB", str(tmp_path / "test.db"))
    monkeypatch.setenv("QDB_MRM_EVIDENCE_DIR", str(tmp_path / "evidence"))
    repository.reset_db()
    st.cache_data.clear()
    yield
    st.cache_data.clear()


@pytest.fixture
def act_as():
    """act_as('Model Validator 1') sets the acting user for data_store calls."""
    def _set(name: str):
        st.session_state["current_user_name"] = name
    return _set


class Upload:
    """Stand-in for a Streamlit UploadedFile."""

    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data
