#!/usr/bin/env python3
"""
Wrapper for running tests/end_to_end_test.py against port 8001 by default.

This keeps backward compatibility with older docs/scripts while the main
end-to-end script supports overriding the API base via env vars.
"""

# This file is meant to be executed as a script, not collected by pytest.
__test__ = False

import os
import sys
from pathlib import Path


def main() -> None:
    # Allow importing the sibling script (tests/end_to_end_test.py) as a module.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    # Back-compat: default to 8001, but allow callers to override.
    os.environ.setdefault("WORKBENCH_API_BASE", "http://127.0.0.1:8001/api/v1")

    from end_to_end_test import main as run  # type: ignore

    run()


if __name__ == "__main__":
    main()

