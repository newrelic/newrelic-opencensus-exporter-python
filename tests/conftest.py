import pytest

try:
    string_types = basestring
except NameError:
    string_types = str


@pytest.fixture
def ensure_utf8():
    def _ensure(s):
        if not isinstance(s, string_types):
            try:
                s = s.decode("utf-8")
            except Exception:
                return
        return s

    return _ensure
