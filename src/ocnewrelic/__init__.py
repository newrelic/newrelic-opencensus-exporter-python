from ocnewrelic.exporter import NewRelicExporter

import os.path

version = os.path.join(os.path.dirname(__file__), "version.txt")
try:
    with open(version) as f:
        __version__ = f.read()
except Exception:  # pragma: no cover
    __version__ = "unknown"  # pragma: no cover

__all__ = ("NewRelicExporter",)
