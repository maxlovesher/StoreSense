"""
Typeset the submission report as a PDF (and export a Word copy).

Turns reports/StoreSense_DMDW_Project_Report.md into
    reports/StoreSense_DMDW_Project_Report.pdf    designed A4 layout: cover, part pages, chapter
                                                   openers, contents and lists with page numbers
    reports/StoreSense_DMDW_Project_Report.docx   plain Word export (Mermaid diagrams stay as code)

How it works:
  1. The Markdown body goes through pandoc to HTML. The cover, contents and lists of figures and
     tables are built here, so the Markdown's own title page and contents sections are skipped.
  2. The HTML is reshaped with BeautifulSoup: chapters and part pages, numbered table and figure
     captions, evidence tags such as [Git], reference list layout.
  3. Each ```mermaid block is drawn once in a headless browser and cached as an SVG in
     reports/pdf/diagrams/ (named by a hash of its source), so later builds reuse it.
  4. Chrome or Edge prints the page twice: the first PDF tells where every heading, figure and
     table landed, and the second fills those page numbers into the contents.
Styles are in reports/pdf/report.css.

Needs: pandoc, Chrome or Edge, beautifulsoup4 and pymupdf (both in requirements.txt). Fonts load
from Google Fonts and Mermaid from cdn.jsdelivr.net, so a new diagram or the intended fonts need an
internet connection (without it, cached diagrams still work and the fonts fall back to Cambria and
Segoe UI). Set STORESENSE_BROWSER to the browser's path if it is not found.

Run from the project root:
    python reports/build_pdf.py
"""
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pymupdf
from bs4 import BeautifulSoup, NavigableString

REPORTS_DIR = Path(__file__).resolve().parent
PDF_DIR = REPORTS_DIR / "pdf"
DIAGRAM_DIR = PDF_DIR / "diagrams"
CSS = PDF_DIR / "report.css"
SOURCE = REPORTS_DIR / "StoreSense_DMDW_Project_Report.md"
PDF_OUT = SOURCE.with_suffix(".pdf")
DOCX_OUT = SOURCE.with_suffix(".docx")

FONTS_URL = ("https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;"
             "0,8..60,700;1,8..60,400&family=Source+Sans+3:wght@400;600;700&family=JetBrains+Mono:wght@400;600"
             "&display=block")
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
MARKDOWN = "markdown-implicit_figures+tex_math_dollars+pipe_tables"
# Sections of the Markdown that the PDF draws itself (cover, contents, lists).
SKIPPED = {"Title Page", "Table of Contents", "List of Figures", "List of Tables"}

BROWSER_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
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


def run(cmd: list[str], stdin: str | None = None) -> str:
    result = subprocess.run(cmd, input=stdin.encode("utf-8") if stdin is not None else None, capture_output=True)
    if result.returncode != 0:
        raise SystemExit(f"{Path(cmd[0]).name} failed:\n{result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout.decode("utf-8", "replace").replace("\r\n", "\n")   # pandoc writes CRLF on Windows


def browser_args(browser: str, profile: Path, budget_ms: int) -> list[str]:
    # A separate profile, so an open browser window does not take over the job; the virtual-time
    # budget lets fonts and scripts finish before the page is printed or dumped.
    return [browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            "--run-all-compositor-stages-before-draw", f"--virtual-time-budget={budget_ms}",
            f"--user-data-dir={profile}"]


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
def split_sections(md: str) -> list[tuple[str, str]]:
    """(heading, text) for every '# ' section, ignoring '#' lines inside code fences."""
    if md.startswith("---\n"):
        md = md[md.index("\n---\n", 4) + 5:]
    sections, title, lines, fenced = [], None, [], False
    for line in md.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("# "):
            if title is not None:
                sections.append((title, "\n".join(lines)))
            title, lines = line[2:].strip(), []
        lines.append(line)
    sections.append((title, "\n".join(lines)))
    return [(t, s) for t, s in sections if t is not None]


def document_title(md: str) -> tuple[str, str]:
    """('StoreSense', 'Retail Data Warehouse ...') from the YAML title."""
    title = re.search(r'^title:\s*"(.+)"\s*$', md, flags=re.M).group(1)
    name, _, subtitle = title.partition(": ")
    return name, subtitle


def mermaid_sources(md: str) -> list[str]:
    return re.findall(r"^```mermaid\n(.*?)^```", md, flags=re.M | re.S)


# ---------------------------------------------------------------------------
# Diagrams (drawn once, cached as SVG)
# ---------------------------------------------------------------------------
def diagram_key(source: str) -> str:
    return hashlib.sha1(source.strip().encode("utf-8")).hexdigest()[:12]


def draw_missing_diagrams(sources: list[str], browser: str, tmp: Path) -> None:
    missing = {diagram_key(s): s for s in sources if not (DIAGRAM_DIR / f"{diagram_key(s)}.svg").exists()}
    if not missing:
        return
    print(f"drawing {len(missing)} diagram(s) with Mermaid ...")
    # Each diagram is drawn on its own with an id we choose (dg-<hash>): Mermaid's own ids come from
    # the clock, which a headless browser freezes, so several diagrams would share one id.
    jobs = json.dumps(list(missing.items())).replace("</", "<\\/")
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="{FONTS_URL}"><script src="{MERMAID_URL}"></script></head>
<body>
<script>
(async () => {{
  await document.fonts.ready;
  const font = '"Source Sans 3", "Segoe UI", sans-serif';
  mermaid.initialize({{ startOnLoad: false, theme: 'neutral', securityLevel: 'loose', fontFamily: font,
    themeVariables: {{ fontFamily: font, fontSize: '14px' }},
    flowchart: {{ htmlLabels: true, useMaxWidth: false, curve: 'basis' }},
    er: {{ useMaxWidth: false }},
    sequence: {{ useMaxWidth: false, wrap: true, width: 120, actorMargin: 28, messageMargin: 28, boxMargin: 6 }} }});
  try {{
    for (const [key, source] of {jobs}) {{
      const {{ svg }} = await mermaid.render('dg-' + key, source);
      const holder = document.createElement('div');
      holder.id = 'd' + key;
      holder.innerHTML = svg;
      document.body.appendChild(holder);
    }}
    document.body.setAttribute('data-done', '1');
  }} catch (e) {{ document.body.setAttribute('data-error', (e && (e.message || e.str)) || String(e)); }}
}})();
</script></body></html>"""
    page_path = tmp / "diagrams.html"
    page_path.write_text(page, encoding="utf-8", newline="\n")
    dom = run(browser_args(browser, tmp / "profile-diagrams", 30000) + ["--dump-dom", page_path.as_uri()])
    body = re.search(r"<body([^>]*)>", dom).group(1)
    if 'data-done="1"' not in body:
        error = re.search(r'data-error="([^"]*)"', body)
        raise SystemExit(f"Mermaid could not draw a diagram: {html.unescape(error.group(1)) if error else 'no result'}")
    DIAGRAM_DIR.mkdir(parents=True, exist_ok=True)
    for key in missing:
        # cut the SVG out of the raw text, so the browser's casing (viewBox, foreignObject) is kept
        svg = re.search(rf'<div id="d{key}">(<svg.*?</svg>)</div>', dom, flags=re.S).group(1)
        (DIAGRAM_DIR / f"{key}.svg").write_text(svg, encoding="utf-8")


# ---------------------------------------------------------------------------
# HTML shaping
# ---------------------------------------------------------------------------
def first_element(tag):
    for child in tag.children:
        if isinstance(child, NavigableString) and not child.strip():
            continue
        return child
    return None


def is_visual(el) -> bool:
    if getattr(el, "name", None) == "div" and "diagram" in el.get("class", []):
        return True
    if getattr(el, "name", None) == "p":
        kids = [c for c in el.children if not (isinstance(c, NavigableString) and not c.strip())]
        return len(kids) == 1 and getattr(kids[0], "name", None) == "img"
    return False


def caption(soup, p, kind: str) -> tuple[object, list[tuple[str, str]]]:
    """A <figcaption> from a '**Figure 6.1 – Title** more text' paragraph, and its (number, title) pairs."""
    cap = soup.new_tag("figcaption")
    found, note = [], None
    for child in list(p.contents):
        m = None
        if getattr(child, "name", None) == "strong":
            m = re.match(rf"{kind} (\d+\.\d+)\s*[–-]\s*", child.get_text())
        if m:
            label = soup.new_tag("span", attrs={"class": "cap-label"})
            label.string = f"{kind} {m.group(1)}"
            cap.append(label)
            first = child.contents[0]
            first.replace_with(NavigableString(str(first)[m.end():]))
            found.append((m.group(1), child.decode_contents().strip().rstrip(".")))
            for node in list(child.contents):
                cap.append(node.extract())
            continue
        node = child.extract()
        if kind == "Table" and found:   # text after a table's title is a note, set in a lighter style
            if note is None:
                note = soup.new_tag("span", attrs={"class": "cap-note"})
                cap.append(note)
            note.append(node)
        else:
            cap.append(node)
    return cap, found


def shape(fragment: str, n_diagrams: int):
    soup = BeautifulSoup(fragment, "html.parser")
    for i, pre in enumerate(soup.select("pre.mermaid")):
        pre.replace_with(soup.new_tag("div", attrs={"class": "diagram", "data-dg": str(i)}))
    assert len(soup.select("div.diagram")) == n_diagrams
    for img in soup.find_all("img"):
        src = img["src"]
        if not re.match(r"^[a-z]+:", src):
            img["src"] = (REPORTS_DIR / src).resolve().as_uri()
        if "dashboard_" in src:
            img["class"] = ["screenshot"]
    for hr in soup.find_all("hr"):
        hr.decompose()
    for anchor in soup.select("code.sourceCode a"):   # empty per-line anchors pandoc adds to code
        anchor.decompose()

    figures, tables = [], []
    for p in list(soup.find_all("p")):
        if p.decomposed or p.parent is None:
            continue
        first = first_element(p)
        if getattr(first, "name", None) != "strong":
            continue
        head = first.get_text()
        if head.startswith("Figure "):
            visuals, sib = [], p.find_next_sibling()
            while sib is not None and is_visual(sib):
                visuals.append(sib)
                sib = sib.find_next_sibling()
            if not visuals:
                continue
            cap, found = caption(soup, p, "Figure")
            fig = soup.new_tag("figure", attrs={"class": "fig" + (" row" if len(visuals) > 1 else ""),
                                                "id": "fig-" + found[0][0].replace(".", "-")})
            p.replace_with(fig)
            holder = fig
            if len(visuals) > 1:
                holder = soup.new_tag("div", attrs={"class": "imgs"})
                fig.append(holder)
            for v in visuals:
                holder.append(v.extract() if v.name == "div" else v.find("img").extract())
                if v.name == "p":
                    v.decompose()
            fig.append(cap)
            figures += [(n, t, fig["id"]) for n, t in found]
        elif head.startswith("Table "):
            table = p.find_next_sibling()
            if getattr(table, "name", None) != "table":
                continue
            cap, found = caption(soup, p, "Table")
            fig = soup.new_tag("figure", attrs={"class": "tbl", "id": "tbl-" + found[0][0].replace(".", "-")})
            p.replace_with(fig)
            fig.append(cap)
            fig.append(table.extract())
            tables += [(n, t, fig["id"]) for n, t in found]

    for code in soup.select("td code, th code"):
        if len(code.get_text()) >= 24:   # only long names may break mid-word; short ones (hashes) stay whole
            code["class"] = code.get("class", []) + ["brk"]
    for table in soup.find_all("table"):
        for colgroup in table.find_all("colgroup"):   # pandoc's fixed widths come from the Markdown dashes;
            colgroup.decompose()                       # the browser sizes columns by their content instead
        cols = len(table.find("tr").find_all(["th", "td"])) if table.find("tr") else 0
        if cols >= 8:
            table["class"] = ["xdense"]
        elif cols >= 6:
            table["class"] = ["dense"]
        if len(table.find_all("tr")) <= 13 and table.parent.name == "figure":
            table.parent["class"] = table.parent.get("class", []) + ["keep"]   # short tables stay on one page
    return soup, figures, tables


def part_title(text: str) -> str:
    small = {"and", "of", "the", "for", "in", "on", "to"}
    return " ".join(w if (i and w in small) else w.capitalize() for i, w in enumerate(text.lower().split()))


def build_sections(soup):
    """Wrap each <h1> and what follows in a <section>; return them with the contents entries."""
    sections, current = [], None
    for el in list(soup.contents):
        if getattr(el, "name", None) == "h1":
            current = soup.new_tag("section")
            sections.append(current)
        if current is not None:
            current.append(el.extract())

    toc = []   # (level, number, title_html, id)
    for sec in sections:
        h1 = sec.find("h1")
        text = h1.get_text().strip()
        hid = h1.get("id") or re.sub(r"\W+", "-", text.lower())
        h1["id"] = hid
        part = re.match(r"PART (\w+)\s*[—-]\s*(.+)", text)
        chapter = re.match(r"(\d+)\.\s+(.+)", text)
        if part:
            sec["class"] = ["part-page"]
            h1.clear()
            label = soup.new_tag("span", attrs={"class": "part-label"})
            label.string = f"Part {part.group(1)}"
            title = soup.new_tag("span", attrs={"class": "part-title"})
            title.string = part_title(part.group(2))
            h1.append(label)
            h1.append(title)
            toc.append((0, "", f"Part {part.group(1)} \u2014 {part_title(part.group(2))}", hid))
            continue
        if text == "Abstract":
            sec["class"] = ["frontsec"]
            kw = sec.find(lambda t: t.name == "p" and t.get_text().startswith("Keywords:"))
            if kw:
                kw["class"] = ["keywords"]
        else:
            sec["class"] = ["chapter"]
        if chapter:
            h1.clear()
            label = soup.new_tag("span", attrs={"class": "chap-label"})
            label.string = f"Chapter {chapter.group(1)}"
            title = soup.new_tag("span", attrs={"class": "chap-title"})
            title.string = chapter.group(2)
            h1.append(label)
            h1.append(title)
            toc.append((1, chapter.group(1), html.escape(chapter.group(2)), hid))
        elif text != "Abstract":
            if text == "References":
                toc.append((0, "", "Back Matter", hid))
            toc.append((1, "", html.escape(text), hid))
        for h2 in sec.find_all("h2"):
            m = re.match(r"(\d+\.\d+|Appendix [A-Z])\s*[–-]?\s*(.+)", h2.get_text().strip())
            if not m:
                continue
            num = m.group(1).replace("Appendix ", "")
            h2.clear()
            span = soup.new_tag("span", attrs={"class": "secnum"})
            span.string = num
            h2.append(span)
            h2.append(NavigableString(m.group(2)))
            toc.append((2, num, html.escape(m.group(2)), h2.get("id")))
        if text == "References":
            for p in sec.find_all("p"):
                first = p.contents[0] if p.contents else None
                m = re.match(r"(\[\d+\])\s+", str(first)) if isinstance(first, NavigableString) else None
                if m:
                    p["class"] = ["ref"]
                    first.replace_with(NavigableString(str(first)[m.end():]))
                    num = soup.new_tag("span", attrs={"class": "refnum"})
                    num.string = m.group(1)
                    p.insert(0, num)
    # each part page lists its chapters
    for i, sec in enumerate(sections):
        if "part-page" in sec.get("class", []):
            items = []
            for later in sections[i + 1:]:
                if "part-page" in later.get("class", []):
                    break
                label = later.find("span", class_="chap-label")
                if label:
                    items.append(f'<li><span>{label.get_text().split()[-1]}</span>{html.escape(later.find("span", class_="chap-title").get_text())}</li>')
            sec.append(BeautifulSoup(f'<ol class="part-chapters">{"".join(items)}</ol>', "html.parser"))
    return sections, toc


TAG_KINDS = {"Git": "git", "Documented": "doc"}


def tagify(text: str) -> str:
    """[Git], [Documented] and [To confirm] become small labels."""
    def repl(m):
        word = m.group(2)
        kind = TAG_KINDS.get(word, "confirm")
        return f'<span class="tag tag-{kind}">{html.escape(word)}</span>'
    return re.sub(r"(<strong>)?\[(Git|Documented|To confirm[^\]<]*)\](?(1)</strong>)", repl, text)


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------
def cover_html(md: str, title_page: str) -> str:
    name, subtitle = document_title(md)
    rows = re.findall(r"^\| \d+ \| ([^|]+?) \| ([^|]+?) \| [^|]+? \|$", title_page, flags=re.M)
    blocks = [b.strip() for b in re.split(r"\n\s*\n", title_page)]
    clean = lambda b: [ln.rstrip("\\").strip().replace("**", "") for ln in b.split("\n") if ln.strip()]
    at = next(i for i, b in enumerate(blocks) if b.startswith("Under the guidance of"))
    guide = clean(blocks[at])[1:]
    school, institution, place = clean(blocks[at + 1])
    year = re.search(r"Academic Year: (.+?)\\?$", title_page, flags=re.M).group(1)
    date = re.search(r"Date of Submission: (.+?)\\?$", title_page, flags=re.M).group(1)
    course = re.search(r"\*\*(Data Mining.+?)\*\*", title_page).group(1)
    group = re.search(r"^by \*\*(.+?)\*\*$", title_page, flags=re.M).group(1)
    team = "".join(f'<tr><td>{html.escape(n)}</td><td class="roll">{html.escape(r)}</td></tr>' for n, r in rows)
    e = html.escape
    return f"""<div class="cover">
  <div class="cover-band"><div class="cover-inst">{e(institution)}</div>
    <div class="cover-school">{e(school)} &middot; {e(place)}</div></div>
  <div class="cover-main">
    <div class="cover-kicker">Project Report</div>
    <div class="cover-title">{e(name)}</div>
    <div class="cover-sub">{e(subtitle)}</div>
    <div class="cover-course">Submitted for the course <b>{e(course)}</b></div>
    <div class="cover-cols">
      <div class="cover-col"><h4>Submitted by {e(group)}</h4><table class="cover-team">{team}</table></div>
      <div class="cover-col"><h4>Under the guidance of</h4><div class="cover-guide">
        <div class="name">{e(guide[0])}</div>{''.join(f'<div class="role">{e(g)}</div>' for g in guide[1:])}</div></div>
    </div>
  </div>
  <div class="cover-foot"><span>Academic Year <b>{e(year)}</b></span><span>Submitted <b>{e(date)}</b></span></div>
</div>"""


def row(href: str, num: str, title: str, page) -> str:
    return (f'<a class="row" href="#{href}"><span class="num">{num}</span><span class="ttl">{title}</span>'
            f'<span class="dots"></span><span class="pg">{page}</span></a>')


def listings(toc, figures, tables, pages: list | None) -> tuple[str, int]:
    """Contents, list of figures and list of tables; pages fills the numbers in link order."""
    pages = iter(pages or [])
    nxt = lambda: next(pages, "")
    items = ['<li class="lvl1">' + row("abstract", "", "Abstract", nxt()) + "</li>",
             '<li class="lvl1">' + row("list-of-figures", "", "List of Figures", nxt()) + "</li>",
             '<li class="lvl1">' + row("list-of-tables", "", "List of Tables", nxt()) + "</li>"]
    links = 3
    for level, num, title, hid in toc:
        if level == 0:
            items.append(f'<li class="lvl0">{html.escape(title)}</li>')
            continue
        items.append(f'<li class="lvl{level}">' + row(hid, num, title, nxt()) + "</li>")
        links += 1
    contents = f'<nav class="listing toc" id="contents"><h1>Contents</h1><ol>{"".join(items)}</ol></nav>'
    lof = "".join("<li>" + row(fid, f"Figure {n}", t, nxt()) + "</li>" for n, t, fid in figures)
    lot = "".join("<li>" + row(tid, f"Table {n}", t, nxt()) + "</li>" for n, t, tid in tables)
    links += len(figures) + len(tables)
    lists = (f'<nav class="listing lof" id="list-of-figures"><h1>List of Figures</h1><ol>{lof}</ol></nav>'
             f'<nav class="listing lot" id="list-of-tables"><h2>List of Tables</h2><ol>{lot}</ol></nav>')
    return contents + lists, links


def link_pages(pdf: Path, count: int) -> list[int] | None:
    """Target page (1-based) of the first `count` internal links, in reading order."""
    pages = []
    with pymupdf.open(pdf) as doc:
        for page in doc:
            links = [l for l in page.get_links() if l.get("kind") in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED)]
            links.sort(key=lambda l: (round(l["from"].y0), l["from"].x0))
            for link in links:
                target = link.get("page")
                if target is None and link.get("nameddest"):
                    target = doc.resolve_names().get(link["nameddest"], {}).get("page")
                pages.append(None if target is None else target + 1)
            if len(pages) >= count:
                break
    pages = pages[:count]
    return pages if len(pages) == count and None not in pages else None


def assemble(md: str, title_page: str, sections, toc, figures, tables, svgs, pages) -> tuple[str, int]:
    front, links = listings(toc, figures, tables, pages)
    abstract = next(s for s in sections if "frontsec" in s.get("class", []))
    abstract.find("h1")["id"] = "abstract"
    rest = [s for s in sections if s is not abstract]
    body = cover_html(md, title_page) + str(abstract) + front + "".join(str(s) for s in rest)
    body = tagify(body)
    for i, svg in enumerate(svgs):
        body = body.replace(f'<div class="diagram" data-dg="{i}"></div>', f'<div class="diagram">{svg}</div>')
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>StoreSense \u2014 DMDW Project Report</title>
<link rel="stylesheet" href="{FONTS_URL}">
<style>{CSS.read_text(encoding="utf-8")}</style></head>
<body>{body}</body></html>"""
    return doc, links


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def print_pdf(browser: str, html_text: str, out: Path, tmp: Path, tag: str) -> None:
    page = tmp / f"report-{tag}.html"
    page.write_text(html_text, encoding="utf-8", newline="\n")
    run(browser_args(browser, tmp / f"profile-{tag}", 20000) +
        ["--generate-pdf-document-outline", f"--print-to-pdf={out}", page.as_uri()])
    if not out.exists():
        raise SystemExit(f"{Path(browser).name} did not write a PDF.")


def build_docx() -> None:
    run(["pandoc", str(SOURCE), "-f", "markdown+tex_math_dollars+pipe_tables", "-t", "docx",
         f"--resource-path={REPORTS_DIR}", "--toc", "--toc-depth=2", "-o", str(DOCX_OUT)])


def main() -> None:
    if shutil.which("pandoc") is None:
        raise SystemExit("pandoc not found. Install it from https://pandoc.org/installing.html")
    browser = find_browser()
    md = SOURCE.read_text(encoding="utf-8")
    sections_md = split_sections(md)
    title_page = next(text for title, text in sections_md if title == "Title Page")
    body_md = "\n\n".join(text for title, text in sections_md if title not in SKIPPED)
    sources = mermaid_sources(body_md)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp = Path(tmp)
        draw_missing_diagrams(sources, browser, tmp)
        svgs = [(DIAGRAM_DIR / f"{diagram_key(s)}.svg").read_text(encoding="utf-8") for s in sources]
        fragment = run(["pandoc", "-f", MARKDOWN, "-t", "html5", "--mathml", "--wrap=none"], stdin=body_md)
        soup, figures, tables = shape(fragment, len(sources))
        sections, toc = build_sections(soup)

        draft, links = assemble(md, title_page, sections, toc, figures, tables, svgs, None)
        print_pdf(browser, draft, tmp / "draft.pdf", tmp, "draft")
        pages = link_pages(tmp / "draft.pdf", links)
        if pages is None:
            print("could not read the page of every contents entry; the contents has no page numbers")
        final, _ = assemble(md, title_page, sections, toc, figures, tables, svgs, pages)
        print_pdf(browser, final, tmp / "report.pdf", tmp, "final")
        if pages is not None and link_pages(tmp / "report.pdf", links) != pages:
            print("warning: page numbers moved between the two passes; check the contents")
        out = PDF_OUT
        try:
            shutil.copyfile(tmp / "report.pdf", out)   # only replace the old PDF once the new one exists
        except PermissionError:                        # the old PDF is open in a viewer (Windows locks it)
            out = PDF_OUT.with_name(PDF_OUT.stem + " (new).pdf")
            shutil.copyfile(tmp / "report.pdf", out)
            print(f"{PDF_OUT.name} is open in another program, so the new PDF was saved as {out.name}")

    build_docx()
    with pymupdf.open(out) as doc:
        print(f"{doc.page_count} pages, {len(sources)} diagrams, {len(figures)} figures, {len(tables)} tables")
    print(f"-> {out}\n-> {DOCX_OUT}")


if __name__ == "__main__":
    main()
