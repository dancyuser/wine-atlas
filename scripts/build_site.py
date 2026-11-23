#!/usr/bin/env python3
"""Create an allowlisted GitHub Pages artifact: no source, archives or caches."""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = (
    "index.html",
    "app.js",
    "styles.css",
    "editorial.css",
    "responsive.css",
    "data/wines.json",
    "data/ratings.json",
    "data/verified-snapshot-2026-11-23.json",
    "data/researched-photos-2026-11-23.json",
)


def build_site(output: Path):
    if output.is_symlink():
        raise ValueError("Refusing symlink output")
    output = output.resolve()
    if output == ROOT.resolve() or output in ROOT.resolve().parents:
        raise ValueError("The public output may not overwrite repository root or ancestors")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for relative in PUBLIC:
        source = ROOT / relative
        if not source.is_file() or source.is_symlink():
            raise ValueError("Missing or unsafe publication input: " + relative)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    (output / ".nojekyll").touch()
    return len(PUBLIC)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    print("PAGES_PUBLIC_FILES", build_site(args.output))


if __name__ == "__main__":
    main()
