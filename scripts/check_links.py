"""Check that every relative Markdown link (and #anchor) in CLAUDE.md, docs/ and memory-bank/ resolves.

  python3 scripts/check_links.py        # exit 1 on broken links"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = [ROOT / "CLAUDE.md", *sorted((ROOT / "docs").rglob("*.md")), *sorted((ROOT / "memory-bank").rglob("*.md"))]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
HTML_ANCHOR = re.compile(r'<a id="([^"]+)"></a>')
FENCE = re.compile(r"```.*?```", re.DOTALL)


def slug(heading: str) -> str:
    """GitHub-style heading slug."""
    text = re.sub(r"[`*]", "", heading.strip().lower())
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    return {slug(h) for h in HEADING.findall(text)} | set(HTML_ANCHOR.findall(text))


def main() -> int:
    broken = []
    for source in FILES:
        text = FENCE.sub("", source.read_text(encoding="utf-8"))
        for target in LINK.findall(text):
            if re.match(r"^[a-z]+:", target):
                continue
            file_part, _, anchor = target.partition("#")
            resolved = (source.parent / file_part).resolve() if file_part else source
            if not resolved.exists():
                broken.append(f"{source.relative_to(ROOT)}: missing file {target}")
            elif anchor and resolved.suffix == ".md" and anchor not in anchors(resolved):
                broken.append(f"{source.relative_to(ROOT)}: missing anchor {target}")
    print("\n".join(broken) or f"OK: all links resolve in {len(FILES)} files")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
