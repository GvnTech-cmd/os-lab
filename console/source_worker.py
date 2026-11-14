"""Private runtime settings worker, launched only through a confirmed job."""
from __future__ import annotations

import json
from pathlib import Path
import secrets
import sys
import os
import signal
import subprocess
import threading

import source_control as control
import source_jobs


def main():
    root = str(Path(__file__).resolve().parent.parent)
    if sys.argv[1] == "--run":
        root = sys.argv[2]
        request = json.loads(sys.argv[3])
        plan = control.build_plan(root, request)
        def parent_closed():
            os.read(sys.stdin.fileno(), 1)
            if os.name == "posix":
                os.killpg(os.getpgrp(), signal.SIGKILL)
            else:
                subprocess.run(["taskkill", "/PID", str(os.getpid()), "/T", "/F"], capture_output=True)
        threading.Thread(target=parent_closed, daemon=True).start()
        result = subprocess.run([control.python(), *plan["engineArgs"]], stdin=subprocess.DEVNULL)
        raise SystemExit(result.returncode)
    request = json.loads(sys.argv[1])
    control.build_plan(root, request)
    options = request["options"]
    if options["action"] == "verify-session":
        sys.path.insert(0, str(Path(root) / "source-lab/engine"))
        from source_lab.evidence.session import SessionBundleReader
        if not os.environ.get("IQ_SESSION_HMAC_KEY") and not os.environ.get("IQ_SESSION_HMAC_KEY_FILE"):
            os.environ["IQ_SESSION_HMAC_KEY_FILE"] = str(control.checked(control.storage(root), "control/session-hmac.key", exists=True))
        path = control.checked(control.storage(root), "analysis/" + options["slug"] + "/runtime-sessions/" + options["session"], exists=True)
        result = SessionBundleReader(path).verify_integrity()
        print(json.dumps(result), flush=True)
        if not result["valid"] or not result["signature_verified"]:
            raise SystemExit(1)
    elif options["action"] == "generate-key":
        source_jobs.atomic(root, "control/session-hmac.key", (secrets.token_hex(32) + "\n").encode())
        print("Private signing key created. Previous sessions need their original key for verification.", flush=True)
    else:
        source_jobs.atomic(root, "control/runtime-settings.json", json.dumps({"testUrl": options["testUrl"]}).encode())
        print("Default canary URL saved; no network request made.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Runtime settings operation failed; verify private storage and environment ownership.", file=sys.stderr)
        raise SystemExit(1)
