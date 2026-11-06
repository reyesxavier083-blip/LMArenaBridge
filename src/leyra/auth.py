"""JWT authentication and password hashing for LEYRA users."""
from __future__ import annotations
import hashlib, hmac, secrets
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import HTTPException, Request
ROLES = {"viewer": 1, "operator": 2, "admin": 3}
_ITERATIONS = 310_000

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return "pbkdf2_sha256$" + str(_ITERATIONS) + "$" + salt.hex() + "$" + digest.hex()

def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256": return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError): return False

def issue_token(user: dict, secret: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(user["id"]), "email": user["email"], "role": user["role"], "iat": now, "exp": now + timedelta(hours=8)}, secret, algorithm="HS256")

def require_role(request: Request, minimum: str, control_token: str, jwt_secret: str) -> dict:
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not supplied:
        raise HTTPException(401, "Bearer token required", headers={"WWW-Authenticate": "Bearer"})
    if control_token and hmac.compare_digest(supplied, control_token):
        return {"sub": "control-token", "email": "control", "role": "admin"}
    if not jwt_secret: raise HTTPException(503, "JWT signing secret is not configured")
    try: claims = jwt.decode(supplied, jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError: raise HTTPException(401, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    if ROLES.get(claims.get("role"), 0) < ROLES[minimum]: raise HTTPException(403, "Insufficient role")
    return claims
