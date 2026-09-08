"""OC-style stateless browser sessions and login throttling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from http.cookies import SimpleCookie


SESSION_COOKIE = "cointent_session"


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _same_secret(left: str, right: str) -> bool:
    left_hash = hashlib.sha256(left.encode()).digest()
    right_hash = hashlib.sha256(right.encode()).digest()
    return hmac.compare_digest(left_hash, right_hash)


@dataclass(frozen=True, slots=True)
class SessionAuth:
    user: str
    password: str
    secret: str = ""
    ttl_seconds: int = 7 * 24 * 3600
    cookie_secure: bool = True

    @classmethod
    def from_env(cls) -> "SessionAuth":
        user = os.environ.get("COINTENT_LOGIN_USER", "").strip()
        password = os.environ.get("COINTENT_LOGIN_PASSWORD", "")
        if bool(user) != bool(password):
            raise RuntimeError("COINTENT_LOGIN_USER and COINTENT_LOGIN_PASSWORD must be configured together")
        ttl = int(os.environ.get("COINTENT_SESSION_TTL_SECONDS", str(7 * 24 * 3600)))
        if ttl < 60:
            raise RuntimeError("COINTENT_SESSION_TTL_SECONDS must be at least 60")
        return cls(
            user=user,
            password=password,
            secret=os.environ.get("COINTENT_SESSION_SECRET", ""),
            ttl_seconds=ttl,
            cookie_secure=os.environ.get("COINTENT_COOKIE_SECURE", "1") != "0",
        )

    @property
    def enabled(self) -> bool:
        return bool(self.user and self.password)

    def credentials_valid(self, user: str, password: str) -> bool:
        user_valid = _same_secret(user, self.user)
        password_valid = _same_secret(password, self.password)
        return self.enabled and user_valid and password_valid

    def issue(self, now: int | None = None) -> str:
        payload = _base64url(json.dumps(
            {"u": self.user, "t": now if now is not None else int(time.time())},
            separators=(",", ":"),
        ).encode())
        return f"{payload}.{self._sign(payload)}"

    def verify(self, token: str | None, now: int | None = None) -> str | None:
        if not self.enabled or not token or "." not in token:
            return None
        payload, signature = token.rsplit(".", 1)
        if not hmac.compare_digest(self._sign(payload), signature):
            return None
        try:
            claims = json.loads(_decode_base64url(payload))
            issued = claims["t"]
            user = claims["u"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None
        current = now if now is not None else int(time.time())
        if not isinstance(issued, int) or not isinstance(user, str):
            return None
        if user != self.user or issued > current + 60 or current - issued >= self.ttl_seconds:
            return None
        return user

    def cookie_token(self, raw_cookie: str) -> str | None:
        try:
            cookie = SimpleCookie(raw_cookie)
        except Exception:
            return None
        morsel = cookie.get(SESSION_COOKIE)
        return morsel.value if morsel is not None else None

    def _sign(self, payload: str) -> str:
        material = self.secret or f"{self.user}\n{self.password}"
        key = hashlib.sha256(material.encode()).digest()
        return _base64url(hmac.new(key, payload.encode(), hashlib.sha256).digest())


@dataclass(slots=True)
class LoginThrottle:
    max_failures: int = 8
    window_seconds: int = 300
    max_sources: int = 1024
    failures: dict[str, tuple[int, float]] = field(default_factory=dict)

    def blocked_for(self, source: str, now: float | None = None) -> int:
        current = now if now is not None else time.monotonic()
        entry = self.failures.get(source)
        if entry is None:
            return 0
        count, started = entry
        if current - started >= self.window_seconds:
            self.failures.pop(source, None)
            return 0
        if count < self.max_failures:
            return 0
        return max(1, int(started + self.window_seconds - current) + 1)

    def fail(self, source: str, now: float | None = None) -> None:
        current = now if now is not None else time.monotonic()
        self.blocked_for(source, current)
        if source in self.failures:
            count, started = self.failures[source]
            self.failures[source] = (count + 1, started)
            return
        if len(self.failures) >= self.max_sources:
            oldest = min(self.failures, key=lambda key: self.failures[key][1])
            self.failures.pop(oldest, None)
        self.failures[source] = (1, current)

    def reset(self, source: str) -> None:
        self.failures.pop(source, None)
