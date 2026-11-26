"""Rewrite CHANGELOG.md as plain text for the plugins.qgis.org changelog.

qgis-plugin-ci copies the last CHANGELOG entries verbatim into the
``changelog=`` field of metadata.txt, but QGIS (plugin manager and
plugins.qgis.org) shows that field as plain text: Markdown bold, links and
code spans would appear as raw ``**``, ``[..](..)`` and backticks.

CI runs this script on its checkout just before ``qgis-plugin-ci package`` /
``release`` (and after the GitHub release notes, which keep the Markdown).
The ``## [X.Y.Z] - YYYY-MM-DD`` headings are left untouched so that
qgis-plugin-ci can still parse the file.

Usage: python scripts/changelog_for_qgis.py [CHANGELOG.md]
"""

import re
import sys
from pathlib import Path

_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_BOLD = re.compile(r"(\*\*|__)(.+?)\1")
_CODE = re.compile(r"`([^`]*)`")
_BULLET = re.compile(r"^(\s*)[*+]\s+")
_SECTION = re.compile(r"^(\s*)([^-\s].*?):?\s*$")


def to_plain_line(line: str) -> str:
    """Convert one Markdown line of a changelog entry to plain text."""
    if line.startswith("#"):
        return line  # version headings, needed by qgis-plugin-ci
    is_section = bool(re.fullmatch(r"\s*\*\*[^*]+\*\*\s*", line))
    line = _BULLET.sub(r"\1- ", line)
    line = _LINK.sub(r"\1", line)
    line = _BOLD.sub(r"\2", line)
    line = _CODE.sub(r"\1", line)
    if is_section:  # "**🚀 Highlights**" -> "🚀 Highlights:"
        line = _SECTION.sub(r"\1\2:", line)
    return line


def to_plain(markdown: str) -> str:
    """Convert a whole CHANGELOG.md content to plain text."""
    return "\n".join(to_plain_line(line) for line in markdown.split("\n"))


def main(argv: list[str]) -> int:
    path = Path(argv[1] if len(argv) > 1 else "CHANGELOG.md")
    content = path.read_text(encoding="utf-8")
    path.write_text(to_plain(content), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
