"""Full-song pretrained pitch transcription on time-aligned source estimates."""
from pathlib import Path
import json,hashlib,logging,os
os.environ.setdefault('NUMBA_CACHE_DIR','/private/tmp/phichain-music-numba')
logging.disable(logging.WARNING)
import numpy as np
import soundfile as sf
import onnxruntime as ort
ort.disable_telemetry_events()
from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import Model,predict

OUT=Path(__file__).resolve().parent


def main():
    a=json.loads((OUT/'alignment.json').read_text())
    source=Path(a['canonical_source'])
    assert hashlib.sha256(source.read_bytes()).hexdigest()==a['canonical_sha256']
    n=a['canonical_samples'];lag=a['stem_minus_pcm_samples'];sr=a['sample_rate']
    aligned=OUT/'aligned-stems';aligned.mkdir(exist_ok=True)
    for name,row in a['stems'].items():
        p=Path(row['path']);assert hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256']
        y,rate=sf.read(p,dtype='float32');assert rate==sr and len(y)>=n+lag
        sf.write(aligned/f'{name}.wav',y[lag:lag+n],sr,subtype='FLOAT')
    options=dict(onset_threshold=.5,frame_threshold=.3,minimum_note_length=75,melodia_trick=True)
    model=Model(ICASSP_2022_MODEL_PATH)
    manifest=dict(model='Spotify Basic Pitch 0.4.0 / ICASSP 2022 ONNX',
                  model_sha256=hashlib.sha256(Path(ICASSP_2022_MODEL_PATH).read_bytes()).hexdigest(),
                  audio_alignment=a,parameters=options,sources={})
    for name,limits in [('vocals',(90,1600)),('bass',(35,500)),('other',(65,2400))]:
        source=aligned/f'{name}.wav'; cache=OUT/f'{name}-transcription.json'
        if cache.exists():
            raw=json.loads(cache.read_text());assert raw['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
        else:
            print('TRANSCRIBE',name,flush=True)
            arrays,midi,notes=predict(source,model,minimum_frequency=limits[0],maximum_frequency=limits[1],**options)
            midi.write(str(OUT/f'{name}-transcription.mid'))
            np.savez_compressed(OUT/f'{name}-model-output.npz',**arrays)
            raw=dict(source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),frequency_limits_hz=limits,
                notes=[dict(id=f'{name}-raw-{i:05d}',start_seconds=float(s),end_seconds=float(e),midi_pitch=int(p),
                            activation=float(v)) for i,(s,e,p,v,bend) in enumerate(notes)])
            cache.write_text(json.dumps(raw,indent=2))
        manifest['sources'][name]=dict(notes=len(raw['notes']),source_sha256=raw['source_sha256'],frequency_limits_hz=limits)
        print('TRANSCRIBED',name,len(raw['notes']),flush=True)
    (OUT/'transcription-manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
