import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("phichain_mcp", Path(__file__).with_name("server.py"))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.adapter = server.Server("unused")
        self.adapter.dispatch({"jsonrpc": "2.0", "id": 0, "method": "initialize",
                               "params": {"protocolVersion": "2025-11-25"}})

    def request(self, name, arguments):
        return self.adapter.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": name, "arguments": arguments}})

    def test_initialize_list_and_notifications(self):
        response = self.adapter.dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(len(response["result"]["tools"]), 6)
        self.assertIsNone(self.adapter.dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(server.Server("unused").dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["error"]["code"], -32000)

    def test_invalid_shapes_never_contact_editor(self):
        invalid = [({}, "apply_edits"), ({"session": "s", "action": "stop"}, "preview"),
                   ({"session": "s", "revision": "r", "operations": []}, "apply_edits"),
                   ({"line_id": 123}, "read_section"), ({"surprise": True}, "get_context"),
                   ({"start_beat": float("nan")}, "read_section")]
        with patch.object(server, "call_editor") as bridge:
            for arguments, name in invalid:
                self.assertTrue(self.request(name, arguments)["result"]["isError"])
            bridge.assert_not_called()

    def test_success_structured_content_and_editor_errors(self):
        with patch.object(server, "call_editor", return_value={"session": "s", "revision": "r"}):
            result = self.request("get_context", {})["result"]
            self.assertFalse(result["isError"])
            self.assertEqual(result["structuredContent"]["session"], "s")
        with patch.object(server, "call_editor", return_value={"error": "Chart changed"}):
            self.assertTrue(self.request("get_context", {})["result"]["isError"])

    def test_loopback_bridge_and_token(self):
        with tempfile.TemporaryDirectory() as directory:
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                endpoint = Path(directory) / "endpoint.json"
                endpoint.write_text(json.dumps({"port": listener.getsockname()[1], "token": "secret"}))
                received = []
                def respond():
                    connection, _ = listener.accept()
                    with connection, connection.makefile("rb") as reader:
                        received.append(json.loads(reader.readline()))
                        connection.sendall(b'{"session":"live","revision":"r"}\n')
                thread = threading.Thread(target=respond)
                thread.start()
                result = server.call_editor(endpoint, "get_context", {})
                thread.join(timeout=2)
                self.assertEqual(received[0]["token"], "secret")
                self.assertEqual(received[0]["tool"], "get_context")
                self.assertEqual(result["session"], "live")

    def test_actual_stdio_process_and_parse_errors(self):
        requests = ["{bad", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}),
                    json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
                    json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
                    json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"})]
        process = subprocess.run([sys.executable, str(Path(__file__).with_name("server.py")), "--endpoint", "missing"],
                                 input="\n".join(requests)+"\n", text=True, capture_output=True, check=True)
        responses = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(responses), 4)
        self.assertEqual(responses[0]["error"]["code"], -32700)
        self.assertEqual(responses[1]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual(responses[3]["result"], {})
        self.assertEqual(process.stderr, "")


if __name__ == "__main__":
    unittest.main()
