"""Shared helpers for the GCSI notebooks.

- ``api``: API key, retries, pagination and the GCSI routes
- ``store``: SQLite storage for the hourly index and the headline feed
- ``metrics``: pooling, smoothing, indicators and headline aggregation
- ``charts``: the notebook charts

The notebooks add ``notebooks/`` to ``sys.path`` and import from here.
"""
