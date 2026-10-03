#!/usr/bin/env python3
"""Publish the weekly digests as the site's newsletter archive.

Reads every ../scripts/content_drafts/YYYY-MM-DD.md, converts it to HTML, and
writes newsletter/YYYY-MM-DD.html plus newsletter/index.html. Run after each
sourcing pass's digest is written; commit the output with the rest of the site.

Stdlib only, on purpose: this Mac has no Node, and the pipeline's other tools
(source_watch, ics_watch) already set the pattern. This same script is where
phase 2 grows — per-event and per-neighborhood pages generated from a catalog
export will use the identical template/writing machinery.

The markdown converter below is deliberately minimal: it covers exactly what
the digests use (#/##/### headings, **bold**, *em*, - lists, ---, links,
paragraphs). If a digest starts using something fancier, extend it then.
"""

import html
import re
from datetime import datetime
from pathlib import Path

SITE = Path(__file__).resolve().parent
DRAFTS = SITE.parent / "scripts" / "content_drafts"
OUT = SITE / "newsletter"

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Enerjia Newsletter</title>
<meta name="description" content="{description}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,400..700,0..100,0..1;1,9..144,400..700,0..100,0..1&display=swap">
<link rel="stylesheet" href="../style.css">
</head>
<body>
<header class="site">
  <div class="wrap">
    <a class="wordmark" href="../"><span class="eps">&epsilon;</span> Enerjia</a>
    <nav class="site">
      <a href="../women.html">Women</a>
      <a href="../singles.html">Singles Circuit</a>
      <a href="./"><strong>Newsletter</strong></a>
    </nav>
  </div>
</header>
<main class="wrap">
<article class="issue">
<p class="issue-date" style="margin-top:40px">{date_human}</p>
{body}
</article>
</main>
<footer class="site">
  <div class="wrap"><p><a href="./">&larr; All issues</a> &middot; <a href="../">Enerjia</a></p></div>
</footer>
</body>
</html>
"""

INDEX = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Newsletter — Enerjia</title>
<meta name="description" content="The Enerjia weekly: what's happening in San Francisco, three picks worth leaving the house for, written by a person who verified every listing.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT,WONK@0,9..144,400..700,0..100,0..1;1,9..144,400..700,0..100,0..1&display=swap">
<link rel="stylesheet" href="../style.css">
</head>
<body>
<header class="site">
  <div class="wrap">
    <a class="wordmark" href="../"><span class="eps">&epsilon;</span> Enerjia</a>
    <nav class="site">
      <a href="../women.html">Women</a>
      <a href="../singles.html">Singles Circuit</a>
      <a href="./"><strong>Newsletter</strong></a>
    </nav>
  </div>
</header>
<main class="wrap">
<div class="hero">
  <h1>The weekly email</h1>
  <p class="lede">Every issue, archived. Sign up on the
  <a href="../index.html#newsletter">home page</a>.</p>
</div>
<ul class="archive">
{items}
</ul>
</main>
<footer class="site">
  <div class="wrap"><p><a href="../">&larr; Enerjia</a></p></div>
</footer>
</body>
</html>
"""


def md_to_html(text: str) -> str:
    out, in_list = [], False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
        return s

    # Paragraphs can wrap across source lines; gather runs between blanks.
    para: list[str] = []

    def flush_para():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_para(); close_list(); continue
        if line.startswith("### "):
            flush_para(); close_list(); out.append(f"<h3>{inline(line[4:])}</h3>"); continue
        if line.startswith("## "):
            flush_para(); close_list(); out.append(f"<h2>{inline(line[3:])}</h2>"); continue
        if line.startswith("# "):
            flush_para(); close_list(); out.append(f"<h1>{inline(line[2:])}</h1>"); continue
        if line.strip() == "---":
            flush_para(); close_list(); out.append("<hr>"); continue
        if line.lstrip().startswith("- "):
            flush_para()
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{inline(line.lstrip()[2:])}</li>"); continue
        para.append(line.strip())

    flush_para(); close_list()
    return "\n".join(out)


def first_paragraph(md: str) -> str:
    for block in md.split("\n\n"):
        b = block.strip()
        if b and not b.startswith("#"):
            return re.sub(r"[*\[\]]", "", b.replace("\n", " "))[:155]
    return "The Enerjia weekly."


def main():
    OUT.mkdir(exist_ok=True)
    issues = []
    # The archive is what subscribers got. A date's `_buttondown_send.md` is
    # that; the bare digest is the working file, and it carries internal notes
    # ("Watch list — don't announce", seed status, copy notes) that must never
    # publish. So: prefer the send version; fall back to the digest only when
    # it is clean of internal markers; otherwise skip the date and say so.
    INTERNAL = ("Watch list", "don't announce", "do not announce", "not seedable", "SEED STATUS")
    for path in sorted(DRAFTS.glob("????-??-??.md"), reverse=True):
        date = datetime.strptime(path.stem, "%Y-%m-%d")
        send = path.with_name(path.stem + "_buttondown_send.md")
        if send.exists():
            md = send.read_text()
        else:
            md = path.read_text()
            if any(marker in md for marker in INTERNAL):
                print(f"skip newsletter/{path.stem}.html  (digest has internal notes and no send version)")
                continue
        title_m = re.search(r"^# (.+)$", md, re.M)
        title = title_m.group(1) if title_m else path.stem
        # Two early issues were published from their digests, whose headings
        # read "Content draft — week of 2026-08-17". The archive shows what
        # a reader would call it.
        wk = re.match(r"Content draft — week of (\d{4}-\d{2}-\d{2})", title)
        if wk:
            title = "The week of " + datetime.strptime(wk.group(1), "%Y-%m-%d").strftime("%B %-d")
        (OUT / f"{path.stem}.html").write_text(PAGE.format(
            title=html.escape(title),
            description=html.escape(first_paragraph(md)),
            date_human=date.strftime("%B %-d, %Y"),
            body=md_to_html(md),
        ))
        issues.append((path.stem, title, date))
        print(f"wrote newsletter/{path.stem}.html  ({title})")

    items = "\n".join(
        f'<li><a href="{stem}.html"><strong>{html.escape(title)}</strong><br>'
        f'<span class="date">{date.strftime("%B %-d, %Y")}</span></a></li>'
        for stem, title, date in issues
    )
    (OUT / "index.html").write_text(INDEX.format(items=items))
    print(f"wrote newsletter/index.html  ({len(issues)} issues)")


if __name__ == "__main__":
    main()
