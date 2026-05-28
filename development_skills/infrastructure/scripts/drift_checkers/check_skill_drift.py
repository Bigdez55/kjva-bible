#!/usr/bin/env python3
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
fail = 0
for s in (ROOT/"platform/sdlc/13_skills/active").glob("*.yaml"):
    if subprocess.call(["python3", str(ROOT/"infrastructure/scripts/skill_evaluators/evaluate_skill.py"), str(s)]) != 0:
        fail += 1
sys.exit(1 if fail else 0)
