"""Independently check the retained files against the acquisition manifest."""
import collections
import hashlib
import json
import pathlib

root = pathlib.Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text())
expected = {row["local_path"] for row in manifest}
actual = {str(path.relative_to(root)) for path in (root / "raw").rglob("*") if path.is_file()}
assert actual == expected, {"missing": sorted(expected - actual), "extra": sorted(actual - expected)}
exclusion_path = root / "provenance" / "excluded-charts.json"
exclusions = json.loads(exclusion_path.read_text()) if exclusion_path.exists() else []
assert not ({row["source_path"] for row in manifest} & {row["source_path"] for row in exclusions})
song_groups = collections.defaultdict(list)
byte_groups = collections.defaultdict(list)
for row in manifest:
    path = root / row["local_path"]
    assert path.stat().st_size == row["bytes"], str(path)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    assert digest.hexdigest() == row["sha256"], str(path)
    song_groups[row["song_id"]].append(row["source_path"])
    byte_groups[row["sha256"]].append(row["source_path"])
result = {
    "verified_files": len(manifest),
    "unique_songs": len(song_groups),
    "intentionally_excluded_files": len(exclusions),
    "total_notes_including_variants": sum(row["note_count"] for row in manifest),
    "primary_variant_notes": sum(row["note_count"] for row in manifest if row["source_path"].endswith(".0/IN.json")),
    "multiple_variant_songs": {key: values for key, values in song_groups.items() if len(values) > 1},
    "byte_identical_groups": [values for values in byte_groups.values() if len(values) > 1],
    "unrequested_files": [],
    "missing_files": [],
    "all_sha256_match": True,
}
(root / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
print(json.dumps(result, ensure_ascii=False, indent=2))
