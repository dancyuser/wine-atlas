#!/usr/bin/env python3
"""Report actual published catalog gaps using the frontend's own rules."""
import argparse
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    cmd=['node',str(ROOT/'scripts/report_catalog_gaps.cjs')]
    if a.output:
        a.output.parent.mkdir(parents=True,exist_ok=True)
        cmd.append(str(a.output))
    subprocess.run(cmd,check=True)
