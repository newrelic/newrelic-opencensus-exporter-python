from opencensus.common.transports import sync
from opencensus.common.utils import timestamp_to_microseconds
from opencensus.trace import base_exporter
from newrelic_sdk import Span, API

import logging

_logger = logging.getLogger(__name__)


class NewRelicTraceExporter(base_exporter.Exporter):
    """Export Span data to the New Relic platform

    This class is responsible for marshalling trace data to the New Relic
    platform.

    :param license_key: Your New Relic license key
    :type license_key: str
    :param service_name: (optional) The name of the entity to report spans
        into. Defaults to "Python Application".
    :type service_name: str
    :param host_name: (optional) Override the host for the API endpoint.
    :type host_name: str
    :param transport: (optional) Class for creating new transport objects. It
        should extend from the base_exporter
        :class:`opencensus.common.transports.base.Transport` type and implement
        :meth:`opencensus.common.transports.base.Transport.export`. Defaults to
        :class:`opencensus.common.transports.sync.SyncTransport`. The other option
        is :class:`opencensus.common.transports.async.AsyncTransport`.
    :type transport: :class:`opencensus.common.transports.base.Transport`

    Usage::

        >>> import os
        >>> from ocnewrelic import NewRelicTraceExporter
        >>> license_key = os.environ.get("NEW_RELIC_LICENSE_KEY")
        >>> trace_exporter = NewRelicTraceExporter(license_key, service_name="My Service")
    """

    def __init__(
        self,
        license_key,
        service_name="Python Application",
        host_name=None,
        transport=sync.SyncTransport,
    ):
        self.entity = service_name
        self.api = API(
            license_key=license_key,
            insert_key=None,
            span_host=host_name,
            metric_host=None,
        )
        self.transport = transport(self)

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
                entity=self.entity,
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
            response = self.api.send_spans(spans)
        except Exception:
            _logger.exception("Failed to send span data to New Relic.")
            return

        if not response.ok:
            _logger.error(
                "Status code received was not ok. Status code: %r", response.status_code
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
        self.transport.export(span_datas)
