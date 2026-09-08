from cointent.session import LoginThrottle, SessionAuth


def test_session_is_signed_expires_and_rotates_with_password() -> None:
    auth = SessionAuth("carter", "long-password", ttl_seconds=60)
    token = auth.issue(now=1_000)

    assert auth.verify(token, now=1_059) == "carter"
    assert auth.verify(token, now=1_060) is None
    assert auth.verify(f"{token}x", now=1_001) is None
    assert SessionAuth("carter", "new-password", ttl_seconds=60).verify(token, now=1_001) is None


def test_login_throttle_limits_failures_without_permanent_lockout() -> None:
    throttle = LoginThrottle(max_failures=2, window_seconds=10)
    throttle.fail("source", now=100)
    assert throttle.blocked_for("source", now=101) == 0
    throttle.fail("source", now=102)
    assert throttle.blocked_for("source", now=103) > 0
    assert throttle.blocked_for("source", now=111) == 0
