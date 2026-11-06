"""Own both local process groups; stop siblings on exit and reap stubborn children."""
import os,signal,subprocess,time
from pathlib import Path

root=Path(__file__).resolve().parents[1]
children=[];stopping=False

def stop(signum=None,frame=None):
    global stopping
    stopping=True

signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
try:
    children.append(subprocess.Popen([str(root/'.venv/bin/python'),'-m','uvicorn','parallax.api:app','--host','127.0.0.1','--port','8000','--timeout-graceful-shutdown','5'],cwd=root,start_new_session=True))
    children.append(subprocess.Popen(['npm','run','dev','--','--host','127.0.0.1'],cwd=root/'dashboard',start_new_session=True))
    while not stopping and all(p.poll() is None for p in children):time.sleep(.25)
finally:
    for p in children:
        try:os.killpg(p.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    deadline=time.monotonic()+8
    for p in children:
        try:p.wait(timeout=max(.1,deadline-time.monotonic()))
        except subprocess.TimeoutExpired:
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait()
