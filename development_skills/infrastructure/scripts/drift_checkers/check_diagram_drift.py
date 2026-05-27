#!/usr/bin/env python3
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.exit(subprocess.call(["python3", str(ROOT/"infrastructure/scripts/diagram_generators/generate_mermaid_atlas.py")]))
