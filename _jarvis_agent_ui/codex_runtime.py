"""Small JSONL client for the official Codex App Server (stdio transport)."""
from __future__ import annotations

import itertools
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path


class CodexProtocolError(RuntimeError):
    pass


def find_codex_command() -> str | None:
    """Find the installed official Codex CLI without depending on PowerShell shims."""
    appdata = os.environ.get("APPDATA", "")
    candidates = []
    if appdata:
        candidates.extend((Path(appdata) / "npm" / "codex.cmd",
                           Path(appdata) / "npm" / "codex.exe"))
    for name in ("codex.cmd", "codex.exe", "codex"):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found))
    for candidate in candidates:
        try:
            if candidate.is_file():
                return str(candidate.resolve())
        except OSError:
            continue
    return None


class CodexAppServer:
    """One short-lived app-server connection. Codex persists thread history itself."""

    def __init__(self, cwd: str | Path, codex_home: str | Path | None = None):
        executable = find_codex_command()
        if not executable:
            raise CodexProtocolError("Codex CLI não encontrado. Instale @openai/codex e tente novamente.")
        self._ids = itertools.count(1)
        self._queue: queue.Queue = queue.Queue()
        self._write_lock = threading.Lock()
        self._closed = False
        suffix = Path(executable).suffix.lower()
        if os.name == "nt" and suffix in (".cmd", ".bat"):
            command = subprocess.list2cmdline([executable, "app-server"])
            args = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", command]
        elif os.name == "nt" and suffix == ".ps1":
            args = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", executable, "app-server"]
        else:
            args = [executable, "app-server"]
        env = os.environ.copy()
        if codex_home:
            env["CODEX_HOME"] = str(Path(codex_home).resolve())
        self.proc = subprocess.Popen(
            args, cwd=str(Path(cwd)), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            bufsize=1, creationflags=(0x08000000 if os.name == "nt" else 0),
        )
        self._reader = threading.Thread(target=self._read_stdout, name="codex-app-server-reader", daemon=True)
        self._reader.start()

    def _read_stdout(self):
        try:
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except Exception:
                    self._queue.put({"_protocol_output": line[:1000]})
                    continue
                if isinstance(message, dict):
                    self._queue.put(message)
        except Exception as exc:
            self._queue.put({"_reader_error": str(exc)[:500]})
        finally:
            self._queue.put({"_reader_eof": True})

    def send(self, payload: dict):
        if self._closed or self.proc.poll() is not None:
            raise CodexProtocolError("O Codex App Server encerrou a conexão.")
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            with self._write_lock:
                assert self.proc.stdin is not None
                self.proc.stdin.write(raw + "\n")
                self.proc.stdin.flush()
        except Exception as exc:
            raise CodexProtocolError("Falha ao enviar mensagem ao Codex App Server: %s" % str(exc)[:300]) from exc

    def notify(self, method: str, params: dict | None = None):
        self.send({"method": method, "params": params or {}})

    def _dispatch(self, message: dict, on_message=None):
        # Server-initiated JSON-RPC requests have both id and method.
        if "id" in message and message.get("method"):
            result = None
            if on_message:
                result = on_message(message)
            if result is None:
                result = {"decision": "decline"}
            self.send({"id": message["id"], "result": result})
        elif on_message:
            on_message(message)

    def request(self, method: str, params: dict | None = None, *, on_message=None, timeout: float = 90):
        request_id = next(self._ids)
        self.send({"method": method, "id": request_id, "params": params or {}})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CodexProtocolError("Tempo esgotado aguardando %s." % method)
            try:
                message = self._queue.get(timeout=min(0.5, remaining))
            except queue.Empty:
                if self.proc.poll() is not None:
                    raise CodexProtocolError("Codex App Server encerrou com código %s." % self.proc.returncode)
                continue
            if message.get("_reader_eof"):
                raise CodexProtocolError("Codex App Server encerrou a conexão antes de responder a %s." % method)
            if message.get("_reader_error"):
                raise CodexProtocolError("Falha lendo Codex App Server: %s" % message["_reader_error"])
            if message.get("_protocol_output"):
                continue
            if message.get("id") == request_id and not message.get("method"):
                if message.get("error"):
                    error = message["error"]
                    raise CodexProtocolError(str(error.get("message") or error)[:1000])
                return message.get("result") or {}
            self._dispatch(message, on_message)

    def next_message(self, timeout: float = 0.5):
        try:
            message = self._queue.get(timeout=timeout)
        except queue.Empty:
            if self.proc.poll() is not None:
                raise CodexProtocolError("Codex App Server encerrou com código %s." % self.proc.returncode)
            return None
        if message.get("_reader_eof"):
            raise CodexProtocolError("Codex App Server encerrou a conexão inesperadamente.")
        if message.get("_reader_error"):
            raise CodexProtocolError("Falha lendo Codex App Server: %s" % message["_reader_error"])
        if message.get("_protocol_output"):
            return None
        return message

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=2)
        except Exception:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=3, creationflags=0x08000000)
                else:
                    self.proc.terminate()
                self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
