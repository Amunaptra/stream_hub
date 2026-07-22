from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_SOURCE = ROOT / "device" / "agent"
HUB_SOURCE = ROOT / "hub" / "backend"
sys.path.insert(0, str(AGENT_SOURCE))
sys.path.insert(0, str(HUB_SOURCE))
