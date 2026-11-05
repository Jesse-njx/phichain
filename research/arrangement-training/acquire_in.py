"""Acquire immutable, original IN charts from the downloader's public upstream."""
import collections
import datetime
import hashlib
import json
import pathlib
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
REPO = "7aGiven/Phigros_Resource"
API = "https://api.github.com/repos/" + REPO


def request(url):
    for attempt in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(
                url, headers={"User-Agent": "PhiChain-IN-corpus-research"}), timeout=60)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
            time.sleep(min(30, int(exc.headers.get("Retry-After", 2 ** (attempt + 1)))))


def get_json(url):
    with request(url) as response:
        return json.load(response)


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    provenance = ROOT / "provenance"
    provenance.mkdir(exist_ok=True)
    lock_path = provenance / "source-lock.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text())
    else:
        lock = {"repository": REPO, "acquired_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        for branch in ("chart", "info"):
            commit = get_json(API + "/commits/" + branch)
            lock[branch] = {"commit": commit["sha"], "tree": commit["commit"]["tree"]["sha"],
                            "commit_date": commit["commit"]["committer"]["date"]}
        save_json(lock_path, lock)
    tree_path = provenance / "chart-tree.json"
    if tree_path.exists():
        tree = json.loads(tree_path.read_text())
    else:
        tree = get_json(API + "/git/trees/" + lock["chart"]["tree"] + "?recursive=1")
        save_json(tree_path, tree)
    assert not tree.get("truncated"), "Incomplete source inventory"
    source_inventory = {entry["path"]: entry for entry in tree["tree"]
                        if entry["type"] == "blob" and entry["path"].endswith("/IN.json")}
    exclusion_path = provenance / "excluded-charts.json"
    exclusions = json.loads(exclusion_path.read_text()) if exclusion_path.exists() else []
    excluded_paths = {entry["source_path"] for entry in exclusions}
    assert excluded_paths <= source_inventory.keys(), "Unknown excluded source paths"
    expected = {path: entry for path, entry in source_inventory.items() if path not in excluded_paths}
    for name in ("info.tsv", "difficulty.tsv", "version.txt"):
        destination = provenance / name
        if not destination.exists():
            with request(f'https://raw.githubusercontent.com/{REPO}/{lock["info"]["commit"]}/{name}') as response:
                destination.write_bytes(response.read())
    catalog = {parts[0]: parts for line in (provenance / "info.tsv").read_text().splitlines()
               if (parts := line.split("\t")) and len(parts) >= 2}
    difficulties = {parts[0]: parts for line in (provenance / "difficulty.tsv").read_text().splitlines()
                    if (parts := line.split("\t")) and len(parts) >= 2}
    archive_url = f'https://codeload.github.com/{REPO}/tar.gz/{lock["chart"]["commit"]}'
    archive = ROOT / "source-chart-snapshot.tar.gz"
    if not archive.exists():
        partial = archive.with_suffix(".gz.partial")
        count = 0
        last_report = time.monotonic()
        print("Downloading compressed chart snapshot", lock["chart"]["commit"], flush=True)
        with request(archive_url) as response, partial.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                count += len(chunk)
                if time.monotonic() - last_report > 15:
                    print("Archive received MiB:", round(count / 1024**2, 1), flush=True)
                    last_report = time.monotonic()
        partial.rename(archive)
    archive_hash = hashlib.sha256()
    with archive.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            archive_hash.update(chunk)
    records = []
    seen = set()
    print("Validating and extracting", len(expected), "IN charts", flush=True)
    with tarfile.open(archive, "r|gz") as source:
        for member in source:
            pieces = pathlib.PurePosixPath(member.name).parts
            relative = "/".join(pieces[1:])
            if not member.isfile() or relative not in expected:
                continue
            assert relative not in seen, "Duplicate archive entry"
            assert ".." not in pieces and not pathlib.PurePosixPath(relative).is_absolute()
            raw = source.extractfile(member).read()
            entry = expected[relative]
            assert len(raw) == entry["size"], relative
            blob_hash = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            assert blob_hash == entry["sha"], "Git blob mismatch: " + relative
            chart = json.loads(raw)
            assert isinstance(chart.get("judgeLineList"), list), relative
            counts = collections.Counter()
            actual_notes = 0
            for line in chart["judgeLineList"]:
                for side in ("notesAbove", "notesBelow"):
                    for note in line.get(side, []):
                        assert all(key in note for key in ("type", "time", "positionX", "holdTime")), relative
                        counts[str(note["type"])] += 1
                        actual_notes += 1
            destination = ROOT / "raw" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                assert hashlib.sha256(destination.read_bytes()).digest() == hashlib.sha256(raw).digest(), "Existing file differs"
            else:
                destination.write_bytes(raw)
            folder = pieces[-2]
            song_id = folder.rsplit(".", 1)[0]
            metadata = catalog.get(song_id, [])
            levels = difficulties.get(song_id, [])
            records.append({"source_path": relative, "local_path": str(destination.relative_to(ROOT)),
                            "song_id": song_id, "title": metadata[1] if len(metadata) > 1 else None,
                            "difficulty": "IN", "constant": levels[3] if len(levels) > 3 else None,
                            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(), "git_blob_sha1": blob_hash,
                            "format_version": chart.get("formatVersion"), "note_count": actual_notes,
                            "declared_note_count": chart.get("numOfNotes"), "note_types": dict(counts),
                            "judge_line_count": len(chart["judgeLineList"]),
                            "source_url": f'https://raw.githubusercontent.com/{REPO}/{lock["chart"]["commit"]}/' + urllib.parse.quote(relative)})
            seen.add(relative)
            if len(records) % 25 == 0:
                print("Verified IN charts:", len(records), flush=True)
    assert seen == set(expected), "Archive missing IN files: " + repr(set(expected) - seen)
    records.sort(key=lambda row: row["source_path"])
    expected_catalog = {song_id for song_id, values in difficulties.items()
                        if len(values) > 3 and values[3].strip() and float(values[3]) > 0}
    actual_ids = {record["song_id"] for record in records}
    summary = {"source": lock, "game_version": (provenance / "version.txt").read_text().strip(),
               "archive_url": archive_url, "archive_sha256": archive_hash.hexdigest(), "archive_bytes": archive.stat().st_size,
               "source_IN_file_count": len(source_inventory), "excluded_source_paths": sorted(excluded_paths),
               "chart_count": len(records), "note_count": sum(r["note_count"] for r in records),
               "raw_bytes": sum(r["bytes"] for r in records),
               "note_types": dict(sum((collections.Counter(r["note_types"]) for r in records), collections.Counter())),
               "format_versions": dict(collections.Counter(str(r["format_version"]) for r in records)),
               "missing_from_archive": sorted(set(expected) - seen),
               "catalog_IN_missing_from_chart_branch": sorted(expected_catalog - actual_ids),
               "chart_IN_not_in_difficulty_catalog": sorted(actual_ids - expected_catalog),
               "declared_count_missing": sum(r["declared_note_count"] is None for r in records),
               "declared_count_mismatches": [r["source_path"] for r in records
                                             if r["declared_note_count"] is not None and r["note_count"] != r["declared_note_count"]],
               "preprocessing_applied": False, "AT_extracted": False}
    save_json(ROOT / "manifest.json", records)
    save_json(ROOT / "summary.json", summary)
    # The transport archive includes other difficulties; retain only the requested originals.
    archive.unlink()
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
