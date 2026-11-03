"""Builds the PowerPoint file: DLIS colours, the school logo on every slide, one picture per slide when there is one,
speaker notes, and right-to-left text for Arabic."""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from . import paths

BLUE, GREEN, NAVY, SOFT = RGBColor(0x2F, 0x82, 0xA8), RGBColor(0xA2, 0xC6, 0x5A), RGBColor(0x1F, 0x2A, 0x5C), RGBColor(0xF1, 0xF7, 0xFB)
W, H = 13.333, 7.5
BULLET_PT = {"kg": 38, "lower": 32, "upper": 28, "middle": 24, "high": 22}
FONT = "Segoe UI"


def _rgb_box(slide, x, y, w, h, color, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = color
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def _style_run(run, size, color=NAVY, bold=False):
    run.font.size = Pt(size); run.font.bold = bold; run.font.color.rgb = color; run.font.name = FONT
    rpr = run._r.get_or_add_rPr()
    for tag in ("a:cs", "a:ea"):
        el = rpr.find(qn(tag))
        if el is None:
            el = rpr.makeelement(qn(tag), {}); rpr.append(el)
        el.set("typeface", FONT)


def _para_dir(p, rtl: bool, align=None):
    ppr = p._p.get_or_add_pPr()
    ppr.set("rtl", "1" if rtl else "0")
    p.alignment = align or (PP_ALIGN.RIGHT if rtl else PP_ALIGN.LEFT)


def _bullet(p, rtl: bool):
    ppr = p._p.get_or_add_pPr()
    ppr.set("marL", "342900"); ppr.set("indent", "-342900")
    for old in ppr.findall(qn("a:buChar")) + ppr.findall(qn("a:buNone")):
        ppr.remove(old)
    clr = ppr.makeelement(qn("a:buClr"), {}); srgb = clr.makeelement(qn("a:srgbClr"), {"val": "2F82A8"}); clr.append(srgb)
    ppr.append(clr)
    ppr.append(ppr.makeelement(qn("a:buChar"), {"char": "•"}))


def _text(slide, x, y, w, h, lines, size, rtl, bold=False, color=NAVY, bullets=False, anchor=MSO_ANCHOR.TOP, align=None, spacing=10):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.1)
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        r = p.add_run(); r.text = line
        _style_run(r, size, color, bold)
        _para_dir(p, rtl, align)
        p.space_after = Pt(spacing)
        if bullets:
            _bullet(p, rtl)
    return tb


def _fit(size: int, chars: int, width: float, height: float) -> int:
    """Largest font (not above `size`) that lets this much text fit the box."""
    for pt in range(size, 13, -1):
        per_line = max(8, int(width * 72 / (pt * 0.5)))      # characters in one line
        lines = chars / per_line * 1.1 + 3                    # a little slack for bullet breaks and the explanation
        if lines * pt * 1.3 / 72 <= height:
            return pt
    return 14


def _rich_text(slide, x, y, w, h, bullets, explain, size, rtl):
    """Bullets, then a smaller explanation paragraph, in one box."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True; tf.vertical_anchor = MSO_ANCHOR.TOP
    tf.margin_left = tf.margin_right = Inches(0.1)
    first = True
    for line in bullets:
        p = tf.paragraphs[0] if first else tf.add_paragraph(); first = False
        r = p.add_run(); r.text = str(line); _style_run(r, size)
        _para_dir(p, rtl); p.space_after = Pt(max(6, size // 3)); _bullet(p, rtl)
    if explain:
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        r = p.add_run(); r.text = explain; _style_run(r, max(14, size - 4), BLUE)
        _para_dir(p, rtl); p.space_before = Pt(8)
    return tb


def _logo(slide, rtl: bool):
    f = paths.resources_dir() / "logo.png"
    if f.is_file():
        w = 1.9
        x = W - 0.4 - w if rtl else 0.4
        slide.shapes.add_picture(str(f), Inches(x), Inches(0.3), width=Inches(w))
    return 2.5  # width taken by the logo corner


def _chrome(slide, rtl: bool, number: int | None):
    _rgb_box(slide, 0, 0, W * 0.72, 0.14, BLUE)
    _rgb_box(slide, W * 0.72, 0, W * 0.28, 0.14, GREEN)
    corner = _logo(slide, rtl)
    if number:
        x = 0.4 if rtl else W - 1.2
        _text(slide, x, H - 0.6, 0.8, 0.4, [str(number)], 14, False, color=BLUE, align=PP_ALIGN.CENTER)
    return corner


def _place_picture(slide, path, x, y, w, h):
    from PIL import Image
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(w / iw, h / ih)
    pw, ph = iw * scale, ih * scale
    px, py = x + (w - pw) / 2, y + (h - ph) / 2
    frame = _rgb_box(slide, px - 0.08, py - 0.08, pw + 0.16, ph + 0.16, SOFT, MSO_SHAPE.ROUNDED_RECTANGLE)
    frame.adjustments[0] = 0.04
    slide.shapes.add_picture(str(path), Inches(px), Inches(py), width=Inches(pw), height=Inches(ph))


def build_deck(out: Path, deck: dict) -> Path:
    """deck: title, subtitle, language ('ar'|'en'), stage, slides=[{title, bullets[], notes, image_path}]."""
    rtl = deck.get("language") == "ar"
    bullet_pt = BULLET_PT.get(deck.get("stage", "upper"), 28)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(W), Inches(H)
    blank = prs.slide_layouts[6]
    slides = deck.get("slides") or []

    # ---- title slide
    s = prs.slides.add_slide(blank)
    _rgb_box(s, 0, 0, W * 0.72, 0.14, BLUE); _rgb_box(s, W * 0.72, 0, W * 0.28, 0.14, GREEN)
    logo = paths.resources_dir() / "logo.png"
    if logo.is_file():
        s.shapes.add_picture(str(logo), Inches((W - 3.6) / 2), Inches(0.5), width=Inches(3.6))
    first_img = next((x.get("image_path") for x in slides if x.get("image_path") and Path(x["image_path"]).is_file()), None)
    text_w = 7.6 if first_img else W - 1.6
    tx = (W - text_w - 0.8 if rtl else 0.8) if first_img else 0.8
    _text(s, tx, 2.5, text_w, 2.2, [deck.get("title", "")], 44, rtl, bold=True, anchor=MSO_ANCHOR.MIDDLE, align=(PP_ALIGN.RIGHT if rtl else PP_ALIGN.LEFT) if first_img else PP_ALIGN.CENTER)
    sub = deck.get("subtitle", "")
    if sub:
        _text(s, tx, 4.8, text_w, 0.8, [sub], 24, rtl, color=BLUE, align=(PP_ALIGN.RIGHT if rtl else PP_ALIGN.LEFT) if first_img else PP_ALIGN.CENTER)
    if first_img:
        px = 0.8 if rtl else W - 0.8 - 4.4
        _place_picture(s, first_img, px, 2.3, 4.4, 4.4)

    # ---- content slides
    for i, sl in enumerate(slides, start=2):
        s = prs.slides.add_slide(blank)
        corner = _chrome(s, rtl, i)
        title_w = W - 0.8 - corner
        tx = 0.4 if rtl else 0.4 + corner
        _text(s, tx, 0.35, title_w, 1.1, [sl.get("title", "")], 34, rtl, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        bullets = [b for b in (sl.get("bullets") or []) if str(b).strip()]
        explain = str(sl.get("explain") or "").strip()
        img = sl.get("image_path")
        has_img = bool(img) and Path(img).is_file()
        top, height = 1.6, H - 1.6 - 0.75
        tw = 7.0 if has_img else W - 1.8
        size = _fit(bullet_pt, sum(len(str(x)) for x in bullets) + len(explain), tw, height)
        tx2 = (W - 0.6 - tw if rtl else 0.6) if has_img else 0.9
        _rich_text(s, tx2, top, tw, height, bullets, explain, size, rtl)
        if has_img:
            iw_ = 5.2
            ix = 0.5 if rtl else W - 0.5 - iw_
            _place_picture(s, img, ix, top, iw_, height)
        if sl.get("notes"):
            s.notes_slide.notes_text_frame.text = str(sl["notes"])
    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    return out
