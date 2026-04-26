"""Scheduled monitor classes (one per cadence).

Each monitor is consumed directly from its concrete module. There is no
aggregate ``MonitorSet`` factory anymore — :mod:`omnitrade.main` constructs
the monitors and binds them to the FastAPI app's APScheduler instance.
"""
