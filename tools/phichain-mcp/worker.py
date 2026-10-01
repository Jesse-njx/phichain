"""Detached worker; job manifests survive adapter/client restarts."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from local_tools import publish

def execute(path):
    path=Path(path);job=json.loads(path.read_text());started=time.time()
    def save():
        staging=path.with_suffix('.tmp');staging.write_text(json.dumps(job),encoding='utf-8');staging.replace(path)
    job.update(state='running',started_at=started);save()
    log=path.parent/'process.log'
    try:
        for index,argv in enumerate(job['commands']):
            job['stage']=index+1;job['stages']=len(job['commands']);save()
            with log.open('ab') as output:
                process=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=output,stderr=output)
                job['process_pid']=process.pid;save()
                try:code=process.wait(timeout=1800)
                except subprocess.TimeoutExpired:
                    process.kill();process.wait();raise ValueError('Job exceeded 30 minute limit')
            if code:raise ValueError(f'Command exited with code {code}: '+log.read_bytes()[-3000:].decode(errors='replace'))
        # All commands end with an output filename; renderer uses -o instead.
        final=job['commands'][-1]
        if '-o' in final:result=final[final.index('-o')+1]
        elif '--to' in final:result=final[2] # converter input output --from ...
        else:result=final[-1]
        publish(result,job['output_path'])
        job.update(state='completed',bytes=Path(job['output_path']).stat().st_size)
    except Exception as e:job.update(state='failed',error=str(e))
    finally:
        job.update(finished_at=time.time(),elapsed_seconds=time.time()-started);save()
        if job.get('snapshot_dir'):shutil.rmtree(job['snapshot_dir'],ignore_errors=True)

if __name__=='__main__':execute(sys.argv[1])
