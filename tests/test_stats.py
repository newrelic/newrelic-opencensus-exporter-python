import logging
import json
import pytest
import time
from datetime import datetime
from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.tags import tag_map as tag_map_module
from opencensus.stats import view as view_module
from opencensus.stats import view_data as view_data_module
from opencensus.stats import metric_utils
from opencensus_ext_newrelic import NewRelicStatsExporter


# The latency in milliseconds
MEASURE = measure_module.MeasureFloat("number", "A number!", "things")

GAUGE_VIEWS = {
    "last": view_module.View(
        "last",
        "A last value",
        ("tag",),
        MEASURE,
        aggregation_module.LastValueAggregation(),
    )
}
COUNT_VIEWS = {
    "count": view_module.View(
        "count", "A count", ("tag",), MEASURE, aggregation_module.CountAggregation()
    ),
    "sum": view_module.View(
        "sum", "A sum", ("tag",), MEASURE, aggregation_module.SumAggregation()
    ),
}
DISTRIBUTION_VIEWS = {
    "distribution": view_module.View(
        "distribution",
        "A distribution",
        ("tag",),
        MEASURE,
        aggregation_module.DistributionAggregation([50.0, 200.0]),
    )
}
VIEWS = {}
VIEWS.update(GAUGE_VIEWS)
VIEWS.update(COUNT_VIEWS)
VIEWS.update(DISTRIBUTION_VIEWS)

TEST_TIME = time.time()
EXPECTED_TIMESTAMP = int(TEST_TIME * 1000.0)
TEST_TIMESTAMP = datetime.utcfromtimestamp(TEST_TIME)


@pytest.fixture
def stats_exporter(insert_key, hosts):
    exporter = NewRelicStatsExporter(
        insert_key, host=hosts["metric"], service_name="Python Application"
    )
    exporter._thread.cancel()

    for view in VIEWS.values():
        exporter.on_register_view(view)

    return exporter


def record_values(view_data_objects, tags, value=1, count=1):
    tag_map = tag_map_module.TagMap(tags)
    for view_data_object in view_data_objects:
        for _ in range(count):
            # Timestamp here is only used to record exemplars. It is safe to
            # leave it as None
            view_data_object.record(tag_map, value, None)


def generate_metrics(view_data_objects):
    metrics = []
    for view_data_object in view_data_objects:
        metric = metric_utils.view_data_to_metric(view_data_object, TEST_TIMESTAMP)
        metrics.append(metric)
    return metrics


def to_view_data(view):
    # Start and end time should be the same value
    # https://github.com/census-instrumentation/opencensus-python/blob/b28a83f84dbbfb539c90c8844a96e9394df24c5b/opencensus/stats/measure_to_view_map.py#L105L106
    #
    # The start and end times should not be used in the calculation of metric
    # timing information
    view_data = view_data_module.ViewData(
        view=view,
        start_time="2019-05-11T00:07:45.0Z",
        end_time="2019-05-11T00:07:45.0Z",
    )
    return view_data


@pytest.mark.parametrize(
    "tag_values",
    ((None,), ("foo",), ("foo", "bar")),
    ids=("no tag value", "single tag value", "multiple tag values"),
)
def test_stats(stats_exporter, ensure_utf8, tag_values):
    view_data_objects = [to_view_data(view) for view in VIEWS.values()]

    # Record values
    for tag_value in tag_values:
        if tag_value:
            tags = {"tag": tag_value}
        else:
            tags = None

        record_values(view_data_objects, tags, value=100)

    # Generate metrics
    metrics = generate_metrics(view_data_objects)

    # Send metrics to exporter
    response = stats_exporter.export_metrics(metrics)

    # Verify headers
    user_agent = response.request.headers["user-agent"]
    assert user_agent.split()[-1].startswith("NewRelic-OpenCensus-Exporter/")

    # Verify payload
    data = json.loads(ensure_utf8(response.request.body))
    common = data[0]["common"]
    assert len(common) == 2
    assert common["interval.ms"] == stats_exporter.interval * 1000
    assert common["attributes"]["service.name"] == "Python Application"

    metrics_data = data[0]["metrics"]
    num_views = len(GAUGE_VIEWS) + len(COUNT_VIEWS) + len(DISTRIBUTION_VIEWS)
    assert len(metrics_data) == (len(tag_values) * num_views), metrics_data

    remaining_tags = {view: set(tag_values) for view in VIEWS}

    for metric_data in metrics_data:
        view_name = metric_data["name"]
        view = VIEWS[view_name]

        # Distribution views will raise an exception since there will be no
        # tags expected for a distribution aggregation
        expected_tags = remaining_tags[view.name]

        assert metric_data["attributes"]["measure.name"] == MEASURE.name
        assert metric_data["attributes"]["measure.unit"] == MEASURE.unit
        assert metric_data["timestamp"] == EXPECTED_TIMESTAMP

        if view_name in GAUGE_VIEWS:
            # Check that each metric is a gauge
            assert "type" not in metric_data
        elif view_name in COUNT_VIEWS:
            assert metric_data["type"] == "count"
        else:
            assert metric_data["type"] == "summary"

        assert len(metric_data) <= 5

        expected_tags.remove(metric_data["attributes"]["tag"])
        if not expected_tags:
            remaining_tags.pop(view.name)

    assert not remaining_tags


def test_empty_payload_is_not_sent(stats_exporter):
    response = stats_exporter.export_metrics(())
    assert response is None


def test_send_metrics_exception(stats_exporter, caplog):
    # Remove the client object to force an exception when send_metrics is called
    delattr(stats_exporter, "client")
    view_data = to_view_data(VIEWS["last"])
    view_data.record(None, 100, None)

    metric = metric_utils.view_data_to_metric(view_data, TEST_TIMESTAMP)

    response = stats_exporter.export_metrics([metric])
    assert response is None

    assert (
        "opencensus_ext_newrelic.stats",
        logging.ERROR,
        "New Relic send_metrics failed with an exception.",
    ) in caplog.record_tuples


@pytest.mark.http_response(status_code=500)
def test_bad_http_response(stats_exporter, caplog):
    view_data = to_view_data(VIEWS["last"])
    view_data.record(None, 100, None)

    metric = metric_utils.view_data_to_metric(view_data, TEST_TIMESTAMP)

    stats_exporter.export_metrics([metric])

    assert (
        "opencensus_ext_newrelic.stats",
        logging.ERROR,
        "New Relic send_metrics failed with status code: 500",
    ) in caplog.record_tuples


def test_count_metric_computes_delta(stats_exporter, ensure_utf8):
    view_data_objects = [to_view_data(view) for view in COUNT_VIEWS.values()]
    for delta_first, delta_second in ((2, 1), (1, 0), (0, 0)):
        record_values(view_data_objects, {"tag": "first"}, count=delta_first)
        record_values(view_data_objects, {"tag": "second"}, count=delta_second)
        metrics = generate_metrics(view_data_objects)

        response = stats_exporter.export_metrics(metrics)
        data = json.loads(ensure_utf8(response.request.body))

        expected_values = {
            view_name: {"first": delta_first, "second": delta_second}
            for view_name in COUNT_VIEWS
        }
        metrics_data = data[0]["metrics"]
        assert len(metrics_data) == len(view_data_objects) * 2
        for metric in metrics_data:
            assert metric["type"] == "count"
            view_values = expected_values[metric["name"]]
            expected_value = view_values.pop(metric["attributes"]["tag"])
            assert metric["value"] == expected_value
            if not view_values:
                expected_values.pop(metric["name"])
        assert not expected_values


def test_summary_metric_computes_delta(stats_exporter, ensure_utf8):
    view_data_objects = [to_view_data(view) for view in DISTRIBUTION_VIEWS.values()]
    for delta_first, delta_second in ((2, 1), (1, 0), (0, 0)):
        record_values(
            view_data_objects,
            {"tag": "first"},
            value=float(delta_first),
            count=delta_first,
        )
        record_values(
            view_data_objects,
            {"tag": "second"},
            value=delta_second,
            count=delta_second,
        )
        metrics = generate_metrics(view_data_objects)

        response = stats_exporter.export_metrics(metrics)
        data = json.loads(ensure_utf8(response.request.body))

        expected_values = {
            view_name: {"first": delta_first, "second": delta_second}
            for view_name in DISTRIBUTION_VIEWS
        }

        metrics_data = data[0]["metrics"]
        assert len(metrics_data) == len(view_data_objects) * 2

        for metric in metrics_data:
            view_values = expected_values[metric["name"]]
            expected_count = view_values.pop(metric["attributes"]["tag"])
            expected_sum = expected_count ** 2

            assert metric["type"] == "summary"
            assert metric["value"] == {
                "count": expected_count,
                "sum": expected_sum,
                "min": None,
                "max": None,
            }


def test_stop_clears_all_state(stats_exporter):
    stats_exporter.stop()

    assert stats_exporter.client is None
    assert stats_exporter.views is None

    # Call on_register_view after stop
    for view in VIEWS.values():
        stats_exporter.on_register_view(view)


def test_default_exporter_values(insert_key):
    exporter = NewRelicStatsExporter(insert_key, service_name="Python Application")
    exporter._thread.cancel()

    assert exporter.interval == 5
