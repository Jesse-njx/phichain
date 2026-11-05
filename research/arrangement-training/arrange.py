"""Generate candidate x arrangements from a trained, locally trusted checkpoint.

Input: {bpm, difficulty, notes:[{time,type,duration}], locked:{index:x}}.
This is a research inference CLI, not an editor bridge or a quality guarantee.
"""
import argparse
import json
import math
import pathlib
import torch
from masked_model import ArrangementTransformer, generate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('input', type=pathlib.Path)
    parser.add_argument('--checkpoint', type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent/'runs/masked-v1/best.pt')
    parser.add_argument('--output', type=pathlib.Path, required=True)
    parser.add_argument('--candidates', type=int, default=4)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--temperature', type=float, default=.9)
    args = parser.parse_args()
    request = json.loads(args.input.read_text())
    assert 0 < float(request['bpm']) and math.isfinite(float(request['bpm']))
    assert 16 <= len(request['notes']) <= 128, 'Expected 16-128 complete note events'
    assert 1 <= args.candidates <= 32 and .05 <= args.temperature <= 2
    notes = []
    for index, note in enumerate(request['notes']):
        t = float(note['time']); duration = float(note.get('duration',0)); kind = int(note['type'])
        assert math.isfinite(t) and math.isfinite(duration) and duration >= 0 and kind in (1,2,3,4)
        assert kind==3 or duration==0, 'Only Hold has nonzero duration'
        assert not notes or t>=notes[-1]['time'], 'Notes must be in chronological order'
        notes.append(dict(id=str(index),time=t,duration=duration,type=kind,x=.5))
    assert notes[-1]['time']-notes[0]['time'] <= 12, 'Maximum supported window is 12 seconds'
    assert all(n['time']+n['duration'] <= notes[-1]['time']+1e-5 for n in notes), 'Do not cut a Hold at the window boundary'
    locked = {int(i):float(x) for i,x in request.get('locked',{}).items()}
    assert all(0<=i<len(notes) and math.isfinite(x) and 0<=x<=1 for i,x in locked.items())
    difficulty=float(request.get('difficulty',14)); assert math.isfinite(difficulty)
    window=dict(notes=notes,bpm=float(request['bpm']),difficulty=difficulty)
    device='mps' if torch.backends.mps.is_available() else 'cpu'
    checkpoint=torch.load(args.checkpoint,map_location='cpu',weights_only=False)
    model=ArrangementTransformer(checkpoint['config']['model']).to(device)
    model.load_state_dict(checkpoint['model'])
    candidates=[]
    for index in range(args.candidates):
        x=generate(model,window,device,seed=args.seed+index,temperature=args.temperature,locked=locked)
        candidates.append([dict(time=n['time'],type=n['type'],duration=n['duration'],x=float(position)) for n,position in zip(notes,x)])
    result=dict(representation='single line, normalized x [0,1], time/duration in seconds',
                checkpoint_step=checkpoint['step'],candidates=candidates,
                limitations=['Candidate arrangements are not verified for two-finger playability or quality.',
                             'Timing, type and duration are fixed; only x is generated.',
                             'Locked x values are quantized to the model 128-position grid.'])
    assert args.output.resolve()!=args.input.resolve(), 'Output must not overwrite the request'
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Wrote',len(candidates),'candidates to',args.output)


if __name__=='__main__':
    main()
