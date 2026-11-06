"""Prevent concurrent writers/collectors sharing a research directory (macOS/Linux)."""
import fcntl
from pathlib import Path

class InstanceLock:
    def __init__(self, root):
        root=Path(root);root.mkdir(parents=True,exist_ok=True)
        self.handle=(root/'.collector.lock').open('a')
        try:
            fcntl.flock(self.handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            raise RuntimeError(f'A collector already owns {root.resolve()}; stop it before starting another.') from None

    def close(self):
        self.handle.close()
