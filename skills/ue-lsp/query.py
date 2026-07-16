#!/usr/bin/env python3
"""Managed clangd semantic queries for Unreal Engine workspaces.

The public CLI owns only a project-local Python service. That service owns one
clangd stdio process and reuses it across definition/hover/reference queries.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import secrets
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Callable
from urllib.parse import quote, unquote, urlsplit

import status as status_module


SEMANTIC_OPERATIONS = {"definition", "hover", "references", "implementation", "rename-preview"}
MANAGEMENT_OPERATIONS = {"status", "start", "stop"}
DEFAULT_QUERY_TIMEOUT = 30.0
DEFAULT_INDEX_TIMEOUT = 120.0


class QueryError(RuntimeError):
    def __init__(self, code: str, message: str, next_actions: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.next_actions = next_actions or []


class ProtocolError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def path_to_uri(path: Path) -> str:
    path = path.resolve()
    if os.name == "nt":
        raw = path.as_posix()
        if raw.startswith("//"):
            host, _, rest = raw[2:].partition("/")
            return f"file://{host}/{quote(rest, safe='/@:')}"
        return "file:///" + quote(raw, safe="/@:")
    return "file://" + quote(path.as_posix(), safe="/@:")


def uri_to_path(uri: str) -> Path:
    parsed = urlsplit(uri)
    if parsed.scheme and parsed.scheme.lower() != "file":
        raise ProtocolError(f"unsupported URI scheme: {parsed.scheme}")
    raw = unquote(parsed.path)
    if parsed.netloc:
        raw = f"//{parsed.netloc}{raw}"
    if re.match(r"^/[A-Za-z]:/", raw):
        raw = raw[1:]
    return Path(raw.replace("/", os.sep))


def read_message(stream: BinaryIO) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if line == b"":
            if not headers:
                return None
            raise ProtocolError("unexpected EOF in JSON-RPC headers")
        if line in (b"\r\n", b"\n"):
            break
        try:
            name, value = line.decode("ascii").split(":", 1)
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProtocolError(f"malformed JSON-RPC header: {line!r}") from exc
        headers[name.strip().lower()] = value.strip()
    try:
        length = int(headers["content-length"])
    except (KeyError, ValueError) as exc:
        raise ProtocolError("missing or invalid Content-Length") from exc
    body = stream.read(length)
    if len(body) != length:
        raise ProtocolError("unexpected EOF in JSON-RPC body")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProtocolError(f"malformed JSON-RPC JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ProtocolError("JSON-RPC payload must be an object")
    return payload


def write_message(stream: BinaryIO, payload: dict[str, Any], lock: threading.Lock | None = None) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    framed = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    if lock:
        with lock:
            stream.write(framed)
            stream.flush()
    else:
        stream.write(framed)
        stream.flush()


class JsonRpcClient:
    def __init__(self, reader: BinaryIO, writer: BinaryIO, notification_handler: Callable[[str, Any], None] | None = None):
        self.reader = reader
        self.writer = writer
        self.notification_handler = notification_handler
        self.write_lock = threading.Lock()
        self.pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self.pending_lock = threading.Lock()
        self.next_id = 1
        self.closed = threading.Event()
        self.error: Exception | None = None
        self.thread = threading.Thread(target=self._read_loop, name="ue-lsp-jsonrpc", daemon=True)
        self.thread.start()

    def notify(self, method: str, params: Any | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        write_message(self.writer, payload, self.write_lock)

    def request(self, method: str, params: Any | None = None, timeout: float = DEFAULT_QUERY_TIMEOUT) -> Any:
        with self.pending_lock:
            request_id = self.next_id
            self.next_id += 1
            response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
            self.pending[request_id] = response_queue
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        write_message(self.writer, payload, self.write_lock)
        try:
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            with self.pending_lock:
                self.pending.pop(request_id, None)
            raise QueryError("timeout", f"LSP request timed out after {timeout:.1f}s") from exc
        if "error" in response:
            error = response["error"]
            raise QueryError("lsp-error", f"clangd returned an error: {error}")
        return response.get("result")

    def _respond_to_server_request(self, message: dict[str, Any]) -> None:
        method = str(message.get("method", ""))
        params = message.get("params") or {}
        if method == "workspace/configuration":
            items = params.get("items", []) if isinstance(params, dict) else []
            result: Any = [None for _ in items]
        elif method == "workspace/applyEdit":
            result = {"applied": False, "failureReason": "ue-lsp only previews edits"}
        elif method in {
            "client/registerCapability",
            "client/unregisterCapability",
            "window/workDoneProgress/create",
        }:
            result = None
        else:
            result = None
        write_message(self.writer, {"jsonrpc": "2.0", "id": message["id"], "result": result}, self.write_lock)

    def _read_loop(self) -> None:
        try:
            while True:
                message = read_message(self.reader)
                if message is None:
                    raise ProtocolError("clangd closed stdout")
                if "method" in message and "id" in message:
                    self._respond_to_server_request(message)
                elif "method" in message:
                    if self.notification_handler:
                        self.notification_handler(str(message["method"]), message.get("params"))
                elif "id" in message:
                    with self.pending_lock:
                        response_queue = self.pending.pop(int(message["id"]), None)
                    if response_queue:
                        response_queue.put(message)
        except Exception as exc:
            self.error = exc
            self.closed.set()
            with self.pending_lock:
                queues = list(self.pending.values())
                self.pending.clear()
            for response_queue in queues:
                response_queue.put({"jsonrpc": "2.0", "error": {"code": -32099, "message": str(exc)}})


class ManagedClangd:
    def __init__(self, project_root: Path, clangd_path: Path, state_dir: Path):
        self.project_root = project_root.resolve()
        self.clangd_path = clangd_path.resolve()
        self.state_dir = state_dir
        self.open_documents: dict[str, tuple[int, int]] = {}
        self.document_lock = threading.Lock()
        self.index_lock = threading.Condition()
        self.index_state = "unknown"
        self.index_progress_seen = False
        self.active_index_tokens: set[str] = set()
        self.last_index_activity = time.monotonic()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "cache").mkdir(parents=True, exist_ok=True)
        clangd_log = open(self.state_dir / "clangd.log", "ab", buffering=0)
        cmd = [
            str(self.clangd_path),
            f"--compile-commands-dir={self.project_root}",
            "--background-index",
            "--log=info",
        ]
        env = os.environ.copy()
        env["XDG_CACHE_HOME"] = str((self.state_dir / "cache").resolve())
        kwargs: dict[str, Any] = {
            "cwd": str(self.project_root),
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": clangd_log,
            "env": env,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(cmd, **kwargs)
        assert self.process.stdin is not None and self.process.stdout is not None
        self.rpc = JsonRpcClient(self.process.stdout, self.process.stdin, self._notification)
        initialize = {
            "processId": os.getpid(),
            "clientInfo": {"name": "ue-lsp-query", "version": "1"},
            "rootUri": path_to_uri(self.project_root),
            "workspaceFolders": [{"uri": path_to_uri(self.project_root), "name": self.project_root.name}],
            "capabilities": {
                "window": {"workDoneProgress": True},
                "workspace": {"configuration": True, "workspaceFolders": True},
                "textDocument": {
                    "definition": {"linkSupport": True},
                    "hover": {"contentFormat": ["markdown", "plaintext"]},
                    "references": {},
                    "implementation": {"linkSupport": True},
                    "rename": {"prepareSupport": False},
                },
            },
        }
        self.rpc.request("initialize", initialize, timeout=30)
        self.rpc.notify("initialized", {})

    def _notification(self, method: str, params: Any) -> None:
        with self.index_lock:
            if method == "clangd/indexingProgress" and isinstance(params, dict):
                self.index_progress_seen = True
                self.last_index_activity = time.monotonic()
                percentage = params.get("percentage")
                self.index_state = "ready" if percentage == 100 else "building"
            elif method == "$/progress" and isinstance(params, dict):
                token = str(params.get("token", ""))
                value = params.get("value") or {}
                title = str(value.get("title", "")) if isinstance(value, dict) else ""
                kind = str(value.get("kind", "")) if isinstance(value, dict) else ""
                is_index = token in self.active_index_tokens or "index" in title.lower() or "index" in token.lower()
                if is_index:
                    self.index_progress_seen = True
                    self.last_index_activity = time.monotonic()
                    if kind == "end":
                        self.active_index_tokens.discard(token)
                        if not self.active_index_tokens:
                            self.index_state = "ready"
                    else:
                        self.active_index_tokens.add(token)
                        self.index_state = "building"
            self.index_lock.notify_all()

    def wait_for_index(self, timeout: float) -> str:
        deadline = time.monotonic() + timeout
        with self.index_lock:
            while time.monotonic() < deadline:
                if self.index_state == "ready":
                    return "ready"
                remaining = deadline - time.monotonic()
                self.index_lock.wait(timeout=min(0.25, max(remaining, 0)))
            return self.index_state

    def _open_document(self, file_path: Path) -> str:
        file_path = file_path.resolve()
        if not file_path.exists():
            raise QueryError("missing-source-file", f"source file does not exist: {file_path}")
        uri = path_to_uri(file_path)
        text = file_path.read_text(encoding="utf-8-sig", errors="replace")
        mtime = file_path.stat().st_mtime_ns
        with self.document_lock:
            current = self.open_documents.get(uri)
            if current is None:
                version = 1
                self.rpc.notify(
                    "textDocument/didOpen",
                    {"textDocument": {"uri": uri, "languageId": "cpp", "version": version, "text": text}},
                )
                self.open_documents[uri] = (version, mtime)
            elif current[1] != mtime:
                version = current[0] + 1
                self.rpc.notify(
                    "textDocument/didChange",
                    {"textDocument": {"uri": uri, "version": version}, "contentChanges": [{"text": text}]},
                )
                self.open_documents[uri] = (version, mtime)
        return uri

    def query(self, request: dict[str, Any]) -> dict[str, Any]:
        operation = str(request["operation"])
        file_path = Path(str(request["file"])).resolve()
        uri = self._open_document(file_path)
        position = {"line": int(request["line"]), "character": int(request["column"])}
        wait_for_index = bool(request.get("wait_for_index"))
        if wait_for_index:
            self.wait_for_index(float(request.get("index_timeout", DEFAULT_INDEX_TIMEOUT)))
        params: dict[str, Any] = {"textDocument": {"uri": uri}, "position": position}
        if operation == "definition":
            method = "textDocument/definition"
        elif operation == "hover":
            method = "textDocument/hover"
        elif operation == "references":
            method = "textDocument/references"
            params["context"] = {"includeDeclaration": bool(request.get("include_declaration", True))}
        elif operation == "implementation":
            method = "textDocument/implementation"
        elif operation == "rename-preview":
            method = "textDocument/rename"
            params["newName"] = str(request["new_name"])
        else:
            raise QueryError("unsupported-operation", f"unsupported operation: {operation}")
        started = time.perf_counter()
        response = self.rpc.request(method, params, timeout=float(request.get("timeout", DEFAULT_QUERY_TIMEOUT)))
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        return {"raw_result": response, "elapsed_ms": elapsed_ms, "index_state": self.index_state}

    def close(self) -> None:
        try:
            if self.process.poll() is None:
                try:
                    self.rpc.request("shutdown", timeout=5)
                    self.rpc.notify("exit")
                    self.process.wait(timeout=5)
                except Exception:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
        finally:
            self.rpc.closed.set()


@dataclass
class ServerPaths:
    root: Path
    metadata: Path
    server_log: Path
    lock: Path


def server_paths(project_root: Path) -> ServerPaths:
    root = project_root / ".ue-lsp"
    return ServerPaths(root=root, metadata=root / "server.json", server_log=root / "server.log", lock=root / "lock")


def compdb_signature(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {"path": str(path.resolve()), "mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def clangd_version(path: Path) -> str:
    result = subprocess.run([str(path), "--version"], check=False, capture_output=True, text=True, errors="replace", timeout=10)
    lines = (result.stdout or result.stderr).splitlines()
    return lines[0].strip() if lines else "unknown"


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def read_server_metadata(project_root: Path) -> dict[str, Any] | None:
    path = server_paths(project_root).metadata
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def send_server_request(metadata: dict[str, Any], request: dict[str, Any], timeout: float = 10) -> dict[str, Any]:
    request = dict(request)
    request["token"] = metadata.get("token")
    encoded = json.dumps(request, ensure_ascii=False).encode("utf-8") + b"\n"
    with socket.create_connection(("127.0.0.1", int(metadata["port"])), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(encoded)
        buffer = bytearray()
        while True:
            block = sock.recv(65536)
            if not block:
                break
            buffer.extend(block)
            if b"\n" in block:
                break
    if not buffer:
        raise QueryError("server-unavailable", "managed ue-lsp server returned no response")
    try:
        response = json.loads(bytes(buffer).split(b"\n", 1)[0].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueryError("malformed-server-response", f"managed ue-lsp server returned malformed JSON: {exc}") from exc
    if not isinstance(response, dict):
        raise QueryError("malformed-server-response", "managed ue-lsp server response is not an object")
    return response


def server_is_current(metadata: dict[str, Any], project_root: Path, clangd_path: Path, compdb: Path) -> bool:
    try:
        if canonical(Path(str(metadata["project_root"]))) != canonical(project_root):
            return False
        if canonical(Path(str(metadata["clangd_path"]))) != canonical(clangd_path):
            return False
        if metadata.get("compile_commands") != compdb_signature(compdb):
            return False
        response = send_server_request(metadata, {"operation": "ping"}, timeout=2)
        return response.get("status") == "ok"
    except Exception:
        return False


def _managed_process_command_line(pid: int) -> str | None:
    if os.name != "nt":
        return None
    script = f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() or None


def terminate_stale_managed_server(metadata: dict[str, Any], project_root: Path) -> None:
    try:
        send_server_request(metadata, {"operation": "stop"}, timeout=5)
        return
    except Exception:
        pass
    pid = int(metadata.get("pid", 0) or 0)
    if pid <= 0:
        return
    if os.name == "nt":
        command_line = _managed_process_command_line(pid)
        expected_script = str(Path(__file__).resolve()).lower()
        if not command_line or expected_script not in command_line.lower() or "_serve" not in command_line:
            return
        if str(project_root.resolve()).lower() not in command_line.lower():
            return
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=False, capture_output=True, timeout=15)
    else:
        try:
            command_line = (Path("/proc") / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            return
        if str(Path(__file__).resolve()) not in command_line or "_serve" not in command_line:
            return
        if str(project_root.resolve()) not in command_line:
            return
        try:
            os.kill(pid, 15)
        except OSError:
            pass


class StartLock:
    def __init__(self, path: Path, timeout: float = 20):
        self.path = path
        self.timeout = timeout
        self.acquired = False

    def __enter__(self) -> "StartLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()} {time.time()}".encode("ascii"))
                os.close(fd)
                self.acquired = True
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > 60:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
                if time.monotonic() >= deadline:
                    raise QueryError("start-lock-timeout", "timed out waiting for the project ue-lsp start lock")
                time.sleep(0.1)

    def __exit__(self, *_: Any) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except OSError:
                pass


def ensure_server(project_root: Path, clangd_path: Path, compdb: Path) -> tuple[dict[str, Any], bool]:
    paths = server_paths(project_root)
    with StartLock(paths.lock):
        metadata = read_server_metadata(project_root)
        if metadata and server_is_current(metadata, project_root, clangd_path, compdb):
            return metadata, False
        if metadata:
            terminate_stale_managed_server(metadata, project_root)
        paths.root.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(24)
        cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "_serve",
            "--project-root",
            str(project_root),
            "--clangd",
            str(clangd_path),
            "--token",
            token,
        ]
        log = open(paths.server_log, "ab", buffering=0)
        kwargs: dict[str, Any] = {"cwd": str(project_root), "stdin": subprocess.DEVNULL, "stdout": log, "stderr": log}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)
        deadline = time.monotonic() + 30
        last_metadata: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            time.sleep(0.1)
            last_metadata = read_server_metadata(project_root)
            if last_metadata and last_metadata.get("token") == token:
                try:
                    response = send_server_request(last_metadata, {"operation": "ping"}, timeout=2)
                    if response.get("status") == "ok":
                        return last_metadata, True
                except Exception:
                    pass
        raise QueryError("server-start-failed", f"managed ue-lsp server did not start; inspect {paths.server_log}")


class QueryTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = False
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[socketserver.StreamRequestHandler], manager: ManagedClangd, token: str):
        self.manager = manager
        self.token = token
        super().__init__(address, handler)


class QueryRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(16 * 1024 * 1024)
        try:
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                raise QueryError("malformed-request", "request must be a JSON object")
            server = self.server
            assert isinstance(server, QueryTCPServer)
            if not secrets.compare_digest(str(request.get("token", "")), server.token):
                raise QueryError("unauthorized", "invalid managed server token")
            operation = request.get("operation")
            if operation == "ping":
                response = {"status": "ok", "pid": os.getpid(), "index_state": server.manager.index_state}
            elif operation == "stop":
                response = {"status": "ok", "stopping": True}
                threading.Thread(target=server.shutdown, daemon=True).start()
            else:
                response = {"status": "ok", **server.manager.query(request)}
        except QueryError as exc:
            response = {"status": "error", "error_code": exc.code, "message": str(exc), "next_actions": exc.next_actions}
        except Exception as exc:
            response = {"status": "error", "error_code": "server-error", "message": str(exc), "next_actions": []}
        self.wfile.write(json.dumps(response, ensure_ascii=False).encode("utf-8") + b"\n")


def serve(project_root: Path, clangd_path: Path, token: str) -> int:
    project_root = project_root.resolve()
    paths = server_paths(project_root)
    compdb = project_root / "compile_commands.json"
    manager = ManagedClangd(project_root, clangd_path, paths.root)
    server = QueryTCPServer(("127.0.0.1", 0), QueryRequestHandler, manager, token)
    metadata = {
        "pid": os.getpid(),
        "port": server.server_address[1],
        "token": token,
        "project_root": str(project_root),
        "clangd_path": str(clangd_path.resolve()),
        "clangd_version": clangd_version(clangd_path),
        "compile_commands": compdb_signature(compdb),
        "started_at": utc_now(),
    }
    write_json_atomic(paths.metadata, metadata)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        manager.close()
        current = read_server_metadata(project_root)
        if current and current.get("token") == token:
            try:
                paths.metadata.unlink()
            except OSError:
                pass
    return 0


def normalize_range(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    start = value.get("start")
    end = value.get("end")
    if not isinstance(start, dict) or not isinstance(end, dict):
        return None
    return {
        "start": {"line": int(start.get("line", 0)) + 1, "column": int(start.get("character", 0)) + 1},
        "end": {"line": int(end.get("line", 0)) + 1, "column": int(end.get("character", 0)) + 1},
    }


def classify_path(path: Path, project_root: Path, engine_root: Path | None) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(project_root.resolve())
        first = relative.parts[0].lower() if relative.parts else ""
        if first == "source":
            return "project-source"
        if first == "intermediate":
            return "project-intermediate"
        return "project-other"
    except ValueError:
        pass
    if engine_root:
        try:
            resolved.relative_to(engine_root.resolve())
            return "engine-source"
        except ValueError:
            pass
    return "external"


def display_path(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def normalize_location(value: Any, project_root: Path, engine_root: Path | None = None) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    uri = value.get("uri") or value.get("targetUri")
    raw_range = value.get("range") or value.get("targetSelectionRange") or value.get("targetRange")
    if not isinstance(uri, str):
        return None
    parsed_range = normalize_range(raw_range)
    if not parsed_range:
        return None
    path = uri_to_path(uri)
    return {
        "file": display_path(path, project_root),
        "line": parsed_range["start"]["line"],
        "column": parsed_range["start"]["column"],
        "range": parsed_range,
        "scope": classify_path(path, project_root, engine_root),
    }


def normalize_locations(value: Any, project_root: Path, engine_root: Path | None = None) -> list[dict[str, Any]]:
    if value is None:
        return []
    values = value if isinstance(value, list) else [value]
    locations = [normalize_location(item, project_root, engine_root) for item in values]
    return [item for item in locations if item is not None]


def _hover_item(value: Any) -> dict[str, str] | None:
    if isinstance(value, str):
        return {"kind": "plaintext", "value": value}
    if isinstance(value, dict):
        if isinstance(value.get("value"), str):
            return {"kind": str(value.get("kind") or value.get("language") or "plaintext"), "value": value["value"]}
    return None


def normalize_hover(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        item = _hover_item(value)
        return {"contents": [item]} if item else None
    contents = value.get("contents")
    raw_items = contents if isinstance(contents, list) else [contents]
    items = [item for item in (_hover_item(raw) for raw in raw_items) if item]
    result: dict[str, Any] = {"contents": items}
    parsed_range = normalize_range(value.get("range"))
    if parsed_range:
        result["range"] = parsed_range
    return result


def normalize_workspace_edit(
    value: Any,
    project_root: Path,
    engine_root: Path | None = None,
) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}

    def add_edits(uri: str, edits: Any) -> None:
        if not isinstance(edits, list):
            return
        path = uri_to_path(uri)
        key = display_path(path, project_root)
        record = files.setdefault(key, {"file": key, "scope": classify_path(path, project_root, engine_root), "edits": []})
        for edit in edits:
            if not isinstance(edit, dict):
                continue
            parsed_range = normalize_range(edit.get("range"))
            if parsed_range:
                record["edits"].append({"range": parsed_range, "new_text": str(edit.get("newText", ""))})

    if isinstance(value, dict):
        changes = value.get("changes")
        if isinstance(changes, dict):
            for uri, edits in changes.items():
                add_edits(str(uri), edits)
        document_changes = value.get("documentChanges")
        if isinstance(document_changes, list):
            for change in document_changes:
                if not isinstance(change, dict):
                    continue
                document = change.get("textDocument")
                if isinstance(document, dict) and isinstance(document.get("uri"), str):
                    add_edits(document["uri"], change.get("edits"))
    file_list = sorted(files.values(), key=lambda item: item["file"].lower())
    return {"files": file_list, "file_count": len(file_list), "edit_count": sum(len(item["edits"]) for item in file_list)}


def symbol_at(file_path: Path, line: int, column: int) -> str | None:
    try:
        lines = file_path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        text = lines[line - 1]
    except (OSError, IndexError):
        return None
    index = max(0, min(column - 1, len(text)))
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]*", text):
        if match.start() <= index <= match.end():
            return match.group(0)
    return None


def resolve_query_file(project_root: Path, raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()


def append_trace(record: dict[str, Any]) -> None:
    raw_path = os.environ.get("UE_LSP_TRACE_PATH", "").strip()
    if not raw_path:
        return
    path = Path(raw_path)
    lock = path.with_suffix(path.suffix + ".lock")
    acquired = False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                acquired = True
                break
            except FileExistsError:
                time.sleep(0.02)
        if not acquired:
            return
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
    except OSError:
        return
    finally:
        if acquired:
            try:
                lock.unlink()
            except OSError:
                pass


def trace_for_result(result: dict[str, Any], args: argparse.Namespace, started: float) -> None:
    operation = str(result.get("operation", getattr(args, "command", "unknown")))
    record = {
        "timestamp": utc_now(),
        "query_id": str(result.get("query_id") or uuid.uuid4()),
        "operation": operation,
        "project_root": result.get("project_root"),
        "file": result.get("request", {}).get("file") if isinstance(result.get("request"), dict) else None,
        "line": result.get("request", {}).get("line") if isinstance(result.get("request"), dict) else None,
        "column": result.get("request", {}).get("column") if isinstance(result.get("request"), dict) else None,
        "result_count": result.get("result_count", 0),
        "index_state": result.get("index_state"),
        "possibly_incomplete": bool(result.get("possibly_incomplete", False)),
        "confidence": result.get("confidence"),
        "elapsed_ms": result.get("elapsed_ms", round((time.perf_counter() - started) * 1000, 3)),
        "status": "success" if result.get("health") in {"ok", "degraded"} else "failure",
        "error_code": result.get("error_code"),
    }
    append_trace(record)


def project_status(args: argparse.Namespace) -> tuple[Path | None, dict[str, Any]]:
    raw_project = getattr(args, "project", "") or os.environ.get("UE_LSP_PROJECT_PATH", "")
    status_args = status_module.StatusArgs(
        project=raw_project,
        source_file=getattr(args, "file", "") or "",
        engine_root=getattr(args, "engine_root", "") or "",
        target=getattr(args, "target", "") or "",
        platform=getattr(args, "platform", "Win64") or "Win64",
        configuration=getattr(args, "configuration", "Development") or "Development",
    )
    value = status_module.collect_status(status_args)
    root = Path(str(value["project_root"])) if value.get("project_root") else None
    return root, value


def error_result(operation: str, code: str, message: str, next_actions: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "operation": operation,
        "query_id": str(uuid.uuid4()),
        "health": "broken",
        "confidence": "invalid",
        "error_code": code,
        "message": message,
        "next_actions": next_actions or [],
        **extra,
    }


def command_status(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root, value = project_status(args)
    value = {"operation": "status", "query_id": str(uuid.uuid4()), **value}
    if project_root:
        metadata = read_server_metadata(project_root)
        value["managed_server"] = {
            "running": bool(metadata and value.get("clangd_path") and value.get("compile_commands_path") and server_is_current(
                metadata, project_root, Path(str(value["clangd_path"])), Path(str(value["compile_commands_path"]))
            )),
            "metadata_path": str(server_paths(project_root).metadata),
            "metadata": metadata,
        }
    return value, 0


def require_ready_project(args: argparse.Namespace) -> tuple[Path, dict[str, Any], Path, Path]:
    project_root, value = project_status(args)
    if project_root is None:
        raise QueryError("invalid-project", "; ".join(str(item) for item in value.get("caveats", [])), ["provide_project_path"])
    state = value.get("compile_commands_health")
    if state != "valid":
        raise QueryError(
            "missing-compdb" if state == "missing" else f"compdb-{state}",
            str((value.get("compile_commands_validation") or {}).get("message") or "workspace compile database is not valid"),
            ["run_status", "generate_workspace_compile_database"],
        )
    clangd_raw = value.get("clangd_path")
    if not clangd_raw:
        raise QueryError("missing-clangd", "clangd was not found on PATH", ["install_or_add_clangd_to_path"])
    return project_root, value, Path(str(clangd_raw)), Path(str(value["compile_commands_path"]))


def command_start(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root, value, clangd_path, compdb = require_ready_project(args)
    metadata, started = ensure_server(project_root, clangd_path, compdb)
    return {
        "operation": "start",
        "query_id": str(uuid.uuid4()),
        "health": "ok",
        "confidence": "high",
        "project_root": str(project_root),
        "compile_commands_path": str(compdb),
        "clangd_path": str(clangd_path),
        "clangd_version": metadata.get("clangd_version"),
        "server_started": started,
        "server": {key: metadata.get(key) for key in ("pid", "port", "started_at")},
        "index_state": send_server_request(metadata, {"operation": "ping"}, timeout=2).get("index_state", "unknown"),
    }, 0


def command_stop(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root, value = project_status(args)
    if project_root is None:
        raise QueryError("invalid-project", "; ".join(str(item) for item in value.get("caveats", [])))
    metadata = read_server_metadata(project_root)
    stopped = False
    if metadata:
        try:
            response = send_server_request(metadata, {"operation": "stop"}, timeout=5)
            stopped = response.get("status") == "ok"
        except Exception:
            terminate_stale_managed_server(metadata, project_root)
            stopped = True
    return {
        "operation": "stop",
        "query_id": str(uuid.uuid4()),
        "health": "ok",
        "confidence": "high",
        "project_root": str(project_root),
        "server_stopped": stopped,
    }, 0


def command_query(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    project_root, value, clangd_path, compdb = require_ready_project(args)
    file_path = resolve_query_file(project_root, args.file)
    if args.line < 1 or args.column < 1:
        raise QueryError("invalid-position", "--line and --column are 1-based and must be positive")
    metadata, _ = ensure_server(project_root, clangd_path, compdb)
    request = {
        "operation": args.command,
        "file": str(file_path),
        "line": args.line - 1,
        "column": args.column - 1,
        "timeout": args.timeout,
        "wait_for_index": args.wait_for_index,
        "index_timeout": args.index_timeout,
    }
    if args.command == "references":
        request["include_declaration"] = not args.exclude_declaration
    if args.command == "rename-preview":
        request["new_name"] = args.new_name
    response = send_server_request(metadata, request, timeout=args.timeout + args.index_timeout + 5)
    if response.get("status") != "ok":
        raise QueryError(
            str(response.get("error_code") or "query-failed"),
            str(response.get("message") or "managed query failed"),
            list(response.get("next_actions") or []),
        )
    raw_result = response.get("raw_result")
    index_state = str(response.get("index_state") or "unknown")
    possibly_incomplete = args.command in {"references", "implementation", "rename-preview"} and index_state != "ready"
    engine_root = Path(str(value["engine_root"])) if value.get("engine_root") else None
    result: dict[str, Any] = {
        "operation": args.command,
        "query_id": str(uuid.uuid4()),
        "health": "ok",
        "confidence": "medium" if possibly_incomplete else "high",
        "project_root": str(project_root),
        "compile_commands_path": str(compdb),
        "clangd_path": str(clangd_path),
        "clangd_version": metadata.get("clangd_version"),
        "symbol": symbol_at(file_path, args.line, args.column),
        "request": {"file": display_path(file_path, project_root), "line": args.line, "column": args.column},
        "index_state": index_state,
        "possibly_incomplete": possibly_incomplete,
        "elapsed_ms": response.get("elapsed_ms"),
        "caveats": ["background index is not ready; cross-file results may be incomplete"] if possibly_incomplete else [],
    }
    if args.command in {"definition", "references", "implementation"}:
        locations = normalize_locations(raw_result, project_root, engine_root)
        result["locations"] = locations
        result["result_count"] = len(locations)
        if args.command == "references":
            result["include_declaration"] = not args.exclude_declaration
    elif args.command == "hover":
        hover = normalize_hover(raw_result)
        result["hover"] = hover
        result["result_count"] = 1 if hover else 0
    else:
        raw_workspace_edit = normalize_workspace_edit(raw_result, project_root, engine_root)
        source_files = [item for item in raw_workspace_edit["files"] if item["scope"] == "project-source"]
        excluded_files = [
            {**item, "excluded_reason": "rename-preview only exposes project Source edits as actionable preview"}
            for item in raw_workspace_edit["files"]
            if item["scope"] != "project-source"
        ]
        workspace_edit = {
            "files": source_files,
            "file_count": len(source_files),
            "edit_count": sum(len(item["edits"]) for item in source_files),
        }
        result["workspace_edit"] = workspace_edit
        result["files"] = source_files
        result["excluded_files"] = excluded_files
        result["excluded_edit_count"] = sum(len(item["edits"]) for item in excluded_files)
        result["result_count"] = workspace_edit["edit_count"]
        result["applied"] = False
    return result, 0


def add_project_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", default="", help=".uproject path or project directory; defaults to UE_LSP_PROJECT_PATH")
    parser.add_argument("--engine-root", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--platform", default="Win64")
    parser.add_argument("--configuration", default="Development")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "start", "stop"):
        child = sub.add_parser(name)
        add_project_options(child)
    for name in ("definition", "hover", "references", "implementation", "rename-preview"):
        child = sub.add_parser(name)
        add_project_options(child)
        child.add_argument("--file", required=True)
        child.add_argument("--line", required=True, type=int)
        child.add_argument("--column", required=True, type=int)
        child.add_argument("--timeout", type=float, default=DEFAULT_QUERY_TIMEOUT)
        child.add_argument("--wait-for-index", action="store_true")
        child.add_argument("--index-timeout", type=float, default=DEFAULT_INDEX_TIMEOUT)
        if name == "references":
            child.add_argument("--exclude-declaration", action="store_true")
        if name == "rename-preview":
            child.add_argument("--new-name", required=True)
    serve_parser = sub.add_parser("_serve", help=argparse.SUPPRESS)
    serve_parser.add_argument("--project-root", required=True)
    serve_parser.add_argument("--clangd", required=True)
    serve_parser.add_argument("--token", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "_serve":
        return serve(Path(args.project_root), Path(args.clangd), args.token)
    started = time.perf_counter()
    try:
        if args.command == "status":
            result, exit_code = command_status(args)
        elif args.command == "start":
            result, exit_code = command_start(args)
        elif args.command == "stop":
            result, exit_code = command_stop(args)
        else:
            result, exit_code = command_query(args)
    except QueryError as exc:
        project_root, _ = project_status(args)
        result = error_result(
            args.command,
            exc.code,
            str(exc),
            exc.next_actions,
            project_root=str(project_root) if project_root else None,
            request={
                "file": getattr(args, "file", None),
                "line": getattr(args, "line", None),
                "column": getattr(args, "column", None),
            },
        )
        exit_code = 1
    except Exception as exc:
        result = error_result(args.command, "internal-error", str(exc))
        exit_code = 1
    trace_for_result(result, args, started)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
