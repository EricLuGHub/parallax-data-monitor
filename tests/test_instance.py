import pytest
from parallax.instance import InstanceLock

def test_duplicate_collector_rejected_and_lock_released(tmp_path):
    first=InstanceLock(tmp_path)
    try:
        with pytest.raises(RuntimeError,match='already owns'):
            InstanceLock(tmp_path)
    finally:
        first.close()
    second=InstanceLock(tmp_path)
    second.close()
