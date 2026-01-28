from __future__ import annotations

import json
from typing import Any


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, separators=(",", ":"), default=str)


def loads(s: str) -> Any:
    return json.loads(s)
