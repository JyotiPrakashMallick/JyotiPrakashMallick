#!/usr/bin/env python3
"""Generate the profile README's SVG assets from live GitHub data.

Self-contained design system:
  header.svg        masthead - kicker, name, positioning line, roles
  links/*.svg       clickable chips (portfolio, linkedin, writing, resume)
  ticker.svg        live layer - last shipped, current focus, refreshed at
  timeline.svg      career timeline rendered as an interactive SVG
  loadtest.svg      illustration - throughput ramp with p99 under the SLA
  flamegraph.svg    illustration - CPU flame graph with the hot path lit
  oss/*.svg         one chip per upstream project, real logo embedded
  activity.svg      daily contribution graph over 12 months
  stats.svg         last-52-weeks totals and language mix
  lifetime.svg      all-time totals since 2014, with a per-year breakdown
  stack/*.svg       tech tiles, color logos from iconify (simple-icons fallback)

Everything is self-contained: fonts and logos are base64-embedded, colours flip
with prefers-color-scheme, no external requests at render time. GitHub camo proxy
friendly.

Usage:  python scripts/gen.py
"""

import base64
import json
import math
import pathlib
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone

# ---------------------------------------------------------------- configuration
USER = "JyotiPrakashMallick"
NAME = "JYOTI PRAKASH MALLICK"
FIRST_YEAR = 2014

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CACHE = ROOT / ".cache"

# ---------------------------------------------------------------- design tokens
LIGHT = dict(
    tx="#1d1d1f",   # Apple text colour
    mu="#6e6e73",   # Apple secondary label
    ac="#0071e3",   # Apple blue
    bd="#d2d2d7",   # Apple separator
    sf="#f5f5f7",   # Apple background
    grid="#e5e5ea",
    on="#ffffff",
)
DARK = dict(
    tx="#f5f5f7",   # Apple dark text
    mu="#98989d",   # Apple dark secondary label
    ac="#2997ff",   # Apple blue (dark)
    bd="#38383a",   # Apple dark separator
    sf="#1c1c1e",   # Apple dark background
    grid="#2c2c2e",
    on="#ffffff",
)

FONTS = {
    # SF Pro only exists on Apple devices and can't be embedded, so everyone
    # else gets Inter - the closest open-source match - baked into the SVG.
    "Inter": ("inter-var.woff2", "400 700"),
}
FD = "-apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
FB = "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif"
FM = "'SF Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

KICKER = "AI PERFORMANCE ENGINEER · CLOUD SCALABILITY · DISTRIBUTED SYSTEMS"
TAGLINE = "Architecting high-throughput AI platforms, distributed systems, and resilient cloud infrastructure."
NOW = "Auditoria.AI · AI Performance Engineer"
ROLES = "AI PERFORMANCE ENGINEER · PRINCIPAL PERF ARCHITECT · CLOUD INFRA"
AVAILABILITY = "HYDERABAD, INDIA · OPEN TO REMOTE"

LINKS = [
    ("PORTFOLIO", "https://jyotiprakash.github.io/", True),
    ("LINKEDIN", "https://www.linkedin.com/in/jyoti-prakash-mallick-10488b1b/", False),
    ("STACK OVERFLOW", "https://stackoverflow.com/users/6623265/jyoti-prakash-mallick", False),
    ("RÉSUMÉ", "https://www.linkedin.com/in/jyoti-prakash-mallick-10488b1b/", False),
]

OSS = [
    ("langchain-ai", "LangGraph", "agent orchestration"),
    ("browser-use", "Browser Use", "browser automation"),
    ("langfuse", "Langfuse", "llm observability"),
    ("groq", "Groq", "llm inference"),
    ("neondatabase", "Neon Postgres", "serverless postgres"),
    ("rudderlabs", "RudderStack", "data pipelines"),
    ("googleapis", "Google BigQuery", "data warehouse"),
]

STACK = [
    ("python", "Python"),
    ("java", "Java"),
    ("javascript", "JavaScript"),
    ("spring", "Spring"),
    ("fastapi", "FastAPI"),
    ("pytorch", "PyTorch"),
    ("huggingface", "Transformers"),
    ("langchain", "LangChain"),
    ("langgraph", "LangGraph"),
    ("anthropic", "Claude"),
    ("openai", "OpenAI"),
    ("ollama", "Ollama"),
    ("qdrant", "Qdrant"),
    ("mlflow", "MLflow"),
    ("mongodb", "MongoDB"),
    ("mysql", "MySQL"),
    ("kafka", "Kafka"),
    ("docker", "Docker"),
    ("kubernetes", "Kubernetes"),
    ("nginx", "Nginx"),
    ("linux", "Linux"),
    ("git", "Git"),
    ("prometheus", "Prometheus"),
    ("aws", "AWS"),
    ("azure", "Azure"),
    ("githubactions", "Actions"),
]

TIMELINE = [
    (
        "JUN 2025 — PRESENT",
        "Auditoria.AI",
        "AI PERFORMANCE ENGINEER",
        "AI-driven enterprise SaaS. Performance engineering for AI/ML pipelines, scalability, and reliability.",
    ),
    (
        "DEC 2025 — JUL 2026",
        "CVS Health, via Insight Global",
        "PERFORMANCE ENGINEER (CONSULTANT)",
        "High-availability healthcare systems. Load strategy, distributed tracing, and SLO enforcement.",
    ),
    (
        "APR 2024 — JUN 2025",
        "Invest4Edu",
        "ENGINEERING LEAD / ARCHITECT",
        "ETL over 10M+ records; RAG Q&A at 78% accuracy; led platform architecture and team.",
    ),
    (
        "FEB 2020 — APR 2024",
        "Parexel & Calyx",
        "PRINCIPAL PERFORMANCE ENGINEER",
        "Clinical trial platforms. Architected load frameworks, bottleneck analysis at enterprise scale.",
    ),
    (
        "SEPT 2017 — FEB 2020",
        "SS&C EZE Software",
        "SR. PERFORMANCE ENGINEER",
        "Financial trading systems. Performance profiling, capacity planning, and automated benchmarking.",
    ),
    (
        "OCT 2014 — SEPT 2017",
        "NCR Corporation",
        "SR. PERFORMANCE ENGINEER",
        "Retail & banking platforms. JMeter harnesses, distributed load generation, real-time telemetry.",
    ),
    (
        "APR 2010 — OCT 2014",
        "Infibeam Avenues",
        "SR. SOFTWARE ENGINEER",
        "E-commerce platform engineering, full-stack automation, and continuous integration pipelines.",
    ),
    (
        "SEPT 2009 — JAN 2010",
        "Zensar Technologies",
        "SOFTWARE ENGINEER INTERN",
        "Enterprise systems integration and early-career software engineering foundations.",
    ),
]


def fetch(url, raw=False):
    """GET with a small on-disk cache so reruns stay cheap and rate limits hold."""
    CACHE.mkdir(exist_ok=True)
    key = CACHE / (re.sub(r"[^a-zA-Z0-9]+", "_", url)[-90:] + (".bin" if raw else ".json"))
    if key.exists():
        return key.read_bytes() if raw else json.loads(key.read_text(encoding="utf-8"))
    req = urllib.request.Request(
        url, headers={"User-Agent": "profile-gen", "Accept": "application/vnd.github+json"}
    )
    body = urllib.request.urlopen(req, timeout=30).read()
    if raw:
        key.write_bytes(body)
        return body
    else:
        key.write_text(body.decode("utf-8"), encoding="utf-8")
        return json.loads(body.decode("utf-8"))


def calendar(frm=None, to=None):
    """Daily contribution counts. Public HTML, no token."""
    url = f"https://github.com/users/{USER}/contributions"
    if frm:
        url += f"?from={frm}&to={to}"
    html = fetch(url, raw=True).decode("utf-8", errors="ignore")
    cells = re.findall(r'data-date="([0-9-]+)"[^>]*id="([^"]+)"[^>]*data-level="\d"', html)
    tips = dict(re.findall(r'<tool-tip[^>]*for="([^"]+)"[^>]*>([^<]*)</tool-tip>', html))
    out = []
    for date, cid in cells:
        m = re.match(r"(\d+|No)", tips.get(cid, "").strip())
        out.append((date, 0 if not m or m.group(1) == "No" else int(m.group(1))))
    return sorted(out)


def longest_streak(days):
    best = run = 0
    for _, n in days:
        run = run + 1 if n else 0
        best = max(best, run)
    return best


def search_count(q):
    try:
        return fetch(f"https://api.github.com/search/issues?q={q}&per_page=1")["total_count"]
    except Exception:
        return 0


def collect():
    days = calendar()
    per_year, all_days = {}, []
    for y in range(FIRST_YEAR, datetime.now(timezone.utc).year + 1):
        yd = calendar(f"{y}-01-01", f"{y}-12-31")
        per_year[y] = sum(n for _, n in yd)
        all_days += yd

    repos, page = [], 1
    while page < 4:
        batch = fetch(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner")
        if not batch:
            break
        repos += batch
        page += 1
    own = [r for r in repos if not r.get("fork")]

    events = fetch(f"https://api.github.com/users/{USER}/events/public?per_page=30")
    shipped = next(
        (e for e in events if e.get("type") == "PushEvent" and not e.get("repo", {}).get("name", "").endswith(USER)),
        None,
    )

    try:
        commits = fetch(f"https://api.github.com/search/commits?q=author:{USER}&per_page=1")["total_count"]
    except Exception:
        commits = 0

    weeks = [sum(n for _, n in days[i:i + 7]) for i in range(0, len(days), 7)]
    return dict(
        days=days,
        total=sum(n for _, n in days),
        peak_week=max(weeks) if weeks else 0,
        repos=len(own),
        stars=sum(r.get("stargazers_count", 0) for r in own),
        langs=Counter(r.get("language") for r in own if r.get("language")).most_common(4),
        shipped=shipped["repo"]["name"].split("/")[-1] if shipped else "—",
        per_year=per_year,
        all_time=sum(per_year.values()),
        streak=longest_streak(sorted(set(all_days))),
        commits=commits,
        prs=search_count(f"author:{USER}+type:pr"),
        merged=search_count(f"author:{USER}+type:pr+is:merged"),
    )


def b64(path, mime):
    return f"data:{mime};base64," + base64.b64encode(pathlib.Path(path).read_bytes()).decode()


def font_face(*families):
    out = []
    for fam in families:
        if fam in FONTS:
            file, weight = FONTS[fam]
            out.append(
                f"@font-face{{font-family:'{fam}';font-style:normal;font-weight:{weight};"
                f"src:url({b64(ASSETS / file, 'font/woff2')}) format('woff2');}}"
            )
    return "".join(out)


def theme_vars():
    light = ";".join(f"--{k}:{v}" for k, v in LIGHT.items())
    dark = ";".join(f"--{k}:{v}" for k, v in DARK.items())
    return f"svg{{{light}}}@media(prefers-color-scheme:dark){{svg{{{dark}}}}}"


BASE_CSS = """
.d{font-family:%s} .b{font-family:%s} .m{font-family:%s}
.tx{fill:var(--tx)} .mu{fill:var(--mu)} .ac{fill:var(--ac)}
.kick{font-size:10.5px;letter-spacing:2.4px;font-weight:500}
.lab{font-size:9px;letter-spacing:1.6px}
.card{fill:var(--sf);stroke:var(--bd);stroke-width:1}
.in{animation:rise .6s cubic-bezier(.2,.7,.2,1) forwards}
@keyframes rise{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:translateY(0)}}
@media(prefers-reduced-motion:reduce){*{animation:none!important}}
""" % (FD, FB, FM)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg(w, h, css, body, label):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">'
        f"<style>{css}</style>{body}</svg>"
    )


# ---------------------------------------------------------------------- header
def header():
    # Calculate responsive font size based on name length so it never overflows
    name_len = len(NAME)
    font_size = 76 if name_len <= 17 else 66 if name_len <= 22 else 58
    y_name = 110

    css = f"""{font_face('Inter')}{theme_vars()}{BASE_CSS}
    .name{{font-size:{font_size}px;font-weight:600;letter-spacing:-.5px}}
    .rule{{stroke:var(--bd);stroke-width:1;transform-origin:left center;
      animation:draw .9s cubic-bezier(.2,.7,.2,1) forwards}}
    .d2{{animation-duration:.72s}} .d3{{animation-duration:.9s}} .d4{{animation-duration:1.08s}}
    .cur{{fill:var(--ac);animation:blink 1.1s steps(1) infinite}}
    @keyframes draw{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
    @keyframes blink{{0%,49%{{opacity:1}}50%,100%{{opacity:0}}}}
    """
    body = f"""<g class="in"><rect x="0" y="26" width="3" height="11" class="ac"/>
<text x="12" y="36" class="m kick ac">{esc(KICKER)}</text></g>
<text x="0" y="{y_name}" class="d name tx in d2">{esc(NAME)}</text>
<line x1="0" y1="132" x2="900" y2="132" class="rule"/>
<g class="in d3"><text x="0" y="158" class="m mu" font-size="12.5">{esc(TAGLINE)}<tspan class="cur" dx="6">&#9608;</tspan></text></g>
<g class="in d4"><text x="0" y="186" class="m mu lab">{esc(AVAILABILITY)}</text>
<text x="900" y="186" text-anchor="end" class="m lab ac">{esc(ROLES)}</text></g>"""
    return svg(900, 196, css, body, f"{NAME} — Profile")


# ----------------------------------------------------------------- link chips
def link_chip(label, filled):
    w = int(len(label) * 7.6 + 34)
    css = f"""{theme_vars()}{BASE_CSS}
    .fillbtn{{fill:var(--ac)}} .ghost{{fill:none;stroke:var(--bd);stroke-width:1}}
    .onac{{fill:var(--on)}}
    """
    shape = (
        f'<rect x="0.5" y="0.5" width="{w - 1}" height="31" rx="3" class="fillbtn"/>'
        if filled
        else f'<rect x="0.5" y="0.5" width="{w - 1}" height="31" rx="3" class="ghost"/>'
    )
    cls = "onac" if filled else "tx"
    body = shape + f'<text x="{w / 2:.0f}" y="20" text-anchor="middle" class="m lab {cls}">{esc(label)}</text>'
    return svg(w, 32, css, body, label)


# --------------------------------------------------------------- stack badges
def stack_badge(slug, label):
    W, H = 80, 64
    css = f"""{theme_vars()}{BASE_CSS}"""
    mark = ""
    icon_path = ASSETS / "icons" / f"{slug}.svg"
    if icon_path.exists():
        raw = icon_path.read_text(encoding="utf-8")
        root = re.search(r"<svg([^>]*)>", raw)
        vb = re.search(r'viewBox="([^"]+)"', root.group(1)).group(1)
        fill = re.search(r'\sfill="([^"]+)"', root.group(1))
        inner = re.sub(r"<title>.*?</title>", "", raw[root.end():raw.rindex("</svg>")])
        if fill:
            inner = f'<g fill="{fill.group(1)}">{inner}</g>'
        mark = (
            f'<svg x="{W / 2 - 11}" y="14" width="22" height="22" viewBox="{vb}" '
            f'preserveAspectRatio="xMidYMid meet">{inner}</svg>'
        )
    body = f"""<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="6" class="card"/>
<rect x="{W / 2 - 16}" y="9" width="32" height="32" rx="7" fill="#ffffff"/>
{mark}
<text x="{W / 2}" y="54" text-anchor="middle" class="b tx" font-size="10.5">{esc(label)}</text>"""
    return svg(W, H, css, body, label)


# ---------------------------------------------------------------------- ticker
def ticker(d):
    stamp = datetime.now(timezone.utc).strftime("%d %b %Y").upper()
    css = f"""{font_face('Inter')}{theme_vars()}{BASE_CSS}
    .bar{{fill:var(--sf)}} .edge{{stroke:var(--bd);stroke-width:1}}
    .dot{{fill:var(--ac);animation:pulse 2s ease-in-out infinite}}
    .halo{{fill:var(--ac);opacity:.3;animation:halo 2s ease-in-out infinite}}
    @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.45}}}}
    @keyframes halo{{0%{{opacity:.3;r:4}}70%,100%{{opacity:0;r:11}}}}
    """
    seg = lambda x, label, value: (
        f'<text x="{x}" y="22" class="m lab mu">{label}</text>'
        f'<text x="{x + len(label) * 7.0 + 14:.0f}" y="22" class="m tx" font-size="11">{esc(value)}</text>'
    )
    body = f"""<rect x="0" y="0" width="900" height="34" class="bar"/>
<line x1="0" y1="0.5" x2="900" y2="0.5" class="edge"/><line x1="0" y1="33.5" x2="900" y2="33.5" class="edge"/>
<circle cx="20" cy="17" r="4" class="halo"/><circle cx="20" cy="17" r="3" class="dot"/>
{seg(38, "LAST SHIPPED", d.get("shipped", "—"))}
{seg(380, "NOW", NOW)}
<text x="880" y="22" text-anchor="end" class="m lab mu">REFRESHED {stamp}</text>"""
    return svg(900, 34, css, body, "live status")


# -------------------------------------------------------------------- timeline
def timeline():
    row, top, axis = 68, 60, 214
    H = top + row * len(TIMELINE) + 8
    css = f"""{font_face('Inter')}{theme_vars()}{BASE_CSS}
    .role{{font-size:17px;font-weight:500}}
    .axis{{stroke:var(--bd);stroke-width:1}}
    .node{{fill:var(--sf);stroke:var(--bd);stroke-width:1.5}}
    .live{{fill:var(--ac);stroke:none}}
    """
    rows = []
    for i, (when, org, title, note) in enumerate(TIMELINE):
        y = top + i * row
        node = "node live" if i == 0 else "node"
        rows.append(
            f'<g class="in" style="animation-duration:{.5 + i * .1:.2f}s">'
            f'<text x="34" y="{y + 4}" class="m mu" font-size="10.5" letter-spacing="1.4">{esc(when)}</text>'
            f'<circle cx="{axis}" cy="{y}" r="4.5" class="{node}"/>'
            f'<text x="{axis + 24}" y="{y + 5}" class="b role tx">{esc(org)}</text>'
            f'<text x="{axis + 24}" y="{y + 25}" class="m ac" font-size="10.5" letter-spacing="1.4">{esc(title)}</text>'
            f'<text x="{axis + 24}" y="{y + 43}" class="m mu" font-size="12">{esc(note)}</text></g>'
        )
    body = (
        f'<line x1="{axis}" y1="{top}" x2="{axis}" y2="{top + row * (len(TIMELINE) - 1)}" class="axis"/>'
        + "".join(rows)
    )
    return svg(900, H, css, body, "work timeline")


# --------------------------------------------------------------- illustrations
def load_test():
    """Throughput ramps up while p99 latency holds under the SLA line."""
    x0, x1, y0, y1, sla = 16, 224, 46, 150, 76
    n = 26
    xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
    # deterministic jitter so the drawing doesn't churn the diff every night
    jit = [3.2 * math.sin(i * 1.7) + 2.1 * math.sin(i * .55) for i in range(n)]
    rps = [y1 - (y1 - y0 - 10) * min(1, i / (n * .7)) for i in range(n)]
    p99 = [128 - 10 * min(1, i / (n * .7)) + jit[i] for i in range(n)]
    area = f"M{x0},{y1} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in zip(xs, rps)) + f" L{x1},{y1} Z"
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, p99))
    css = f"""{font_face('Inter')}{theme_vars()}{BASE_CSS}
    .grid{{stroke:var(--grid);stroke-width:1}}
    .sla{{stroke:var(--mu);stroke-width:1;stroke-dasharray:3 3}}
    .rps{{fill:var(--ac);opacity:.14}}
    .p99{{fill:none;stroke:var(--ac);stroke-width:2;stroke-linejoin:round}}
    .wipe{{transform-box:fill-box;transform-origin:left;animation:wipe 6s cubic-bezier(.4,0,.2,1) infinite}}
    .dot{{fill:var(--ac);animation:pulse 1.2s ease-in-out infinite}}
    @keyframes wipe{{0%{{transform:scaleX(0)}}70%,92%{{transform:scaleX(1)}}100%{{transform:scaleX(1);opacity:0}}}}
    @keyframes pulse{{50%{{opacity:.25}}}}
    """
    grid = "".join(
        f'<line x1="{x0}" y1="{y:.0f}" x2="{x1}" y2="{y:.0f}" class="grid"/>'
        for y in (y0, (y0 + y1) / 2, y1)
    )
    body = f"""<rect x=".5" y=".5" width="239" height="179" rx="10" class="card"/>
<text x="16" y="26" class="m lab mu">LOAD TEST · RAMP</text>
<text x="224" y="26" text-anchor="end" class="b ac" font-size="11" font-weight="600">p99 42 ms</text>
<defs><clipPath id="c"><rect x="{x0}" y="0" width="{x1 - x0 + 4}" height="180" class="wipe"/></clipPath></defs>
{grid}
<line x1="{x0}" y1="{sla}" x2="{x1}" y2="{sla}" class="sla"/>
<text x="{x0}" y="{sla - 5}" class="m mu" font-size="8">SLA 100 ms</text>
<g clip-path="url(#c)"><path d="{area}" class="rps"/><path d="{line}" class="p99"/>
<circle cx="{xs[-1]:.1f}" cy="{p99[-1]:.1f}" r="3" class="dot"/></g>
<text x="{x0}" y="166" class="m mu" font-size="8">0 rps</text>
<text x="{x1}" y="166" text-anchor="end" class="m mu" font-size="8">10k rps</text>"""
    return svg(240, 180, css, body, "Load test: throughput ramps while p99 latency stays under SLA")


FLAME = [  # (row, start, width, frame, on the hot path)
    (0, 0, 208, "main", False),
    (1, 0, 132, "handle_request", True),
    (1, 134, 74, "gc", False),
    (2, 0, 92, "serialize", True),
    (2, 94, 38, "db.query", False),
    (2, 134, 50, "mark", False),
    (3, 0, 70, "json.dumps", True),
    (3, 94, 30, "pool", False),
    (3, 134, 28, "sweep", False),
    (4, 0, 52, "encode", True),
    (4, 54, 14, "", False),
    (5, 0, 30, "utf8", True),
]


def flame_graph():
    """CPU profile that stacks up frame by frame, hot path in the accent colour."""
    x0, base, h = 16, 158, 18
    css = f"""{font_face('Inter')}{theme_vars()}{BASE_CSS}
    .fr{{fill:var(--grid);stroke:var(--sf);stroke-width:1}}
    .hot{{fill:var(--ac)}}
    .lbl{{font-size:8.5px;fill:var(--tx)}} .lbl.on{{fill:var(--on)}}
    .st{{opacity:0;animation:stack 6s ease-out infinite}}
    .glow{{animation:pulse 1.4s ease-in-out infinite}}
    @keyframes stack{{0%{{opacity:0;transform:translateY(6px)}}8%,88%{{opacity:1;transform:none}}100%{{opacity:0}}}}
    @keyframes pulse{{50%{{opacity:.7}}}}
    @media(prefers-reduced-motion:reduce){{.st{{opacity:1}}}}
    """
    frames = []
    for row, start, w, name, hot in FLAME:
        y = base - (row + 1) * h
        label = name if len(name) * 5.2 < w - 6 else ""
        frames.append(
            f'<g class="st" style="animation-delay:{row * .35:.2f}s">'
            f'<rect x="{x0 + start}" y="{y}" width="{w}" height="{h - 1}" rx="2" class="fr{" hot glow" if hot else ""}"/>'
            + (f'<text x="{x0 + start + 5}" y="{y + 12}" class="m lbl{" on" if hot else ""}">{esc(label)}</text>' if label else "")
            + "</g>"
        )
    body = f"""<rect x=".5" y=".5" width="239" height="179" rx="10" class="card"/>
<text x="16" y="26" class="m lab mu">CPU PROFILE</text>
<text x="224" y="26" text-anchor="end" class="b ac" font-size="11" font-weight="600">hot path 38%</text>
{"".join(frames)}
<text x="16" y="172" class="m mu" font-size="8">flame graph · sampled 99 Hz</text>"""
    return svg(240, 180, css, body, "CPU flame graph with the hot path highlighted")


# ------------------------------------------------------------------- oss chips
def oss_chip(org, name, what):
    W, H = 196, 58
    css = f"""{theme_vars()}{BASE_CSS}"""
    logo_path = ASSETS / "logos" / f"{org}.png"
    img_tag = ""
    if logo_path.exists():
        img_tag = (
            f'<image href="{b64(logo_path, "image/png")}" x="14" y="15" width="28" height="28" '
            f'clip-path="url(#c)" preserveAspectRatio="xMidYMid slice"/>'
        )
    body = f"""<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="5" class="card"/>
<clipPath id="c"><rect x="14" y="15" width="28" height="28" rx="6"/></clipPath>
<rect x="14" y="15" width="28" height="28" rx="6" fill="#ffffff"/>
{img_tag}
<text x="54" y="29" class="b tx" font-size="12.5">{esc(name)}</text>
<text x="54" y="42" class="m lab mu">{esc(what.upper())}</text>"""
    return svg(W, H, css, body, f"{name} — {what}")


# -------------------------------------------------------------------- activity
def activity(d):
    W, H = 900, 250
    days, vals = [x[0] for x in d["days"]], [x[1] for x in d["days"]]
    peak = max(vals) or 1
    x0, x1, base, top = 34, W - 34, 200, 76
    step = (x1 - x0) / max(len(vals) - 1, 1)
    pts = [(x0 + i * step, base - (v / peak) * (base - top)) for i, v in enumerate(vals)]
    line = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    area = f"{line} L{pts[-1][0]:.1f} {base} L{pts[0][0]:.1f} {base} Z"

    grid = []
    for frac in (0.25, 0.5, 0.75, 1.0):
        y = base - frac * (base - top)
        val = int(peak * frac)
        grid.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" class="grid"/>')
        grid.append(f'<text x="{x0 - 8}" y="{y + 3:.1f}" text-anchor="end" class="m lab mu">{val}</text>')

    ticks, seen = [], None
    for i, iso in enumerate(days):
        if iso[:7] != seen:
            seen = iso[:7]
            x = x0 + i * step
            if x < x1 - 20:
                ticks.append(f'<line x1="{x:.1f}" y1="{base}" x2="{x:.1f}" y2="{base + 4}" class="grid"/>')
                ticks.append(
                    f'<text x="{x:.1f}" y="{base + 18}" text-anchor="middle" class="m lab mu">'
                    f'{datetime.strptime(iso, "%Y-%m-%d").strftime("%b").upper()}</text>'
                )

    css = f"""{font_face('Inter')}{theme_vars()}{BASE_CSS}
    .grid{{stroke:var(--grid);stroke-width:1}}
    .spark{{fill:none;stroke:var(--ac);stroke-width:1.6;stroke-linejoin:round;
      stroke-dasharray:4200;animation:trace 2.4s cubic-bezier(.3,.6,.2,1) forwards}}
    .fill{{fill:var(--ac);opacity:.12;animation:fade 1.8s forwards}}
    @keyframes trace{{from{{stroke-dashoffset:4200}}to{{stroke-dashoffset:0}}}}
    @keyframes fade{{from{{opacity:0}}to{{opacity:.12}}}}
    """
    body = f"""<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="6" class="card"/>
<rect x="34" y="34" width="3" height="10" class="ac"/>
<text x="46" y="43" class="m kick ac">LAST 12 MONTHS</text>
<text x="{W - 34}" y="43" text-anchor="end" class="m lab mu">{len(days)} DAYS · PEAK {peak}/DAY</text>
{''.join(grid)}
<path d="{area}" class="fill"/><path d="{line}" class="spark"/>
<line x1="{x0}" y1="{base}.5" x2="{x1}" y2="{base}.5" class="grid"/>
{''.join(ticks)}"""
    return svg(W, H, css, body, "daily contribution activity")


def number_row(cols, width, y_num=104, pad=34):
    """Five big numbers with two label lines, evenly spread."""
    step = (width - pad * 2) / len(cols)
    out = []
    for i, (n, l1, l2) in enumerate(cols):
        x = pad + i * step
        out.append(
            f'<g class="in" style="animation-duration:{.5 + i * .12:.2f}s">'
            f'<text x="{x:.0f}" y="{y_num}" class="d tx" font-size="40">{n}</text>'
            f'<text x="{x:.0f}" y="{y_num + 18}" class="m lab ac">{l1}</text>'
            f'<text x="{x:.0f}" y="{y_num + 32}" class="m lab mu">{l2}</text></g>'
        )
    return "".join(out)


# ----------------------------------------------------------------------- stats
def stats(d):
    W, H = 900, 196
    cols = [
        (f'{d["total"]:,}', "CONTRIBUTIONS", "LAST 52 WEEKS"),
        (f'{d["peak_week"]}', "BUSIEST WEEK", "CONTRIBUTIONS"),
        (f'{d["repos"]}', "PUBLIC REPOS", "AUTHORED"),
        (f'{d["stars"]}', "STARS", "EARNED"),
        (f"{len(OSS)}", "UPSTREAM", "PROJECTS FILED"),
    ]
    total = sum(c for _, c in d["langs"]) or 1
    bar, lx, legend, last = [], 34, [], -999
    for i, (name, count) in enumerate(d["langs"]):
        w = (W - 68) * count / total
        pct = count * 100 // total
        bar.append(
            f'<rect x="{lx:.1f}" y="160" width="{max(w - 2, 1):.1f}" height="6" rx="1" class="ac" '
            f'style="opacity:{1 - i * .22:.2f};transform-origin:left;'
            f'animation:grow {.6 + i * .12:.2f}s cubic-bezier(.2,.7,.2,1) forwards"/>'
        )
        if pct >= 5 and lx - last > 100:
            legend.append((lx, f"{name.upper()} {pct}%"))
            last = lx
        lx += w
    for x, t in legend:
        bar.append(f'<text x="{x:.1f}" y="182" class="m lab mu">{t}</text>')

    css = f"""{font_face('Inter')}{theme_vars()}{BASE_CSS}
    @keyframes grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
    """
    body = f"""<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="6" class="card"/>
<rect x="34" y="34" width="3" height="10" class="ac"/>
<text x="46" y="43" class="m kick ac">RECENT</text>
<text x="{W - 34}" y="43" text-anchor="end" class="m lab mu">AUTO-GENERATED NIGHTLY · NOT A BADGE</text>
{number_row(cols, W)}{''.join(bar)}"""
    return svg(W, H, css, body, "last 52 weeks totals and language mix")


# -------------------------------------------------------------------- lifetime
def lifetime(d):
    W, H = 900, 254
    cols = [
        (f'{d["all_time"]:,}', "CONTRIBUTIONS", "ALL TIME"),
        (f'{d["commits"]:,}', "COMMITS", "AUTHORED"),
        (f'{d["prs"]}', "PULL REQUESTS", f'{d["merged"]} MERGED'),
        (f'{d["streak"]}', "LONGEST STREAK", "DAYS"),
        (f'{len(d["per_year"])}', "YEARS", "ON GITHUB"),
    ]

    years = sorted(d["per_year"])
    peak = max(d["per_year"].values()) or 1
    num_years = len(years)
    span = (W - 68) / max(num_years, 1)
    bw = max(min(span * 0.72, 76), 24)
    ybase, ytop = 218, 166
    bars = []
    for i, y in enumerate(years):
        v = d["per_year"][y]
        h = max((v / peak) * (ybase - ytop), 2)
        x = 34 + i * span + (span - bw) / 2
        font_size = 10 if num_years > 8 else 11
        bars.append(
            f'<rect x="{x:.1f}" y="{ybase - h:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="2" class="ac" '
            f'style="opacity:.85;transform-origin:center bottom;'
            f'animation:sprout {.6 + i * .05:.2f}s cubic-bezier(.2,.7,.2,1) forwards"/>'
            f'<text x="{x + bw / 2:.1f}" y="{ybase - h - 7:.1f}" text-anchor="middle" class="m tx" font-size="{font_size}">{v}</text>'
            f'<text x="{x + bw / 2:.1f}" y="{ybase + 17}" text-anchor="middle" class="m lab mu">{y}</text>'
        )

    css = f"""{font_face('Inter')}{theme_vars()}{BASE_CSS}
    .grid{{stroke:var(--grid);stroke-width:1}}
    @keyframes sprout{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
    """
    body = f"""<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="6" class="card"/>
<rect x="34" y="34" width="3" height="10" class="ac"/>
<text x="46" y="43" class="m kick ac">ALL TIME</text>
<text x="{W - 34}" y="43" text-anchor="end" class="m lab mu">CONTRIBUTIONS PER YEAR</text>
{number_row(cols, W)}
<line x1="34" y1="{ybase}.5" x2="{W - 34}" y2="{ybase}.5" class="grid"/>
{''.join(bars)}"""
    return svg(W, H, css, body, "all-time GitHub totals by year")


def main():
    print("Collecting telemetry from GitHub...")
    d = collect()
    for sub in ("links", "oss", "stack"):
        (ASSETS / sub).mkdir(parents=True, exist_ok=True)

    written = []

    def put(rel, markup):
        target = ASSETS / rel
        target.write_text(markup, encoding="utf-8")
        written.append((rel, len(markup)))

    print("Rendering SVG assets...")
    put("header.svg", header())
    put("ticker.svg", ticker(d))
    put("timeline.svg", timeline())
    put("loadtest.svg", load_test())
    put("flamegraph.svg", flame_graph())
    put("activity.svg", activity(d))
    put("stats.svg", stats(d))
    put("lifetime.svg", lifetime(d))

    for label, _url, filled in LINKS:
        norm = label.lower().replace("é", "e").replace(" ", "")
        put(f"links/{norm}.svg", link_chip(label, filled))
    for org, name, what in OSS:
        put(f"oss/{org}.svg", oss_chip(org, name, what))
    for slug, label in STACK:
        put(f"stack/{slug}.svg", stack_badge(slug, label))

    print("\nGenerated assets:")
    for name, size in written:
        print(f"  {name:<30} {size / 1024:6.1f} KB")
    print(
        f"\n52wk={d['total']} peak_week={d['peak_week']} | all_time={d['all_time']} "
        f"commits={d['commits']} prs={d['prs']}/{d['merged']} streak={d['streak']}\n"
        f"per_year={dict(sorted(d['per_year'].items()))}"
    )


if __name__ == "__main__":
    main()
