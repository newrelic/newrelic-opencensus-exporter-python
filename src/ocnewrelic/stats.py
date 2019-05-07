import calendar
from opencensus.stats import stats
from opencensus.metrics import transport
from newrelic_sdk import API, GaugeMetric

import logging

_logger = logging.getLogger(__name__)


class NewRelicStatsExporter(object):
    """Export Metric data to the New Relic platform

    This class is responsible for marshalling metric data to the New Relic
    platform.

    :param insert_key: Insights insert key
    :type insert_key: str
    :param interval: (optional) Metrics will be sent every ``interval``
        seconds. Default is 5 seconds.
    :type interval: int or float
    :param host: (optional) Override the host for the API endpoint.
    :type host: str

    Usage::

        >>> import os
        >>> from ocnewrelic import NewRelicStatsExporter
        >>> insert_key = os.environ.get("NEW_RELIC_INSERT_KEY")
        >>> stats_exporter = NewRelicStatsExporter(insert_key)
        >>> stats_exporter.stop()
    """

    def __init__(self, insert_key, interval=5, host=None):
        self.api = API(
            license_key=None, insert_key=insert_key, span_host=None, metric_host=host
        )
        self.views = {}

        # Register an exporter thread for this exporter
        thread = transport.get_exporter_thread(stats.stats, self, interval=interval)
        self.interval = thread.interval
        self._stop = getattr(thread, "stop", None) or getattr(thread, "cancel")

    def on_register_view(self, view):
        """Called when a view is registered with the view manager

        :param view: View object to register
        :type view: :class:`opencensus.stats.view.View`
        """
        self.views[view.name] = view

    def export_metrics(self, metrics):
        """Immediately send all metric data to the monitoring backend.

        :param metrics: list of Metric objects to send to the monitoring
            backend
        :type metrics: :class:`opencensus.metrics.export.metric.Metric`
        """
        nr_metrics = []
        for metric in metrics:
            descriptor = metric.descriptor
            name = descriptor.name
            description = descriptor.description
            unit = descriptor.unit

            view = self.views[name]
            tags = {
                "description": description,
                "unit": unit,
                "aggregationType": view.aggregation.aggregation_type,
            }

            for timeseries in metric.time_series:
                # In distribution aggregations, the values do not have a value attribute
                # We simply ignore this case for now
                try:
                    value = timeseries.points[0].value.value
                except AttributeError:
                    continue

                timestamp = timeseries.points[0].timestamp
                time_tuple = timestamp.utctimetuple()
                epoch_time_secs = calendar.timegm(time_tuple)
                epoch_time_mus = epoch_time_secs * 1e6 + timestamp.microsecond
                end_time_ms = epoch_time_mus // 1000

                label_values = (l.value for l in timeseries.label_values)

                _tags = tags.copy()
                _tags.update(zip(view.columns, label_values))

                nr_metric = GaugeMetric(
                    name=name, value=value, tags=_tags, end_time_ms=end_time_ms
                )
                nr_metrics.append(nr_metric)

        try:
            response = self.api.send_metrics(nr_metrics)
        except Exception:
            _logger.exception("Failed to send metric data to New Relic.")
            return

        if not response.ok:
            _logger.error(
                "status code received was not ok. Status code: %r", response.status_code
            )
        return response

    def stop(self):
        """Terminate the exporter background thread"""
        return self._stop()
