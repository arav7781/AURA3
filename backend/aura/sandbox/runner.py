"""Run a command in a fresh ``aura-sandbox`` container.

Hardening on every run: no network, read-only root filesystem with a small ``/tmp`` tmpfs, all
capabilities dropped, ``no-new-privileges``, an init process, memory (no swap) / CPU / pid / open-file /
file-size limits, and a hard deadline after which the container is killed. The only writable host path is
the run's workspace, mounted at ``/work``. Containers are labelled and always removed; leftovers from a
crash are reaped at startup.

With Colima the Docker daemon runs in a VM: the client connects to ``DOCKER_HOST`` explicitly, and the
workspace must live under ``$HOME`` (the only host path Colima shares).
"""

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import docker
from docker.errors import DockerException, ImageNotFound, NotFound
from docker.types import Ulimit

from aura.core.config import get_settings

logger = logging.getLogger("aura.sandbox")

LABEL = "aura.sandbox"
LineCallback = Callable[[str, str], None]  # (stream, line) — called from a worker thread


@dataclass
class RunSpec:
    argv: list[str]
    workspace: Path
    files: dict[str, bytes] = field(default_factory=dict)
    timeout_s: float = 60.0
    mem: str = "512m"
    cpus: float = 1.0
    kind: Literal["python", "office"] = "python"
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    status: Literal["ok", "error", "timeout", "oom", "failed_to_start"]
    exit_code: int | None
    stdout: list[str]
    stderr: list[str]
    truncated: bool
    ms: int
    container_id: str | None = None


class SandboxUnavailable(RuntimeError):
    pass


class SandboxRunner:
    def __init__(self) -> None:
        self._client: docker.DockerClient | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._lock = threading.Lock()

    def client(self) -> docker.DockerClient:
        with self._lock:
            if self._client is None:
                try:
                    self._client = docker.DockerClient(base_url=get_settings().docker_host, timeout=30)
                    self._client.ping()
                except DockerException as exc:
                    self._client = None
                    raise SandboxUnavailable(f"Docker is not reachable at {get_settings().docker_host}: {exc}") from exc
            return self._client

    def status(self) -> str:
        try:
            self.client().images.get(get_settings().sandbox_image)
            return "ready"
        except SandboxUnavailable:
            return "docker_unavailable"
        except ImageNotFound:
            return "image_missing"

    def reap(self) -> int:
        """Remove containers left behind by a previous process."""
        try:
            leftovers = self.client().containers.list(all=True, filters={"label": LABEL})
        except SandboxUnavailable:
            return 0
        for container in leftovers:
            try:
                container.remove(force=True)
            except DockerException:
                pass
        return len(leftovers)

    async def run(self, spec: RunSpec, on_line: LineCallback | None = None) -> RunResult:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(get_settings().sandbox_max_concurrent)
        async with self._semaphore:
            return await asyncio.to_thread(self._run_blocking, spec, on_line)

    def _run_blocking(self, spec: RunSpec, on_line: LineCallback | None) -> RunResult:
        settings = get_settings()
        workspace = spec.workspace.resolve()
        if not str(workspace).startswith(str(Path.home())):
            raise SandboxUnavailable("sandbox workspaces must live under $HOME (Colima shares only that path)")
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "out").mkdir(exist_ok=True)
        for rel, data in spec.files.items():
            target = (workspace / rel).resolve()
            if not str(target).startswith(str(workspace)):
                raise ValueError(f"file path escapes the workspace: {rel}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

        client = self.client()
        started = time.monotonic()
        container = None
        try:
            container = client.containers.create(
                settings.sandbox_image,
                spec.argv,
                user=f"{os.getuid()}:{os.getgid()}",
                network_mode="none",
                mem_limit=spec.mem,
                memswap_limit=spec.mem,
                nano_cpus=int(spec.cpus * 1_000_000_000),
                pids_limit=256 if spec.kind == "office" else 128,
                read_only=True,
                tmpfs={"/tmp": "rw,nosuid,nodev,size=256m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                init=True,
                ulimits=[Ulimit(name="nofile", soft=512, hard=512), Ulimit(name="fsize", soft=50 << 20, hard=50 << 20)],
                volumes={str(workspace): {"bind": "/work", "mode": "rw"}},
                working_dir="/work",
                environment={"HOME": "/tmp", "PYTHONUNBUFFERED": "1", **spec.env},
                labels={LABEL: "1", "aura.kind": spec.kind},
            )
        except (DockerException, ImageNotFound) as exc:
            raise SandboxUnavailable(f"could not create the sandbox container: {exc}") from exc

        timed_out = threading.Event()
        stdout: list[str] = []
        stderr: list[str] = []
        truncated = False
        exit_code: int | None = None

        def kill_at_deadline() -> None:
            if not done.wait(spec.timeout_s):
                timed_out.set()
                try:
                    container.kill()
                except DockerException:
                    pass

        done = threading.Event()
        watchdog = threading.Thread(target=kill_at_deadline, daemon=True)
        try:
            container.start()
            watchdog.start()
            for raw in container.logs(stream=True, follow=True, stdout=True, stderr=True):
                for line in raw.decode("utf-8", "replace").splitlines():
                    stream, text = self._parse(line, spec.kind)
                    if stream == "exit":
                        exit_code = int(text)
                        continue
                    if stream == "trunc":
                        truncated = True
                        continue
                    (stdout if stream == "out" else stderr).append(text)
                    if on_line is not None:
                        on_line(stream, text)
            state = container.wait(timeout=10)
            done.set()
            if exit_code is None:
                exit_code = state.get("StatusCode")
            container.reload()
            oom = bool(container.attrs.get("State", {}).get("OOMKilled"))
        except DockerException as exc:
            done.set()
            logger.warning("sandbox run failed: %s", exc)
            return RunResult("failed_to_start", None, stdout[-200:], [*stderr[-200:], str(exc)], truncated,
                             int((time.monotonic() - started) * 1000))
        finally:
            done.set()
            try:
                container.remove(force=True)
            except (DockerException, NotFound):
                pass

        ms = int((time.monotonic() - started) * 1000)
        if timed_out.is_set():
            status: Literal["ok", "error", "timeout", "oom", "failed_to_start"] = "timeout"
        elif oom:
            status = "oom"
        else:
            status = "ok" if exit_code == 0 else "error"
        return RunResult(status, exit_code, stdout[-500:], stderr[-500:], truncated, ms, container.id)

    @staticmethod
    def _parse(line: str, kind: str) -> tuple[str, str]:
        if kind == "python" and line.startswith("{"):
            import json

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                return "out", line
            k = record.get("k")
            if k == "exit":
                return "exit", str(record.get("code", 1))
            if k == "trunc":
                return "trunc", ""
            if k in ("out", "err"):
                return k, str(record.get("line", ""))
        return "out", line


runner = SandboxRunner()
