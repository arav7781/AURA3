"""Runs one user program inside the sandbox and reports its output as JSON lines.

Usage: python /opt/aura/runner.py /work/main.py

Every line this wrapper prints is one JSON object: {"k": "out"|"err", "line": ...} for program output,
{"k": "trunc"} once the output cap is hit, and a final {"k": "exit", "code": ...}. The program's own
stdout/stderr are piped through here, so it cannot forge these records, and output beyond the cap is
dropped instead of flooding the host.
"""

import json
import subprocess
import sys
import threading

MAX_LINES = 2000
MAX_LINE_CHARS = 4000


def main() -> int:
    script = sys.argv[1] if len(sys.argv) > 1 else "/work/main.py"
    proc = subprocess.Popen(
        [sys.executable, "-u", script],
        cwd="/work",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
        bufsize=1,
    )
    lock = threading.Lock()
    count = [0]
    truncated = [False]

    def emit(record: dict) -> None:
        with lock:
            sys.stdout.write(json.dumps(record) + "\n")
            sys.stdout.flush()

    def pump(stream, kind: str) -> None:
        for raw in stream:
            with lock:
                count[0] += 1
                over = count[0] > MAX_LINES
            if over:
                if not truncated[0]:
                    truncated[0] = True
                    emit({"k": "trunc"})
                continue
            emit({"k": kind, "line": raw.rstrip("\n")[:MAX_LINE_CHARS]})

    threads = [threading.Thread(target=pump, args=(proc.stdout, "out")), threading.Thread(target=pump, args=(proc.stderr, "err"))]
    for t in threads:
        t.start()
    code = proc.wait()
    for t in threads:
        t.join()
    emit({"k": "exit", "code": code})
    return 0


if __name__ == "__main__":
    sys.exit(main())
