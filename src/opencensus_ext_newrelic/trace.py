# Copyright 2019 New Relic, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from opencensus.common.transports import async_
from opencensus.common.utils import timestamp_to_microseconds
from opencensus.trace import base_exporter
from newrelic_telemetry_sdk import Span, SpanClient

import logging

try:
    from opencensus_ext_newrelic.version import version as __version__
except ImportError:  # pragma: no cover
    __version__ = "unknown"  # pragma: no cover

_logger = logging.getLogger(__name__)


class DefaultTransport(async_.AsyncTransport):
    def __init__(
        self, exporter, grace_period=None, max_batch_size=600, wait_period=5.0
    ):
        super(DefaultTransport, self).__init__(
            exporter, grace_period, max_batch_size, wait_period
        )

    def stop(self):
        """Terminate the background thread"""
        self.worker._export_pending_data()


class NewRelicTraceExporter(base_exporter.Exporter):
    """Export Span data to the New Relic platform

    This class is responsible for marshalling trace data to the New Relic
    platform.

    :param insert_key: Insights insert key
    :type insert_key: str
    :param service_name: (optional) The name of the entity to report spans
        into. Defaults to "Python Application".
    :type service_name: str
    :param host: (optional) Override the host for the API endpoint.
    :type host: str
    :param transport: (optional) Class for creating new transport objects. It
        should extend from the base_exporter
        :class:`opencensus.common.transports.base.Transport` type and implement
        :meth:`opencensus.common.transports.base.Transport.export`. Defaults to
        an async transport sending data every 5 seconds. The other option is
        :class:`opencensus.common.transports.async.AsyncTransport`.
    :type transport: :class:`opencensus.common.transports.base.Transport`

    Usage::

        >>> import os
        >>> from opencensus_ext_newrelic import NewRelicTraceExporter
        >>> insert_key = os.environ.get("NEW_RELIC_INSERT_KEY")
        >>> trace_exporter = NewRelicTraceExporter(
        ...     insert_key, service_name="My Service")
        >>> trace_exporter.stop()
    """

    def __init__(self, insert_key, service_name, host=None, transport=DefaultTransport):
        self._common = {"attributes": {"service.name": service_name}}
        client = self.client = SpanClient(insert_key=insert_key, host=host)
        client.add_version_info("NewRelic-OpenCensus-Exporter", __version__)
        self._transport = transport(self)

    def emit(self, span_datas):
        """Immediately marshal span data to the tracing backend

        :param span_datas: list of :class:`opencensus.trace.span_data.SpanData`
            to emit
        :type span_datas: list
        """
        spans = []
        for span_data in span_datas:
            start_timestamp_mus = timestamp_to_microseconds(span_data.start_time)
            end_timestamp_mus = timestamp_to_microseconds(span_data.end_time)
            duration_mus = end_timestamp_mus - start_timestamp_mus

            start_time_ms = start_timestamp_mus // 1000
            duration_ms = duration_mus // 1000

            span = Span(
                name=span_data.name,
                tags=span_data.attributes,
                guid=span_data.span_id,
                trace_id=span_data.context.trace_id,
                parent_id=span_data.parent_span_id,
                start_time_ms=start_time_ms,
                duration_ms=duration_ms,
            )

            spans.append(span)

        try:
            response = self.client.send_batch(spans, self._common)
        except Exception:
            _logger.exception("New Relic send_spans failed with an exception.")
            return

        if not response.ok:
            _logger.error(
                "New Relic send_spans failed with status code: %r", response.status
            )

        return response

    def export(self, span_datas):
        """Export the trace. Send trace to transport, and transport will call
        exporter.emit() to actually send the trace to the specified tracing
        backend.

        :param span_datas: list of :class:`opencensus.trace.span_data.SpanData`
            to export.
        :type span_datas: list
        """
        if self._transport is not None:
            return self._transport.export(span_datas)

    def stop(self):
        """Terminate the exporter and any background threads"""
        transport = self._transport

        # Send all pending data
        if hasattr(transport, "stop"):
            transport.stop()

        # Clear all internal state
        self._transport = self.client = None
