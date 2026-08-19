"""
Purpose: Provides demo authentication, signed session tokens, and reusable
role-based authorization dependencies for vendor and administrator endpoints.
"""

import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

SECRET = os.getenv("AUTH_SECRET", "change-this-demo-secret")
USERS = {
    os.getenv("VENDOR_USERNAME", "vendor@example.com"): (os.getenv("VENDOR_PASSWORD", "vendor-demo"), "vendor"),
    os.getenv("ADMIN_USERNAME", "admin@example.com"): (os.getenv("ADMIN_PASSWORD", "admin-demo"), "admin"),
}
bearer = HTTPBearer(auto_error=False)


# Encodes token bytes using URL-safe Base64 without padding.
def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


# Decodes a URL-safe Base64 token segment back into bytes.
def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


# Validates demo credentials and issues an eight-hour signed role token.
def login(username: str, password: str) -> dict:
    record = USERS.get(username)
    if not record or not hmac.compare_digest(record[0], password):
        raise HTTPException(401, "Invalid login")
    payload = _encode(json.dumps({"sub": username, "role": record[1], "exp": int(time.time()) + 28800}).encode())
    signature = _encode(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
    return {"access_token": f"{payload}.{signature}", "token_type": "bearer", "role": record[1]}


# Verifies the bearer token signature and returns its authenticated claims.
def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    try:
        payload, signature = credentials.credentials.split(".")
        expected = _encode(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected): raise ValueError
        claims = json.loads(_decode(payload))
        if claims["exp"] < time.time(): raise ValueError
        return claims
    except (AttributeError, ValueError, KeyError, json.JSONDecodeError):
        raise HTTPException(401, "Authentication required")


# Builds a FastAPI dependency that restricts an endpoint to one role.
def require_role(role: str):
    # Rejects authenticated users whose token lacks the required role.
    def dependency(user=Depends(current_user)):
        if user["role"] != role: raise HTTPException(403, f"{role.title()} access required")
        return user
    return dependency
