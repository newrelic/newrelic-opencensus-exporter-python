import calendar
from opencensus.stats import stats
from opencensus.metrics import transport
from newrelic_sdk import API, GaugeMetric


class NewRelicStatsExporter(object):
    def __init__(self, insert_key, interval=None, host=None):
        self.api = API(
            license_key=None, insert_key=insert_key, span_host=None, metric_host=host
        )
        self.views = {}

        # Register an exporter thread for this exporter
        transport.get_exporter_thread(stats.stats, self, interval=interval)

    def on_register_view(self, view):
        self.views[view.name] = view

    def export_metrics(self, metrics):
        nr_metrics = []
        for metric in metrics:
            descriptor = metric.descriptor
            name = descriptor.name
            description = descriptor.description
            unit = descriptor.unit

            tags = {"description": description, "unit": unit}

            view = self.views[name]
            for timeseries in metric.time_series:
                # In distribution aggregations, the values are not integers
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
                    name=name, value=value, tags=tags, end_time_ms=end_time_ms
                )
                nr_metrics.append(nr_metric)

        self.api.send_metrics(nr_metrics)
