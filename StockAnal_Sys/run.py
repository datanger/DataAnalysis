# run.py
import sys
import os
from pathlib import Path

# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def _simple_load_dotenv(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        text = path.read_text(encoding="utf-8", errors="ignore")

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if not k:
            continue
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        # Do not override env values already provided by the shell.
        os.environ.setdefault(k, v)


def _load_env_files() -> None:
    candidates = [
        # Allow placing .env at repo root (cwd), or next to this run.py (StockAnal_Sys/.env).
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
    ]

    try:
        from dotenv import load_dotenv  # type: ignore
    except ModuleNotFoundError:
        for p in candidates:
            _simple_load_dotenv(p)
        return

    for p in candidates:
        load_dotenv(p, override=False)


_load_env_files()

if os.getenv("UI_PREVIEW", "").lower() in {"1", "true", "yes"}:
    from app.web.ui_preview_server import app  # type: ignore
else:
    try:
        # Prefer the full server (real features).
        from app.web.web_server import app  # type: ignore
    except Exception as e:  # noqa: BLE001
        # UI-first workflow: allow previewing templates even when optional deps are missing.
        print(f"[UI preview] Falling back to minimal server: {e}", file=sys.stderr)
        from app.web.ui_preview_server import app  # type: ignore

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8888))
    host = os.environ.get('HOST', '0.0.0.0')
    app.run(host=host, port=port, debug=False)
