import json
import math
from pathlib import Path
import struct
import sys
import wave
sys.path.insert(0, str(Path.cwd()/'tools/phichain-mcp'))
from music_server import Worker, DEFAULT_MODEL
path=Path.cwd()/'../runtime/music-smoke.wav'
with wave.open(str(path),'wb') as audio:
    audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(16000)
    samples=[]
    for i in range(16000*4):
        t=i/16000
        frequency=[261.63,329.63,392,523.25][int(t)]
        envelope=min(1,(t%1)*20)*max(0,1-(t%1))
        samples.append(struct.pack('<h',int(8000*envelope*math.sin(2*math.pi*frequency*t))))
    audio.writeframes(b''.join(samples))
worker=Worker(str(Path.cwd()/'../runtime/music-runtime/bin/python'),DEFAULT_MODEL,300)
try:
    result=worker.ask({'audio_path':str(path),'prompt':'Describe the sounds you actually hear in this short clip. Are vocals or drums present? Be brief.','max_tokens':128})
    print(json.dumps(result,indent=2))
    (Path.cwd()/'../runtime/music-smoke-result.json').write_text(json.dumps(result,indent=2)+'\n')
finally:
    worker.close()
