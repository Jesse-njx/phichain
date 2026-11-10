"""Offline, dependency-free report. No server, remote assets, or automatic opening."""
import html
import json
from pathlib import Path


def write_report(result, destination):
    payload = json.dumps(result, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace(
        ">", "\\u003e").replace("&", "\\u0026")
    title = html.escape(Path(result["source"]["path"]).stem)
    template = Path(__file__).with_name("report.html").read_text()
    destination.write_text(template.replace("__TITLE__", title).replace("__ANALYSIS_DATA__", payload))
