import json
import os
import pytest
import math
import time
import datetime
from ocnewrelic import NewRelicTraceExporter
from opencensus.trace.span_data import SpanData
from opencensus.trace import span_context


@pytest.fixture
def trace_exporter():
    license_key = os.environ.get("NEW_RELIC_LICENSE_KEY", "")
    exporter = NewRelicTraceExporter(license_key=license_key)
    return exporter


def test_trace(trace_exporter, ensure_utf8):
    epoch = datetime.datetime.utcfromtimestamp(0)
    start_time = datetime.datetime.utcnow()
    time.sleep(0.1)
    end_time = datetime.datetime.utcnow()

    span_data = SpanData(
        name="test_span",
        context=span_context.SpanContext(
            trace_id="2dd43a1d6b2549c6bc2a1a54c2fc0b05", span_id="6e0c63257de34c92"
        ),
        span_id="6e0c63257de34c92",
        parent_span_id="6e0c63257de34c93",
        attributes={"key1": "value1"},
        start_time=start_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        end_time=end_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        stack_trace=None,
        links=None,
        status=None,
        time_events=None,
        same_process_as_parent_span=None,
        child_span_count=None,
        span_kind=0,
    )

    response = trace_exporter.emit([span_data])
    span_payload = json.loads(ensure_utf8(response.request.body))["spans"][0]

    duration = math.floor((end_time - start_time).total_seconds() * 1000)
    timestamp = math.floor((start_time - epoch).total_seconds() * 1000)

    assert span_payload["durationMs"] == duration
    assert span_payload["traceId"] == span_data.context.trace_id
    assert span_payload["name"] == span_data.name
    assert span_payload["parentId"] == span_data.parent_span_id
    assert span_payload["guid"] == span_data.context.span_id
    assert span_payload["tags"] == span_data.attributes
    assert span_payload["timestamp"] == timestamp
    assert span_payload["entityName"] == "Python Application"
