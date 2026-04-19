"""Shared pytest fixtures.

Stubs ``blpapi`` before the app is imported so tests can run on machines
without the Bloomberg SDK installed. Only the few attributes we touch in
the serialisation path need to exist.
"""

from __future__ import annotations

import sys
import types


def _install_blpapi_stub() -> None:
    if "blpapi" in sys.modules:
        return
    stub = types.ModuleType("blpapi")

    class _Event:
        RESPONSE = 1
        TIMEOUT = 2
        SUBSCRIPTION_DATA = 3
        SUBSCRIPTION_STATUS = 4
        SESSION_STATUS = 5
        SERVICE_STATUS = 6

    class _DataType:
        FLOAT32 = 1
        FLOAT64 = 2
        INT32 = 3
        INT64 = 4
        BOOL = 5
        DATE = 6
        DATETIME = 7
        TIME = 8
        STRING = 9

    stub.Event = _Event
    stub.DataType = _DataType
    stub.Session = object
    stub.SessionOptions = object
    stub.SubscriptionList = object
    stub.CorrelationId = object
    sys.modules["blpapi"] = stub


_install_blpapi_stub()
