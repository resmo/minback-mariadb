import pytest

from minback.retry import retry


def flaky(failures):
    calls = []

    def fn():
        calls.append(1)
        if len(calls) <= failures:
            raise OSError(f"fail {len(calls)}")
        return "done"

    return fn, calls


def test_succeeds_after_failures_with_backoff():
    fn, calls = flaky(2)
    sleeps = []
    assert retry(fn, attempts=3, delay=5, what="x", sleep=sleeps.append) == "done"
    assert len(calls) == 3
    assert sleeps == [5, 10]


def test_gives_up_and_reraises():
    fn, calls = flaky(5)
    sleeps = []
    with pytest.raises(OSError, match="fail 3"):
        retry(fn, attempts=3, delay=1, what="x", sleep=sleeps.append)
    assert len(calls) == 3
    assert sleeps == [1, 2]


def test_single_attempt_does_not_sleep():
    fn, _ = flaky(1)
    sleeps = []
    with pytest.raises(OSError):
        retry(fn, attempts=1, delay=1, what="x", sleep=sleeps.append)
    assert sleeps == []
