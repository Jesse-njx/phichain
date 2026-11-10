#!/usr/bin/env python3
"""Dependency-free MCP stdio adapter for the live PhiChain editor."""
import argparse
import json
import math
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import motion

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

BPM_LIST = {"type":"array","minItems":1,"maxItems":1000,"items":obj({"beat":BEAT,"bpm":{"type":"number","minimum":1,"maximum":1000}},("beat","bpm"))}
OPERATIONS.append(obj({"op":{"const":"set_bpm_list"},"bpm_list":BPM_LIST},("op","bpm_list")))


def tool(name, description, schema, read_only=False, destructive=False):
    return {"name": name, "description": description, "inputSchema": schema,
            "annotations": {"readOnlyHint": read_only, "destructiveHint": destructive,
                            "idempotentHint": read_only, "openWorldHint": False}}


TOOLS = [
    tool("editor_status", "Read GUI/headless runtime status without an open project. Includes headless, project, pending, last_error and created_path. Poll after lifecycle requests; pending=null and last_error=null means completion. A successful create reports created_path; open_project is a separate step.", obj({}), True),
    tool("create_project", "Create a new native project and import a local song plus optional cover without dialogs. Requires no open project or pending lifecycle job. path must be a NEW absolute directory with an existing parent; never overwrites. music_path: MP3/WAV/OGG/FLAC; optional illustration_path: PNG/JPG/JPEG. Source data is decoded/validated, copied into the project and left unchanged. meta defaults to empty fields. The new chart has one visible judgment line (opacity 255). Asynchronous: poll editor_status, then open_project using created_path. Not undoable.",
         obj({"path": STRING, "music_path": STRING, "illustration_path": STRING, "meta": META}, ("path", "music_path"))),
    tool("open_project", "Open an existing native project by absolute path without a file dialog. Requires no open project or pending lifecycle job. Asynchronous: poll editor_status until pending=null; check last_error and project before editing.", obj({"path": STRING}, ("path",))),
    tool("close_project", "Close the current project with fresh session/revision. Unsaved work and active edits reject; save first. Poll editor_status until project=null and pending=null before opening another project.", obj(GUARD, ("session", "revision"))),
    tool("get_context", "Read the open project's session/revision, lines, BPM, offset, selected objects and IDs, selected line, playback and undo state, including undo_author/redo_author (agent, human, or null). Start here. IDs are opaque strings valid only in this project session.", obj({}), True),
    tool("read_section", "Read editable notes, overlapping holds and line events in [start_beat,end_beat). Defaults to beats 0–32. Optionally filter by line_id. Includes curve track references; generated curve notes are not editable. Returns fresh session/revision.", obj({"start_beat": NUMBER, "end_beat": NUMBER, "line_id": ID}), True),
    tool("inspect_motion", "Inspect 1–32 explicit note IDs, or the current selected editable notes. Requires live session/revision and an elapsed-audio range of at most 12 seconds. Returns 2–12 actual rendered frames (default 6), screen trajectories, landing positions, carrier/ancestor IDs, sampled transforms and contributing events, including hidden lines. Read-only: no playback, chart, selection or history changes. Requires local phichain-renderer, ffmpeg and GPU; never falls back to an offline chart. Frames use default styling at 960×540 and 30 fps, with hit effects hidden. A local HTML report overlays IDs, carriers and trajectories. Results remain tied to the captured revision; check live_revision_changed. Generated notes appear in frames but cannot be selected as targets.",
         obj({**GUARD, "note_ids": {"type":"array","items":ID,"minItems":1,"maxItems":32,"uniqueItems":True},
              "from_seconds":{"type":"number","minimum":0,"maximum":86400}, "to_seconds":{"type":"number","exclusiveMinimum":0,"maximum":86400},
              "frames":{"type":"integer","minimum":2,"maximum":12}}, ("session","revision","from_seconds","to_seconds")), True),
    tool("apply_edits", "Validate and apply 1–1000 operations as ONE undo step. Supply session/revision from the latest read. Update operations replace the full note/event: preserve unmodified fields. Each existing ID may occur once. Hold notes require positive hold_beat. Curve endpoints cannot be deleted. Returns before/after changes and created IDs. Does not save. Stale edits fail without mutation; re-read and regenerate.",
         obj({**GUARD, "operations": {"type": "array", "minItems": 1, "maxItems": 1000,
                                      "items": {"oneOf": OPERATIONS}}}, ("session", "revision", "operations")), destructive=True),
    tool("preview", "Play, pause, or seek the editor preview. Supply the current project session. time_seconds is elapsed audio time, including chart offset. Optional time_seconds seeks before play/pause; seek requires time_seconds. Seeking is processed on the next editor frame. Read context to observe actual playback position. GUI mode changes the human's shared playback controls. Headless mode uses a silent clock with the same seek/play/pause actions and stops at the audio duration.",
         obj({"session": STRING, "action": {"enum": ["play", "pause", "seek"]},
              "time_seconds": {"type": "number", "minimum": 0}}, ("session", "action"))),
    tool("history", "Undo or redo ONE entry in the shared history. Explicitly choose author: agent or human. Must match the next undo_author/redo_author from get_context; mismatch fails without mutation. Cannot skip entries. Requires fresh session/revision. This may undo a human edit; only use when requested or when reverting your known latest batch.",
         obj({**GUARD, "action": {"enum": ["undo", "redo"]}, "author": {"enum": ["agent", "human"]}}, ("session", "revision", "action", "author")), destructive=True),
    tool("save", "Save the current live chart and metadata to the open project's files. Requires fresh session/revision. Use when the user asks to save; edits remain in memory until saved or autosaved by PhiChain.",
         obj(GUARD, ("session", "revision")), destructive=True),
]
TOOLS += [
    tool("preview_passage", "Render a guarded live passage of at most 12 audio seconds to a local MP4 and HTML video with play/pause, looping and scrubbing. Does not open the report or alter editor playback, chart or history. Uses PhiChain rendering as visual ground truth; 960×540, 30 fps, default styling, hidden hit effects. Requires renderer, ffmpeg and GPU. Returns captured revision and live_revision_changed.",
         obj({**GUARD,"from_seconds":{"type":"number","minimum":0,"maximum":86400},"to_seconds":{"type":"number","exclusiveMinimum":0,"maximum":86400}}, ("session","revision","from_seconds","to_seconds")), True),
    tool("animate_selection", "Apply explicit motion groups on existing carriers, as one undo step. dry_run must be explicit. Every note on each affected carrier must be included (including future notes); child lines and curve dependencies reject. Merge only identical event timelines with the same parent; preserve note IDs, kinds, hit times, local x, speed and hold durations. Supplied event channels replace their ENTIRE timelines on the destination carrier; omitted channels stay unchanged. Supports zero/negative line speed for early-visible playable notes. Never allocates lines or deletes source carriers. Default budget 24 counts ALL lines, including decoration; explicitly raise for larger charts. Review full visibility and landing motion before applying.",
         obj({**GUARD,"dry_run":{"type":"boolean"},"line_budget":{"type":"integer","minimum":1,"maximum":1024},
              "groups":{"type":"array","minItems":1,"maxItems":24,"items":obj({"carrier_id":ID,"note_ids":{"type":"array","items":ID,"minItems":1,"maxItems":1000,"uniqueItems":True},"events":{"type":"array","items":EVENT,"minItems":1,"maxItems":512}},("carrier_id","note_ids","events"))}}, ("session","revision","dry_run","groups")), destructive=True),
]
BY_NAME = {tool["name"]: tool for tool in TOOLS}
for name in ("inspect_motion", "preview_passage"):
    BY_NAME[name]["annotations"]["idempotentHint"] = False
MUSIC_FIRST_INSTRUCTIONS = (
    "Please get a full grasp of the entire piece before starting charting. "
    "Listen to and understand the whole song: its structure, emotional arc, recurring motifs, "
    "instrumentation, transitions, climaxes and resolution. Use the music MCP when available; "
    "cover the complete audio in overlapping passages and synthesize a whole-piece understanding "
    "before placing notes or designing motion. Do not infer the whole piece from a short excerpt. "
    "If full-song listening is unavailable or uncertain, state the gap rather than claiming understanding. "
)
INSTRUCTIONS = MUSIC_FIRST_INSTRUCTIONS + (
    "Use the native PhiChain runtime (GUI or headless) as the only chart state. Start with editor_status. Use create_project to import music into a new project, poll status, then open_project and poll again. Once open, use get_context, then read_section for relevant beats. "
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
    if kind == "string" and isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise ValueError(f"{path} is too short")
        if len(value) > schema.get("maxLength", sys.maxsize):
            raise ValueError(f"{path} is too long")
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
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            raise ValueError(f"{path} must contain unique values")
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
    limit = 16 * MAX_MESSAGE if name == "authoring_commit" else MAX_MESSAGE
    if len(payload) > limit:
        raise ValueError("Editor request exceeds bridge byte limit")
    with socket.create_connection(("127.0.0.1", port), timeout=12) as connection:
        connection.sendall(payload)
        with connection.makefile("rb") as reader:
            response = reader.readline(16 * MAX_MESSAGE + 1)
    if not response or len(response) > 16 * MAX_MESSAGE:
        raise ValueError("Missing or oversized editor response; re-read state before retrying edits")
    return json.loads(response)


class Server:
    def __init__(self, endpoint, renderer=None, catalog=None, executor=None, instructions=None):
        self.endpoint = endpoint
        self.renderer = renderer
        self.initialized = False
        self.tools = TOOLS if catalog is None else catalog
        self.by_name = {tool["name"]: tool for tool in self.tools}
        self.executor = executor
        self.instructions = INSTRUCTIONS if instructions is None else instructions

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
                      "serverInfo": {"name": "phichain", "version": "0.5.0"},
                      "instructions": self.instructions}
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return self.error(request_id, -32000, "Initialize the MCP server first")
        elif method == "tools/list":
            result = {"tools": self.tools}
        elif method == "tools/call":
            name = params.get("name")
            if not isinstance(name, str) or name not in self.by_name:
                return self.error(request_id, -32602, "Unknown tool")
            arguments = params.get("arguments", {})
            try:
                validate(arguments, self.by_name[name]["inputSchema"])
                images = []
                if self.executor is not None and name not in BY_NAME:
                    data = self.executor(name, arguments)
                elif name == "inspect_motion":
                    data, images = motion.inspect(lambda method, args: call_editor(self.endpoint, method, args), arguments, self.renderer)
                elif name == "preview_passage":
                    data = motion.preview_passage(lambda method, args: call_editor(self.endpoint, method, args), arguments, self.renderer)
                else:
                    data = call_editor(self.endpoint, name, arguments)
                is_error = isinstance(data, dict) and "error" in data
                result = {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                          "isError": is_error}
                if not is_error:
                    result["structuredContent"] = data
                    for frame, image in zip(data.get("frames", []), images):
                        result["content"].extend([{"type":"text","text":f"Frame at {frame['time_seconds']:.4f}s audio; note/carrier IDs and pixel positions are in structuredContent."}, image])
            except (OSError, ValueError, TypeError, KeyError, OverflowError, ZeroDivisionError) as error:
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
    parser.add_argument("--renderer", help="Absolute phichain-renderer executable for inspect_motion")
    options = parser.parse_args()
    server = Server(options.endpoint, options.renderer)
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
