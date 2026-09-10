"""PROTOCOL section 11's figure for the false-activation cells.

    python tools/make_plate_figure.py

Writes `docs/figures/plate_gap.svg` and `plate_gap_data.json`.

Section 11 asks for *"the two regulatory test points marked and the violation sitting
between them"*. The hazard figure (`make_figure.py`) shows that for property S, a
certified lower bound against a must-brake threshold. This shows it for the standard's
own false-activation test, where it is starker and needs no explanation of what the
threshold means: FMVSS 127 fixes the limit at 0.25 g, the three lighting conditions it
tests are the three points, and the measured peak between them is 138% of the limit.

**Both the plate and the control are drawn.** A bar is the peak commanded deceleration
with the steel plate on the road; the tick is the same illumination driven with **no
plate**. Where they coincide the braking is not a response to the plate, and the figure
must show that rather than assert it -- otherwise every bar over the limit reads as false
activation, and for two of the three arms it is not.

Measured peaks, not bounds. The certificates are in `verify_*_plate_A.json`; this is what
the vehicle did, over ten repetitions per point.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import carla_jobs as J  # noqa: E402

OUT = J.OUT
FIGS = J.REPO / "docs" / "figures"
ARMS = [("P_pts", "#eb6834"), ("P_pts3", "#8a5cd6"), ("P_cont", "#2a78d6")]


def load():
    rows, endpoints = [], {}
    ep = json.loads((OUT / "policy_endpoints_plate.json").read_text())
    for key, cell in ep["cells"].items():
        pol, cond = key.split("|")
        endpoints.setdefault(pol, {})[cond] = cell["peak_demand_mps2"]

    base = None
    for pol, _ in ARMS:
        p = json.loads((OUT / f"witness_{pol}_plate.json").read_text())
        c = json.loads((OUT / f"witness_{pol}_none_plate.json").read_text())
        cby = {(x["from_deg"], x["to_deg"]): x for x in c["cells"]}
        fv = json.loads((OUT / f"verify_{pol}_plate_A.json").read_text())
        unc = {(x["from_deg"], x["to_deg"]) for x in fv["cells"]
               if x.get("family_uncovered")}
        if base is None:
            base = [{"from_deg": x["from_deg"], "to_deg": x["to_deg"],
                     "driven_at_deg": x["driven_at_deg"],
                     "family_uncovered": (x["from_deg"], x["to_deg"]) in unc,
                     "arms": {}} for x in p["cells"]]
        for row, x in zip(base, p["cells"]):
            o = cby[(x["from_deg"], x["to_deg"])]
            row["arms"][pol] = {
                "peak_plate": x["worst_peak_mps2"],
                "peak_no_plate": o["worst_peak_mps2"],
                "x_limit_plate": x["worst_peak_x_limit"],
                "x_limit_no_plate": round(o["worst_peak_mps2"] / x["nuisance_limit_mps2"], 4),
                "passes_plate": f"{x['passes_protocol']}/{x['of']}",
                "passes_no_plate": f"{o['passes_protocol']}/{o['of']}",
                "verdict": x["verdict"],
            }
        rows = base
    limit = json.loads((OUT / "witness_P_pts_plate.json").read_text()
                       )["cells"][0]["nuisance_limit_mps2"]
    return rows, endpoints, limit


def svg(rows, endpoints, limit) -> str:
    W, PH, PAD_B = 1000, 340, 116
    H = PH + PAD_B
    L, R = 62, W - 16
    n = len(rows)
    cw = (R - L) / n
    bw = min(15.0, cw * 0.24)
    y_max = max(1.5, max(a["x_limit_plate"] for r in rows for a in r["arms"].values()) * 1.12)

    def ym(v):
        return 26 + (y_max - v) / y_max * (PH - 76)

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" '
         f'role="img" aria-label="Peak commanded deceleration on the FMVSS 127 '
         f'false-activation scenario, by illumination">',
         '<style>text{font:12px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;'
         'fill:#52514e}.t{font-size:14px;font-weight:600;fill:#0b0b0b}'
         '.s{font-size:10px;fill:#7b7a75}.v{font-size:11px;font-weight:700}</style>',
         '<defs><pattern id="unc" width="6" height="6" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" '
         'stroke="#b9b8b2" stroke-width="2"/></pattern></defs>',
         f'<rect width="{W}" height="{H}" fill="#fcfcfb"/>',
         f'<text class="t" x="{L}" y="16">Peak commanded deceleration on the steel trench '
         f'plate, 50 mph — × FMVSS 127&#8217;s 0.25 g nuisance limit</text>']

    for i, r in enumerate(rows):
        if r["family_uncovered"]:
            o.append(f'<rect x="{L + i * cw:.1f}" y="22" width="{cw:.1f}" '
                     f'height="{PH - 68:.1f}" fill="url(#unc)" opacity="0.45"/>')

    g = 0.0
    while g <= y_max + 1e-9:
        o.append(f'<line x1="{L}" x2="{R}" y1="{ym(g):.1f}" y2="{ym(g):.1f}" '
                 f'stroke="#dedcd6"/>')
        o.append(f'<text class="s" x="{L - 7}" y="{ym(g) + 4:.1f}" '
                 f'text-anchor="end">{g:.1f}</text>')
        g += 0.25

    # The limit. Everything on this page is a fraction of it, so it is the only line that
    # carries a verdict and it is drawn like one.
    o.append(f'<line x1="{L}" x2="{R}" y1="{ym(1.0):.1f}" y2="{ym(1.0):.1f}" '
             f'stroke="#c8102e" stroke-width="2.5"/>')
    o.append(f'<text class="v" x="{R}" y="{ym(1.0) - 7:.1f}" text-anchor="end" '
             f'fill="#c8102e">FMVSS 127 limit, 0.25 g = {limit:.3f} m/s²</text>')

    for i, r in enumerate(rows):
        x0 = L + i * cw
        for k, (pol, col) in enumerate(ARMS):
            a = r["arms"][pol]
            bx = x0 + cw / 2 + (k - 1) * (bw + 3) - bw / 2
            v = min(a["x_limit_plate"], y_max)
            o.append(f'<rect x="{bx:.1f}" y="{ym(v):.1f}" width="{bw:.1f}" '
                     f'height="{max(1.0, ym(0) - ym(v)):.1f}" fill="{col}" '
                     f'opacity="{0.95 if a["x_limit_plate"] > 1.0 else 0.72}"/>')
            # The control: same illumination, no steel. A visible gap means the plate did
            # something; coincidence means it did not.
            c = min(a["x_limit_no_plate"], y_max)
            o.append(f'<line x1="{bx - 2.5:.1f}" x2="{bx + bw + 2.5:.1f}" '
                     f'y1="{ym(c):.1f}" y2="{ym(c):.1f}" stroke="#0b0b0b" '
                     f'stroke-width="1.6"/>')
            if a["x_limit_plate"] > 1.0:
                o.append(f'<text class="v" x="{bx + bw / 2:.1f}" y="{ym(v) - 5:.1f}" '
                         f'text-anchor="middle" fill="{col}">'
                         f'{a["x_limit_plate"]:.2f}×</text>')
        lab = f'{r["driven_at_deg"]:+.2f}'
        o.append(f'<text class="s" x="{x0 + cw / 2:.1f}" y="{PH - 34:.1f}" '
                 f'text-anchor="middle" transform="rotate(-52 {x0 + cw / 2:.1f} '
                 f'{PH - 34:.1f})">{lab}</text>')

    o.append(f'<text class="s" x="{L}" y="{PH - 4:.1f}">sun altitude driven, degrees — '
             f'the axis runs +60° (daylight) to −30° (darkness)</text>')

    ly = PH + 24
    o.append(f'<text class="t" x="{L}" y="{ly}">At the three lighting conditions FMVSS 127 '
             f'actually tests, every arm is under 16% of the limit:</text>')
    ly += 17
    for pol, col in ARMS:
        e = endpoints[pol]
        parts = "   ".join(
            f'{c.replace("darkness_", "dark ")} {e[c] / limit:.3f}×'
            for c in ("daylight", "darkness_lowbeam", "darkness_highbeam"))
        o.append(f'<text x="{L}" y="{ly}"><tspan fill="{col}" font-weight="700">'
                 f'{pol}</tspan>   {parts}</text>')
        ly += 16
    o.append(f'<text class="s" x="{L}" y="{ly + 4}">Bars: peak over 10 runs with the plate. '
             f'Black tick: the same illumination with the plate REMOVED. Hatched: the '
             f'sub-interval the disturbance family cannot represent (A6).</text>')
    # Below the limit, bar and tick differ by run-to-run variation on demands two orders
    # of magnitude under the threshold -- 0.089 against 0.011 is a 736% relative change
    # and means nothing. The only difference that decides anything is one that crosses
    # the red line, and saying so on the figure is cheaper than a reader over-reading a
    # gap that a caption did not warn them about.
    flips = [(pol, r) for r in rows for pol, _ in ARMS
             if r["arms"][pol]["x_limit_plate"] > 1.0 >= r["arms"][pol]["x_limit_no_plate"]]
    o.append(f'<text class="s" x="{L}" y="{ly + 19}">Gaps below the limit are run-to-run '
             f'variation on demands far under it and decide nothing. '
             + (f'The plate changes a verdict in exactly one place: '
                + ", ".join(f'{pol} at {r["driven_at_deg"]:+.2f}°, '
                            f'{r["arms"][pol]["x_limit_no_plate"]:.3f}× → '
                            f'{r["arms"][pol]["x_limit_plate"]:.3f}×' for pol, r in flips)
                + '.' if flips else 'The plate changes no verdict anywhere.')
             + '</text>')
    o.append("</svg>")
    return "\n".join(o)


def main() -> int:
    FIGS.mkdir(parents=True, exist_ok=True)
    rows, endpoints, limit = load()
    J.claim_output(FIGS / "plate_gap.svg").write_text(svg(rows, endpoints, limit) + "\n")
    J.claim_output(FIGS / "plate_gap_data.json").write_text(json.dumps({
        "nuisance_limit_mps2": limit,
        "endpoints_peak_mps2": endpoints,
        "sub_intervals": rows,
        "note": ("Measured peak commanded deceleration over 10 repetitions per point, "
                 "with and without the plate. Bounds are in verify_*_plate_A.json; this "
                 "is what the vehicle did."),
    }, indent=2) + "\n")
    for pol, _ in ARMS:
        over = [r for r in rows if r["arms"][pol]["x_limit_plate"] > 1.0]
        plate_only = [r for r in rows
                      if r["arms"][pol]["x_limit_plate"] > 1.0
                      and r["arms"][pol]["x_limit_no_plate"] <= 1.0]
        worst = max(endpoints[pol].values()) / limit
        print(f"  {pol:<7} worst regulatory test point {worst:.3f}x limit;  "
              f"{len(over)} sub-interval(s) over the limit;  "
              f"{len(plate_only)} of those ONLY with the plate present")
    print(f"  wrote {(FIGS / 'plate_gap.svg').relative_to(J.REPO)} and its data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
