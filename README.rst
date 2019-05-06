New Relic OpenCensus Exporter
=============================

Stats Example
^^^^^^^^^^^^^

.. code-block:: python

  import os
  import time
  from opencensus.stats import aggregation as aggregation_module
  from opencensus.stats import measure as measure_module
  from opencensus.stats import stats as stats_module
  from opencensus.stats import view as view_module
  from ocnewrelic import NewRelicStatsExporter

  # The stats recorder
  stats = stats_module.stats
  view_manager = stats.view_manager
  stats_recorder = stats.stats_recorder
  stats_exporter = NewRelicStatsExporter(os.environ['NEW_RELIC_INSERT_KEY'])
  view_manager.register_exporter(stats_exporter)

  # Create the measures and views
  # The latency in milliseconds
  m_latency_ms = measure_module.MeasureFloat(
      "task_latency", "The task latency in milliseconds", "ms")

  latency_view = view_module.View(
      "task_latency_latest",
      "The latest task latency",
      [],
      m_latency_ms,
      aggregation_module.LastValueAggregation())
  view_manager.register_view(latency_view)
  mmap = stats_recorder.new_measurement_map()

  # Record a metric
  mmap.measure_float_put(m_latency_ms, 100)
  mmap.record()

  # Wait for everything to send
  time.sleep(6)

Tracer Example
^^^^^^^^^^^^^^

.. code-block:: python

  import os
  import time
  from opencensus.trace.tracer import Tracer
  from opencensus.trace import samplers
  from ocnewrelic import NewRelicTraceExporter

  newrelic = NewRelicTraceExporter(license_key=os.environ["NEW_RELIC_LICENSE_KEY"])

  tracer = Tracer(exporter=newrelic, sampler=samplers.AlwaysOnSampler())

  with tracer.span(name="main") as span:
    time.sleep(0.5)
