#!/usr/bin/env python3
"""Exercise a dedicated headless executable through both real MCP stdio adapters.

Uses synthetic audio and a temporary project. Never connects to an existing host.
"""
import argparse
import json
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import wave


class Client:
    def __init__(self, script, endpoint):
        self.process = subprocess.Popen(
            [sys.executable, str(script), "--endpoint", str(endpoint)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
        )
        self.counter = 0
        self.rpc("initialize", {"protocolVersion": "2025-11-25"})

    def rpc(self, method, params):
        self.counter += 1
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.counter,
                                            "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        if not select.select([self.process.stdout], [], [], 15)[0]:
            raise RuntimeError("MCP response timed out")
        response = json.loads(self.process.stdout.readline())
        assert "error" not in response, response
        return response["result"]

    def call(self, name, args=None):
        result = self.rpc("tools/call", {"name": name, "arguments": args or {}})
        assert not result.get("isError"), result
        return result["structuredContent"]

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        self.process.stdout.close()


def guard(data):
    return {key: data[key] for key in ("session", "revision")}


def settled(client):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = client.call("editor_status")
        if result["pending"] is None:
            assert result["last_error"] is None, result
            return result
        time.sleep(0.02)
    raise RuntimeError("Lifecycle timed out")


def run(binary):
    scripts = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="phichain-headless-") as directory:
        root = Path(directory)
        endpoint, project, music = root / "endpoint.json", root / "project", root / "song.wav"
        with wave.open(str(music), "wb") as output:
            output.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            output.writeframes(b"\x00\x00" * 16000)
        with (root / "host.log").open("w+") as log:
            host = subprocess.Popen([str(binary), "--headless", "--mcp-endpoint", str(endpoint)],
                                    stdout=log, stderr=log, cwd=root)
            clients = []
            try:
                deadline = time.monotonic() + 15
                while not endpoint.exists():
                    if host.poll() is not None or time.monotonic() > deadline:
                        log.seek(0)
                        raise RuntimeError("Host failed to start: " + log.read())
                    time.sleep(0.02)
                base = Client(scripts / "server.py", endpoint)
                clients.append(base)
                agent = Client(scripts / "agent_server.py", endpoint)
                clients.append(agent)
                status = base.call("editor_status")
                assert status["pid"] == host.pid and status["headless"] is True, status
                assert status["project"] is None
                base.call("create_project", {"path": str(project), "music_path": str(music)})
                assert settled(base)["created_path"] == str(project)
                base.call("open_project", {"path": str(project)})
                data = settled(base)["project"]
                initial_session = data["session"]
                change = {**guard(data), "dry_run": True, "operations": [{
                    "op": "insert", "path": "/notes/new:smoke", "value": {
                        "line_id": data["lines"][0]["id"], "note": {
                            "kind": "tap", "above": True, "beat": [1, 0, 1], "x": 42, "speed": 1,
                        },
                    },
                }]}
                agent.call("chart_patch", change)
                assert base.call("get_context")["note_count"] == 0
                agent.call("chart_patch", {**change, "dry_run": False})
                data = base.call("get_context")
                assert data["note_count"] == 1
                base.call("history", {**guard(data), "action": "undo", "author": "agent"})
                data = base.call("get_context")
                assert data["note_count"] == 0
                base.call("history", {**guard(data), "action": "redo", "author": "agent"})
                base.call("preview", {"session": data["session"], "action": "seek", "time_seconds": 1})
                assert base.call("get_context")["time_seconds"] == 1
                base.call("preview", {"session": data["session"], "action": "play", "time_seconds": 1.98})
                time.sleep(0.1)
                data = base.call("get_context")
                assert data["paused"] is True and abs(data["time_seconds"] - 2) < 0.001, data
                base.call("save", guard(data))
                data = base.call("get_context")
                base.call("close_project", guard(data))
                assert settled(base)["project"] is None
                base.call("open_project", {"path": str(project)})
                data = settled(base)["project"]
                assert data["note_count"] == 1 and data["session"] != initial_session
                assert (project / "music.wav").read_bytes() == music.read_bytes()
                print(json.dumps({"ok": True, "host": "headless", "adapters": ["server.py", "agent_server.py"],
                                  "verified": ["create", "import", "open", "dry_run", "edit", "undo", "redo",
                                               "silent_seek", "end_pause", "save", "close", "reopen"]}))
            finally:
                for client in clients:
                    client.close()
                host.terminate()
                try:
                    host.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    host.kill()
                    host.wait()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    run(parser.parse_args().binary.resolve(strict=True))
