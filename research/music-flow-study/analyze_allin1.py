"""Run upstream pretrained All-In-One on complete songs; retain evidence."""
from pathlib import Path
import os,json,time,logging
ROOT=Path(__file__).resolve().parent
os.environ['TORCH_HOME']=str(ROOT/'model-cache/torch')
os.environ['HF_HOME']=str(ROOT/'model-cache/huggingface')
os.environ['MPLCONFIGDIR']=str(ROOT/'mpl-cache')
os.environ['NUMBA_CACHE_DIR']=str(ROOT/'numba-cache')
os.environ['PYTORCH_ENABLE_MPS_FALLBACK']='1'
import torch,allin1
from allin1.demix import demix
from analyze_librosa import SONGS
torch.set_num_threads(4)
logging.getLogger('natten.functional').setLevel(logging.ERROR)
if __name__=='__main__':
 for title,filename,index,gaps in [SONGS[-1],*SONGS[:-1]]:
  path=Path(filename) if filename.startswith('/') else ROOT/'audio'/filename
  print('START',title,flush=True);started=time.time()
  demix([path],ROOT/'demix','mps' if torch.backends.mps.is_available() else 'cpu')
  result=allin1.analyze(path,out_dir=ROOT/'allin1',model='harmonix-fold0',device='cpu',keep_byproducts=True,demix_dir=ROOT/'demix',spec_dir=ROOT/'spectrograms',multiprocess=False,include_activations=True)
  print('DONE',title,'elapsed',time.time()-started,'bpm',result.bpm,'segments',result.segments,flush=True)
