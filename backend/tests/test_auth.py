"""
Purpose: Verifies that vendor/admin credentials produce separate roles and that
malformed authentication tokens are rejected.
"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from app.auth import current_user, login


# Confirms the two configured accounts cannot collapse into one role.
def test_vendor_and_admin_receive_distinct_roles():
    assert login("vendor@example.com", "vendor-demo")["role"] == "vendor"
    assert login("admin@example.com", "admin-demo")["role"] == "admin"


# Confirms invalid bearer tokens receive an authentication error.
def test_invalid_token_is_rejected():
    with pytest.raises(HTTPException) as error:
        current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad.token"))
    assert error.value.status_code == 401
