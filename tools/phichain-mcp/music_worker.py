#!/usr/bin/env python3
"""Private JSON-lines inference worker. stdout is reserved for protocol messages."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    args = parser.parse_args()
    # Redirect even native-library stdout so model loading cannot corrupt MCP/worker JSON.
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), 'w', buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    model = None
    for line in sys.stdin:
        try:
            request = json.loads(line)
            with contextlib.redirect_stdout(sys.stderr):
                import mlx.core as mx
                from mlx_audio.stt import load
                if model is None:
                    model = load(args.model, strict=True)
                mx.reset_peak_memory()
                result = model.generate(request['audio_path'], prompt=request['prompt'],
                    max_tokens=request['max_tokens'], temperature=0.0,
                    prefill_step_size=512, strip_thinking=True, verbose=False)
                response = {'answer':result.text, 'model':str(Path(args.model).resolve()),
                    'backend':'mlx-audio', 'generation_tokens':result.generation_tokens,
                    'output_may_be_truncated':result.generation_tokens >= request['max_tokens'],
                    'prompt_tokens':result.prompt_tokens,
                    'mlx_peak_memory_bytes':mx.get_peak_memory()}
                mx.clear_cache()
        except Exception as error:
            response = {'error':f'{type(error).__name__}: {error}. Verify the local MLX runtime and model installation.'}
        protocol.write(json.dumps(response, ensure_ascii=False) + '\n')
        protocol.flush()


if __name__ == '__main__':
    main()
