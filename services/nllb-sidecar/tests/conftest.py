import os
import sys
from pathlib import Path

# Must be set before `app` is imported anywhere in the test session -- it
# decides at import time whether to spawn the (heavy) model-loading thread.
os.environ.setdefault("NLLB_DISABLE_MODEL_LOAD", "true")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
