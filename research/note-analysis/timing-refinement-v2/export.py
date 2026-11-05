"""Export the validation-selected timing method without selecting gameplay notes."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parent
    selection=json.loads((root/'selection.json').read_text())
    winner=max(selection,key=lambda k:selection[k]['validation']['macro_coverage']['10'])
    events=json.loads((root/'events.json').read_text())
    sources={r['id']:r for r in json.loads((root/'protocol.json').read_text())['rows']}
    output=dict(schema_version=1,method=winner,selection_basis='Validation-only ±10ms chart-head coverage',
        scope='Fixed-budget acoustic candidates; not chosen gameplay notes. Intensity and source attribution are not estimated.',songs=[])
    for split,methods in events.items():
        for raw,corrected in zip(methods['raw'],methods[winner]):
            assert raw['id']==corrected['id'] and len(raw['times'])==len(corrected['times'])
            sid=raw['id']; token=hashlib.sha256(sid.encode()).hexdigest()[:12]
            source=sources[sid]
            output['songs'].append(dict(id=sid,split=split,audio=source['audio'],audio_sha256=source['audio_sha256'],
                events=[dict(id=f'{token}-{i:05d}',raw_time_seconds=a,time_seconds=b,
                             correction_ms=(b-a)*1000,evidence='Interpolated spectral-flux peak')
                        for i,(a,b) in enumerate(zip(raw['times'],corrected['times']))]))
    (root/'selected-events.json').write_text(json.dumps(output,ensure_ascii=False,indent=2))
    print(f"Exported {winner}: {len(output['songs'])} evaluated songs; stable candidate IDs, no chart edits.")


if __name__=='__main__':main()
