#!/usr/bin/env python3
"""Render the Ohio briefing artifact to a print-ready PDF.

The artifact is authored as an Artifact fragment (no <html>/<body> skeleton) and
is theme-aware. For print we wrap it in a real document, pin the LIGHT theme (a
PDF is a document, not a screen), keep background colours so the semantic chips
and table highlights survive, and add break rules so figures and tables are not
split across pages.
"""
import os
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "ohio_briefing.html")
WRAP = os.path.join(HERE, "_print.html")
OUT = os.path.join(HERE, "Ohio-flood-model-briefing.pdf")

PRINT_CSS = """
<style id="print-rules">
@page { size: Letter; margin: 16mm 14mm 18mm; }
html, body { background: #fff !important; }
* { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
.wrap { max-width: none !important; padding: 0 !important; }
body { font-size: 10.5pt; line-height: 1.5; }
.mast { padding-top: 0; }
.mast h1 { font-size: 25pt; }
.mast .standfirst { font-size: 12pt; }
section { margin-bottom: 30px; }
.shead h2 { font-size: 15pt; }
figure, .figbox, .tablewrap, .rec, .pull, .limit, .disclaim,
.blu li, table tr, footer { break-inside: avoid; page-break-inside: avoid; }
.shead, h1, h2, h3 { break-after: avoid; page-break-after: avoid; }
.blu { break-inside: avoid; }
.tablewrap { overflow: visible !important; }
table { min-width: 0 !important; font-size: 9pt; }
th, td { padding: 6px 9px; }
figcaption { font-size: 9pt; }
a { color: inherit; text-decoration: none; }
</style>
"""

body = open(SRC, encoding="utf-8").read()
# Chromium here has no proxy for outbound font fetches, so serve the webfonts
# from inlined base64 instead of the Google Fonts link (also makes the PDF
# fully self-contained).
inline = open(os.path.join(HERE, "fonts_inline.css"), encoding="utf-8").read()
body = body.replace(
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&'
    'family=IBM+Plex+Serif:wght@400;500;600&display=swap">',
    "<style>" + inline + "</style>")
doc = ('<!doctype html><html lang="en" data-theme="light"><head>'
       '<meta charset="utf-8">'
       '<meta name="viewport" content="width=device-width,initial-scale=1">'
       '</head><body>' + body + PRINT_CSS + '</body></html>')
open(WRAP, "w", encoding="utf-8").write(doc)

with sync_playwright() as p:
    b = p.chromium.launch(
        executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
        args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1100, "height": 1400})
    pg.goto("file://" + WRAP, wait_until="networkidle")
    pg.emulate_media(media="print")
    # make sure the webfonts actually arrived before paginating
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(2500)
    loaded = pg.evaluate(
        "Array.from(document.fonts).filter(f=>f.status==='loaded')"
        ".map(f=>f.family+' '+f.weight)")
    print("fonts loaded:", sorted(set(loaded)) or "NONE (fallback stacks in use)")
    pg.pdf(path=OUT, format="Letter", print_background=True,
           margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"},
           display_header_footer=True,
           header_template='<div></div>',
           footer_template=(
               '<div style="width:100%;font-family:Helvetica,Arial,sans-serif;'
               'font-size:7.5pt;color:#6C7F86;padding:0 14mm;display:flex;'
               'justify-content:space-between;">'
               '<span>Independent hindcast study &middot; central Ohio flood, 19&ndash;20 August 2026'
               ' &middot; not an official agency product</span>'
               '<span class="pageNumber"></span></div>'))
    b.close()
print("->", OUT, os.path.getsize(OUT) // 1024, "KB")
