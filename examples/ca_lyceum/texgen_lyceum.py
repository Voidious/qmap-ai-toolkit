"""Original procedural 'lamplit academy' textures for ca_lyceum (all generated from code,
quantized to the Quake palette; LibreQuake palette, BSD-3).

A classical academy at night: cream marble, honey travertine, Pompeian red plaster, a
midnight-blue observatory, porphyry dado and bronze fittings, lit by oil lamps.
Zones (callout = wall + lamp-band glow):
  atr   - hub atrium          cream marble ashlar, coffered ceiling     amber band
  obs   - tower observatory   midnight-blue star-chart plaster          moon-white band
  amp   - pit amphitheatre    honey travertine, sand arena floor        firelight band
  pal   - duel hall           b4: black fresco, Greek-key mosaic floor  gold band
  gal   - its gallery         b4: black stucco, vermilion pilasters     (no band)
  stoa  - balcony / gallery   ochre stucco and pilasters, terracotta    (no band)
  brk   - passages            Roman brick, limestone flags              (no band)
Usage: python3 texgen_lyceum.py outdir
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
import texgen_runic as R  # noqa: E402
from fsq import fs_quantize, STONE  # noqa: E402
from texgen import HM, fbm, colorize, grime_map  # noqa: E402

R.T.ALBEDO = 0.84
rivet_row = R.rivet_row
TAU = 2 * np.pi

CREAM = (170, 164, 146)
TRAV = (156, 128, 90)
POMP = (150, 50, 38)
OCHRE = (176, 128, 72)
MIDNIGHT = (34, 38, 70)
BRONZE = (136, 98, 44)
BRONZE_D = (82, 58, 28)
GOLD = (190, 160, 70)
PORPH = (96, 52, 60)
CHAR = (74, 70, 66)
TERRA = (150, 74, 50)
BRICK = (126, 66, 46)

#        strip glow (core idx, edge idx)
GLOW = {'atr': (237, 235), 'obs': (245, 244), 'amp': (234, 232), 'pal': (252, 241), 'stoa': (237, 235),
        'brk': (237, 235), 'gal': (252, 241), 'cli': (252, 241)}


def q1(rgb):
    return R.quantize(np.zeros((1, 1, 3)) + np.array(rgb, float))[0, 0]


def veins(h, w, seed, cy=1, cx=2, turb=5.0, width=0.06):
    """Tileable marble veining: thin wandering lines, 0..1."""
    yy, xx = np.mgrid[0:h, 0:w]
    t = fbm(h, w, seed, base=3, octaves=5)
    ph = TAU * (cx * xx / w + cy * yy / h) + turb * t
    m = np.abs(np.sin(ph))
    return np.clip(1 - m / width, 0, 1) ** 2


def marble_rgb(h, w, seed, col, vein_amt=0.22, vein_col=(96, 92, 88), cy=1, cx=2, cloud=0.10):
    v = veins(h, w, seed, cy, cx)
    v2 = veins(h, w, seed + 17, cy + 1, cx - 1 if cx > 1 else 1, turb=7.0, width=0.03)
    cl = fbm(h, w, seed + 5, base=2, octaves=4)
    base = np.array(col, float) * (1 - cloud + 2 * cloud * cl)[..., None]
    vv = np.clip(v * vein_amt + v2 * vein_amt * 0.6, 0, 1)[..., None]
    return base * (1 - vv) + np.array(vein_col, float) * vv


def mosaic(rgb, t=4, grout=0.72):
    """Tesserae: flat colour per t x t cell, darker grout lines."""
    h, w, _ = rgb.shape
    out = rgb.copy()
    for y in range(0, h, t):
        for x in range(0, w, t):
            out[y:y + t, x:x + t] = rgb[min(h - 1, y + t // 2), min(w - 1, x + t // 2)]
    yy, xx = np.mgrid[0:h, 0:w]
    g = (yy % t == 0) | (xx % t == 0)
    out[g] *= grout
    return out


# ------------------------------------------------------------------ walls
def tex_wall(z, seed):
    if z == 'atr':             # cream marble ashlar: 2 courses of 32, drafted margins, veining
        h, w = 64, 128
        hm = HM(h, w)
        rng = np.random.default_rng(seed)
        tm = np.ones((h, w))
        for r in range(2):
            off = 32 if r else 0
            for x in range(0, w, 64):
                hm.plate(x + off + 1, r * 32 + 1, x + off + 64, r * 32 + 32, 1.0, 2)
                hm.groove(x + off + 4, r * 32 + 4, x + off + 61, r * 32 + 5, 0.25)   # drafted margin
                hm.groove(x + off + 4, r * 32 + 28, x + off + 61, r * 32 + 29, 0.25)
                X = (hm.X - (x + off)) % w
                tm[(X < 64) & (hm.Y >= r * 32) & (hm.Y < r * 32 + 32)] = 1 + 0.07 * (rng.random() * 2 - 1)
        rgb = marble_rgb(h, w, seed, CREAM) * hm.shade(0.9)[..., None] * R.T.ALBEDO * tm[..., None]
        return rgb * (1 - grime_map(h, w, seed + 3, 0.08)[..., None])
    if z == 'obs':             # midnight-blue plaster, gold stars and constellations, gold meridian strip
        h, w = 128, 128
        cl = fbm(h, w, seed, base=3, octaves=4)
        rgb = np.array(MIDNIGHT, float) * (0.8 + 0.4 * cl)[..., None] * R.T.ALBEDO
        rng = np.random.default_rng(seed)
        stars = [(int(rng.integers(12, w - 4)), int(rng.integers(0, h))) for _ in range(26)]
        # constellation lines between near neighbours (faint gold)
        for k in range(0, 18, 3):
            a, b, c = stars[k], stars[k + 1], stars[k + 2]
            for p, q in ((a, b), (b, c)):
                dy = (q[1] - p[1] + h // 2) % h - h // 2
                n = int(max(abs(q[0] - p[0]), abs(dy))) + 1
                if n > 60:
                    continue
                for s in np.linspace(0, 1, n):
                    x = int(round(p[0] + (q[0] - p[0]) * s)) % w
                    y = int(round(p[1] + dy * s)) % h
                    rgb[y, x] = rgb[y, x] * 0.5 + np.array((110, 92, 50)) * 0.5
        for k, (x, y) in enumerate(stars):
            big = k % 4 == 0
            rgb[y % h, x % w] = (210, 186, 96)
            if big:
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    rgb[(y + dy) % h, (x + dx) % w] = (150, 128, 60)
        # gold meridian strip with a bead line, one per 128
        rgb[:, 0:10] = np.array((118, 92, 46)) * (0.85 + 0.3 * fbm(h, 10, seed + 4, base=2))[..., None]
        rgb[:, 1] *= 1.25
        rgb[:, 8] *= 0.6
        rgb[::8, 4:6] = (170, 140, 70)
        return rgb
    if z == 'amp':             # honey travertine: big blocks, horizontal pitting
        h, w = 64, 128
        hm = HM(h, w)
        rng = np.random.default_rng(seed)
        tm = np.ones((h, w))
        for r in range(2):
            off = 48 if r else 0
            for x in range(0, w, 64):
                hm.plate(x + off + 1, r * 32 + 1, x + off + 64, r * 32 + 32, 1.0, 2)
                X = (hm.X - (x + off)) % w
                tm[(X < 64) & (hm.Y >= r * 32) & (hm.Y < r * 32 + 32)] = 1 + 0.10 * (rng.random() * 2 - 1)
        pits = fbm(h, w, seed + 8, base=8, octaves=3, sy=1, sx=4)
        hm.H -= np.clip(pits - 0.66, 0, 1) * 4.0
        streak = fbm(h, w, seed + 9, base=4, octaves=3, sy=4, sx=1)
        rgb = colorize(TRAV, hm.shade(1.0), streak, grime_map(h, w, seed + 3, 0.16))
        return rgb * tm[..., None]
    if z == 'pal':             # Pompeian red panels, 64 wide x 80 tall, black pilaster strips, ochre lines
        h, w = 80, 128
        cl = fbm(h, w, seed, base=3, octaves=4)
        rgb = np.array(POMP, float) * (0.86 + 0.24 * cl)[..., None] * R.T.ALBEDO
        yy, xx = np.mgrid[0:h, 0:w]
        X = xx % 64
        black = (X < 8) | (yy < 3) | (yy >= h - 3)
        rgb[black] = np.array((40, 30, 28)) * (0.9 + 0.2 * cl[black])[..., None]
        oc = (((X == 13) | (X == 58)) & (yy >= 8) & (yy < h - 8)) | (((yy == 8) | (yy == h - 9)) & (X >= 13) & (X <= 58))
        rgb[oc] = (150, 112, 50)
        # little candelabrum motif painted in each black strip
        cand = ((X >= 3) & (X < 5) & (yy >= 10) & (yy < h - 10)) | ((X >= 1) & (X < 7) & (yy % 20 == 10))
        rgb[cand] = (120, 92, 44)
        return rgb * (1 - grime_map(h, w, seed + 3, 0.10)[..., None])
    if z == 'stoa':            # ochre stucco with cream fluted pilasters; no horizontal joints
        h, w = 128, 128
        cl = fbm(h, w, seed, base=3, octaves=5)
        rgb = np.array(OCHRE, float) * (0.84 + 0.3 * cl)[..., None] * R.T.ALBEDO
        hm = HM(h, w)
        for x0 in (0, 64):
            hm.plate(x0, 0, x0 + 14, h + h, 1.2, 1)
            for f in range(2, 14, 4):
                hm.groove(x0 + f, 0, x0 + f + 2, h, 0.5)
        sh = hm.shade(1.0)
        pil = (hm.X % 64) < 14
        prgb = marble_rgb(h, w, seed + 2, (172, 166, 148), 0.12) * R.T.ALBEDO
        rgb[pil] = prgb[pil]
        rgb = rgb * sh[..., None]
        rgb[:, 14] *= 0.6
        rgb[:, 15] *= 0.8
        return rgb * (1 - grime_map(h, w, seed + 3, 0.10)[..., None])
    # brk: Roman brick, thin courses (8 high) with thick mortar
    h, w = 32, 64
    hm = HM(h, w)
    rng = np.random.default_rng(seed)
    tm = np.ones((h, w))
    for r in range(4):
        off = 16 if r % 2 else 0
        for x in range(0, w, 32):
            hm.plate(x + off + 1, r * 8 + 2, x + off + 31, r * 8 + 8, 1.0, 1)
            X = (hm.X - (x + off)) % w
            tm[(X < 32) & (hm.Y >= r * 8) & (hm.Y < r * 8 + 8)] = 1 + 0.16 * (rng.random() * 2 - 1)
    mortar = hm.H < 0.2
    rgb = colorize(BRICK, hm.shade(0.9), fbm(h, w, seed, base=4), grime_map(h, w, seed + 3, 0.14))
    rgb = rgb * tm[..., None]
    rgb[mortar] = np.array((112, 100, 84)) * (0.85 + 0.25 * fbm(h, w, seed + 6, base=8)[mortar])[..., None] * R.T.ALBEDO
    return rgb


# ------------------------------------------------------------------ floors
def tex_floor(z, seed):
    if z == 'atr':             # octagon-and-dot: cream marble octagons, porphyry diamonds at corners
        n = 64
        rgb = marble_rgb(n, n, seed, (164, 158, 142), 0.18) * R.T.ALBEDO
        yy, xx = np.mgrid[0:n, 0:n]
        dx, dy = np.minimum(xx, n - xx), np.minimum(yy, n - yy)
        dia = (dx + dy) < 12
        rgb[dia] = (np.array(PORPH) * (0.9 + 0.2 * fbm(n, n, seed + 2, base=8))[..., None])[dia] * R.T.ALBEDO
        edge = (np.abs(dx + dy - 12) < 1) | (xx == 0) | (yy == 0)
        rgb[edge & ~dia] *= 0.62
        rgb[edge & dia] *= 0.8
        return rgb
    if z == 'obs':             # dark blue-grey slabs, bronze inlay lines on the 64 grid, thin 16 sub-lines
        n = 64
        rgb = marble_rgb(n, n, seed, (70, 72, 88), 0.15, (40, 40, 52)) * R.T.ALBEDO
        yy, xx = np.mgrid[0:n, 0:n]
        rgb[(xx < 2) | (yy < 2)] = np.array(BRONZE) * 0.9
        rgb[(xx == 32) | (yy == 32)] *= 0.72
        return rgb
    if z == 'amp':             # arena sand: fine grain, raked ripples, a few pebbles
        n = 64
        g = fbm(n, n, seed, base=16, octaves=3)
        yy, xx = np.mgrid[0:n, 0:n]
        rip = 0.5 + 0.5 * np.sin(TAU * (4 * yy / n + 0.6 * fbm(n, n, seed + 1, base=2, octaves=2)))
        rgb = np.array((146, 124, 84), float) * (0.88 + 0.10 * g + 0.05 * rip)[..., None] * R.T.ALBEDO
        rng = np.random.default_rng(seed)
        for _ in range(9):
            x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
            rgb[y, x] *= 0.6
            rgb[y, (x + 1) % n] *= 0.75
        return rgb
    if z == 'pal':             # chequer: cream and charcoal marble squares of 32
        n = 64
        a = marble_rgb(n, n, seed, (166, 160, 146), 0.16) * R.T.ALBEDO
        b = marble_rgb(n, n, seed + 7, CHAR, 0.20, (120, 116, 110)) * R.T.ALBEDO
        yy, xx = np.mgrid[0:n, 0:n]
        chk = ((xx // 32) + (yy // 32)) % 2 == 1
        rgb = np.where(chk[..., None], b, a)
        rgb[(xx % 32 == 0) | (yy % 32 == 0)] *= 0.7
        return rgb
    if z == 'stoa':            # terracotta tiles 32, dark grout, each tile its own tone
        n = 64
        hm = HM(n, n)
        rng = np.random.default_rng(seed)
        tm = np.ones((n, n))
        for y in (0, 32):
            for x in (0, 32):
                hm.plate(x + 1, y + 1, x + 32, y + 32, 1.0, 2)
                tm[(hm.X >= x) & (hm.X < x + 32) & (hm.Y >= y) & (hm.Y < y + 32)] = 1 + 0.12 * (rng.random() * 2 - 1)
        rgb = colorize(TERRA, hm.shade(0.9), fbm(n, n, seed, base=4), grime_map(n, n, seed + 4, 0.14, False))
        rgb = rgb * tm[..., None]
        rgb[hm.H < 0.15] = (54, 42, 34)
        return rgb
    # brk: worn limestone flags, staggered
    n = 64
    hm = HM(n, n)
    hm.plate(1, 1, 40, 32, 0.8, 2)
    hm.plate(41, 1, 64, 32, 0.8, 2)
    hm.plate(25, 33, 64 + 1, 64, 0.8, 2)
    hm.plate(1, 33, 24, 64, 0.8, 2)
    rgb = colorize((132, 122, 104), hm.shade(1.0), fbm(n, n, seed, base=4), grime_map(n, n, seed + 5, 0.2, False))
    rgb[hm.H < 0.1] = (48, 44, 38)
    return rgb


# ------------------------------------------------------------------ ceilings
def tex_ceil(z, seed):
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    if z == 'atr':             # coffers: cream frame, stepped recess, gold rosette
        hm = HM(n, n)
        hm.plate(0, 0, n, n, 2.0, 1)
        hm.plate(8, 8, 56, 56, -1.0, 2, mode='add')
        hm.plate(14, 14, 50, 50, -1.0, 2, mode='add')
        rgb = marble_rgb(n, n, seed, (128, 122, 110), 0.10) * hm.shade(1.0)[..., None] * R.T.ALBEDO
        rec = (xx >= 14) & (xx < 50) & (yy >= 14) & (yy < 50)
        rgb[rec] = rgb[rec] * 0.55 + np.array((60, 40, 50)) * 0.45 * 0.8     # porphyry-dark recess
        r = np.hypot(xx - 31.5, yy - 31.5)
        ang = np.arctan2(yy - 31.5, xx - 31.5)
        ros = r < 7 + 2 * np.cos(8 * ang)
        rgb[ros] = np.array(GOLD) * (1.1 - r[ros] / 14)[..., None]
        return rgb
    if z == 'obs':             # painted heaven: deep blue with gold stars, faint rib lines every 64
        rgb = np.array((26, 30, 60), float) * (0.8 + 0.4 * fbm(n, n, seed, base=3))[..., None] * R.T.ALBEDO
        rng = np.random.default_rng(seed)
        for _ in range(14):
            x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
            rgb[y, x] = (200, 176, 90)
        rgb[(xx < 2) | (yy < 2)] = np.array(BRONZE_D) * 1.1
        return rgb
    if z in ('amp', 'stoa', 'pal'):   # timber: beams along x every 64, planks between
        wood = {'amp': (88, 64, 44), 'stoa': (100, 72, 46), 'pal': (76, 56, 42)}[z]
        hm = HM(n, n)
        for y in range(0, n, 8):
            hm.plate(0, y + 1, n, y + 8, 0.6, 1)
        hm.plate(0, 0, n, 14, 2.4, 2)
        grain = fbm(n, n, seed, base=4, octaves=4, sy=1, sx=8)
        rgb = colorize(wood, hm.shade(1.0), grain, grime_map(n, n, seed + 2, 0.15, False))
        rgb[(yy >= 14) & (yy < 16)] *= 0.45
        if z == 'pal':          # painted beam soffit: red band with an ochre line
            rgb[2:12] = rgb[2:12] * 0.5 + np.array(POMP) * 0.5 * R.T.ALBEDO
            rgb[6:8] = np.array((150, 112, 50)) * R.T.ALBEDO
        return rgb
    # brk: brick soffit
    return _brick_soffit(seed)


def _brick_soffit(seed):
    h, w = 64, 64
    hm = HM(h, w)
    for r in range(8):
        off = 16 if r % 2 else 0
        for x in range(0, w, 32):
            hm.plate(x + off + 1, r * 8 + 2, x + off + 31, r * 8 + 8, 1.0, 1)
    rgb = colorize((96, 56, 42), hm.shade(0.9), fbm(h, w, seed, base=4), grime_map(h, w, seed + 3, 0.2, False))
    rgb[hm.H < 0.2] = (70, 62, 54)
    return rgb


# ------------------------------------------------------------------ bands
def tex_strip(z, seed):
    """64x16 lamp band: bronze housing, a row of oil-lamp glass panes between palmette bosses."""
    core_i, edge_i = GLOW[z]
    hm = HM(16, 64)
    hm.plate(0, 0, 64, 16, 1.4, 2)
    hm.groove(0, 3, 64, 13, 1.0)
    for x in (16, 48):
        hm.dome(x, 8, 4.5, 2.0)
    rgb = colorize(BRONZE, hm.shade(1.0), fbm(16, 64, seed, base=4))
    rgb[3:13] *= 0.35
    idx = R.quantize(rgb)
    yy, xx = np.mgrid[0:16, 0:64]
    d = np.minimum((xx - 16) % 32, 32 - (xx - 16) % 32)
    boss = np.hypot(d, yy - 8) < 5
    pane = (~boss) & (yy >= 5) & (yy <= 10) & (np.abs(d) >= 6)
    edge = pane & ((yy == 5) | (yy == 10) | (d == 6))
    idx[pane] = core_i
    idx[edge] = edge_i
    bi = R.quantize(colorize(np.array(BRONZE) * 1.25, hm.shade(1.2), fbm(16, 64, seed + 1, base=4)))
    idx[boss] = bi[boss]
    return idx


def tex_base(seed):                # dado: porphyry with white specks, bronze lip
    h, w = 32, 64
    hm = HM(h, w)
    hm.plate(0, 4, 64, 32, 1.3, 2)
    hm.groove(0, 29, 64, 30, 0.5)
    rgb = colorize(PORPH, hm.shade(), fbm(h, w, seed, base=6), grime_map(h, w, seed, 0.12, False))
    sp = fbm(h, w, seed + 3, base=32, octaves=1) > 0.86
    rgb[sp] = (150, 120, 120)
    rgb[0:3] = BRONZE
    rgb[1] = np.array(BRONZE) * 1.25
    rgb[3] = (24, 16, 14)
    return rgb


def tex_trim(seed):                # cornice: cream fillet, dentils, a bead
    h, w = 16, 64
    hm = HM(h, w)
    hm.plate(0, 0, 64, 4, 1.8, 1)                    # fillet
    for x in range(0, 64, 8):
        hm.plate(x + 1, 5, x + 7, 11, 1.4, 1)        # dentils
    for x in range(0, 64, 4):
        hm.dome(x + 2, 13, 1.6, 1.0)                 # bead
    rgb = marble_rgb(h, w, seed, (176, 170, 152), 0.08) * hm.shade(1.2)[..., None] * R.T.ALBEDO
    rgb[4] *= 0.55
    rgb[11] *= 0.6
    return rgb


def tex_tread(seed):               # marble step slab: worn centre, darker arris
    n = 32
    hm = HM(n, n)
    hm.plate(0, 1, n, n, 0.5, 4)
    rgb = marble_rgb(n, n, seed, (158, 154, 140), 0.14) * hm.shade(1.0)[..., None] * R.T.ALBEDO
    return rgb * (1 - grime_map(n, n, seed, 0.10, False)[..., None])


def tex_riser(seed):               # marble riser: rounded nosing highlight, shadow below it
    h, w = 16, 32
    rgb = marble_rgb(h, w, seed, (124, 121, 112), 0.10) * R.T.ALBEDO
    rgb[0:2] = rgb[0:2] * 1.3
    rgb[2] *= 0.45
    rgb[3] *= 0.75
    return rgb


# ------------------------------------------------------------------ columns
def _flutes(h, w, seed):
    hm = HM(h, w)
    xx = np.arange(w)
    prof = np.cos(TAU * (xx % 8) / 8)                # concave flutes, 8 per 64
    hm.H = np.broadcast_to(0.9 * prof, (h, w)).copy()
    hm.H[:, (xx % 8) == 0] += 0.6                    # fillets between flutes
    return hm


def tex_pillar(seed):              # fluted cream marble shaft (no collars: vertically uniform)
    h, w = 128, 64
    hm = _flutes(h, w, seed)
    rgb = marble_rgb(h, w, seed, (176, 170, 152), 0.12, cy=2, cx=1) * hm.shade(0.45)[..., None] * R.T.ALBEDO
    return rgb * (1 - grime_map(h, w, seed + 1, 0.08)[..., None])


def tex_pcap(seed):                # capital: abacus, egg-and-dart, bronze necking ring, flute tops
    h, w = 32, 64
    hm = _flutes(h, w, seed)
    hm.H[0:20] = 0
    hm.plate(0, 0, 64, 7, 2.2, 1)                    # abacus
    for x in range(0, 64, 8):
        hm.dome(x + 4, 13, 4.2, 1.6)                 # eggs
    hm.plate(0, 21, 64, 25, 1.8, 1)                  # necking ring
    rgb = marble_rgb(h, w, seed, (178, 172, 154), 0.08) * hm.shade(0.9)[..., None] * R.T.ALBEDO
    rgb[7] *= 0.45
    for x in range(0, 64, 8):                        # darts
        rgb[9:17, x] = rgb[9:17, x] * 0.5
    rgb[21:25] = np.array(BRONZE) * hm.shade(0.9)[21:25, :, None] * 1.1
    rgb[19:21] *= 0.6
    return rgb


def tex_pbase(seed):               # base: flute ends, bronze ring, torus, square plinth
    h, w = 32, 64
    hm = _flutes(h, w, seed)
    hm.H[8:32] = 0
    hm.plate(0, 8, 64, 11, 1.6, 1)                   # bronze ring
    yy = np.arange(h)
    tor = np.clip(1 - ((yy - 16) / 4.5) ** 2, 0, 1)
    hm.H[12:21] = np.maximum(hm.H[12:21], 2.0 * np.sqrt(tor[12:21])[:, None])
    hm.plate(0, 22, 64, 32, 1.2, 1)                  # plinth
    rgb = marble_rgb(h, w, seed, (176, 170, 152), 0.08) * hm.shade(0.9)[..., None] * R.T.ALBEDO
    rgb[8:11] = np.array(BRONZE) * hm.shade(0.9)[8:11, :, None] * 1.1
    rgb[22:32] = (marble_rgb(10, 64, seed + 3, PORPH, 0.1) * R.T.ALBEDO * hm.shade(0.9)[22:32, :, None])
    rgb[21] *= 0.5
    return rgb


# ------------------------------------------------------------------ blocks, lamps
def tex_block(seed, top=False):    # marble altar block: laurel wreath relief, bronze corner caps
    n = 64
    hm = HM(n, n)
    hm.plate(0, 0, n, n, 1.0, 1)
    hm.plate(5, 5, 59, 59, -0.6, 2, mode='add')
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(xx - 31.5, yy - 31.5)
    if top:
        hm.plate(16, 16, 48, 48, 0.4, 1, mode='add')
    else:
        ang = np.arctan2(yy - 31.5, xx - 31.5)
        leaf = (np.abs(r - 16) < 3.2) & (np.cos(14 * ang) > -0.2) & ~((ang > 1.25) & (ang < 1.9))
        hm.H[leaf] += 1.1
    rgb = marble_rgb(n, n, seed, (168, 162, 146), 0.12) * hm.shade(1.0)[..., None] * R.T.ALBEDO
    cap = ((xx < 7) | (xx >= 57)) & ((yy < 7) | (yy >= 57))
    rgb[cap] = np.array(BRONZE) * hm.shade(1.0)[cap][..., None] * 1.05
    if top:
        ins = (np.abs(xx - 31.5) < 16.5) & (np.abs(yy - 31.5) < 16.5) & ~((np.abs(xx - 31.5) < 14.5) & (np.abs(yy - 31.5) < 14.5))
        rgb[ins] = np.array(BRONZE) * 1.05
    return rgb * (1 - grime_map(n, n, seed + 2, 0.12)[..., None])


def tex_lampbox(seed):
    hm = HM(16, 32)
    hm.plate(0, 2, 32, 14, 1.0, 2)
    return colorize(BRONZE_D, hm.shade(), fbm(16, 32, seed))


def tex_light(seed):               # ceiling lamp underside: amber glass disc in a bronze ring, radial ribs
    y, x = np.mgrid[0:32, 0:32]
    r = np.hypot(x - 15.5, y - 15.5)
    ang = np.arctan2(y - 15.5, x - 15.5)
    idx = np.full((32, 32), q1(BRONZE_D), np.uint8)
    glass = r < 13
    idx[glass] = 237
    idx[glass & (r > 10.5)] = 235
    idx[r < 5] = 239
    idx[glass & (np.abs(np.sin(4 * ang)) < 0.12) & (r > 5)] = q1(BRONZE_D)
    idx[(r >= 13) & (r < 15)] = q1(BRONZE)
    return idx


def tex_wlamp(seed, kind='lantern'):
    """Wall fixtures, 32x32. lantern: bronze frame with amber glass; fire: bronze bowl with
    flames; star: bronze armillary ring with moon-white glass."""
    y, x = np.mgrid[0:32, 0:32]
    hm = HM(32, 32)
    if kind == 'fire':
        rgb = np.zeros((32, 32, 3)) + np.array(BRONZE_D) * 0.8
        bowl = (y >= 18) & (np.abs(x - 15.5) < 14 - (y - 18) * 0.6)
        hm.H[bowl] = 1.0
        b = colorize(BRONZE, hm.shade(1.2), fbm(32, 32, seed))
        rgb[bowl] = b[bowl]
        rgb[18] = np.array(BRONZE) * 1.3
        idx = R.quantize(rgb)
        fl = fbm(32, 32, seed + 3, base=4, octaves=3)
        hgt = (18 - y).astype(float)
        wid = np.zeros((32, 32))
        for cx_, top in ((15.5, 16.0), (9.5, 10.0), (21.5, 11.0)):     # three tongues
            wid = np.maximum(wid, (1 - hgt / top) * (6.5 if cx_ == 15.5 else 4.0) - np.abs(x - cx_) + 2 * (fl - 0.5))
        flame = (y < 18) & (wid > 0)
        heat = np.clip(1 - hgt / 16 + 0.25 * (fl - 0.5) + 0.06 * wid, 0, 1)
        ramp = np.array([232, 233, 234, 235, 236, 237, 238, 239])
        idx[flame] = ramp[np.clip((heat[flame] * 7.99).astype(int), 0, 7)]
        return idx
    hm.plate(0, 0, 32, 32, 1.5, 3)
    rivet_row(hm, 2, 2, 32, 28, r=1.0)
    rivet_row(hm, 29, 2, 32, 28, r=1.0)
    idx = R.quantize(colorize(BRONZE, hm.shade(), fbm(32, 32, seed)))
    if kind == 'star':
        r = np.hypot(x - 15.5, y - 15.5)
        glass = r < 10
        idx[glass] = 245
        idx[glass & (r > 8)] = 244
        idx[r < 3.5] = 246
        idx[(np.abs(r - 12) < 1.2)] = q1(GOLD)
        idx[glass & ((np.abs(x - 15.5) < 0.8) | (np.abs(y - 15.5) < 0.8)) & (r > 3.5)] = q1(BRONZE_D)
        return idx
    glass = (x >= 7) & (x < 25) & (y >= 5) & (y < 27)
    arch = glass & ~((y < 10) & (np.hypot(x - 15.5, y - 10) > 9))
    idx[arch] = 237
    idx[arch & ((x == 7) | (x == 24) | (y == 26))] = 235
    idx[arch & (np.hypot(x - 15.5, y - 17) < 3.5)] = 239
    idx[arch & (abs(x - 15.5) < 1)] = q1(BRONZE_D)
    return idx


# ------------------------------------------------------------------ floor / ceiling medallions
def tex_medal(seed):               # 128: mosaic medallion for the RL plinth top
    n = 128
    yy, xx = np.mgrid[0:n, 0:n]
    cx = cy = 63.5
    r = np.hypot(xx - cx, yy - cy)
    ang = np.arctan2(yy - cy, xx - cx)
    base = marble_rgb(n, n, seed, (164, 158, 142), 0.15)
    col = base.copy()
    col[r < 60] = (156, 150, 136)                                    # cream field
    wave = (r >= 48) & (r < 56)
    chk = ((np.floor((ang + np.pi) / (TAU / 48)) + (r >= 52)) % 2) == 0
    col[wave & chk] = (40, 34, 32)
    col[wave & ~chk] = (156, 146, 128)
    col[(r >= 56) & (r < 60)] = BRONZE
    col[(r >= 45) & (r < 48)] = (40, 34, 32)
    col[r < 45] = TERRA
    # 8-point star: two squares, cream with a dark outline
    def sq(a):
        u = (xx - cx) * np.cos(a) + (yy - cy) * np.sin(a)
        v = -(xx - cx) * np.sin(a) + (yy - cy) * np.cos(a)
        return np.maximum(np.abs(u), np.abs(v))
    s = np.minimum(sq(0), sq(np.pi / 4))
    col[(s < 30) & (r < 45)] = (40, 34, 32)
    col[(s < 27) & (r < 45)] = (172, 164, 146)
    col[r < 14] = (40, 34, 32)
    col[r < 12] = GOLD
    col[r < 5] = TERRA
    m = mosaic(col, 4, 0.78)
    out = np.where((r < 60)[..., None], m, base) * R.T.ALBEDO
    return out


def tex_rose(seed):                # 192: compass rose inlaid in the observatory floor
    n = 192
    yy, xx = np.mgrid[0:n, 0:n]
    c = (n - 1) / 2
    r = np.hypot(xx - c, yy - c)
    ang = np.arctan2(yy - c, xx - c)
    rgb = marble_rgb(n, n, seed, (70, 72, 88), 0.15, (40, 40, 52))
    ring = (np.abs(r - 90) < 2.2) | (np.abs(r - 80) < 1.4)
    tick = (r > 80) & (r < 90) & (np.abs(np.sin(6 * ang)) < 0.05)
    small = (r > 84) & (r < 90) & (np.abs(np.sin(36 * ang)) < 0.12)
    rgb[ring | tick | small] = np.array(BRONZE) * 1.1

    def star(npts, rad, w0, phase=0.0):
        a = (ang - phase) % (TAU / npts) - TAU / npts / 2
        return r < rad * (1 - np.abs(a) / (TAU / npts / 2)) + w0 * (1 - r / rad)

    big = star(4, 76, 4)
    mid = star(4, 52, 3, np.pi / 4)
    sml = star(8, 34, 2, np.pi / 8)
    side = np.sin(4 * (ang)) > 0
    rgb[sml] = np.array(BRONZE) * 0.95
    rgb[mid] = np.where(side[mid][..., None], np.array((60, 60, 72)), np.array((128, 120, 106)))
    rgb[big] = np.where((np.sin(4 * (ang - np.pi / 4)) > 0)[big][..., None],
                        np.array((156, 146, 128)), np.array((86, 84, 92)))
    edge = big ^ np.roll(big, 1, 0) | big ^ np.roll(big, 1, 1)
    rgb[edge] = np.array(BRONZE_D)
    rgb[r < 9] = GOLD
    rgb[r < 4] = BRONZE_D
    return rgb * R.T.ALBEDO


def tex_ocring(seed):              # 192: ceiling around the 128 oculus - bronze rings and gold stars
    n = 192
    yy, xx = np.mgrid[0:n, 0:n]
    c = (n - 1) / 2
    d = np.maximum(np.abs(xx - c), np.abs(yy - c))   # square frame (the hole is square)
    rgb = np.array((26, 30, 60), float) * (0.8 + 0.4 * fbm(n, n, seed, base=4))[..., None] * R.T.ALBEDO
    hm = HM(n, n)
    for d0, d1, hh in ((64, 72, 2.0), (80, 84, 1.4), (92, 96, 1.4)):
        m = (d >= d0) & (d < d1)
        hm.H[m] = hh
    sh = hm.shade(1.0)
    m = hm.H > 0
    rgb[m] = (np.array(BRONZE) * sh[..., None])[m]
    rng = np.random.default_rng(seed)
    for _ in range(40):
        x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
        if 73 <= max(abs(x - c), abs(y - c)) < 79 or 85 <= max(abs(x - c), abs(y - c)) < 91:
            rgb[y, x] = (210, 186, 96)
    return rgb


def tex_sky(seed):                 # night: deep blue-black, a faint milky way, many stars; thin clouds in front
    n = 128
    back = R.fbm(n, n, seed, base=3, octaves=5)
    yy, xx = np.mgrid[0:n, 0:n]
    band = np.exp(-((((xx + yy * 0.6) % n) - 64) / 14.0) ** 2) * (0.6 + 0.6 * R.fbm(n, n, seed + 3, base=8, octaves=3))
    c0, c1 = np.array([6, 8, 20]), np.array([30, 34, 64])
    bi = R.quantize(c0 + (c1 - c0) * np.clip(back * 0.6 + band * 0.7, 0, 1)[..., None])
    rng = np.random.default_rng(seed)
    for _ in range(170):
        x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
        bi[y, x] = [254, 253, 245, 246, 252][int(rng.integers(0, 5))] if rng.random() < 0.55 else q1((120, 120, 140))
    front = R.fbm(n, n, seed + 50, base=4, octaves=4)
    fa = np.clip((front - 0.58) * 3.0, 0, 1)
    fi = R.quantize(np.array([36, 38, 58]) * (0.7 + 0.4 * fa[..., None]))
    fi = np.where(fi == 0, 1, fi)
    fi = np.where(fa > 0.2, fi, 0)
    return np.concatenate([fi, bi], 1)


# ------------------------------------------------------------------ b4: black fresco duel hall + gallery
BLACK = (26, 24, 24)
VERMIL = (168, 52, 34)
GOLDL = (196, 160, 72)
WHITE = (176, 172, 158)


def fre_wall(seed):
    """Pompeian 'black room' panels, 64 x 80: black field, vermilion frame bands, gilt inner line,
    a gold candelabrum in each divider and a gilt rosette in each panel."""
    h, w = 80, 128
    yy, xx = np.mgrid[0:h, 0:w]
    cl = fbm(h, w, seed, base=3, octaves=4)
    rgb = np.array(BLACK) * (0.85 + 0.3 * cl)[..., None]
    X = xx % 64
    div = X < 12
    red = ((X >= 12) & (X < 15)) | (X >= 61) | (yy < 3) | (yy >= h - 3)
    rgb[red] = np.array(VERMIL) * (0.85 + 0.3 * cl[red])[..., None]
    gl = (((X == 18) | (X == 57)) & (yy >= 7) & (yy < h - 7)) | (((yy == 7) | (yy == h - 8)) & (X >= 18) & (X <= 57))
    rgb[gl] = GOLDL
    stalk = (X >= 5) & (X < 7) & (yy >= 6) & (yy < h - 6)
    rgb[stalk] = (150, 120, 56)
    for y0 in range(12, h - 8, 14):
        rgb[y0, :][(X[y0] >= 2) & (X[y0] < 10)] = (150, 120, 56)
        rgb[(np.hypot(X - 5.5, yy - (y0 + 6)) < 2.0) & div] = (190, 150, 66)
    r = np.hypot(X - 37.5, yy - 39.5)
    ang = np.arctan2(yy - 39.5, X - 37.5)
    ros = (r < 5 + 1.6 * np.cos(6 * ang)) & (X >= 15)
    rgb[ros] = GOLDL
    rgb[(np.abs(r - 9) < 0.7) & (X >= 15)] = (150, 120, 56)
    return rgb * R.T.ALBEDO


def gal_wall(seed):
    """Gallery: black stucco between vermilion pilasters (every 64) with gilt edges, a thin gold
    candelabrum up the middle of each bay. Vertical only, so any wall height reads whole."""
    h, w = 128, 128
    yy, xx = np.mgrid[0:h, 0:w]
    cl = fbm(h, w, seed, base=3, octaves=4)
    rgb = np.array(BLACK) * (0.85 + 0.3 * cl)[..., None]
    X = xx % 64
    pil = X < 12
    rgb[pil] = np.array(VERMIL) * (0.85 + 0.3 * cl[pil])[..., None]
    rgb[(X == 0) | (X == 11)] = GOLDL
    rgb[(X == 1) | (X == 10)] *= 0.6
    stalk = (X >= 37) & (X < 39)
    rgb[stalk] = (150, 120, 56)
    for y0 in range(8, h, 32):
        rgb[(np.hypot(X - 37.5, yy - y0) < 2.4)] = (190, 150, 66)
        for s in (-1, 1):
            leaf = (np.abs((X - 37.5) - s * 4) < 3) & (np.abs(yy - (y0 + 10) + np.abs(X - 37.5) * 0.6) < 1)
            rgb[leaf] = (150, 120, 56)
    return rgb * R.T.ALBEDO


_KEY = ['.######.',
        '.#....#.',
        '.#.##.#.',
        '.#.####.',
        '.#......',
        '########']


def fre_floor(seed):
    """Black-and-white Roman mosaic laid tessera by tessera (4 units each): slate field, a running
    Greek-key band along two edges of every 128 square (so the floor reads as a grid of framed
    panels), a framed corner block where bands cross, a white diamond with a vermilion heart."""
    T, n = 4, 128
    g = n // T                                     # 32 tesserae
    key = np.array([[c == '#' for c in row] for row in _KEY])
    grid = np.zeros((g, g), int)                   # 0 slate, 1 white, 2 vermilion
    for ty in range(g):
        for tx in range(g):
            if ty < 8 and tx >= 8:                 # horizontal band: border, gap, 6-row key
                grid[ty, tx] = 1 if ty == 0 else (key[ty - 2, (tx - 8) % 8] if ty >= 2 else 0)
            elif tx < 8 and ty >= 8:               # vertical band (same key, turned)
                grid[ty, tx] = 1 if tx == 0 else (key[tx - 2, (ty - 8) % 8] if tx >= 2 else 0)
            elif tx < 8 and ty < 8:                # corner block
                ring = max(abs(tx - 4.5), abs(ty - 4.5))
                if tx == 0 or ty == 0 or tx == 7 or ty == 7 or (1.5 <= ring < 2.5):
                    grid[ty, tx] = 1
                elif ring < 1:
                    grid[ty, tx] = 2
            else:                                  # field: diamond
                d = abs(tx - 19.5) + abs(ty - 19.5)
                if 5 <= d < 6:
                    grid[ty, tx] = 1
                elif d < 2:
                    grid[ty, tx] = 2
    rng = np.random.default_rng(seed)
    cols = {0: np.array((64, 62, 64)), 1: np.array(WHITE), 2: np.array((150, 46, 34))}
    rgb = np.zeros((n, n, 3))
    for ty in range(g):
        for tx in range(g):
            c = cols[grid[ty, tx]] * (0.9 + 0.18 * rng.random())
            rgb[ty * T:(ty + 1) * T, tx * T:(tx + 1) * T] = c
    yy, xx = np.mgrid[0:n, 0:n]
    rgb[(yy % T == 0) | (xx % T == 0)] *= 0.72
    return rgb * R.T.ALBEDO


def fre_ceil(seed):
    """Black-painted timber with vermilion and gilt beam soffits."""
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    hm = HM(n, n)
    for y in range(0, n, 8):
        hm.plate(0, y + 1, n, y + 8, 0.6, 1)
    hm.plate(0, 0, n, 14, 2.4, 2)
    grain = fbm(n, n, seed, base=4, octaves=4, sy=1, sx=8)
    rgb = colorize((44, 38, 36), hm.shade(1.0), grain)
    rgb[2:12] = np.array(VERMIL) * 0.55
    rgb[6:8] = GOLDL
    rgb[(yy >= 14) & (yy < 16)] *= 0.45
    return rgb


def _key_cells():
    return np.array([[c == '#' for c in row] for row in _KEY])


def tex_dais(seed):
    """192: mosaic for the YA platform top, laid tessera by tessera (48 x 48 of 4): a Greek-key band
    running round all four edges (baseline inward), framed corner blocks, and a gold victor's laurel
    wreath tied with a vermilion ribbon round a white star."""
    T, n = 4, 192
    g = n // T
    key = _key_cells()
    grid = np.zeros((g, g), int)                   # 0 slate, 1 white, 2 vermilion, 3 gold, 4 dark gold
    for ty in range(g):
        for tx in range(g):
            inx, iny = 8 <= tx < g - 8, 8 <= ty < g - 8
            if not inx and not iny:                # corner block
                cx, cy = (tx if tx < 8 else g - 1 - tx), (ty if ty < 8 else g - 1 - ty)
                ring = max(abs(cx - 3.5), abs(cy - 3.5))
                if cx == 0 or cy == 0 or cx == 7 or cy == 7 or (1.5 <= ring < 2.5):
                    grid[ty, tx] = 1
                elif ring < 1:
                    grid[ty, tx] = 2
            elif not iny:                          # top / bottom bands
                r = ty if ty < 8 else g - 1 - ty
                grid[ty, tx] = 1 if r == 0 else (key[r - 2, (tx - 8) % 8] if r >= 2 else 0)
            elif not inx:                          # left / right bands
                r = tx if tx < 8 else g - 1 - tx
                grid[ty, tx] = 1 if r == 0 else (key[r - 2, (ty - 8) % 8] if r >= 2 else 0)
            else:                                  # field: wreath, ribbon, star
                dx, dy = tx - 23.5, ty - 23.5
                rr = np.hypot(dx, dy)
                a = np.arctan2(dy, dx)
                if 8.5 <= rr < 12.5 and dy < 9:     # laurel: leaf pairs along the ring
                    ph = (a * 12 / np.pi) % 2
                    leaf = abs(rr - 10.5) < 1.6 - 0.7 * abs(ph - 1)
                    if leaf:
                        grid[ty, tx] = 3 if (rr < 10.5) == (ph < 1) else 4
                if 9.5 <= dy < 14.5 and abs(abs(dx) - (0.8 + (dy - 9.5) * 0.85)) < 0.9:
                    grid[ty, tx] = 2               # ribbon: two tails from a knot under the wreath
                if 8.5 <= dy < 10.5 and abs(dx) < 1.6:
                    grid[ty, tx] = 2
                s8 = max(abs(dx), abs(dy)) * 0.75 + 0.25 * min(abs(dx), abs(dy))
                s8b = (abs(dx) + abs(dy)) * 0.72
                if min(s8, s8b) < 3.6:
                    grid[ty, tx] = 1
                if rr < 1.2:
                    grid[ty, tx] = 2
                if 13.5 <= max(abs(dx), abs(dy)) < 14.5:
                    grid[ty, tx] = 1               # thin white frame round the field
    rng = np.random.default_rng(seed)
    cols = {0: np.array((64, 62, 64)), 1: np.array(WHITE), 2: np.array((150, 46, 34)),
            3: np.array((200, 164, 72)), 4: np.array((140, 108, 44))}
    rgb = np.zeros((n, n, 3))
    for ty in range(g):
        for tx in range(g):
            rgb[ty * T:(ty + 1) * T, tx * T:(tx + 1) * T] = cols[grid[ty, tx]] * (0.9 + 0.18 * rng.random())
    yy, xx = np.mgrid[0:n, 0:n]
    rgb[(yy % T == 0) | (xx % T == 0)] *= 0.72
    return rgb * R.T.ALBEDO


def cli_floor(seed):
    """Climb landings and the small doorways: slate tesserae with a small white diamond every 32."""
    T, n = 4, 64
    g = n // T
    grid = np.zeros((g, g), int)
    for ty in range(g):
        for tx in range(g):
            d = abs((tx % 8) - 3.5) + abs((ty % 8) - 3.5)
            if d < 1.5:                            # small white diamond every 32 - a calm dot grid
                grid[ty, tx] = 1
    rng = np.random.default_rng(seed)
    cols = {0: np.array((64, 62, 64)), 1: np.array(WHITE)}
    rgb = np.zeros((n, n, 3))
    for ty in range(g):
        for tx in range(g):
            rgb[ty * T:(ty + 1) * T, tx * T:(tx + 1) * T] = cols[grid[ty, tx]] * (0.9 + 0.18 * rng.random())
    yy, xx = np.mgrid[0:n, 0:n]
    rgb[(yy % T == 0) | (xx % T == 0)] *= 0.72
    return rgb * R.T.ALBEDO


ZONES = ('atr', 'obs', 'amp', 'pal', 'stoa', 'brk', 'gal', 'cli')


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    names = []

    # b3: error-diffusion onto the palette - stone and marble use the neutral/warm ramps only so
    # greys and the rosy-beige ramp mix into cream; coloured surfaces may use every non-fullbright
    FULL = list(range(0, 224))
    stone = ('atr_', 'trim', 'tread', 'riser', 'pillar', 'pcap', 'pbase', 'crate', 'amp_', 'brk_', 'stoa_')

    def put(name, img):
        if img.ndim == 2:
            idx = img
        else:
            if any(k in name for k in stone) and 'ceil' not in name:
                idx = fs_quantize(np.clip(img, 0, 255), STONE, 0.9, seed=len(names))
            else:                      # coloured surfaces: plain nearest colour (diffusion speckles reds)
                idx = R.quantize(np.clip(img, 0, 255))
        R.save(outdir, name, idx)
        names.append(name)

    for k, z in enumerate(ZONES):
        s = 7300 + 41 * k
        if z in ('pal', 'gal', 'cli'):     # b4/b5: black fresco duel hall, its gallery and the climb
            put(f'ly_{z}_wall', fre_wall(s) if z == 'pal' else gal_wall(s if z == 'gal' else s - 41))
            put(f'ly_{z}_flr', cli_floor(s + 1) if z == 'cli' else fre_floor(s + 1))
            put(f'ly_{z}_ceil', fre_ceil(s + 2))
        else:
            put(f'ly_{z}_wall', tex_wall(z, s))
            put(f'ly_{z}_flr', tex_floor(z, s + 1))
            put(f'ly_{z}_ceil', tex_ceil(z, s + 2))
        put(f'ly_{z}_strp', tex_strip(z, s + 3))
    put('ly_base', tex_base(71))
    put('ly_trim', tex_trim(72))
    put('ly_tread', tex_tread(73))
    put('ly_riser', tex_riser(74))
    put('ly_pillar', tex_pillar(75))
    put('ly_pcap', tex_pcap(76))
    put('ly_pbase', tex_pbase(77))
    put('ly_crate', tex_block(78))
    put('ly_cratetop', tex_block(79, top=True))
    put('ly_lampbox', tex_lampbox(80))
    put('ly_light', tex_light(81))
    put('ly_wlamp', tex_wlamp(82, 'lantern'))
    put('ly_wfire', tex_wlamp(83, 'fire'))
    put('ly_wstar', tex_wlamp(84, 'star'))
    put('ly_medal', tex_medal(85))
    put('ly_rose', tex_rose(86))
    put('ly_dais', tex_dais(89))
    put('ly_ocring', tex_ocring(87))
    put('sky_lyceum', tex_sky(88))
    open(os.path.join(outdir, '..', 'ltex_names.txt'), 'w').write('\n'.join(names) + '\n')
    print(len(names), 'textures:', ' '.join(names))


if __name__ == '__main__':
    main(sys.argv[1])
