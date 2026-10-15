"""
Make the PDF (and Word file) of the submission report.

Turns reports/StoreSense_DMDW_Project_Report.md into
    reports/StoreSense_DMDW_Project_Report.pdf    A4, page numbers, Mermaid diagrams drawn
    reports/StoreSense_DMDW_Project_Report.docx   Mermaid diagrams stay as code (Word cannot draw them)

How: pandoc writes one HTML page (styles from reports/pdf/print.css, charts embedded),
reports/pdf/mermaid_header.html turns each ```mermaid block into a diagram, and a
headless Chrome or Edge prints the page to PDF.

Needs: pandoc, and Chrome or Edge. The Mermaid script loads from cdn.jsdelivr.net,
so the build needs an internet connection. Set STORESENSE_BROWSER to a browser's
path if it is not found. If PyMuPDF is installed (pip install pymupdf), the PDF is
checked for diagrams that failed to draw.

Run from the project root after editing the report (for example, filling in the placeholders):
    python reports/build_pdf.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent
PDF_DIR = REPORTS_DIR / "pdf"
SOURCE = REPORTS_DIR / "StoreSense_DMDW_Project_Report.md"
PDF_OUT = SOURCE.with_suffix(".pdf")
DOCX_OUT = SOURCE.with_suffix(".docx")

TITLE = "StoreSense: Retail Data Warehouse and Market Basket Analysis"
MARKDOWN = "markdown+tex_math_dollars+pipe_tables"
# The table of contents says to make page numbers in Word; a PDF has them already.
WORD_ONLY_NOTE = "*Page numbers are left out of this Markdown version"

BROWSER_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_browser() -> str:
    """Chrome or Edge: STORESENSE_BROWSER if set, else the PATH, else the usual install folders."""
    if os.environ.get("STORESENSE_BROWSER"):
        return os.environ["STORESENSE_BROWSER"]
    for name in ("chrome", "google-chrome", "chromium", "chromium-browser", "msedge"):
        if shutil.which(name):
            return shutil.which(name)
    for path in BROWSER_PATHS:
        if Path(path).exists():
            return path
    raise SystemExit("Chrome or Edge not found. Set STORESENSE_BROWSER to its path.")


def pdf_markdown(text: str) -> str:
    """The report without the Word-only note in the table of contents."""
    return "\n".join(line for line in text.split("\n") if not line.startswith(WORD_ONLY_NOTE))


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"{Path(cmd[0]).name} failed:\n{result.stderr.strip()}")


def build_html(md_path: Path, html_path: Path) -> None:
    run(["pandoc", str(md_path), "-f", MARKDOWN, "-t", "html5", "-s", "--mathml", "--embed-resources",
         f"--resource-path={REPORTS_DIR}", "--css", str(PDF_DIR / "print.css"),
         "--include-in-header", str(PDF_DIR / "mermaid_header.html"),
         "--metadata", f"title={TITLE}", "-o", str(html_path)])


def print_pdf(browser: str, html_path: Path, pdf_path: Path, profile_dir: Path) -> None:
    # A separate profile, so an open Chrome window does not take over the job.
    # The virtual-time budget gives the Mermaid script time to draw before printing.
    run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         "--run-all-compositor-stages-before-draw", "--virtual-time-budget=30000",
         f"--user-data-dir={profile_dir}", f"--print-to-pdf={pdf_path}", html_path.as_uri()])
    if not pdf_path.exists():
        raise SystemExit(f"{Path(browser).name} did not write a PDF.")


def build_docx() -> None:
    run(["pandoc", str(SOURCE), "-f", MARKDOWN, "-t", "docx", f"--resource-path={REPORTS_DIR}",
         "--toc", "--toc-depth=2", "-o", str(DOCX_OUT)])


def check_pdf() -> None:
    """Page count, and a failure if a diagram did not draw (needs PyMuPDF; skipped without it)."""
    try:
        import pymupdf
    except ImportError:
        print("PyMuPDF not installed: open the PDF and check that the diagrams in sections 6 and 12 are drawn.")
        return
    with pymupdf.open(PDF_OUT) as doc:
        text = "".join(page.get_text() for page in doc)
        print(f"{doc.page_count} pages")
    if "Mermaid error" in text or "Syntax error" in text:
        raise SystemExit("A Mermaid diagram did not draw: see the red message on page 1 of the PDF.")


def main() -> None:
    if shutil.which("pandoc") is None:
        raise SystemExit("pandoc not found. Install it from https://pandoc.org/installing.html")
    browser = find_browser()
    # ignore_cleanup_errors: on Windows the browser can still hold its profile files for a moment
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        md_path = tmp / "report.md"
        md_path.write_text(pdf_markdown(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")
        build_html(md_path, tmp / "report.html")
        print_pdf(browser, tmp / "report.html", tmp / "report.pdf", tmp / "browser-profile")
        shutil.move(tmp / "report.pdf", PDF_OUT)   # only replace the old PDF once the new one exists
    build_docx()
    print(f"-> {PDF_OUT}\n-> {DOCX_OUT}")
    check_pdf()


if __name__ == "__main__":
    sys.exit(main())
