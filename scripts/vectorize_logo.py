"""Rebuild the DLIS logo as clean vector paths from the small raster image.

Method: enlarge the picture, measure how much "ink" each pixel has, take the half-way contour of every shape,
fit smooth Bezier curves (Schneider's algorithm, with real corners kept), and paint each shape with the
gradient or colour measured from the original.

    python scripts/vectorize_logo.py INPUT.png OUT_DIR
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage import measure

S = 8  # enlarge factor used while measuring


# ------------------------------------------------------------------ Bezier fitting (Schneider)
def _bez(c, t):
    mt = 1 - t
    return ((mt ** 3)[:, None] * c[0] + (3 * mt ** 2 * t)[:, None] * c[1]
            + (3 * mt * t ** 2)[:, None] * c[2] + (t ** 3)[:, None] * c[3])


def _d1(c, t):
    mt = 1 - t
    return (3 * (mt ** 2)[:, None] * (c[1] - c[0]) + 6 * (mt * t)[:, None] * (c[2] - c[1]) + 3 * (t ** 2)[:, None] * (c[3] - c[2]))


def _d2(c, t):
    return 6 * (1 - t)[:, None] * (c[2] - 2 * c[1] + c[0]) + 6 * t[:, None] * (c[3] - 2 * c[2] + c[1])


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def _chord(P):
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    return d / d[-1] if d[-1] > 0 else np.linspace(0, 1, len(P))


def _gen(P, u, t1, t2):
    c0, c3 = P[0], P[-1]
    A1 = (3 * (1 - u) ** 2 * u)[:, None] * t1
    A2 = (3 * (1 - u) * u ** 2)[:, None] * t2
    C = np.array([[(A1 * A1).sum(), (A1 * A2).sum()], [(A1 * A2).sum(), (A2 * A2).sum()]])
    tmp = P - (((1 - u) ** 3 + 3 * (1 - u) ** 2 * u)[:, None] * c0 + (3 * (1 - u) * u ** 2 + u ** 3)[:, None] * c3)
    X = np.array([(A1 * tmp).sum(), (A2 * tmp).sum()])
    det = C[0, 0] * C[1, 1] - C[0, 1] * C[1, 0]
    seg = np.linalg.norm(c3 - c0)
    if abs(det) > 1e-12:
        a1 = (X[0] * C[1, 1] - X[1] * C[0, 1]) / det
        a2 = (C[0, 0] * X[1] - C[1, 0] * X[0]) / det
    else:
        a1 = a2 = 0.0
    if a1 < 1e-6 * seg or a2 < 1e-6 * seg:
        a1 = a2 = seg / 3
    return np.array([c0, c0 + t1 * a1, c3 + t2 * a2, c3])


def _reparam(c, P, u):
    q = _bez(c, u)
    d1, d2 = _d1(c, u), _d2(c, u)
    num = ((q - P) * d1).sum(axis=1)
    den = (d1 * d1).sum(axis=1) + ((q - P) * d2).sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        new = np.where(np.abs(den) > 1e-12, u - num / den, u)
    return np.clip(new, 0, 1)


def _fit(P, t1, t2, err2, out):
    if len(P) == 2:
        d = np.linalg.norm(P[1] - P[0]) / 3
        out.append(np.array([P[0], P[0] + t1 * d, P[1] + t2 * d, P[1]]))
        return
    u = _chord(P)
    c = _gen(P, u, t1, t2)
    worst, split = 0.0, len(P) // 2
    for _ in range(12):
        dist = ((_bez(c, u) - P) ** 2).sum(axis=1)
        worst, split = dist.max(), int(dist.argmax())
        if worst < err2:
            out.append(c)
            return
        if worst > err2 * 16:
            break
        u = _reparam(c, P, u)
        c = _gen(P, u, t1, t2)
    split = min(max(split, 1), len(P) - 2)
    tc = _unit(P[split - 1] - P[split + 1])
    _fit(P[: split + 1], t1, tc, err2, out)
    _fit(P[split:], -tc, t2, err2, out)


def _resample(poly, step):
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1)
    d = np.r_[0, np.cumsum(seg)]
    n = max(int(d[-1] / step), 8)
    s = np.linspace(0, d[-1], n, endpoint=False)
    return np.c_[np.interp(s, d, poly[:, 0]), np.interp(s, d, poly[:, 1])]


def _corners(P, k, deg):
    n = len(P)
    ang = np.zeros(n)
    for i in range(n):
        a, b = P[i] - P[i - k], P[(i + k) % n] - P[i]
        ang[i] = np.degrees(np.arccos(np.clip(np.dot(_unit(a), _unit(b)), -1, 1)))
    idx = []
    for i in range(n):
        win = [ang[(i + j) % n] for j in range(-k, k + 1)]
        if ang[i] >= deg and ang[i] >= max(win):
            idx.append(i)
    # merge neighbours closer than k
    merged = []
    for i in idx:
        if not merged or i - merged[-1] > k:
            merged.append(i)
    return merged


def fit_closed(poly, err=0.34, step=0.12, corner_deg=48):
    """poly: Nx2 closed contour (x,y) in output units. Returns list of cubic segments."""
    P = _resample(poly, step)
    n = len(P)
    k = 6
    corners = _corners(P, k, corner_deg)
    segs: list = []
    if not corners:
        corners = [0, n // 2]
        smooth = True
    else:
        smooth = False
    m = len(corners)
    for a in range(m):
        i, j = corners[a], corners[(a + 1) % m]
        idx = list(range(i, j + 1)) if j > i else list(range(i, n)) + list(range(0, j + 1))
        seg = P[idx]
        kk = min(4, len(seg) - 1)
        if smooth:
            t1 = _unit(P[(i + 3) % n] - P[(i - 3) % n])
            t2 = _unit(P[(j - 3) % n] - P[(j + 3) % n])
        else:
            t1 = _unit(seg[kk] - seg[0])
            t2 = _unit(seg[-1 - kk] - seg[-1])
        _fit(seg, t1, t2, err * err, segs)
    return segs


def to_path(segs, ndigits=2):
    f = lambda v: f"{v:.{ndigits}f}".rstrip("0").rstrip(".")
    d = [f"M{f(segs[0][0][0])} {f(segs[0][0][1])}"]
    for c in segs:
        chord = c[3] - c[0]
        L = np.linalg.norm(chord)
        straight = L > 0 and all(abs(chord[0]*(c[i][1]-c[0][1]) - chord[1]*(c[i][0]-c[0][0])) / L < 0.04 for i in (1, 2))
        if straight:
            d.append(f"L{f(c[3][0])} {f(c[3][1])}")
        else:
            d.append("C" + " ".join(f"{f(p[0])} {f(p[1])}" for p in c[1:]))
    return "".join(d) + "Z"


# ------------------------------------------------------------------ measuring the picture
def load(path):
    bgr = cv2.imread(str(path))
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    big = cv2.resize(rgb, None, fx=S, fy=S, interpolation=cv2.INTER_LANCZOS4).astype(np.float32)
    return rgb, big


def region_mask(shape, x0, y0, x1, y1):
    m = np.zeros(shape[:2], bool)
    m[int(y0 * S): int(y1 * S), int(x0 * S): int(x1 * S)] = True
    return m


def shapes_from_field(field, region, blur=0.55, min_area=1.5):
    # blur is in source pixels
    """Contours (output units) of every shape where field >= .5, grouped per connected shape."""
    f = ndi.gaussian_filter(np.where(region, field, 0), blur * S)
    mask = f >= 0.5
    lab, n = ndi.label(mask)
    out = []
    for i in range(1, n + 1):
        comp = lab == i
        area = comp.sum() / S ** 2
        if area < min_area:
            continue
        sl = ndi.find_objects(comp.astype(int))[0]
        pad = 3
        y0, y1 = max(sl[0].start - pad, 0), sl[0].stop + pad
        x0, x1 = max(sl[1].start - pad, 0), sl[1].stop + pad
        sub = np.where(comp[y0:y1, x0:x1], f[y0:y1, x0:x1], 0)
        contours = measure.find_contours(sub, 0.5)
        polys = []
        for c in contours:
            if len(c) < 20:
                continue
            xy = np.c_[(c[:, 1] + x0 + 0.5) / S, (c[:, 0] + y0 + 0.5) / S]
            if np.linalg.norm(xy[0] - xy[-1]) < 1e-6:
                xy = xy[:-1]
            polys.append(xy)
        if polys:
            out.append({"mask": comp, "polys": polys, "area": area})
    return out


def poly_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1)))


def gradient_for(big, comp):
    """Fit a straight-line colour gradient (start/end colour and direction) to the pixels of one shape."""
    er = ndi.binary_erosion(comp, iterations=int(0.5 * S))
    ys, xs = np.nonzero(er if er.sum() > 200 else comp)
    cols = big[ys, xs]
    X = np.c_[xs / S, ys / S, np.ones(len(xs))]
    coef, *_ = np.linalg.lstsq(X, cols, rcond=None)  # 3x3: columns = r,g,b
    lum_w = np.array([0.30, 0.59, 0.11])
    g = coef[:2] @ lum_w
    cx, cy = xs.mean() / S, ys.mean() / S
    if np.linalg.norm(g) < 0.5:  # almost flat
        c = cols.mean(axis=0)
        return None, c
    d = g / np.linalg.norm(g)
    proj = (xs / S) * d[0] + (ys / S) * d[1]
    lo, hi = np.percentile(proj, 1), np.percentile(proj, 99)
    A = np.c_[proj, np.ones(len(proj))]
    cc, *_ = np.linalg.lstsq(A, cols, rcond=None)
    c_lo, c_hi = cc[0] * lo + cc[1], cc[0] * hi + cc[1]
    # centre line through the shape's centre, along d
    p0 = np.array([cx, cy]) + d * (lo - (cx * d[0] + cy * d[1]))
    p1 = np.array([cx, cy]) + d * (hi - (cx * d[0] + cy * d[1]))
    return (p0, p1, np.clip(c_lo, 0, 255), np.clip(c_hi, 0, 255)), cols.mean(axis=0)


def hexcol(c):
    c = np.clip(np.round(c), 0, 255).astype(int)
    return "#%02x%02x%02x" % tuple(c)


def build(src: Path, out_dir: Path):
    rgb, big = load(src)
    R, G, B = big[..., 0], big[..., 1], big[..., 2]
    H, W = rgb.shape[:2]
    shape = big.shape

    layers = []  # each: dict(kind, polys, fill, grad)

    # ---- emblem (blue figures + swooshes)
    emb_region = region_mask(shape, 30, 8, 172, 142)
    f_em = np.clip((238 - R) / (238 - 100), 0, 1)
    for sh in shapes_from_field(f_em, emb_region, blur=0.9, min_area=8):
        grad, mean = gradient_for(big, sh["mask"])
        is_green = (mean[1] - mean[2]) > 30 and mean[1] > mean[0]
        layers.append({"group": "mark", "polys": sh["polys"], "grad": grad, "color": mean, "green": is_green, "area": sh["area"]})

    # ---- DLIS letters (navy)
    f_navy = np.clip((236 - R) / (236 - 80), 0, 1) * (B > R + 15)
    for sh in shapes_from_field(f_navy, region_mask(shape, 183, 24, 345, 79)):
        layers.append({"group": "text", "polys": sh["polys"], "grad": None, "color": big[sh["mask"]].mean(axis=0), "area": sh["area"], "role": "navy"})

    # ---- "American Division" (green)
    f_green = np.clip((236 - B) / (236 - 80), 0, 1)
    for sh in shapes_from_field(f_green, region_mask(shape, 165, 79, 362, 100.2), min_area=0.6):
        layers.append({"group": "text", "polys": sh["polys"], "grad": None, "color": big[sh["mask"]].mean(axis=0), "area": sh["area"], "role": "green"})

    # ---- "Brilliant Education" (brown-grey)
    f_brown = np.clip((232 - G) / (232 - 105), 0, 1)
    for sh in shapes_from_field(f_brown, region_mask(shape, 165, 100.2, 362, 128), min_area=0.4):
        layers.append({"group": "text", "polys": sh["polys"], "grad": None, "color": big[sh["mask"]].mean(axis=0), "area": sh["area"], "role": "brown"})

    # one flat colour per text line (the median of its letters) so every letter matches
    for role in ("navy", "green", "brown"):
        cols = [l["color"] for l in layers if l.get("role") == role]
        if cols:
            med = np.median(np.array(cols), axis=0)
            for l in layers:
                if l.get("role") == role:
                    l["color"] = med
    return layers, (W, H)


def font_text(path, text, x0, x1, base_y, cap_h, color, tracking_fit=True):
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    f = TTFont(path)
    gs, cmap, hmtx = f.getGlyphSet(), f.getBestCmap(), f["hmtx"]
    cap = getattr(f["OS/2"], "sCapHeight", 0) or f["head"].unitsPerEm * 0.7
    k = cap_h / cap
    names = [cmap[ord(c)] for c in text]
    adv = [hmtx[n][0] * k for n in names]
    natural = sum(adv)
    gap = (x1 - x0 - natural) / (len(text) - 1) if tracking_fit and len(text) > 1 else 0
    x, parts = x0, []
    for n, a in zip(names, adv):
        pen = SVGPathPen(gs, ntos=lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
        gs[n].draw(TransformPen(pen, (k, 0, 0, -k, x, base_y)))
        d = pen.getCommands()
        if d:
            parts.append(d)
        x += a + gap
    return "".join(parts)


def bbox_of(layers, role):
    pts = np.vstack([p for l in layers if l.get("role") == role for p in l["polys"]])
    return pts.min(axis=0), pts.max(axis=0)


def replace_text_with_fonts(layers):
    G = "/usr/share/fonts/truetype/google-fonts/"
    spec = {
        "navy": (G + "Poppins-Light.ttf", "DLIS", None),
        "green": (G + "Poppins-SemiBold.ttf" if False else G + "Poppins-Medium.ttf", "American Division", None),
        "brown": ("/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf", "Brilliant Education", None),
    }
    colors = {r: next(l["color"] for l in layers if l.get("role") == r) for r in spec}
    boxes = {r: bbox_of(layers, r) for r in spec}
    keep = [l for l in layers if l["group"] == "mark"]
    for r, (font, text, _) in spec.items():
        lo, hi = boxes[r]
        if r == "navy":
            cap_h, base = hi[1] - lo[1], hi[1]
        elif r == "green":
            cap_h, base = (hi[1] - lo[1]) * 0.86, hi[1]
        else:
            cap_h, base = (hi[1] - lo[1]) * 0.72, hi[1] - (hi[1] - lo[1]) * 0.18
        keep.append({"group": "text", "polys": [], "grad": None, "color": colors[r], "area": 1, "role": r,
                     "fitted": [font_text(font, text, lo[0], hi[0], base, cap_h, colors[r])], "bbox": (lo, hi)})
    return keep


def make_svg(layers, groups, bbox_pad=3.0, mono=None, title="DLIS American Division"):
    chosen = [l for l in layers if l["group"] in groups]
    for l in chosen:
        if "fitted" in l:
            continue
        l["fitted"] = []
        for poly in l["polys"]:
            if poly_area(poly) < 0.3:
                continue
            segs = fit_closed(poly)
            l["fitted"].append(to_path(segs))
    pts = np.vstack([p for l in chosen for p in l["polys"]] + [np.array(b) for l in chosen if "bbox" in l for b in [l["bbox"][0], l["bbox"][1]]])
    x0, y0 = pts.min(axis=0) - bbox_pad
    x1, y1 = pts.max(axis=0) + bbox_pad
    w, h = x1 - x0, y1 - y0
    defs, body = [], []
    gid = 0
    for l in chosen:
        d = "".join(l["fitted"])
        if not d:
            continue
        if mono:
            fill = mono
        elif l["grad"] is not None:
            p0, p1, c0, c1 = l["grad"]
            gid += 1
            defs.append(f'<linearGradient id="g{gid}" gradientUnits="userSpaceOnUse" x1="{p0[0]:.2f}" y1="{p0[1]:.2f}" x2="{p1[0]:.2f}" y2="{p1[1]:.2f}">'
                        f'<stop offset="0" stop-color="{hexcol(c0)}"/><stop offset="1" stop-color="{hexcol(c1)}"/></linearGradient>')
            fill = f"url(#g{gid})"
        else:
            fill = hexcol(l["color"])
        body.append(f'<path fill="{fill}" fill-rule="evenodd" d="{d}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.2f} {y0:.2f} {w:.2f} {h:.2f}" width="{w:.0f}" height="{h:.0f}" role="img" aria-label="{title}">'
           f'<title>{title}</title>' + (f"<defs>{''.join(defs)}</defs>" if defs else "") + "".join(body) + "</svg>")
    return svg


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    layers, size = build(src, out)
    # circular heads become exact circles (cleaner and perfectly round)
    for l in layers:
        if l["group"] == "mark" and len(l["polys"]) == 1:
            p = l["polys"][0]
            r = np.sqrt(l["area"] / np.pi)
            c = p.mean(axis=0)
            dev = np.abs(np.linalg.norm(p - c, axis=1) - r).max()
            if dev < 0.12 * r and l["area"] < 120:
                l["circle"] = (c, r)
    layers = replace_text_with_fonts(layers)
    (out / "logo.svg").write_text(make_svg(layers, {"mark", "text"}), encoding="utf-8")
    (out / "logo-mark.svg").write_text(make_svg(layers, {"mark"}, title="DLIS"), encoding="utf-8")
    (out / "logo-white.svg").write_text(make_svg(layers, {"mark", "text"}, mono="#ffffff"), encoding="utf-8")
    print("shapes:", {g: sum(1 for l in layers if l["group"] == g) for g in ("mark", "text")})
    for l in layers:
        if l["group"] == "mark":
            print(" mark area %.0f %s grad=%s" % (l["area"], "green" if l["green"] else "blue", "yes" if l["grad"] else "flat"))


if __name__ == "__main__":
    main()
