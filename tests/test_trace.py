import logging
import json
import pytest
from opencensus_ext_newrelic import NewRelicTraceExporter
from opencensus.common.transports import sync
from opencensus.trace import span_context
from opencensus.trace.span_data import SpanData


class Transport(sync.SyncTransport):
    def export(self, datas):
        return self.exporter.emit(datas)


@pytest.fixture
def trace_exporter(hosts, insert_key):
    exporter = NewRelicTraceExporter(
        insert_key=insert_key,
        transport=Transport,
        host=hosts["trace"],
        service_name="Python Application",
    )
    return exporter


SPAN_DATA = {
    "name": "test_span",
    "context": span_context.SpanContext(
        trace_id="2dd43a1d6b2549c6bc2a1a54c2fc0b05", span_id="6e0c63257de34c92"
    ),
    "span_id": "6e0c63257de34c92",
    "parent_span_id": "6e0c63257de34c93",
    "attributes": {"key1": "value1"},
    "start_time": "2019-05-11T00:07:48.0Z",
    "end_time": "2019-05-11T00:07:49.0Z",
    "span_kind": 0,
}
for field in SpanData._fields:
    if field not in SPAN_DATA:
        SPAN_DATA[field] = None

SPAN_DATA = SpanData(**SPAN_DATA)


def test_trace(trace_exporter, ensure_utf8):
    duration = 1000
    timestamp = 1557533268000

    response = trace_exporter.export([SPAN_DATA])
    data = json.loads(ensure_utf8(response.request.body))
    assert len(data) == 1
    data = data[0]
    spans, common = data["spans"], data["common"]
    assert len(spans) == 1
    span = spans[0]
    attributes = span["attributes"]

    assert span["id"] == SPAN_DATA.context.span_id
    assert span["timestamp"] == timestamp
    assert span["trace.id"] == SPAN_DATA.context.trace_id

    for name, value in SPAN_DATA.attributes.items():
        assert attributes[name] == value

    assert attributes["duration.ms"] == duration
    assert attributes["name"] == SPAN_DATA.name
    assert attributes["parent.id"] == SPAN_DATA.parent_span_id

    assert common["attributes"]["service.name"] == "Python Application"


def test_send_spans_exception(trace_exporter, caplog):
    # Remove the client object to force an exception when send_spans is called
    delattr(trace_exporter, "client")

    response = trace_exporter.export([SPAN_DATA])
    assert response is None

    assert (
        "opencensus_ext_newrelic.trace",
        logging.ERROR,
        "New Relic send_spans failed with an exception.",
    ) in caplog.record_tuples


@pytest.mark.http_response(status_code=500)
def test_bad_http_response(trace_exporter, caplog):
    trace_exporter.export([SPAN_DATA])

    assert (
        "opencensus_ext_newrelic.trace",
        logging.ERROR,
        "New Relic send_spans failed with status code: 500",
    ) in caplog.record_tuples


def test_stop_clears_all_state(trace_exporter):
    trace_exporter.stop()

    assert trace_exporter.client is None

    # Calling export after stop
    trace_exporter.export(())
