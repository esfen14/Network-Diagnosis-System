"""Fail when a relative markdown link in AGENTS.md, README.md, spec files/, docs/ or server/tests/ is broken."""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def main(root):
    root = Path(root)
    files = [root / "AGENTS.md", root / "README.md"]
    files.extend(sorted((root / "spec files").glob("*.md")))
    files.extend(sorted((root / "docs").rglob("*.md")))
    files.extend(sorted((root / "server" / "tests").rglob("*.md")))
    broken = []
    for doc in files:
        for target in LINK.findall(doc.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path = unquote(target.split("#")[0])
            if path and not (doc.parent / path).exists():
                broken.append(f"{doc.relative_to(root)} -> {target}")
    if broken:
        print("Broken relative links:")
        for line in broken:
            print("  " + line)
        return 1
    print(f"{len(files)} documents, all relative links resolve")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
