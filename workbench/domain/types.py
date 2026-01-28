from __future__ import annotations

from enum import Enum


class Exchange(str, Enum):
    SSE = "SSE"
    SZSE = "SZSE"


class Market(str, Enum):
    CN_A = "CN_A"


class Adj(str, Enum):
    RAW = "RAW"
    QFQ = "QFQ"
    HFQ = "HFQ"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class RiskStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
