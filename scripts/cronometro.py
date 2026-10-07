"""Roda um comando e grava "<segundos> <pico de memória em KB>" (o /usr/bin/time -f "%e %M" sem depender dele).
python scripts/cronometro.py <arquivo de saída> <comando> [args...]"""

import resource
import subprocess
import sys
import time

inicio = time.monotonic()
rc = subprocess.call(sys.argv[2:])
seg = time.monotonic() - inicio
kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
with open(sys.argv[1], "w") as f:
    f.write(f"{seg:.1f} {kb}\n")
sys.exit(rc)
