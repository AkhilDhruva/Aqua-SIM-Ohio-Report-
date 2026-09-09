#!/usr/bin/env python3
"""Assemble the Ohio agency report from the authoring workflow's journal.

Usage: python3 report/build_report.py <workflow_journal.jsonl> [--no-pdf] [--no-docx]

Reads each agent's returned result from the workflow journal (the authoritative
record of what every writer, checker and reviser returned), takes the LAST
Markdown produced for each section number (a revision supersedes a draft),
the executive summary from the synthesis agent, and the critic's findings, and
builds:

    report/Ohio_Flood_Hindcast_Report_<date>.html   self-contained, fonts inlined
    report/Ohio_Flood_Hindcast_Report_<date>.pdf    Letter, print CSS
    report/Ohio_Flood_Hindcast_Report_<date>.docx   editable copy for the agency
    report/report_sources.json                      citation index

CITATIONS. Writers were required to tag every number with [src: <repo path>].
This assembler converts each tag into a numbered reference and emits a
"Sources cited" appendix mapping numbers to repository paths at the commit the
report was built from, so any figure in the report can be traced to a file and
verified with sha256sum. Tags are never silently dropped: a tag whose path does
not exist in the repository is rendered as a visible "[UNRESOLVED SOURCE]".

Nothing here edits report text. If a section is wrong, the fix is a revision in
the workflow, not a patch in the assembler.
"""
import base64
import html
import json
import os
import re
import subprocess
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
TODAY = date.today().isoformat()
BASENAME = f"Ohio_Flood_Hindcast_Report_{TODAY}"

TITLE = "Central Ohio Flood of 19 to 20 August 2026: An Independent Hindcast and Its Limits for Road-Closure Decisions"
SUBTITLE = "Technical report for Ohio state and county agencies"
AUTHOR = "Akhil Dhruva"
AFFIL = "Independent research. Not a product of, endorsed by, or reviewed by ODOT, the National Weather Service, USGS, or any Ohio agency."

FIGS = {6: ["fig1_road_vs_channel.png", "fig2_prediction_outcome.png"], 9: ["fig3_numerical_health.png"]}
FIG_CAPTIONS = {
    "fig1_road_vs_channel.png": "Figure 1. Carriageway depth against the channel beside it at 6 to 8 m resolution, for every corridor point with a 60 s probe series. Where the two lines separate, a 60 m cell averaging them together reports the road as flooded when it is not.",
    "fig2_prediction_outcome.png": "Figure 2. All twelve corridor points: the terrain-only freeboard prediction against what the fine grid did, including the seven points that cannot be scored and the reason for each.",
    "fig3_numerical_health.png": "Figure 3. Franklinton numerical health sampled while the run was in progress: Froude number, water volume in the domain, and the outfall boundary velocity that set the run's cost.",
}


def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True).stdout.strip()


# ---------------------------------------------------------------- journal
def load_journal(path):
    labels, results = {}, []
    for line in open(path, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get("type") == "started":
            labels[d["key"]] = d.get("label", "")
        elif d.get("type") == "result" and isinstance(d.get("result"), dict):
            results.append((labels.get(d["key"], ""), d["result"]))
    sections, exec_md, critique = {}, None, None
    for lab, r in results:
        if lab.startswith("synth:") and "markdown" in r:
            exec_md = r["markdown"]
        elif lab.startswith("critic:"):
            critique = r
        elif "markdown" in r and isinstance(r.get("section"), int):
            sections[r["section"]] = r          # later results overwrite earlier: revise > draft
    return sections, exec_md, critique


# ---------------------------------------------------------------- citations
class Cites:
    def __init__(self):
        self.order, self.index = [], {}

    def ref(self, path):
        path = path.strip().strip("`")
        if path not in self.index:
            self.index[path] = len(self.order) + 1
            self.order.append(path)
        return self.index[path]


CITES = Cites()
TAG = re.compile(r"\s*\[src:\s*([^\]]+)\]")


def cite_html(m):
    n = CITES.ref(m.group(1))
    ok = os.path.exists(os.path.join(REPO, m.group(1).strip().strip("`")))
    return f'<sup class="cite{"" if ok else " bad"}">[{n}{"" if ok else " UNRESOLVED SOURCE"}]</sup>'


def cite_text(m):
    n = CITES.ref(m.group(1))
    return f" [{n}]"


# ---------------------------------------------------------------- markdown -> html (GFM subset)
def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    s = TAG.sub(cite_html, s)
    return s


def md_to_html(md):
    out, i, lines = [], 0, md.splitlines()
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-+", lines[i + 1]):
            hdr = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            out.append('<div class="tablewrap"><table><thead><tr>' + "".join(f"<th>{inline(h)}</th>" for h in hdr)
                       + "</tr></thead><tbody>" + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows)
                       + "</tbody></table></div>")
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", ln)
        if m:
            lvl = len(m.group(1))
            text = m.group(2).strip()
            anchor = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            out.append(f'<h{lvl} id="{anchor}">{inline(text)}</h{lvl}>')
            i += 1
            continue
        if re.match(r"^\s*[-*]\s+", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        if re.match(r"^\s*\d+[.)]\s+", ln):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+[.)]\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+[.)]\s+", "", lines[i]))
                i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue
        if ln.strip().startswith(">"):
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{inline(' '.join(q))}</blockquote>")
            continue
        if not ln.strip():
            i += 1
            continue
        para = []
        while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,4}\s|\||\s*[-*]\s|\s*\d+[.)]\s|>)", lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


# ---------------------------------------------------------------- fonts
def inline_fonts():
    """Try to embed IBM Plex; fall back silently to system fonts."""
    css_url = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500"
               "&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Serif:wght@400;500;600&display=swap")
    try:
        css = subprocess.run(["curl", "-sS", "--max-time", "25", "-A", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36", css_url],
                             capture_output=True, text=True, timeout=40).stdout
        if "@font-face" not in css:
            return ""
        def repl(m):
            url = m.group(1)
            b = subprocess.run(["curl", "-sS", "--max-time", "25", url], capture_output=True, timeout=40).stdout
            return f"url(data:font/woff2;base64,{base64.b64encode(b).decode()})"
        return "<style>" + re.sub(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", repl, css) + "</style>"
    except Exception:
        return ""


CSS = """
<style>
:root{--paper:#fff;--ink:#0F1C21;--ink-soft:#41555C;--ink-faint:#6C7F86;--rule:#C6D0D3;--rule-strong:#9FADB2;
--water:#1D5C6B;--alert:#A8322B;--alert-bg:#A8322B12;--verified:#3F6B4A;--verified-bg:#3F6B4A12;--caution:#9A6B1E;--surface:#F4F6F7}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:"IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif;font-size:11pt;line-height:1.55}
.wrap{max-width:900px;margin:0 auto;padding:0 28px 60px}
h1,h2,h3,h4{font-family:"IBM Plex Serif",Georgia,serif;margin:0;text-wrap:balance}
h1{font-size:26pt;line-height:1.15;font-weight:600;letter-spacing:-.01em}
h2{font-size:17pt;font-weight:600;margin:34px 0 12px;padding-top:14px;border-top:1px solid var(--rule)}
h3{font-size:13pt;font-weight:600;margin:22px 0 8px}h4{font-size:11.5pt;font-weight:600;margin:16px 0 6px}
p{margin:0 0 11px}ul,ol{margin:0 0 11px 22px;padding:0}li{margin:0 0 4px}
code{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.9em;background:var(--surface);padding:1px 4px;border-radius:3px}
blockquote{margin:12px 0;padding:10px 16px;border-left:3px solid var(--rule-strong);color:var(--ink-soft);background:var(--surface)}
.tablewrap{overflow-x:auto;margin:12px 0 16px;border:1px solid var(--rule);border-radius:4px}
table{border-collapse:collapse;width:100%;font-size:9.5pt}th,td{padding:6px 9px;text-align:left;border-bottom:1px solid var(--rule);vertical-align:top}
thead th{font-family:"IBM Plex Mono",monospace;font-size:8.5pt;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-faint);background:var(--surface);white-space:nowrap}
tbody tr:last-child td{border-bottom:none}
sup.cite{font-family:"IBM Plex Mono",monospace;font-size:7.5pt;color:var(--water);margin-left:2px}sup.cite.bad{color:var(--alert);font-weight:600}
.cover{padding:70px 0 36px;border-bottom:2px solid var(--ink);margin-bottom:26px}
.eyebrow{font-family:"IBM Plex Mono",monospace;font-size:9pt;letter-spacing:.14em;text-transform:uppercase;color:var(--ink-faint);margin:0 0 16px}
.sub{font-size:14pt;color:var(--ink-soft);margin:14px 0 0;font-family:"IBM Plex Serif",Georgia,serif}
.meta{margin-top:26px;font-family:"IBM Plex Mono",monospace;font-size:9pt;color:var(--ink-faint);line-height:1.8}.meta b{color:var(--ink-soft);font-weight:500}
.disclaim{margin:26px 0 0;padding:14px 16px;border-left:3px solid var(--caution);background:var(--surface);font-size:10pt;line-height:1.5;color:var(--ink-soft)}
.toc{margin:0 0 30px;padding:18px 22px;background:var(--surface);border:1px solid var(--rule);border-radius:4px}
.toc h2{border:0;margin:0 0 10px;padding:0;font-size:10pt;font-family:"IBM Plex Mono",monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-faint)}
.toc ol{margin:0 0 0 20px}.toc li{margin:0 0 3px}.toc a{color:var(--ink);text-decoration:none}
figure{margin:18px 0 22px;padding:0}figure img{width:100%;border:1px solid var(--rule);border-radius:4px}
figcaption{font-size:9.5pt;color:var(--ink-faint);margin-top:8px;line-height:1.45}
.sources{font-size:9.5pt}.sources li{margin:0 0 3px;font-family:"IBM Plex Mono",monospace;word-break:break-all}
.critique{font-size:10pt;color:var(--ink-soft)}
@media print{@page{size:Letter;margin:16mm 14mm 18mm}.wrap{max-width:none;padding:0}h2{break-after:avoid}figure,.tablewrap,blockquote,.disclaim{break-inside:avoid}.cover{padding-top:40px}}
</style>
"""


def build_html(sections, exec_md, critique):
    commit = git("rev-parse", "HEAD")
    short = commit[:7]
    body_parts = []
    order = [1] + sorted(k for k in sections if k != 1)
    toc = []
    for n in order:
        md = exec_md if n == 1 else sections[n]["markdown"]
        if not md:
            continue
        # ensure the level-2 heading carries the section number
        hmatch = re.search(r"^##\s+(.*)$", md, re.M)
        title = hmatch.group(1).strip() if hmatch else (f"{n}. Executive summary" if n == 1 else sections[n].get("title", f"Section {n}"))
        if not re.match(r"^\d+\.", title):
            title = f"{n}. {title}"
            md = re.sub(r"^##\s+.*$", f"## {title}", md, count=1, flags=re.M) if hmatch else f"## {title}\n\n{md}"
        anchor = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        toc.append(f'<li><a href="#{anchor}">{html.escape(title)}</a></li>')
        part = md_to_html(md)
        for fig in FIGS.get(n, []):
            fp = os.path.join(REPO, "figures", fig)
            if os.path.exists(fp):
                b64 = base64.b64encode(open(fp, "rb").read()).decode()
                part += (f'<figure><img alt="{html.escape(FIG_CAPTIONS.get(fig, fig))}" src="data:image/png;base64,{b64}">'
                         f'<figcaption>{html.escape(FIG_CAPTIONS.get(fig, fig))} Source: <code>figures/{fig}</code>.</figcaption></figure>')
        body_parts.append(part)

    # sources appendix (must come after all sections are rendered, so CITES is complete)
    src_items = []
    for i, p in enumerate(CITES.order, 1):
        fp = os.path.join(REPO, p)
        exists = os.path.exists(fp)
        digest = ""
        if exists and os.path.isfile(fp):
            import hashlib
            digest = hashlib.sha256(open(fp, "rb").read()).hexdigest()[:16]
        src_items.append(f"<li>[{i}] <code>{html.escape(p)}</code>{' sha256 ' + digest + '…' if digest else (' (directory)' if exists else ' <b>UNRESOLVED</b>')}</li>")
    sources_html = ('<h2 id="sources-cited">Sources cited</h2>'
                    f'<p>Every bracketed reference in this report points to a file in the study repository '
                    f'<code>AkhilDhruva/Aqua-SIM-Ohio-Report-</code> at commit <code>{short}</code>. '
                    f'The SHA-256 prefix shown is that file\'s content hash at this commit; <code>sha256sum</code> on a checkout reproduces it. '
                    f'The engine is <code>akhildhruva/aqua-sim</code> at commit <code>0b452c9</code>.</p>'
                    f'<ol class="sources">{"".join(src_items)}</ol>')

    crit_html = ""
    if critique:
        def ul(items):
            return "<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>" if items else "<p>None recorded.</p>"
        crit_html = ('<h2 id="reviewer-notes">Independent reviewer notes on this report</h2>'
                     '<p class="critique">Before release, an independent review pass read the whole report as an Ohio agency engineer would and recorded the following. '
                     'They are reproduced here unedited, so the reader sees what the review found and not only what was fixed.</p>'
                     f'<h3>What a government reader may still need</h3>{ul(critique.get("missing_for_government_reader", []))}'
                     f'<h3>Inconsistencies between sections</h3>{ul(critique.get("inconsistencies_between_sections", []))}'
                     f'<h3>Claims flagged as insufficiently supported</h3>{ul(critique.get("unsupported_claims_surviving", []))}'
                     f'<h3>Endorsement or affiliation risks</h3>{ul(critique.get("endorsement_or_affiliation_risks", []))}'
                     f'<h3>Overall</h3><p class="critique">{inline(critique.get("overall", ""))}</p>')

    cover = f"""
<div class="cover">
  <p class="eyebrow">Independent hindcast study &middot; Central Ohio flood of 19&ndash;20 August 2026</p>
  <h1>{html.escape(TITLE)}</h1>
  <p class="sub">{html.escape(SUBTITLE)}</p>
  <div class="meta">
    <b>Author</b> {html.escape(AUTHOR)}<br>
    <b>Date</b> {TODAY}<br>
    <b>Version</b> repository commit {short} &middot; engine commit 0b452c9<br>
    <b>Status</b> Research &mdash; not operationally validated<br>
    <b>Record of evidence</b> github.com/AkhilDhruva/Aqua-SIM-Ohio-Report-
  </div>
  <p class="disclaim"><b>What this document is.</b> {html.escape(AFFIL)} Observed impacts are drawn from public reporting and public data; several timestamps are approximate or inferred and are labelled as such. Every number carries a bracketed reference to the repository file it comes from. Nothing here should be used as the basis of an operational decision without agency review and independent verification.</p>
</div>
<div class="toc"><h2>Contents</h2><ol>{''.join(toc)}<li><a href="#sources-cited">Sources cited</a></li>{'<li><a href="#reviewer-notes">Independent reviewer notes</a></li>' if critique else ''}</ol></div>
"""
    doc = (f"<title>{html.escape(TITLE)}</title>\n" + inline_fonts() + CSS +
           f'<div class="wrap">{cover}{"".join(body_parts)}{sources_html}{crit_html}'
           f'<p class="critique" style="margin-top:40px;border-top:1px solid var(--rule);padding-top:12px">Built by <code>report/build_report.py</code> from the authoring workflow journal; assembled {TODAY}.</p></div>')
    return doc


def to_pdf(html_path, pdf_path):
    from playwright.sync_api import sync_playwright
    import glob
    # The pip-installed Playwright may be newer than the pre-installed Chromium
    # build; point it at whatever browser is actually on disk rather than
    # downloading one (network-restricted host; PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1).
    cands = ([os.environ["PW_CHROMIUM"]] if os.environ.get("PW_CHROMIUM") else []) + \
            sorted(glob.glob("/opt/pw-browsers/chromium-*/chrome-linux*/chrome")) + \
            sorted(glob.glob("/opt/pw-browsers/chromium_headless_shell-*/chrome-headless-shell-linux*/chrome-headless-shell")) + \
            ["/opt/pw-browsers/chromium"]
    exe = next((c for c in cands if os.path.isfile(c) and os.access(c, os.X_OK)), None)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        pg = b.new_page()
        pg.goto("file://" + os.path.abspath(html_path))
        pg.wait_for_timeout(800)
        pg.pdf(path=pdf_path, format="Letter", print_background=True,
               margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"})
        b.close()


def to_docx(sections, exec_md, critique, docx_path):
    from docx import Document
    from docx.shared import Pt, Inches
    d = Document()
    st = d.styles["Normal"]; st.font.name = "Calibri"; st.font.size = Pt(10.5)
    d.add_heading(TITLE, 0)
    d.add_paragraph(SUBTITLE)
    d.add_paragraph(f"Author: {AUTHOR}    Date: {TODAY}    Version: repository commit {git('rev-parse','--short','HEAD')}, engine commit 0b452c9")
    d.add_paragraph(AFFIL + " Nothing here should be used as the basis of an operational decision without agency review and independent verification.")
    order = [1] + sorted(k for k in sections if k != 1)
    for n in order:
        md = exec_md if n == 1 else sections[n]["markdown"]
        if not md:
            continue
        lines = md.splitlines(); i = 0
        while i < len(lines):
            ln = lines[i]
            if ln.startswith("|") and i + 1 < len(lines) and re.match(r"^\|?\s*:?-+", lines[i + 1]):
                hdr = [c.strip() for c in ln.strip().strip("|").split("|")]; i += 2
                rows = []
                while i < len(lines) and lines[i].startswith("|"):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
                t = d.add_table(rows=1, cols=len(hdr)); t.style = "Light Grid Accent 1"
                for j, h in enumerate(hdr):
                    t.rows[0].cells[j].text = TAG.sub(cite_text, re.sub(r"[*`]", "", h))
                for r in rows:
                    cells = t.add_row().cells
                    for j, c in enumerate(r[:len(hdr)]):
                        cells[j].text = TAG.sub(cite_text, re.sub(r"[*`]", "", c))
                d.add_paragraph("")
                continue
            m = re.match(r"^(#{1,4})\s+(.*)$", ln)
            if m:
                d.add_heading(TAG.sub(cite_text, re.sub(r"[*`]", "", m.group(2))), min(len(m.group(1)), 4)); i += 1; continue
            if re.match(r"^\s*[-*]\s+", ln):
                d.add_paragraph(TAG.sub(cite_text, re.sub(r"[*`]", "", re.sub(r"^\s*[-*]\s+", "", ln))), style="List Bullet"); i += 1; continue
            if re.match(r"^\s*\d+[.)]\s+", ln):
                d.add_paragraph(TAG.sub(cite_text, re.sub(r"[*`]", "", re.sub(r"^\s*\d+[.)]\s+", "", ln))), style="List Number"); i += 1; continue
            if not ln.strip():
                i += 1; continue
            para = []
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#{1,4}\s|\||\s*[-*]\s|\s*\d+[.)]\s)", lines[i]):
                para.append(lines[i].strip()); i += 1
            d.add_paragraph(TAG.sub(cite_text, re.sub(r"[*`]", "", " ".join(para))))
        for fig in FIGS.get(n, []):
            fp = os.path.join(REPO, "figures", fig)
            if os.path.exists(fp):
                d.add_picture(fp, width=Inches(6.5)); d.add_paragraph(FIG_CAPTIONS.get(fig, fig))
    d.add_heading("Sources cited", 1)
    d.add_paragraph(f"Bracketed references point to files in AkhilDhruva/Aqua-SIM-Ohio-Report- at commit {git('rev-parse','--short','HEAD')}; engine akhildhruva/aqua-sim at 0b452c9.")
    for i, p in enumerate(CITES.order, 1):
        d.add_paragraph(f"[{i}] {p}")
    if critique:
        d.add_heading("Independent reviewer notes on this report", 1)
        for k, lab in (("missing_for_government_reader", "What a government reader may still need"), ("inconsistencies_between_sections", "Inconsistencies between sections"),
                       ("unsupported_claims_surviving", "Claims flagged as insufficiently supported"), ("endorsement_or_affiliation_risks", "Endorsement or affiliation risks")):
            d.add_heading(lab, 2)
            for x in critique.get(k, []) or ["None recorded."]:
                d.add_paragraph(re.sub(r"[*`]", "", x), style="List Bullet")
        d.add_heading("Overall", 2); d.add_paragraph(re.sub(r"[*`]", "", critique.get("overall", "")))
    d.save(docx_path)


def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    sections, exec_md, critique = load_journal(sys.argv[1])
    if not sections:
        print("no sections found in journal"); return 1
    print(f"sections: {sorted(sections)}  exec_summary: {'yes' if exec_md else 'NO'}  critique: {'yes' if critique else 'NO'}")
    os.makedirs(HERE, exist_ok=True)
    html_path = os.path.join(HERE, BASENAME + ".html")
    doc = build_html(sections, exec_md, critique)
    open(html_path, "w", encoding="utf-8").write(doc)
    print("->", html_path, f"({len(doc):,} bytes, {len(CITES.order)} sources cited)")
    json.dump({"commit": git("rev-parse", "HEAD"), "built": TODAY,
               "sources": [{"n": i + 1, "path": p, "exists": os.path.exists(os.path.join(REPO, p))} for i, p in enumerate(CITES.order)],
               "sections": {str(n): {"title": sections[n].get("title"), "status_gaps": sections[n].get("gaps", [])} for n in sections},
               "critique": critique}, open(os.path.join(HERE, "report_sources.json"), "w"), indent=1)
    unresolved = [p for p in CITES.order if not os.path.exists(os.path.join(REPO, p))]
    if unresolved:
        print(f"WARNING: {len(unresolved)} unresolved source paths: {unresolved}")
    if "--no-pdf" not in sys.argv:
        pdf = os.path.join(HERE, BASENAME + ".pdf"); to_pdf(html_path, pdf); print("->", pdf, f"({os.path.getsize(pdf)//1024} KB)")
    if "--no-docx" not in sys.argv:
        docx = os.path.join(HERE, BASENAME + ".docx"); to_docx(sections, exec_md, critique, docx); print("->", docx, f"({os.path.getsize(docx)//1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
