import os
import functools
import pytest
import zlib
from newrelic_telemetry_sdk.client import HTTPResponse
from urllib3 import HTTPConnectionPool

try:
    string_types = basestring
except NameError:
    string_types = str


def _ensure_utf8(s):
    if not isinstance(s, string_types):
        try:
            s = s.decode("utf-8")
        except Exception:
            return
    return s


def _decompress_data(d):
    return _ensure_utf8(zlib.decompress(d, 31))


class Request(object):
    def __init__(instance, self, method, url, body=None, headers=None, *args, **kwargs):
        headers = headers or self.headers
        instance.method = method
        instance.url = url
        instance.body = body
        instance.headers = headers
        instance.args = args
        instance.kwargs = kwargs


def _capture_request(wrapped, status_code, disable_requests):
    if disable_requests:

        @functools.wraps(wrapped)
        def wrapper(*args, **kwargs):
            response = HTTPResponse(status=202)
            response.request = Request(*args, **kwargs)
            if status_code is not None:
                response.status = status_code
            return response

    else:

        @functools.wraps(wrapped)
        def wrapper(*args, **kwargs):
            response = wrapped(*args, **kwargs)
            response.request = Request(*args, **kwargs)
            if status_code is not None:
                response.status = status_code
            return response

    return wrapper


def _http_response(status_code):
    return status_code


@pytest.fixture
def decompress_payload():
    return _decompress_data


@pytest.fixture
def insert_key():
    return os.environ.get("NEW_RELIC_INSERT_KEY", "")


@pytest.fixture
def hosts():
    host = os.environ.get("NEW_RELIC_HOST", "")

    hosts = {"trace": None, "metric": None}

    if host.startswith("staging"):
        hosts["trace"] = "staging-trace-api.newrelic.com"
        hosts["metric"] = "staging-metric-api.newrelic.com"

    return hosts


@pytest.fixture(autouse=True)
def mocked_responses(request, monkeypatch):
    status_code = None
    disable_requests = False

    # Determine if the proper key exists for this test. If it does not exist,
    # do not attempt to send requests to New Relic and instead immediately
    # return a response object with the mocked status code.
    if "insert_key" in request.node.fixturenames:
        insert_key = request.getfixturevalue("insert_key")
        if not insert_key:
            status_code = 200
            disable_requests = True

    # The response marker always overrides the status code
    http_response_marker = request.node.get_closest_marker("http_response")
    if http_response_marker:
        status_code = _http_response(
            *http_response_marker.args, **http_response_marker.kwargs
        )

    wrapped = HTTPConnectionPool.urlopen
    monkeypatch.setattr(
        HTTPConnectionPool,
        "urlopen",
        _capture_request(wrapped, status_code, disable_requests),
    )
