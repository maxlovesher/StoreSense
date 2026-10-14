"""
Assemble the single project report from the section files.

Owner: Member 6 (Dashboard & Integration)

Joins reports/sections/00_*.md ... 07_*.md, in file-name order, into one file,
reports/StoreSense_report.md, with a title block and a table of contents. The
sections link to their charts as ../figures/x.png; in the assembled file (one
folder higher) the links become figures/x.png, so the images still show.

To make a Word or PDF file from the result (needs pandoc installed):
    pandoc reports/StoreSense_report.md -o reports/StoreSense_report.docx --resource-path=reports

Run from the project root:
    python reports/build_report.py
"""
import re
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent
SECTIONS_DIR = REPORTS_DIR / "sections"
OUTPUT = REPORTS_DIR / "StoreSense_report.md"

TITLE = "StoreSense: Retail Data Warehouse and Market Basket Analysis"
SUBTITLE = "DMDW (Data Mining & Data Warehousing) course project, KIIT"


def section_files(sections_dir: Path = SECTIONS_DIR) -> list[Path]:
    """The section files in report order (their names start with 00, 01, ...)."""
    return sorted(p for p in sections_dir.glob("[0-9][0-9]_*.md"))


def rewrite_image_links(text: str) -> str:
    """../figures/x.png (from reports/sections/) becomes figures/x.png (from reports/)."""
    return text.replace("](../figures/", "](figures/")


def heading(text: str) -> str:
    """The first '# ' line of a section."""
    match = re.search(r"^# (.+)$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else "(untitled)"


def anchor(title: str) -> str:
    """The link target GitHub makes for a heading: lower case, punctuation removed, spaces to hyphens."""
    slug = re.sub(r"[^\w\s-]", "", title.lower())
    return re.sub(r"\s", "-", slug.strip())


def image_targets(text: str) -> list[str]:
    """Every image path a markdown text uses, as written."""
    return re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text)


def build(sections_dir: Path = SECTIONS_DIR) -> str:
    texts = [p.read_text(encoding="utf-8").strip() for p in section_files(sections_dir)]
    toc = "\n".join(f"{i}. [{heading(t)}](#{anchor(heading(t))})" for i, t in enumerate(texts, start=1))
    body = "\n\n---\n\n".join(rewrite_image_links(t) for t in texts)
    return f"# {TITLE}\n\n*{SUBTITLE}*\n\n## Contents\n\n{toc}\n\n---\n\n{body}\n"


def main() -> None:
    report = build()
    OUTPUT.write_text(report, encoding="utf-8")
    missing = [img for img in image_targets(report) if not (REPORTS_DIR / img).exists()]
    print(f"{len(section_files())} sections, {len(report.split()):,} words -> {OUTPUT}")
    if missing:
        print("images that do not exist: " + ", ".join(missing))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
