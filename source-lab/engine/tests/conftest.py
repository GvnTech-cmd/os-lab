"""Shared pytest fixtures for engine tests."""

import secrets

import pytest


@pytest.fixture(autouse=True)
def session_hmac_key(monkeypatch):
    """Gives every test a fresh session HMAC key without storing one in the repo."""
    monkeypatch.setenv("IQ_SESSION_HMAC_KEY", secrets.token_hex(32))
    monkeypatch.delenv("IQ_SESSION_HMAC_KEY_FILE", raising=False)
