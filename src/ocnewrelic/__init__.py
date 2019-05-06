from ocnewrelic.trace import NewRelicTraceExporter
from ocnewrelic.stats import NewRelicStatsExporter

try:
    from ocnewrelic.version import version as __version__
except ImportError:  # pragma: no cover
    __version__ = "unknown"  # pragma: no cover

__all__ = ("NewRelicTraceExporter", "NewRelicStatsExporter")
