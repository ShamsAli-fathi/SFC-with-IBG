import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IBG_DIR = ROOT / "IBG"

sys.path.insert(0, str(IBG_DIR))
os.environ.setdefault("MPLCONFIGDIR", "/tmp/ibg-matplotlib")
