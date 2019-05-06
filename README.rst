New Relic OpenCensus Exporter
=============================

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
