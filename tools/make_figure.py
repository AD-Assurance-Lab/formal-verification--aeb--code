"""PROTOCOL section 11's figure, generated from the result files.

    python tools/make_figure.py --scenario lead

Writes `docs/figures/dusk_gap_data.json` and `docs/figures/dusk_gap.html`.

**Why this is a tool and not a hand-built page.** The figure that shipped with iteration 2
had its numbers typed into a `const D = [...]` inside the HTML. Nothing tied them to
`results/carla/*.json`, nothing would notice if a verdict changed underneath them, and the
standing rule is that a number in a paper comes from a committed invocation. Section 11
calls this plot the thing that decides whether the work travels, which makes it the last
artifact that should be maintained by hand.

**What it refuses to do.** It will not plot a certified margin for a sub-interval the
disturbance family cannot represent. A6 declares the horizon sliver uncovered, and a
CERTIFIED verdict there is a statement about blends that do not correspond to any render.
Those sub-intervals are drawn hatched and excluded from every headline count, because the
alternative -- a bar that looks like all the others -- is the figure quietly claiming
coverage the study does not have.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.REPO / "results" / "carla"
FIGS = J.REPO / "docs" / "figures"
POLICIES = ["P_pts", "P_cont"]


def load(scenario: str) -> tuple[list[dict], dict]:
    """One row per sub-interval, with both policies' margin and driven outcome."""
    verify, witness = {}, {}
    for pol in POLICIES:
        vpath = OUT / f"verify_{pol}_{scenario}.json"
        if not vpath.exists():
            raise SystemExit(f"missing {vpath.relative_to(J.REPO)}; run tools/verify.py")
        verify[pol] = json.loads(vpath.read_text())
        wpath = OUT / f"witness_{pol}_{scenario}.json"
        witness[pol] = json.loads(wpath.read_text()) if wpath.exists() else None

    ref = verify[POLICIES[0]]["cells"]
    for pol in POLICIES[1:]:
        other = verify[pol]["cells"]
        if len(other) != len(ref) or any(
            abs(a["from_deg"] - b["from_deg"]) > 1e-6 for a, b in zip(ref, other)
        ):
            raise SystemExit(
                f"{POLICIES[0]} and {pol} were certified over DIFFERENT sub-intervals; "
                "they are not comparable and must not share a chart. Re-run verify for "
                "both against the same tools/build_family_knots.py output.")

    rows = []
    for i, cell in enumerate(ref):
        mid = (cell["from_deg"] + cell["to_deg"]) / 2.0
        row = {
            "from_deg": cell["from_deg"],
            "to_deg": cell["to_deg"],
            "mid_deg": round(mid, 3),
            "family_uncovered": bool(cell.get("family_uncovered")),
        }
        for pol in POLICIES:
            c = verify[pol]["cells"][i]
            row[pol] = {
                "margin": c["margin_x_threshold"],
                "verdict": c["verdict"],
                "witness_range_m": c.get("witness_range_m"),
            }
            w = witness[pol]
            if w is not None:
                wc = next(
                    (r for r in w["cells"]
                     if abs(r["from_deg"] - cell["from_deg"]) < 1e-6), None)
                if wc is not None:
                    # PROTOCOL section 7's frozen criterion. See the note in
                    # tools/record_cells.py: prematurity is property A, not property S.
                    row[pol]["drove"] = wc.get("passes_protocol", wc["passes"])
                    row[pol]["of"] = wc["of"]
                    row[pol]["agrees"] = wc["agrees"]
                    row[pol]["premature"] = wc.get("premature", 0)
                    row[pol]["contacts"] = wc.get("contacts")
        rows.append(row)

    covered = [r for r in rows if not r["family_uncovered"]]
    meta = {
        "scenario": scenario,
        "threshold_mps2": verify[POLICIES[0]]["threshold_mps2"],
        "r_req_m": verify[POLICIES[0]]["r_req_m"],
        "poses_inside_r_req": verify[POLICIES[0]]["poses_inside_r_req"],
        "sub_intervals": len(rows),
        "sub_intervals_covered": len(covered),
        "sub_intervals_uncovered": len(rows) - len(covered),
        "agreement": {
            pol: (witness[pol]["agreement"] if witness[pol] else None) for pol in POLICIES
        },
        "model_sha256": {pol: verify[pol].get("model_sha256") for pol in POLICIES},
    }
    return rows, meta


def summarise(rows: list[dict], meta: dict) -> dict:
    """The sentences the page states, derived here rather than written by hand."""
    covered = [r for r in rows if not r["family_uncovered"]]
    out = {}
    for pol in POLICIES:
        fals = [r for r in covered if r[pol]["verdict"] == "FALSIFIED"]
        width = sum(r["from_deg"] - r["to_deg"] for r in fals)
        driven = [r for r in covered if "drove" in r[pol]]
        out[pol] = {
            "certified": sum(1 for r in covered if r[pol]["verdict"] == "CERTIFIED"),
            "of_covered": len(covered),
            "falsified_width_deg": round(width, 3),
            "clean_drives": sum(1 for r in driven if r[pol]["drove"] == r[pol]["of"]),
            "driven_cells": len(driven),
            # The direction of every disagreement is the number a safety audience reads
            # first: a certificate that clears something which then fails is a different
            # kind of tool from one that flags something which then drives.
            "certified_then_failed": sum(
                1 for r in driven
                if r[pol]["verdict"] == "CERTIFIED" and r[pol]["drove"] < r[pol]["of"]),
            "falsified_then_drove_clean": sum(
                1 for r in driven
                if r[pol]["verdict"] == "FALSIFIED" and r[pol]["drove"] == r[pol]["of"]),
        }
    return out


def render_html(rows, meta, summary, scenario: str) -> str:
    data = []
    for r in rows:
        d = {"mid": f"{r['mid_deg']:+.2f}".rstrip("0").rstrip("."),
             "unc": r["family_uncovered"]}
        for pol, key in (("P_pts", "pts"), ("P_cont", "cont")):
            d[key] = r[pol]["margin"]
            d[key + "D"] = r[pol].get("drove")
            d[key + "N"] = r[pol].get("of")
        data.append(d)

    pts, cont = summary["P_pts"], summary["P_cont"]
    scen_word = "stopped lead vehicle" if scenario == "lead" else "crossing pedestrian"
    lede = (
        f"<b>P_pts</b> passes both regulatory lighting conditions and is falsified across "
        f"<b>{pts['falsified_width_deg']:.1f}°</b> of sun altitude between them. "
        f"<b>P_cont</b>, identical but for how the illumination axis was sampled, is "
        f"falsified across {cont['falsified_width_deg']:.1f}°."
    )
    unc_note = ""
    if meta["sub_intervals_uncovered"]:
        bad = [r for r in rows if r["family_uncovered"]]
        spans = ", ".join(f"{r['from_deg']:+.3f}° to {r['to_deg']:+.3f}°" for r in bad)
        unc_note = (
            f"<li><b>{meta['sub_intervals_uncovered']} sub-interval is declared "
            f"uncovered</b> ({spans}). The blend cannot represent the horizon at any "
            f"width, so a bound there quantifies over images the simulator would never "
            f"render. Drawn hatched, and excluded from every count on this page.</li>")

    agree_note = ""
    if any(meta["agreement"].values()):
        parts = [f"{p} {meta['agreement'][p]}" for p in POLICIES if meta["agreement"][p]]
        direction = (
            "Nothing was certified and then failed."
            if pts["certified_then_failed"] == 0 and cont["certified_then_failed"] == 0
            else f"{pts['certified_then_failed'] + cont['certified_then_failed']} "
                 f"sub-interval(s) were certified and then failed, which is the "
                 f"unsafe direction and is the finding.")
        agree_note = (
            f"<li><b>Certificate against driving:</b> {', '.join(parts)} sub-intervals "
            f"agree. {direction}</li>")

    return TEMPLATE.replace("__DATA__", json.dumps(data)) \
                   .replace("__LEDE__", lede) \
                   .replace("__UNC__", unc_note) \
                   .replace("__AGREE__", agree_note) \
                   .replace("__SCEN__", html.escape(scen_word)) \
                   .replace("__RREQ__", f"{meta['r_req_m'] * J.FT:.1f}") \
                   .replace("__NPOSE__", str(meta["poses_inside_r_req"])) \
                   .replace("__NSUB__", str(meta["sub_intervals"]))


TEMPLATE = r"""<title>The Dusk Gap</title>
<style>
  .viz-root {
    color-scheme: light;
    --surface-1: #fcfcfb; --surface-2: #f3f2ef;
    --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #7b7a75;
    --rule: #dedcd6; --series-1: #2a78d6; --series-2: #eb6834; --band: #f0efec;
  }
  @media (prefers-color-scheme: dark) {
    :root:where(:not([data-theme="light"])) .viz-root {
      color-scheme: dark;
      --surface-1: #1a1a19; --surface-2: #232322;
      --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8e8d84;
      --rule: #3a3a37; --series-1: #3987e5; --series-2: #d95926; --band: #262624;
    }
  }
  :root[data-theme="dark"] .viz-root {
    color-scheme: dark;
    --surface-1: #1a1a19; --surface-2: #232322;
    --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8e8d84;
    --rule: #3a3a37; --series-1: #3987e5; --series-2: #d95926; --band: #262624;
  }
  body { margin: 0; background: var(--surface-1); }
  .viz-root {
    background: var(--surface-1); color: var(--text-primary);
    font: 15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    padding: 32px 24px 56px; max-width: 1000px; margin: 0 auto;
  }
  h1 { font-size: 27px; line-height: 1.2; margin: 0 0 6px; letter-spacing: -0.01em; }
  .sub { color: var(--text-secondary); margin: 0 0 28px; max-width: 66ch; }
  .lede { border-left: 3px solid var(--series-1); padding: 2px 0 2px 16px;
          margin: 0 0 30px; font-size: 17px; max-width: 62ch; }
  .lede b { font-weight: 650; }
  h2 { font-size: 15px; margin: 30px 0 2px; letter-spacing: 0.01em; }
  .cap { color: var(--text-muted); font-size: 13px; margin: 0 0 10px; max-width: 74ch; }
  .legend { display: flex; gap: 20px; align-items: center; margin: 0 0 6px; flex-wrap: wrap; }
  .key { display: flex; gap: 7px; align-items: center; font-size: 13px;
         color: var(--text-secondary); }
  .sw { width: 13px; height: 13px; border-radius: 3px; }
  .wrap { overflow-x: auto; }
  svg { display: block; min-width: 720px; width: 100%; height: auto; }
  text { fill: var(--text-secondary); font: 11px ui-sans-serif, system-ui, sans-serif; }
  text.axl { fill: var(--text-muted); font-size: 11px; }
  text.dlab { fill: var(--text-primary); font-size: 11px; font-weight: 600; }
  details { margin-top: 26px; border-top: 1px solid var(--rule); padding-top: 14px; }
  summary { cursor: pointer; font-size: 14px; color: var(--text-secondary); }
  table { border-collapse: collapse; margin-top: 12px; font-size: 13px; width: 100%; }
  th, td { text-align: right; padding: 5px 10px; border-bottom: 1px solid var(--rule); }
  th:first-child, td:first-child { text-align: left; }
  ul.notes { padding-left: 18px; max-width: 74ch; }
  ul.notes li { margin: 8px 0; color: var(--text-secondary); }
  ul.notes b { color: var(--text-primary); font-weight: 620; }
  #tip { position: fixed; pointer-events: none; opacity: 0; transition: opacity .1s;
         background: var(--surface-2); border: 1px solid var(--rule); border-radius: 7px;
         padding: 7px 10px; font: 12px/1.45 ui-sans-serif, system-ui, sans-serif;
         color: var(--text-primary); max-width: 260px; z-index: 9; }
</style>
<div class="viz-root">
  <h1>The dusk gap</h1>
  <p class="sub">A camera-only AEB policy on the __SCEN__ scenario, certified over every
  illumination between two mandated test conditions, then driven at the illuminations the
  certificate names. Required braking range __RREQ__ ft; __NPOSE__ poses inside it;
  __NSUB__ sub-intervals of sun altitude.</p>

  <p class="lede">__LEDE__</p>

  <div class="legend">
    <span class="key"><span class="sw" style="background:var(--series-1)"></span>
      P_pts &middot; trained on the regulatory test points only</span>
    <span class="key"><span class="sw" style="background:var(--series-2)"></span>
      P_cont &middot; trained on the illumination continuum</span>
  </div>

  <h2>Certified margin, per sub-interval</h2>
  <p class="cap">Lower bound on commanded deceleration, as a multiple of the brake decision
  threshold. At or above 1.0 the policy is certified to brake in time for every illumination
  in that sub-interval. Below it, it is not.</p>
  <div class="wrap"><svg id="s1" viewBox="0 0 900 300" role="img"
    aria-label="Certified margin by sub-interval for two policies"></svg></div>

  <h2>Driven outcome, ten runs per sub-interval</h2>
  <p class="cap">Closed-loop runs at each sub-interval's midpoint illumination, a rendered
  condition rather than an interpolation. Certified sub-intervals were driven too, so the
  chart can distinguish a working certificate from one that flags everything.</p>
  <div class="wrap"><svg id="s2" viewBox="0 0 900 230" role="img"
    aria-label="Driven pass rate out of ten by sub-interval for two policies"></svg></div>

  <details>
    <summary>Table view</summary>
    <table id="tbl"><thead><tr>
      <th>Sub-interval midpoint</th>
      <th>P_pts margin</th><th>P_pts drove</th>
      <th>P_cont margin</th><th>P_cont drove</th>
    </tr></thead><tbody></tbody></table>
  </details>

  <details open>
    <summary>What this does and does not establish</summary>
    <ul class="notes">
      <li><b>The control is what makes it mean something.</b> The two policies share
      architecture, training recipe and sample count. Only the illumination levels they saw
      differ, so the gap is attributable to how that axis was sampled.</li>
      __AGREE__
      __UNC__
      <li><b>Scope.</b> Simulation only, one map, one site, one speed, one vehicle, camera
      only. This is a subset of FMVSS 127 scenarios and is not a compliance
      demonstration.</li>
      <li><b>Generated</b> by <code>tools/make_figure.py</code> from
      <code>results/carla/verify_*.json</code> and <code>witness_*.json</code>. No number
      on this page is typed by hand.</li>
    </ul>
  </details>
</div>
<div id="tip" role="status"></div>

<script>
const D = __DATA__;
const tip = document.getElementById('tip');
const fmt = v => (v < 0 ? "−" : "") + Math.abs(v).toFixed(2);

function show(e, html) {
  tip.innerHTML = html; tip.style.opacity = 1;
  const x = Math.min(e.clientX + 14, innerWidth - 272);
  tip.style.left = x + 'px'; tip.style.top = (e.clientY + 16) + 'px';
}
function hide() { tip.style.opacity = 0; }

function svgEl(n, a) {
  const e = document.createElementNS('http://www.w3.org/2000/svg', n);
  for (const k in a) e.setAttribute(k, a[k]);
  return e;
}

// A sub-interval the disturbance family cannot represent is drawn hatched, so it cannot
// be read as a bar like the others. It is excluded from every count in the prose.
function defsOnce(svg) {
  if (svg.querySelector('defs')) return;
  const defs = svgEl('defs', {});
  const pat = svgEl('pattern', {id: 'unc' + svg.id, width: 6, height: 6,
    patternUnits: 'userSpaceOnUse', patternTransform: 'rotate(45)'});
  pat.appendChild(svgEl('rect', {width: 6, height: 6, fill: 'var(--band)'}));
  pat.appendChild(svgEl('line', {x1: 0, y1: 0, x2: 0, y2: 6,
    stroke: 'var(--text-muted)', 'stroke-width': 2}));
  defs.appendChild(pat); svg.appendChild(defs);
}

function uncoveredBands(svg, L, R, T, B) {
  const w = (R - L) / D.length;
  D.forEach((d, i) => {
    if (!d.unc) return;
    svg.appendChild(svgEl('rect', {x: L + i * w, y: T, width: w, height: B - T,
      fill: 'url(#unc' + svg.id + ')', opacity: 0.55}));
  });
}

function tickLabel(svg, cx, yy, txt) {
  const t = svgEl('text', {x: cx, y: yy, class: 'tick', 'text-anchor': 'end',
    transform: `rotate(-55 ${cx} ${yy})`});
  t.textContent = txt; svg.appendChild(t);
}

function drawMargins() {
  const svg = document.getElementById('s1');
  defsOnce(svg);
  const L = 58, R = 884, T = 16, B = 236;
  const vals = D.flatMap(d => [d.pts, d.cont]);
  const yMax = Math.max(2.0, Math.ceil(Math.max(...vals) * 2) / 2);
  const yMin = Math.min(-0.45, Math.floor(Math.min(...vals) * 2) / 2);
  const y = v => B - (v - yMin) / (yMax - yMin) * (B - T);
  uncoveredBands(svg, L, R, T, B);

  for (let g = Math.ceil(yMin * 2) / 2; g <= yMax + 1e-9; g += 0.5) {
    svg.appendChild(svgEl('line', {x1: L, x2: R, y1: y(g), y2: y(g),
      stroke: 'var(--rule)', 'stroke-width': Math.abs(g - 1) < 1e-9 ? 0 : 1}));
    const t = svgEl('text', {x: L - 9, y: y(g) + 4, class: 'tick', 'text-anchor': 'end'});
    t.textContent = g.toFixed(1); svg.appendChild(t);
  }
  svg.appendChild(svgEl('line', {x1: L, x2: R, y1: y(1), y2: y(1),
    stroke: 'var(--text-secondary)', 'stroke-width': 2, 'stroke-dasharray': '6 4'}));
  const th = svgEl('text', {x: R, y: y(1) - 7, class: 'axl', 'text-anchor': 'end'});
  th.textContent = 'certified at or above 1.0'; svg.appendChild(th);

  const w = (R - L) / D.length, bw = Math.min(17, w * 0.31), gap = 2;
  D.forEach((d, i) => {
    const cx = L + (i + 0.5) * w;
    [['pts', 'var(--series-1)', -1], ['cont', 'var(--series-2)', 1]].forEach(([k, c, s]) => {
      const v = d[k], top = Math.min(y(v), y(0)), h = Math.abs(y(v) - y(0));
      const x = cx + (s < 0 ? -bw - gap / 2 : gap / 2);
      const r = svgEl('rect', {x, y: top, width: bw, height: Math.max(h, 1.5), rx: 4,
        fill: c, opacity: d.unc ? 0.35 : 1});
      r.addEventListener('mousemove', e => show(e,
        `<b>${k === 'pts' ? 'P_pts' : 'P_cont'}</b> &middot; midpoint ${d.mid}°<br>` +
        `certified margin <b>${fmt(v)}×</b> threshold<br>` +
        (d.unc ? 'family UNCOVERED here; not counted' :
          `${v >= 1 ? 'certified' : 'falsified'}` +
          (d[k + 'D'] === null || d[k + 'D'] === undefined ? '' :
            ` &middot; drove ${d[k + 'D']}/${d[k + 'N']}`))));
      r.addEventListener('mouseleave', hide);
      svg.appendChild(r);
    });
    tickLabel(svg, cx, B + 15, d.mid);
  });
  svg.appendChild(svgEl('line', {x1: L, x2: R, y1: y(0), y2: y(0),
    stroke: 'var(--rule)', 'stroke-width': 1}));
  const ax = svgEl('text', {x: (L + R) / 2, y: 293, class: 'axl', 'text-anchor': 'middle'});
  ax.textContent = 'sun altitude at the sub-interval midpoint (degrees)';
  svg.appendChild(ax);
  const ay = svgEl('text', {x: 14, y: (T + B) / 2, class: 'axl',
    'text-anchor': 'middle', transform: `rotate(-90 14 ${(T + B) / 2})`});
  ay.textContent = '× decision threshold'; svg.appendChild(ay);
}

function drawDriven() {
  const svg = document.getElementById('s2');
  defsOnce(svg);
  const L = 58, R = 884, T = 16, B = 166;
  const N = Math.max(...D.map(d => d.ptsN || d.contN || 10));
  const y = v => B - v / N * (B - T);
  uncoveredBands(svg, L, R, T, B);
  [0, N / 2, N].forEach(g => {
    svg.appendChild(svgEl('line', {x1: L, x2: R, y1: y(g), y2: y(g),
      stroke: 'var(--rule)', 'stroke-width': 1}));
    const t = svgEl('text', {x: L - 9, y: y(g) + 4, class: 'tick', 'text-anchor': 'end'});
    t.textContent = g; svg.appendChild(t);
  });
  const w = (R - L) / D.length;
  D.forEach((d, i) => {
    const cx = L + (i + 0.5) * w;
    [['ptsD', 'var(--series-1)', -1], ['contD', 'var(--series-2)', 1]].forEach(([k, c, s]) => {
      const v = d[k];
      if (v === null || v === undefined) return;   // not driven yet: draw nothing
      const px = cx + s * 7;
      svg.appendChild(svgEl('line', {x1: px, x2: px, y1: y(0), y2: y(v),
        stroke: c, 'stroke-width': 2, opacity: .45}));
      const g = svgEl('circle', {cx: px, cy: y(v), r: 6, fill: c,
        stroke: 'var(--surface-1)', 'stroke-width': 2});
      g.addEventListener('mousemove', e => show(e,
        `<b>${k === 'ptsD' ? 'P_pts' : 'P_cont'}</b> &middot; midpoint ${d.mid}°<br>` +
        `drove <b>${v}/${N}</b>`));
      g.addEventListener('mouseleave', hide);
      svg.appendChild(g);
      if (v < N) {
        const t = svgEl('text', {x: px, y: y(v) - 11, class: 'dlab', 'text-anchor': 'middle'});
        t.textContent = v + '/' + N; svg.appendChild(t);
      }
    });
    tickLabel(svg, cx, B + 15, d.mid);
  });
  const ay = svgEl('text', {x: 14, y: (T + B) / 2, class: 'axl',
    'text-anchor': 'middle', transform: `rotate(-90 14 ${(T + B) / 2})`});
  ay.textContent = 'runs passed'; svg.appendChild(ay);
  const ax = svgEl('text', {x: (L + R) / 2, y: 223, class: 'axl', 'text-anchor': 'middle'});
  ax.textContent = 'sun altitude at the sub-interval midpoint (degrees)';
  svg.appendChild(ax);
}

function table() {
  const b = document.querySelector('#tbl tbody');
  const dr = (v, n) => (v === null || v === undefined) ? '—' : v + '/' + n;
  D.forEach(d => {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${d.mid}°${d.unc ? ' (uncovered)' : ''}</td>` +
                   `<td>${fmt(d.pts)}</td><td>${dr(d.ptsD, d.ptsN)}</td>` +
                   `<td>${fmt(d.cont)}</td><td>${dr(d.contD, d.contN)}</td>`;
    b.appendChild(tr);
  });
}

drawMargins(); drawDriven(); table();
</script>
"""



def render_svg(rows, meta, summary, scenario: str) -> str:
    """A STATIC svg of the same two panels, with no JavaScript.

    The HTML page builds its charts in the browser, which is right for reading it and
    useless for a README, a slide or a paper: GitHub renders an <img> and runs nothing.
    So the same numbers are drawn again here, server-side. Both come from the same `rows`,
    so they cannot disagree.
    """
    W, TOP_H, GAP, BOT_H, PAD_B = 980, 300, 26, 210, 54
    H = TOP_H + GAP + BOT_H + PAD_B
    L, R = 66, W - 24
    n = len(rows)
    cw = (R - L) / n
    bw = min(16.0, cw * 0.30)

    # Scale to the COVERED sub-intervals. An uncovered one is excluded from every claim
    # on the page, so letting its bound set the axis would compress the range a reader is
    # meant to read in order to show a number that does not count. Its bar is still drawn,
    # clamped to the plot area, inside its hatched column.
    margins = [r[p]["margin"] for r in rows for p in POLICIES
               if not r["family_uncovered"]] or \
              [r[p]["margin"] for r in rows for p in POLICIES]
    y_max = max(2.0, (int(max(margins) * 2) + 1) / 2)
    y_min = min(-0.5, (int(min(margins) * 2) - 1) / 2)

    def ym(v):
        return 20 + (y_max - v) / (y_max - y_min) * (TOP_H - 60)

    reps = max((r[p].get("of") or 10) for r in rows for p in POLICIES)
    dy0, dy1 = TOP_H + GAP + 18, TOP_H + GAP + BOT_H - 34

    def yd(v):
        return dy1 - (v / reps) * (dy1 - dy0)

    C1, C2 = "#2a78d6", "#eb6834"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
        f'role="img" aria-label="Certified margin and driven outcome by sub-interval">',
        # No media queries and no theme switching. This file is meant to be embedded
        # with <img> in a README and dropped into a slide, and both strip or ignore
        # stylesheet features unpredictably. One light rendering that looks the same
        # everywhere beats two that sometimes do.
        '<style>'
        'text{font:12px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;fill:#52514e}'
        '.t{font-size:14px;font-weight:600;fill:#0b0b0b}'
        '.s{font-size:11px;fill:#7b7a75}'
        '.v{font-size:11px;font-weight:600;fill:#0b0b0b}'
        '</style>',
        '<defs><pattern id="unc" width="6" height="6" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" '
        'stroke="#b9b8b2" stroke-width="2"/></pattern></defs>',
        f'<rect class="bg" width="{W}" height="{H}" fill="#fcfcfb"/>',
    ]

    for i, r in enumerate(rows):
        if r["family_uncovered"]:
            out.append(f'<rect x="{L + i * cw:.1f}" y="14" width="{cw:.1f}" '
                       f'height="{TOP_H - 46:.1f}" fill="url(#unc)" opacity="0.5"/>')
            out.append(f'<rect x="{L + i * cw:.1f}" y="{dy0 - 4:.1f}" width="{cw:.1f}" '
                       f'height="{dy1 - dy0 + 8:.1f}" fill="url(#unc)" opacity="0.5"/>')

    out.append(f'<text class="t" x="{L}" y="14">Certified margin, '
               f'× brake decision threshold — certified at or above 1.0</text>')
    g = y_min
    while g <= y_max + 1e-9:
        out.append(f'<line class="gr" x1="{L}" x2="{R}" y1="{ym(g):.1f}" '
                   f'y2="{ym(g):.1f}" stroke="#dedcd6" stroke-width="1"/>')
        out.append(f'<text class="s" x="{L - 8}" y="{ym(g) + 4:.1f}" '
                   f'text-anchor="end">{g:.1f}</text>')
        g += 0.5
    out.append(f'<line x1="{L}" x2="{R}" y1="{ym(1):.1f}" y2="{ym(1):.1f}" '
               f'stroke="#52514e" stroke-width="2" stroke-dasharray="6 4"/>')

    for i, r in enumerate(rows):
        cx = L + (i + 0.5) * cw
        for pol, colour, side in ((POLICIES[0], C1, -1), (POLICIES[1], C2, 1)):
            v = r[pol]["margin"]
            top, bot = min(ym(v), ym(0)), max(ym(v), ym(0))
            top, bot = max(top, 18.0), min(bot, float(TOP_H - 46))  # clamp to the panel
            x = cx + (-bw - 1 if side < 0 else 1)
            out.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" '
                       f'height="{max(bot - top, 1.5):.1f}" rx="3" fill="{colour}" '
                       f'opacity="{0.35 if r["family_uncovered"] else 1}"/>')
        lab = f'{r["mid_deg"]:+.2f}'.rstrip("0").rstrip(".")
        out.append(f'<text class="s" x="{cx:.1f}" y="{TOP_H - 30:.1f}" '
                   f'text-anchor="end" transform="rotate(-55 {cx:.1f} '
                   f'{TOP_H - 30:.1f})">{lab}</text>')
    out.append(f'<line class="gr" x1="{L}" x2="{R}" y1="{ym(0):.1f}" y2="{ym(0):.1f}" '
               f'stroke="#b9b8b2" stroke-width="1"/>')

    driven_any = any("drove" in r[p] for r in rows for p in POLICIES)
    if driven_any:
        out.append(f'<text class="t" x="{L}" y="{TOP_H + GAP + 4:.1f}">Driven outcome, '
                   f'{reps} runs at each sub-interval midpoint</text>')
        for v in (0, reps // 2, reps):
            out.append(f'<line class="gr" x1="{L}" x2="{R}" y1="{yd(v):.1f}" '
                       f'y2="{yd(v):.1f}" stroke="#dedcd6" stroke-width="1"/>')
            out.append(f'<text class="s" x="{L - 8}" y="{yd(v) + 4:.1f}" '
                       f'text-anchor="end">{v}</text>')
        for i, r in enumerate(rows):
            cx = L + (i + 0.5) * cw
            for pol, colour, side in ((POLICIES[0], C1, -1), (POLICIES[1], C2, 1)):
                d = r[pol].get("drove")
                if d is None:
                    continue
                px = cx + side * 6
                out.append(f'<line x1="{px:.1f}" x2="{px:.1f}" y1="{yd(0):.1f}" '
                           f'y2="{yd(d):.1f}" stroke="{colour}" stroke-width="2" '
                           f'opacity="0.45"/>')
                out.append(f'<circle cx="{px:.1f}" cy="{yd(d):.1f}" r="5" '
                           f'fill="{colour}"/>')
                # Label only the INTERMITTENT results. A clean pass sits on the top
                # gridline and a total failure sits on the zero line, so both are already
                # unambiguous, and labelling them collided across adjacent sub-intervals
                # -- 16 columns at 56 px each cannot carry a 28 px label on either side
                # of every dot. What a reader cannot infer from position is 3/10 versus
                # 7/10, and that is what gets a number.
                if 0 < d < reps:
                    # Staggered by policy, above for one and below for the other. Two
                    # policies landing on the SAME intermittent rate at the same
                    # sub-interval is the case a reader most wants to read exactly, and
                    # it is the one where two centred labels sit on top of each other.
                    dy = -9 if side < 0 else 17
                    out.append(
                        f'<text class="v" x="{px:.1f}" y="{yd(d) + dy:.1f}" '
                        f'fill="{colour}" text-anchor="middle">{d}/{reps}</text>')
            lab = f'{r["mid_deg"]:+.2f}'.rstrip("0").rstrip(".")
            out.append(f'<text class="s" x="{cx:.1f}" y="{dy1 + 12:.1f}" '
                       f'text-anchor="end" transform="rotate(-55 {cx:.1f} '
                       f'{dy1 + 12:.1f})">{lab}</text>')

    ly = H - 12
    out.append(f'<rect x="{L}" y="{ly - 9}" width="11" height="11" rx="2" fill="{C1}"/>')
    out.append(f'<text x="{L + 17}" y="{ly}">P_pts · regulatory test points only'
               f'</text>')
    out.append(f'<rect x="{L + 250}" y="{ly - 9}" width="11" height="11" rx="2" '
               f'fill="{C2}"/>')
    out.append(f'<text x="{L + 267}" y="{ly}">P_cont · illumination continuum</text>')
    out.append(f'<text class="s" x="{R}" y="{ly}" text-anchor="end">sun altitude at the '
               f'sub-interval midpoint (degrees)</text>')
    out.append('</svg>')
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenario", default="lead", choices=["lead", "ped"])
    args = ap.parse_args()

    rows, meta = load(args.scenario)
    summary = summarise(rows, meta)
    FIGS.mkdir(parents=True, exist_ok=True)

    suffix = "" if args.scenario == "lead" else f"_{args.scenario}"
    (FIGS / f"dusk_gap_data{suffix}.json").write_text(
        json.dumps({"meta": meta, "summary": summary, "rows": rows}, indent=1) + "\n")
    (FIGS / f"dusk_gap{suffix}.html").write_text(
        render_html(rows, meta, summary, args.scenario))
    (FIGS / f"dusk_gap{suffix}.svg").write_text(
        render_svg(rows, meta, summary, args.scenario))

    print(f"\n  {args.scenario}: {meta['sub_intervals']} sub-intervals, "
          f"{meta['sub_intervals_covered']} covered")
    for pol in POLICIES:
        s = summary[pol]
        print(f"  {pol:7s} certified {s['certified']}/{s['of_covered']} covered, "
              f"falsified width {s['falsified_width_deg']:.2f} deg, "
              f"driven clean {s['clean_drives']}/{s['driven_cells']}, "
              f"certified-then-failed {s['certified_then_failed']}")
    print(f"  wrote docs/figures/dusk_gap{suffix}.{{html,svg,}} and "
          f"dusk_gap_data{suffix}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
