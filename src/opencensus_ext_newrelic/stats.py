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

import calendar
from opencensus.stats import stats
from opencensus.metrics import transport
from opencensus.stats import aggregation
from newrelic_telemetry_sdk import (
    MetricBatch,
    MetricClient,
    GaugeMetric,
    CountMetric,
    SummaryMetric,
)

import logging

try:
    from opencensus_ext_newrelic.version import version as __version__
except ImportError:  # pragma: no cover
    __version__ = "unknown"  # pragma: no cover

_logger = logging.getLogger(__name__)
COUNT_AGGREGATION_TYPES = {aggregation.CountAggregation, aggregation.SumAggregation}


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
    :param port: (optional) Override the port for the API endpoint.
    :type port: int

    Usage::

        >>> import os
        >>> from opencensus_ext_newrelic import NewRelicStatsExporter
        >>> insert_key = os.environ.get("NEW_RELIC_INSERT_KEY")
        >>> stats_exporter = NewRelicStatsExporter(
        ...     insert_key, service_name="My Service")
        >>> stats_exporter.stop()
    """

    def __init__(self, insert_key, service_name, interval=5, host=None, port=443):
        client = self.client = MetricClient(insert_key=insert_key, host=host, port=port)
        client.add_version_info("NewRelic-OpenCensus-Exporter", __version__)
        self.views = {}
        self.merged_values = {}

        # Register an exporter thread for this exporter
        thread = self._thread = transport.get_exporter_thread(
            [stats.stats], self, interval=interval
        )
        self.interval = thread.interval

        self._common = {
            "interval.ms": self.interval * 1000,
            "attributes": {"service.name": service_name},
        }

    def on_register_view(self, view):
        """Called when a view is registered with the view manager

        :param view: View object to register
        :type view: :class:`opencensus.stats.view.View`
        """
        if self.views is not None:
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
            view = self.views[name]
            measure_name = view.measure.name
            measure_unit = view.measure.unit
            aggregation_type = view.aggregation

            tags = {"measure.name": measure_name, "measure.unit": measure_unit}

            for timeseries in metric.time_series:
                value = timeseries.points[0].value
                if hasattr(value, "value"):
                    value = value.value
                elif hasattr(value, "count") and hasattr(value, "sum"):
                    value = {"count": value.count, "sum": value.sum}
                else:
                    _logger.warning(
                        "Unable to send metric %s with value: %s", name, value
                    )
                    break

                timestamp = timeseries.points[0].timestamp
                time_tuple = timestamp.utctimetuple()
                epoch_time_secs = calendar.timegm(time_tuple)
                epoch_time_mus = epoch_time_secs * 1e6 + timestamp.microsecond
                end_time_ms = epoch_time_mus // 1000

                labels = (
                    (k, l.value) for k, l in zip(view.columns, timeseries.label_values)
                )

                _tags = tags.copy()
                _tags.update(labels)

                if isinstance(value, dict):
                    identity = MetricBatch.create_identity(name, _tags, "summary")

                    # compute a delta count based on the previous value. if one
                    # does not exist, report the raw count value.
                    if identity in self.merged_values:
                        last = self.merged_values[identity]
                        delta_count = value["count"] - last["count"]
                        delta_sum = value["sum"] - last["sum"]
                    else:
                        delta_count = value["count"]
                        delta_sum = value["sum"]

                    self.merged_values[identity] = value

                    nr_metric = SummaryMetric(
                        name=name,
                        count=delta_count,
                        sum=delta_sum,
                        min=None,
                        max=None,
                        tags=_tags,
                        end_time_ms=end_time_ms,
                        interval_ms=None,
                    )

                elif type(aggregation_type) in COUNT_AGGREGATION_TYPES:
                    identity = MetricBatch.create_identity(name, _tags, "count")

                    # Compute a delta count based on the previous value. If one
                    # does not exist, report the raw count value.
                    delta = value - self.merged_values.get(identity, 0)
                    self.merged_values[identity] = value
                    value = delta

                    nr_metric = CountMetric(
                        name=name,
                        value=value,
                        tags=_tags,
                        end_time_ms=end_time_ms,
                        interval_ms=None,
                    )

                else:
                    nr_metric = GaugeMetric(
                        name=name, value=value, tags=_tags, end_time_ms=end_time_ms
                    )

                nr_metrics.append(nr_metric)

        # Do not send an empty metrics payload
        if not nr_metrics:
            return

        try:
            response = self.client.send_batch(nr_metrics, common=self._common)
        except Exception:
            _logger.exception("New Relic send_metrics failed with an exception.")
            return

        if not response.ok:
            _logger.error(
                "New Relic send_metrics failed with status code: %r", response.status
            )
        return response

    def stop(self):
        """Terminate the exporter background thread"""
        thread = self._thread

        stop = getattr(thread, "stop", None) or getattr(thread, "cancel")
        stop()

        # Send all pending metrics
        thread.function(*thread.args, **thread.kwargs)

        # Clear all internal state
        self._thread = self.client = self.views = self.count_values = None
