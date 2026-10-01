#!/usr/bin/env python3
"""Dependency-free MCP stdio adapter for the live PhiChain editor."""
import argparse
import json
import math
from pathlib import Path
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_tools import LocalTools

VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MAX_MESSAGE = 1_048_576


def obj(properties, required=()):
    return {"type": "object", "properties": properties,
            "required": list(required), "additionalProperties": False}


STRING = {"type": "string"}
NUMBER = {"type": "number"}
ID = {"type": "string", "pattern": "^[0-9]+$"}
BEAT = {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3,
        "description": "[whole, numerator, denominator], denominator positive. E.g. [4,1,2] = beat 4.5."}
NOTE_PROPERTIES = {"kind": {"enum": ["tap", "drag", "hold", "flick"]},
                   "above": {"type": "boolean"}, "beat": BEAT, "x": NUMBER,
                   "speed": {"type": "number", "exclusiveMinimum": 0}, "hold_beat": BEAT}
NOTE = obj(NOTE_PROPERTIES, ("kind", "above", "beat", "x", "speed"))
EVENT = obj({"kind": {"enum": ["x", "y", "rotation", "opacity", "speed"]},
             "start_beat": BEAT, "end_beat": BEAT,
             "value": {"oneOf": [obj({"type": {"const": "constant"}, "value": NUMBER}, ("type", "value")),
                                  obj({"type": {"const": "transition"}, "start": NUMBER, "end": NUMBER,
                                       "easing": {"description": "PhiChain easing value; copy from read_section."}},
                                      ("type", "start", "end", "easing"))]}},
            ("kind", "start_beat", "end_beat", "value"))
META = obj({key: STRING for key in ("name", "composer", "charter", "illustrator", "level")},
           ("name", "composer", "charter", "illustrator", "level"))
GUARD = {"session": STRING, "revision": STRING}
OPERATIONS = []
for action, fields in (
    ("create_note", {"line_id": ID, "note": NOTE}),
    ("update_note", {"id": ID, "note": NOTE}),
    ("delete_note", {"id": ID}),
    ("create_event", {"line_id": ID, "event": EVENT}),
    ("update_event", {"id": ID, "event": EVENT}),
    ("delete_event", {"id": ID}),
    ("set_offset", {"offset": NUMBER}),
    ("set_meta", {"meta": META}),
):
    OPERATIONS.append(obj({"op": {"const": action}, **fields}, ("op", *fields)))

PARENT = {"oneOf":[ID,{"type":"null"}]}
CURVE_OPTIONS = obj({"kind":{"enum":["tap","drag","flick","hold"]},"hold_beat":BEAT,
    "density":{"type":"integer","minimum":1,"maximum":256},"curve":{"type":"object"}},("kind","density","curve"))
for action,fields in (
    ("create_line",{"name":STRING,"parent_id":PARENT}),
    ("update_line",{"id":ID,"name":STRING,"parent_id":PARENT}),
    ("delete_line",{"id":ID,"cascade":{"type":"boolean"}}),
    ("reorder_lines",{"line_ids":{"type":"array","items":ID,"minItems":1}}),
    ("create_curve_track",{"line_id":ID,"from_id":ID,"to_id":ID,"options":CURVE_OPTIONS}),
    ("update_curve_track",{"id":ID,"from_id":ID,"to_id":ID,"options":CURVE_OPTIONS}),
    ("delete_curve_track",{"id":ID}),
):
    required=[key for key in fields if key not in ("parent_id","cascade")]
    OPERATIONS.append(obj({"op":{"const":action},**fields},("op",*required)))


def tool(name, description, schema, read_only=False, destructive=False):
    return {"name": name, "description": description, "inputSchema": schema,
            "annotations": {"readOnlyHint": read_only, "destructiveHint": destructive,
                            "idempotentHint": read_only, "openWorldHint": False}}


TOOLS = [
    tool("get_context", "Read the open project's session/revision, lines, BPM, offset, selected objects and IDs, selected line, playback and undo state. Start here. IDs are opaque strings valid only in this project session.", obj({}), True),
    tool("read_section", "Read editable notes, overlapping holds and line events in [start_beat,end_beat). Defaults to beats 0–32. Optionally filter by line_id. Includes curve track references; generated curve notes are not editable. Returns fresh session/revision.", obj({"start_beat": NUMBER, "end_beat": NUMBER, "line_id": ID}), True),
    tool("apply_edits", "Validate and apply 1–1000 operations as ONE undo step. Supply session/revision from the latest read. Update operations replace the full note/event: preserve unmodified fields. Each existing ID may occur once. Hold notes require positive hold_beat. Curve endpoints cannot be deleted. Returns before/after changes and created IDs. Does not save. Stale edits fail without mutation; re-read and regenerate.",
         obj({**GUARD, "operations": {"type": "array", "minItems": 1, "maxItems": 1000,
                                      "items": {"oneOf": OPERATIONS}}}, ("session", "revision", "operations")), destructive=True),
    tool("preview", "Play, pause, or seek the editor preview. Supply the current project session. time_seconds is elapsed audio time, including chart offset. Optional time_seconds seeks before play/pause; seek requires time_seconds. Seeking is processed on the next editor frame. Read context to observe actual playback position. This changes the human's shared playback controls.",
         obj({"session": STRING, "action": {"enum": ["play", "pause", "seek"]},
              "time_seconds": {"type": "number", "minimum": 0}}, ("session", "action"))),
    tool("history", "Undo or redo ONE entry in the shared human/agent history. Requires fresh session/revision. This may undo a human edit; only use when requested or when reverting your known latest batch.",
         obj({**GUARD, "action": {"enum": ["undo", "redo"]}}, ("session", "revision", "action")), destructive=True),
    tool("save", "Save the current live chart and metadata to the open project's files. Requires fresh session/revision. Use when the user asks to save; edits remain in memory until saved or autosaved by PhiChain.",
         obj(GUARD, ("session", "revision")), destructive=True),
]
PATH = {"type":"string", "minLength":1, "description":"Absolute local filesystem path"}
INT = {"type":"integer"}
TOOLS += [
    tool("editor_status", "Identify the MCP-connected build/PID, pending load, last load error and open project. Works before opening a project; unreachable endpoints return connected=false.", obj({}), True),
    tool("launch_editor", "Launch the configured PhiChain build with MCP and asset paths. Reuses a reachable editor; refuses an unreachable existing endpoint. Poll editor_status for readiness.", obj({"project_path":PATH})),
    tool("create_project", "Create a new project from prepared audio and metadata, including a visible default line. Refuses existing destinations. Does not open it; use open_project.", obj({"path":PATH,"audio_path":PATH,"meta":META,"illustration_path":PATH}, ("path","audio_path","meta"))),
    tool("open_project", "Request loading a project into an empty editor. Close/save the current project first. Poll editor_status; acknowledgment is not successful loading.", obj({"path":PATH}, ("path",))),
    tool("close_project", "Close the current saved project with fresh session/revision. Refuses unsaved work and active human edits. Poll editor_status to verify.", obj(GUARD,("session","revision"))),
    tool("project_snapshot", "Read native serialized chart and metadata at a guarded revision, including unsaved edits and asset paths. Used by render/export without saving or changing the live project.", obj(GUARD,("session","revision")),True),
    tool("find_local_audio", "Search explicit local directories for audio by normalized filename terms, including NCM. Bounded traversal; reports truncation. Inspect candidates for embedded metadata.", obj({"roots":{"type":"array","items":PATH,"minItems":1,"maxItems":20},"query":STRING,"limit":{"type":"integer","minimum":1,"maximum":200}},("roots",)),True),
    tool("inspect_audio", "Inspect actual codec, bitrate, duration, tags and artwork. Supports local NCM extraction in a temporary directory. Requires ffprobe and openssl for NCM.", obj({"path":PATH},("path",)),True),
    tool("import_audio", "Prepare local audio at a new explicit path; extract NCM, preserve matching original codec or convert as required. Return source hash, reencoding status and optional artwork. Never overwrite source/output.", obj({"source_path":PATH,"output_path":PATH,"format":{"enum":["mp3","wav","flac","ogg"]},"artwork_output":PATH},("source_path","output_path"))),
    tool("render_preview", "Render a snapshot of this exact live revision, including unsaved edits, into an MP4. Range is elapsed audio seconds. Returns persistent job ID immediately; poll render_status. Does not save or change editor playback.", obj({**GUARD,"output_path":PATH,"from_seconds":{"type":"number","minimum":0},"to_seconds":{"type":"number","exclusiveMinimum":0},"width":INT,"height":INT,"fps":INT},("session","revision","output_path","from_seconds","to_seconds"))),
    tool("capture_preview", "Render a PNG still at elapsed audio time from a guarded live chart snapshot. Returns job ID; poll render_status.", obj({**GUARD,"output_path":PATH,"time_seconds":{"type":"number","minimum":0},"width":INT,"height":INT},("session","revision","output_path","time_seconds"))),
    tool("render_status", "Read persistent render/capture/export job state, revision, output path or diagnostic error. Jobs survive MCP adapter restarts.", obj({"job_id":STRING},("job_id",)),True),
    tool("export_chart", "Export the exact live revision through PhiChain's converter into a new file. Returns job ID; poll render_status. Converter diagnostics are reported; conversion can lose unsupported format features.", obj({**GUARD,"output_path":PATH,"format":{"enum":["phichain","official","rpe"]}},("session","revision","output_path","format"))),
]
TOOLS += [
    tool("validate_chart", "Read-only chart checks including generated curves, contact demand, duplicate notes, offscreen hit centers with native easing/ancestor transforms, invisible lines, nonpositive scroll speed, overlapping events and audio/range boundaries. Warnings are design findings; conservative contact counts are not a playability proof. Default viewport aspect is 16:9.", obj({"start_beat":NUMBER,"end_beat":NUMBER,"aspect_ratio":NUMBER,"max_contacts":{"type":"integer","minimum":1,"maximum":10}}),True),
    tool("select_objects", "Replace editor selection with explicit editable note/event/curve IDs; optional line_id changes selected line. Empty ids clears selection. Requires current session; does not create history.", obj({"session":STRING,"ids":{"type":"array","items":ID,"maxItems":1000},"line_id":ID},("session","ids"))),
    tool("set_editor_view", "Focus a chart beat, set timeline zoom/density/spectrogram, or switch layout to default or preview. Requires current session. Focus pauses playback and queues a seek; read context to observe it. Changes shared review UI without chart history.", obj({"session":STRING,"focus_beat":NUMBER,"zoom":{"type":"number","minimum":0.1,"maximum":5},"density":{"type":"integer","minimum":1,"maximum":256},"show_spectrogram":{"type":"boolean"},"layout":{"enum":["default","preview"]}},("session",))),
]
BY_NAME = {tool["name"]: tool for tool in TOOLS}
INSTRUCTIONS = (
    "Coordinate with the human in the live PhiChain editor. Start with get_context, then read_section for relevant beats. "
    "Use selection IDs to resolve 'these notes'. Preserve fields not requested to change. "
    "Apply edits through apply_edits using the latest session/revision; each batch is one undo step. "
    "On stale state, re-read and reconsider. On transport timeout, read state before retrying: the edit may have executed. "
    "Never blindly undo: history is shared. Preview changes in PhiChain; explain your changes in chat."
)


def validate(value, schema, path="arguments"):
    """Validate the schema subset used by this adapter before touching the editor."""
    if "oneOf" in schema:
        matches = 0
        for variant in schema["oneOf"]:
            try:
                validate(value, variant, path)
                matches += 1
            except ValueError:
                pass
        if matches != 1:
            raise ValueError(f"{path} must match exactly one supported operation/value shape")
        return
    if "const" in schema and value != schema["const"]:
        raise ValueError(f"{path} must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} must be one of {schema['enum']}")
    kind = schema.get("type")
    if kind == "null" and value is not None:
        raise ValueError(f"{path} must be null")
    if kind == "string" and isinstance(value,str) and len(value) < schema.get("minLength", 0):
        raise ValueError(f"{path} is too short")
    types = {"object": dict, "array": list, "string": str, "boolean": bool}
    if kind in types and not isinstance(value, types[kind]):
        raise ValueError(f"{path} must be {kind}")
    if kind in ("number", "integer"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{path} must be a finite {kind}")
        if kind == "integer" and not isinstance(value, int):
            raise ValueError(f"{path} must be an integer")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} is above maximum")
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} is below minimum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValueError(f"{path} must exceed {schema['exclusiveMinimum']}")
    if kind == "string" and schema.get("pattern") and not value.isascii():
        raise ValueError(f"{path} must contain ASCII digits")
    if kind == "string" and schema.get("pattern") and not value.isdecimal():
        raise ValueError(f"{path} must contain digits")
    if kind == "object":
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        for key, item in value.items():
            if key not in properties:
                if schema.get("additionalProperties") is False:
                    raise ValueError(f"Unknown field {path}.{key}")
            else:
                validate(item, properties[key], f"{path}.{key}")
    if kind == "array":
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", sys.maxsize):
            raise ValueError(f"{path} has invalid length")
        for index, item in enumerate(value):
            validate(item, schema.get("items", {}), f"{path}[{index}]")


def call_editor(endpoint, name, arguments):
    # Re-read descriptor every call so an editor restart can use a new port/token.
    descriptor = json.loads(Path(endpoint).read_text(encoding="utf-8"))
    port = descriptor["port"]
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Invalid editor endpoint port")
    payload = json.dumps({"token": descriptor["token"], "tool": name, "arguments": arguments},
                         allow_nan=False, separators=(",", ":")).encode() + b"\n"
    if len(payload) > MAX_MESSAGE:
        raise ValueError("Request exceeds 1 MiB")
    with socket.create_connection(("127.0.0.1", port), timeout=12) as connection:
        connection.sendall(payload)
        with connection.makefile("rb") as reader:
            response = reader.readline(16 * MAX_MESSAGE + 1)
    if not response or len(response) > 16 * MAX_MESSAGE:
        raise ValueError("Missing or oversized editor response; re-read state before retrying edits")
    return json.loads(response)


class Server:
    def __init__(self, endpoint, config=None):
        self.endpoint = endpoint
        self.local = LocalTools(endpoint, lambda name, args: call_editor(self.endpoint, name, args), config)
        self.initialized = False

    def dispatch(self, request):
        request_id = request.get("id")
        if request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return self.error(request_id, -32600, "Invalid JSON-RPC request")
        if "id" not in request:  # Notifications never receive a response.
            return None
        if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
            return self.error(None, -32600, "Request ID must be a string or integer")
        method = request["method"]
        params = request.get("params", {})
        if not isinstance(params, dict):
            return self.error(request_id, -32602, "params must be an object")
        if method == "initialize":
            version = params.get("protocolVersion")
            if not isinstance(version, str):
                return self.error(request_id, -32602, "protocolVersion is required")
            self.initialized = True
            result = {"protocolVersion": version if version in VERSIONS else VERSIONS[0],
                      "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "phichain", "version": "0.2.0"},
                      "instructions": INSTRUCTIONS}
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return self.error(request_id, -32000, "Initialize the MCP server first")
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str) or name not in BY_NAME:
                return self.error(request_id, -32602, "Unknown tool")
            arguments = params.get("arguments", {})
            try:
                validate(arguments, BY_NAME[name]["inputSchema"])
                data = self.local.call(name, arguments) if name in LocalTools.NAMES else call_editor(self.endpoint, name, arguments)
                is_error = isinstance(data, dict) and "error" in data and name != "render_status"
                result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                          "isError": is_error}
                if not is_error:
                    result["structuredContent"] = data
            except (OSError, ValueError, KeyError, OverflowError, subprocess.SubprocessError) as error:
                result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
        else:
            return self.error(request_id, -32601, f"Unknown method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def error(request_id, code, message):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="Endpoint JSON created by PhiChain --mcp-endpoint")
    for name in ("editor", "renderer", "converter", "ffmpeg", "ffprobe"):
        parser.add_argument("--"+name, help="Absolute executable path override")
    options = parser.parse_args()
    server = Server(options.endpoint, {name:getattr(options,name) for name in ("editor", "renderer", "converter", "ffmpeg", "ffprobe")})
    for line in sys.stdin:
        try:
            if len(line.encode("utf-8")) > MAX_MESSAGE:
                raise ValueError("MCP request exceeds 1 MiB")
            request = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid number {value}")))
            response = server.dispatch(request) if isinstance(request, dict) else server.error(None, -32600, "Request must be an object")
        except (ValueError, RecursionError) as error:
            response = server.error(None, -32700, str(error))
        if response is not None:
            print(json.dumps(response, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
