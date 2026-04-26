from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEPS = ROOT / ".deps"
if DEPS.exists():
    sys.path.insert(0, str(DEPS))

from streamlit.web import cli as stcli  # noqa: E402


if __name__ == "__main__":
    port = os.environ.get("PORT", "8501")
    address = os.environ.get("STREAMLIT_SERVER_ADDRESS")
    if not address:
        address = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"

    sys.argv = [
        "streamlit",
        "run",
        str(ROOT / "app" / "app.py"),
        "--server.address",
        address,
        "--server.port",
        port,
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
    ]
    raise SystemExit(stcli.main())
