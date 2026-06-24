from __future__ import annotations

import os

os.environ.setdefault("BUDGET_TRACKER_DB", "/tmp/budget_tracker_demo.db")
os.environ.setdefault("BUDGET_TRACKER_SEED", "demo_seed.db")

from app import create_app

app = create_app()
