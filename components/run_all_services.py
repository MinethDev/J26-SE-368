"""Starts all four component services for local development (Windows, macOS, Linux).

    python components/run_all_services.py            # all four
    python components/run_all_services.py pull-request quality

Press Ctrl+C to stop them all.
"""

import subprocess
import sys
import time
from pathlib import Path

SERVICES = {"planning": 8001, "sprint": 8002, "quality": 8003, "pull-request": 8004}
ROOT = Path(__file__).resolve().parent


def main() -> None:
    args = sys.argv[1:]
    # Auto-reload is off by default: on Windows, one service reloading sends Ctrl+C
    # to the whole console, which stops every service. Restart this script after code changes.
    reload = "--reload" in args
    names = [a for a in args if a != "--reload"] or list(SERVICES)
    unknown = [n for n in names if n not in SERVICES]
    if unknown:
        sys.exit(f"Unknown service(s): {', '.join(unknown)}. Choose from: {', '.join(SERVICES)}")

    procs = []
    for name in names:
        cmd = [sys.executable, "-m", "uvicorn", "app:app", "--port", str(SERVICES[name])]
        if reload:
            cmd.append("--reload")
        procs.append(subprocess.Popen(cmd, cwd=ROOT / name / "service"))
        print(f"[services] {name:<13} http://127.0.0.1:{SERVICES[name]}/docs")
    try:
        while all(p.poll() is None for p in procs):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
