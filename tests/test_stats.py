import json
import os
import pytest
from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.stats import stats as stats_module
from opencensus.stats import view as view_module
from ocnewrelic import NewRelicStatsExporter


@pytest.fixture
def stats_exporter():
    insert_key = os.environ.get("NEW_RELIC_INSERT_KEY", "")
    exporter = NewRelicStatsExporter(insert_key)
    exporter.stop()
    return exporter


def test_stats_recorder(stats_exporter, ensure_utf8):
    stats = stats_module.stats
    view_manager = stats.view_manager
    stats_recorder = stats.stats_recorder
    view_manager.register_exporter(stats_exporter)

    # Create the measures and views
    metric_name = "task_latency_latest"
    metric_value = 100
    metric_description = "The latest task latency"
    metric_unit = "ms"
    # The latency in milliseconds
    m_latency_ms = measure_module.MeasureFloat(
        "task_latency", "The task latency in milliseconds", metric_unit
    )

    latency_view = view_module.View(
        metric_name,
        metric_description,
        [],
        m_latency_ms,
        aggregation_module.LastValueAggregation(),
    )
    view_manager.register_view(latency_view)
    mmap = stats_recorder.new_measurement_map()

    # Record a metric
    mmap.measure_float_put(m_latency_ms, metric_value)
    mmap.record()
    # Send metrics to the exporter
    response = stats_exporter.export_metrics(stats.get_metrics())
    data = json.loads(ensure_utf8(response.request.body))
    metric_data = data[0]["metrics"][0]
    assert metric_data["name"] == metric_name
    assert metric_data["value"] == metric_value
    assert metric_data["attributes"]["description"] == metric_description
    assert metric_data["attributes"]["unit"] == metric_unit
