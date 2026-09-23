"""Accounts: hashed passwords, and the JWT that says which user a request is from.

Passwords are hashed with Argon2, not encrypted: a hash can't be turned back into the password, so a
leaked users table doesn't leak passwords. The token is an HS256 JWT holding the user's id; the Next
app keeps it in an httpOnly cookie and sends it here as a Bearer header, so the browser's JavaScript
never sees it.
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Header, HTTPException
from pwdlib import PasswordHash

import db

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "")
if len(JWT_SECRET) < 32:
    raise ValueError("JWT_SECRET is missing or shorter than 32 characters. Generate one with: openssl rand -base64 48")

TOKEN_LIFETIME = timedelta(days=7)

password_hasher = PasswordHash.recommended()  # Argon2

# Checked against when an email isn't registered, so a missing account takes as long to reject as a
# wrong password. Otherwise the response time would tell an attacker which emails have accounts
UNKNOWN_USER_HASH = password_hasher.hash("no-such-user")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    return password_hasher.verify(password, password_hash or UNKNOWN_USER_HASH) and password_hash is not None


def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user_id, "iat": now, "exp": now + TOKEN_LIFETIME}, JWT_SECRET, algorithm="HS256")


def user_from_header(authorization: str | None) -> dict | None:
    """The user a Bearer token belongs to, None with no token, or 401 for a bad or expired one"""
    if not authorization:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Please log in again.")

    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=["HS256"], options={"require": ["exp", "sub"]})
        user_id = str(uuid.UUID(claims["sub"]))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(401, "Your session has expired. Please log in again.")

    rows = db.fetch("SELECT id::text AS id, email FROM users WHERE id = %s", (user_id,))
    if not rows:
        # A valid token for an account that has since been deleted
        raise HTTPException(401, "Please log in again.")
    return rows[0]


def current_user(authorization: str | None = Header(default=None)) -> dict:
    """For routes that need a logged-in user"""
    user = user_from_header(authorization)
    if user is None:
        raise HTTPException(401, "Please log in.")
    return user


def optional_user(authorization: str | None = Header(default=None)) -> dict | None:
    """For routes guests can use too: the user when there is one, None for a guest"""
    return user_from_header(authorization)
