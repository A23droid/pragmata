import sys
from pathlib import Path

# Automatically ensure project root is on sys.path so 'backend.*' imports resolve cleanly
_repo_root = str(Path(__file__).resolve().parent.parent.parent)
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
