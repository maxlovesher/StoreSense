"""
Tests for the report assembly (reports/build_report.py).

The first tests use two tiny made-up section files. The last ones check the real
report: all eight sections are there, every chart it uses exists, and the
committed StoreSense_report.md is up to date with the sections.
"""
import pytest

from reports import build_report as br


@pytest.fixture
def sections(tmp_path):
    (tmp_path / "02_second.md").write_text("# 2. Second\n\n![chart](../figures/b.png)\n", encoding="utf-8")
    (tmp_path / "01_first.md").write_text("# 1. First\n\nText with ![a](../figures/a.png) in it.\n", encoding="utf-8")
    (tmp_path / "notes.md").write_text("# not a section\n", encoding="utf-8")   # no number: left out
    return tmp_path


def test_sections_are_taken_in_number_order_and_unnumbered_files_are_left_out(sections):
    assert [p.name for p in br.section_files(sections)] == ["01_first.md", "02_second.md"]


def test_assembled_report_has_toc_in_order_and_separators(sections):
    out = br.build(sections)
    assert out.startswith(f"# {br.TITLE}")
    assert "1. [1. First](#1-first)" in out and "2. [2. Second](#2-second)" in out
    assert out.index("# 1. First") < out.index("# 2. Second")
    assert "not a section" not in out
    assert out.count("\n---\n") == 2   # one after the contents, one between the two sections


def test_image_links_are_rewritten_for_the_folder_one_level_up(sections):
    out = br.build(sections)
    assert "](figures/a.png)" in out and "](figures/b.png)" in out
    assert "../figures" not in out


def test_heading_and_anchor():
    assert br.heading("intro\n# 3. Association rules\ntext") == "3. Association rules"
    assert br.anchor("3. Association rules") == "3-association-rules"
    assert br.anchor("7. Insights, limitations and future work") == "7-insights-limitations-and-future-work"


def test_image_targets():
    assert br.image_targets("![x](figures/a.png) and ![y](figures/b.png)") == ["figures/a.png", "figures/b.png"]


def test_the_real_report_has_all_eight_sections_in_order():
    names = [p.name for p in br.section_files()]
    assert [n[:2] for n in names] == ["00", "01", "02", "03", "04", "05", "06", "07"]
    headings = [br.heading(p.read_text(encoding="utf-8")) for p in br.section_files()]
    assert [h.split(".")[0] for h in headings[1:]] == ["1", "2", "3", "4", "5", "6", "7"]


def test_every_chart_the_real_report_uses_exists():
    report = br.build()
    images = br.image_targets(report)
    assert len(images) >= 8
    missing = [img for img in images if not (br.REPORTS_DIR / img).exists()]
    assert not missing, missing


def test_the_committed_report_is_up_to_date():
    """If this fails, a section changed: run `python reports/build_report.py` and commit the result."""
    assert br.OUTPUT.read_text(encoding="utf-8") == br.build()
