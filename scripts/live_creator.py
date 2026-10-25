"""Run the Creator (agent/creator.py) on files or folders from the terminal: prints its steps and token use, writes
the building and the remaining issues as JSON. Uses the real Claude API (ANTHROPIC_API_KEY in .env).

    uv run --env-file .env python scripts/live_creator.py <file|folder>... [--out building.json] [--images DIR]
"""

import argparse
import base64
import json
import time
from pathlib import Path

from agent.creator import Creator
from agent.creator_tools import ImportSession
from core.plan_import.ingest import load_sources

SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".heic", ".heif", ".webp", ".tif", ".tiff", ".bmp"}


def files_of(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for path in map(Path, paths):
        found += sorted(p for p in path.rglob("*") if p.suffix.lower() in SUFFIXES) if path.is_dir() else [path]
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--out", default="building.json")
    parser.add_argument("--images", help="save every image the model was shown here")
    args = parser.parse_args()

    files = files_of(args.paths)
    sources, warnings = load_sources([(file.name, file.read_bytes()) for file in files])
    print(f"{len(sources)} sources from {len(files)} files; warnings: {warnings}")
    creator = Creator(ImportSession(sources, warnings))
    started = time.monotonic()
    shown = 0
    call = creator.tools.call

    def call_and_keep(name: str, arguments: dict) -> list[dict]:
        nonlocal shown
        blocks = call(name, arguments)
        if args.images:
            Path(args.images).mkdir(parents=True, exist_ok=True)
            for block in blocks:
                if block["type"] == "image":
                    shown += 1
                    (Path(args.images) / f"{shown:03d}-{name}.png").write_bytes(base64.b64decode(block["source"]["data"]))
        return blocks

    creator.tools.call = call_and_keep

    def show(step: dict) -> None:
        elapsed = f"{time.monotonic() - started:6.1f}s"
        if step["kind"] == "say":
            print(f"{elapsed}  » {step['text']}", flush=True)
        elif step["kind"] == "tool":
            print(f"{elapsed}    {step['name']}" + (f" (level {step['level']})" if "level" in step else ""), flush=True)
        elif step["kind"] == "tool_done" and not step["ok"]:
            print(f"{elapsed}    ✗ {step['name']} failed", flush=True)

    creator.on_step = show
    result = creator.run()
    usage = result.usage
    print(f"\n{result.status} in {time.monotonic() - started:.0f}s · {usage.requests} requests · in {usage.input_tokens} "
          f"(cache read {usage.cache_read_input_tokens}, write {usage.cache_creation_input_tokens}) · out "
          f"{usage.output_tokens}")
    if result.building is not None:
        Path(args.out).write_text(json.dumps(result.building, indent=1, ensure_ascii=False), encoding="utf-8")
        errors = [issue for issue in result.issues if issue["severity"] == "error"]
        print(f"wrote {args.out}: {len(result.building['floors'])} floors, {len(result.building['spaces'])} spaces, "
              f"{len(result.building['openings'])} openings, {len(result.building['vertical_connectors'])} connectors; "
              f"{len(errors)} errors")
        for issue in errors[:15]:
            print("  -", issue["message"])
    else:
        print(result.reason)


if __name__ == "__main__":
    main()
