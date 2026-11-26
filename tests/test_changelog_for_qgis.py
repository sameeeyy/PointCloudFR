"""Tests for scripts/changelog_for_qgis.py (plain-text changelog for QGIS)."""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "changelog_for_qgis.py"
_spec = importlib.util.spec_from_file_location("changelog_for_qgis", _SCRIPT)
changelog_for_qgis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(changelog_for_qgis)
to_plain = changelog_for_qgis.to_plain


def test_strips_markdown_from_bullets():
    md = "* **Proxy**: uses `requests` ([#56](https://github.com/x/y/issues/56))."
    assert to_plain(md) == "- Proxy: uses requests (#56)."


def test_section_title_becomes_plain_label():
    assert (
        to_plain("**🚀 Highlights & Improvements**") == "🚀 Highlights & Improvements:"
    )


def test_nested_bullets_keep_indentation():
    assert to_plain("  * **Sub**: item") == "  - Sub: item"


def test_version_headings_untouched():
    md = "# Changelog\n\n## [2.3.2] - 2026-11-14\n"
    assert to_plain(md) == md


def test_numbered_list_and_plain_text_unchanged():
    md = "1. Download the `x.zip` asset.\nPlain line."
    assert to_plain(md) == "1. Download the x.zip asset.\nPlain line."


def test_output_still_parsed_by_qgis_plugin_ci_regexp():
    """The version headings must survive so qgis-plugin-ci can split entries."""
    import re

    regexp = r"(?<=##)\s*\[*(v?0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\]?"
    md = "## [2.3.2] - 2026-11-14\n\n**Fixes**\n\n* **A**: b\n"
    assert re.search(regexp, to_plain(md))
