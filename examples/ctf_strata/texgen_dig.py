"""Original procedural 'The dig' textures for ctf_strata (all generated from code, quantized to the
Quake palette as distributed with LibreQuake, BSD-3).

An excavation through rock layers. The rock tells you which floor you are on:
  floor 0   dark blue-grey SLATE (lower halls, undercrofts), timber-lagged roofs, rails in the undercrofts
  the slab  a black COAL / iron seam, seen wherever the levels meet (pit, bases, well shafts)
  floor 256 pale LIMESTONE: chalk with flint bands (north decks), buff with fossils (south decks),
            grey (well rooms)
  the pit   the atrium is an open quarry under a night sky: slate below the seam, a drilled
            limestone quarry face above it
Team colour lives in mineral veins and crystal: lapis (blue base), cinnabar (red base).
Lights: caged miners' lamps; the light strip is a cable of caged bulbs on a timber batten.
Usage: python3 texgen_dig.py outdir      (writes outdir/*.png and wad_args.txt for makewad.py)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
import texgen_runic as R  # noqa: E402
from texgen import HM, fbm, colorize, grime_map  # noqa: E402
from fsq import fs_quantize, STONE, q1  # noqa: E402

R.T.ALBEDO = 0.84
TAU = 2 * np.pi

SLATE = (66, 72, 86)
SLATE_D = (40, 44, 54)
CHALK = (178, 174, 160)
BUFF = (170, 148, 108)
IRONSTONE = (150, 146, 138)
GREYL = (136, 138, 134)
COAL = (24, 23, 25)
RUST = (118, 64, 34)
OCHRE = (150, 108, 52)
TIMBER = (100, 72, 44)
TIMBER_D = (60, 42, 26)
IRON = (60, 60, 64)
IRON_L = (96, 96, 102)
GRAVEL = (70, 68, 66)
TEAM = {'b': dict(c1=(34, 46, 156), c2=(96, 120, 210), bulb=(244, 245), lamp=(245, 246)),     # lapis
        'r': dict(c1=(170, 52, 26), c2=(214, 116, 58), bulb=(233, 234), lamp=(234, 235)),    # cinnabar
        'n': dict(c1=(170, 160, 140), c2=(220, 214, 196), bulb=(237, 238), lamp=(238, 239))}  # quartz / warm
SLATE_SET = list(range(1, 16)) + list(range(32, 48)) + list(range(16, 24))
MASK = {}       # textures that mix saturated pixels into stone set MASK['m'] (True = nearest-colour pixel)


def q(img, pal=None, seed=0):
    """Stone: error-diffusion over a palette subset; masked pixels (veins, paint) nearest-colour."""
    img = np.clip(img, 0, 255)
    m = MASK.pop('m', None)
    if pal is None:
        return R.quantize(img)
    base = fs_quantize(img, pal, 0.85, seed=seed)
    if m is not None:
        base = np.where(m, R.quantize(img), base).astype(np.uint8)
    return base


def wrapd(v, c, n):
    return ((v - c + n / 2) % n) - n / 2


def hexmask(dx, dy, r):
    """Flat-topped hexagon."""
    ax, ay = np.abs(dx), np.abs(dy)
    return (ay < r * 0.866) & (ax * 0.866 + ay * 0.5 < r * 0.866)


# ------------------------------------------------------------------ rock
def hewn(h, w, seed, col, lam=7.0, chip=4, k=1.1):
    """Pick-hewn rock face: faceted chips (terraced noise), thin horizontal laminations."""
    hm = HM(h, w)
    yy, xx = np.mgrid[0:h, 0:w]
    big = fbm(h, w, seed, base=2, octaves=4)
    hm.H = np.floor(big * chip * 2) / chip * 1.6
    hm.H += 0.5 * fbm(h, w, seed + 1, base=8, octaves=3)
    wob = fbm(h, w, seed + 2, base=2, octaves=2, sy=1, sx=2) * 6
    lamin = np.sin(TAU * (yy + wob) / lam)
    hm.H += 0.18 * lamin
    var = 0.6 * fbm(h, w, seed + 3, base=4, octaves=3) + 0.4 * (0.5 + 0.5 * np.sin(TAU * (yy + wob) / (lam * 3.7)))
    rgb = colorize(col, hm.shade(k), var, grime_map(h, w, seed + 4, 0.16))
    return rgb, hm


def slate_wall(seed, col=SLATE, bolts=False, team=None):
    n = 128
    rgb, hm = hewn(n, n, seed, col, lam=6.0, chip=5)
    yy, xx = np.mgrid[0:n, 0:n]
    rust = np.clip(fbm(n, n, seed + 7, base=8, octaves=2, sy=0, sx=1) - 0.6, 0, 1) * 2.2
    rgb = rgb * (1 - 0.35 * rust[..., None]) + np.array(RUST) * 0.35 * rust[..., None] * 0.8
    mm = np.zeros((n, n), bool)
    if bolts:                                   # rockbolt plates on a staggered grid
        for cy, cx in ((32, 32), (96, 96)):
            plate = (np.abs(wrapd(xx, cx, n)) < 6) & (np.abs(wrapd(yy, cy, n)) < 6)
            rgb[plate] = np.array(IRON_L) * 0.84
            rim = plate & ((np.abs(wrapd(xx, cx, n)) >= 5) | (np.abs(wrapd(yy, cy, n)) >= 5))
            rgb[rim] = np.array(IRON) * 0.6
            rgb[np.hypot(wrapd(xx, cx, n), wrapd(yy, cy, n)) < 2.2] = np.array(IRON) * 0.5
            rgb[(np.abs(wrapd(xx, cx, n)) < 6) & (wrapd(yy, cy, n) >= 6) & (wrapd(yy, cy, n) < 14)] *= 0.75
    if team:
        T = TEAM[team]
        v = fbm(n, n, seed + 11, base=3, octaves=4)
        frag = fbm(n, n, seed + 13, base=3, octaves=2) > 0.5
        vein = (np.abs(v - 0.5) < 0.008) & frag
        rgb[vein] = np.array(T['c1']) * 0.8
        mm |= vein
        rng = np.random.default_rng(seed)
        for _ in range(2):                      # small crystal clusters on the veins
            ys, xs = np.nonzero(vein)
            if not len(ys):
                break
            k = rng.integers(0, len(ys))
            cy, cx = ys[k], xs[k]
            for dx, dy, r in ((0, 0, 4.5), (5, -3, 3.2), (-4, 3, 3.0)):
                hx = hexmask(wrapd(xx, cx + dx, n), wrapd(yy, cy + dy, n), r)
                rgb[hx] = T['c2']
                rgb[hx & (wrapd(yy, cy + dy, n) > 0)] = T['c1']
                mm |= hx
    MASK['m'] = mm
    return rgb


def limestone(seed, col, kind):
    """Sawn limestone blocks (32-tall courses), sedimentary bands; chalk: flint nodules, buff: fossils."""
    n = 128
    hm = HM(n, n)
    yy, xx = np.mgrid[0:n, 0:n]
    rng = np.random.default_rng(seed)
    tone = np.ones((n, n))
    for r in range(4):
        off = (r * 40) % 96
        x = -96
        while x < n + 96:
            L = 96 if (r + x // 96) % 2 else 64
            hm.plate(x + off + 1, r * 32 + 1, x + off + L, r * 32 + 32, 1.0, 2)
            X = (xx - (x + off)) % n
            tone[(X < L) & (yy >= r * 32) & (yy < r * 32 + 32)] = 1 + 0.07 * (rng.random() * 2 - 1)
            x += L
    saw = (np.sin(TAU * (xx * 0.8 + yy * 0.35) / 5.0) * 0.5 + 0.5) * 0.15
    hm.H += saw * (hm.H > 0.5)
    wob = fbm(n, n, seed + 2, base=2, octaves=2, sy=1, sx=2) * 5
    bands = 0.5 + 0.5 * np.sin(TAU * (yy + wob) / 21.0) * np.sin(TAU * (yy + wob) / 9.0)
    var = 0.55 * bands + 0.45 * fbm(n, n, seed + 3, base=4, octaves=3)
    rgb = colorize(col, hm.shade(1.0), var, grime_map(n, n, seed + 4, 0.12)) * tone[..., None]
    if kind == 'chalk':                         # flint nodules in a band through each course
        for _ in range(9):
            cy = rng.integers(0, 4) * 32 + 14 + rng.integers(0, 6)
            cx = rng.integers(0, n)
            rx, ry = rng.uniform(2, 4.5), rng.uniform(1.3, 2.2)
            blob = (wrapd(xx, cx, n) / rx) ** 2 + (wrapd(yy, cy, n) / ry) ** 2 < 1
            rgb[blob] = rgb[blob] * 0.45 + np.array((40, 42, 48)) * 0.55 * 0.84
    elif kind == 'buff':                        # fossil shells: little ribbed fans and spirals
        for _ in range(10):
            cy, cx = rng.integers(0, n), rng.integers(0, n)
            dx, dy = wrapd(xx, cx, n), wrapd(yy, cy, n)
            r = np.hypot(dx, dy)
            a = np.arctan2(dy, dx)
            if rng.random() < 0.5:
                sh = (r < 5) & (dy < 0.5) & (np.sin(a * 7) > 0)
            else:
                sh = (np.abs(r - (1.2 + 0.9 * ((a + np.pi) / TAU) * 4)) < 0.6) & (r < 5)
            rgb[sh] *= 0.72
    elif kind == 'iron':                        # banded ironstone: thin rust-ochre beds in pale grey
        b = np.sin(TAU * (yy + wob) / 16.0) + 0.6 * np.sin(TAU * (yy + wob) / 7.0 + 1.3)
        w8 = np.clip(b - 0.45, 0, 1) * 1.8
        w8 = np.clip(w8, 0, 1)
        rgb = rgb * (1 - 0.75 * w8[..., None]) + np.array(RUST) * 0.84 * 0.75 * w8[..., None] * tone[..., None]
    elif kind == 'grey':                        # bedding: darker shale partings
        part = np.abs(np.sin(TAU * (yy + wob) / 32.0 + 1.0)) < 0.06
        rgb[part] *= 0.7
    return rgb


def pit_wall(seed):
    """Quarry face above the seam: rough hewn pale limestone in wavy beds, a few half drill-holes."""
    n = 128
    yy, xx = np.mgrid[0:n, 0:n]
    rng = np.random.default_rng(seed)
    wob = fbm(n, n, seed + 2, base=2, octaves=2, sy=1, sx=2) * 8
    bands = 0.5 + 0.5 * np.sin(TAU * (yy + wob) / 32.0) * np.cos(TAU * (yy + wob) / 13.0)
    col = np.array(CHALK) * (0.8 + 0.22 * bands)[..., None] + np.array((-12, -8, 4)) * (1 - bands)[..., None]
    rgb, hm = hewn(n, n, seed, (1, 1, 1), lam=10.0, chip=4, k=1.3)
    rgb = rgb / (np.array((1, 1, 1)) * 0.84) * col * 0.84 / 1.0
    drill = np.zeros((n, n), bool)
    for _ in range(4):
        cx = rng.integers(0, n)
        y0 = rng.integers(0, n)
        L = rng.integers(26, 40)
        d = wrapd(xx, cx, n)
        m = (np.abs(d) < 1.8) & (((yy - y0) % n) < L)
        drill |= m
        rgb[m & (d < 0)] *= 0.55
        rgb[m & (d >= 0)] *= 0.8
    rust = np.clip(fbm(n, n, seed + 7, base=6, octaves=2, sy=0, sx=1) - 0.62, 0, 1) * 2
    rgb = rgb * (1 - 0.3 * rust[..., None]) + np.array(OCHRE) * 0.3 * rust[..., None] * 0.8
    return rgb


def team_lime(seed, team):
    """Base walls above the seam: grey limestone with team veins and crystal clusters."""
    n = 128
    tint = {'b': (96, 106, 134), 'r': (132, 102, 94)}[team]      # lapis-grey / cinnabar-stained stone
    rgb = limestone(seed, tint, 'grey')
    yy, xx = np.mgrid[0:n, 0:n]
    T = TEAM[team]
    v = fbm(n, n, seed + 11, base=3, octaves=4)
    frag = fbm(n, n, seed + 13, base=2, octaves=2) > 0.42
    vein = (np.abs(v - 0.5) < 0.014) & frag
    halo = (np.abs(v - 0.5) < 0.03) & frag & ~vein
    rgb[halo] = rgb[halo] * 0.6 + np.array(T['c1']) * 0.4 * 0.84
    rgb[vein] = np.array(T['c1']) * 0.9
    mm = vein | halo
    rng = np.random.default_rng(seed + 1)
    ys, xs = np.nonzero(vein)
    for _ in range(3):
        k = rng.integers(0, len(ys))
        cy, cx = ys[k], xs[k]
        for dx, dy, r in ((0, 0, 6), (7, -4, 4), (-6, 4, 4.2), (3, 7, 3)):
            hx = hexmask(wrapd(xx, cx + dx, n), wrapd(yy, cy + dy, n), r)
            rgb[hx] = T['c2']
            rgb[hx & (wrapd(yy, cy + dy, n) > 0)] = T['c1']
            rgb[hx & (np.abs(wrapd(xx, cx + dx, n)) < 1)] = np.array(T['c2']) * 1.15
            mm |= hx
    MASK['m'] = mm
    return rgb


def seam(seed):
    """The slab between floors: a black coal seam, glints, rust-stained parting below (32 tall)."""
    h, w = 32, 64
    yy, xx = np.mgrid[0:h, 0:w]
    top = 3 + 2 * fbm(h, w, seed, base=4, octaves=2)[0]
    bot = 26 + 3 * fbm(h, w, seed + 1, base=4, octaves=2)[0]
    rgb = np.zeros((h, w, 3)) + np.array(SLATE_D) * 0.84
    coal = (yy >= top[None, :]) & (yy < bot[None, :])
    hm = HM(h, w)
    hm.H = np.floor(fbm(h, w, seed + 2, base=4, octaves=3) * 6) / 3
    c = colorize(COAL, hm.shade(1.4), fbm(h, w, seed + 3, base=8), None)
    rgb[coal] = c[coal]
    rng = np.random.default_rng(seed)
    gl = coal & (rng.random((h, w)) < 0.012)
    rgb[gl] = (70, 68, 74)
    rust = (yy >= bot[None, :]) & (yy < bot[None, :] + 3)
    rgb[rust] = np.array(RUST) * 0.9
    rgb[(yy == np.floor(top)[None, :].astype(int))] = np.array(OCHRE) * 0.6
    return rgb


# ------------------------------------------------------------------ bands
def ballast(seed, col=GRAVEL):
    """Kickplate: dark rubble footing (32 x 64), cellular stones."""
    h, w = 32, 64
    yy, xx = np.mgrid[0:h, 0:w]
    rng = np.random.default_rng(seed)
    pts = np.stack([rng.uniform(0, w, 22), rng.uniform(0, h, 22)], 1)
    d1 = np.full((h, w), 1e9)
    d2 = np.full((h, w), 1e9)
    idn = np.zeros((h, w), int)
    for k, (px, py) in enumerate(pts):
        d = np.hypot(wrapd(xx, px, w), wrapd(yy, py, h))
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        idn = np.where(closer, k, idn)
        d1 = np.minimum(d1, d)
    edge = d2 - d1
    tone = 0.8 + 0.4 * rng.random(len(pts))[idn]
    rgb = np.array(col, float) * tone[..., None] * (0.55 + 0.45 * np.clip(edge / 3, 0, 1))[..., None] * 0.84
    rgb[0:2] = np.array(TIMBER_D) * 0.9               # a timber sill on top of the footing
    rgb[2] = np.array(TIMBER_D) * 0.5
    return rgb


def lime_base(seed, col):
    h, w = 32, 64
    hm = HM(h, w)
    hm.plate(1, 3, 64, 32, 1.0, 2)
    rgb = colorize(np.array(col) * 0.72, hm.shade(1.1), fbm(h, w, seed, base=4), grime_map(h, w, seed + 1, 0.2, False))
    rgb[0:2] = np.array(TIMBER_D) * 0.9
    rgb[2] = np.array(TIMBER_D) * 0.5
    return rgb


def timber_trim(seed):
    """Cornice: a timber header beam with an iron strap every 64 (16 x 64)."""
    h, w = 16, 64
    yy, xx = np.mgrid[0:h, 0:w]
    grain = fbm(h, w, seed, base=2, octaves=4, sy=4, sx=1)
    rgb = np.array(TIMBER, float) * (0.75 + 0.4 * grain)[..., None] * 0.84
    rgb[0:2] *= 1.15
    rgb[14:16] *= 0.45
    strap = (xx >= 28) & (xx < 36)
    rgb[strap] = np.array(IRON) * 0.84
    rgb[strap & ((yy == 4) | (yy == 11)) & ((xx == 30) | (xx == 33))] = np.array(IRON_L)
    return rgb


def cable(seed, team):
    """Light strip: a dark timber batten carrying a cable and caged bulbs every 32 (16 x 64)."""
    h, w = 16, 64
    yy, xx = np.mgrid[0:h, 0:w]
    grain = fbm(h, w, seed, base=2, octaves=4, sy=4, sx=1)
    rgb = np.array(TIMBER_D, float) * (0.7 + 0.35 * grain)[..., None] * 0.84
    rgb[0] *= 1.3
    rgb[15] *= 0.4
    sag = 4 + 1.2 * np.cos(TAU * xx / 32)
    rgb[np.abs(yy - sag) < 0.7] = (14, 14, 16)
    idx = R.quantize(rgb)
    core, edge = TEAM[team]['bulb']
    for cx in (15.5, 47.5):
        d = np.hypot(xx - cx, (yy - 9.0) * 1.15)
        idx[d < 4.2] = edge
        idx[d < 2.6] = core
        idx[(d < 5.2) & (d >= 4.2)] = q1((28, 28, 30))
        cage = (d < 5.0) & ((np.abs(xx - cx) < 0.6) | (np.abs(yy - 9.0) < 0.5))
        idx[cage] = q1((34, 34, 36))
        idx[(np.abs(xx - cx) < 1.5) & (yy >= 4) & (yy < 6)] = q1((22, 22, 24))   # socket on the cable
    return idx


# ------------------------------------------------------------------ floors
def cells2(n, seed, k):
    """Tileable cellular partition: (cell id, distance to the nearest joint)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n]
    g = int(np.sqrt(k))
    pts = [((a + 0.2 + 0.6 * rng.random()) * n / g, (b + 0.2 + 0.6 * rng.random()) * n / g) for a in range(g) for b in range(g)]
    d1 = np.full((n, n), 1e9)
    d2 = np.full((n, n), 1e9)
    idn = np.zeros((n, n), int)
    for k_, (px, py) in enumerate(pts):
        d = np.hypot(wrapd(xx, px, n) * 1.0, wrapd(yy, py, n) * 1.15)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        idn = np.where(closer, k_, idn)
        d1 = np.minimum(d1, d)
    return idn, (d2 - d1) / 2, len(pts)


def flags(seed, col, n=64, team=None, worn=0.12):
    """Irregular flagstones (cellular slabs) with dark joints."""
    idn, edge, npts = cells2(n, seed, 9)
    rng = np.random.default_rng(seed + 1)
    hm = HM(n, n)
    hm.H = np.clip(edge / 2.0, 0, 1) * 0.9 + 0.15 * fbm(n, n, seed + 2, base=8, octaves=2)
    tone = 0.88 + 0.22 * rng.random(npts)[idn]
    rgb = colorize(col, hm.shade(1.0), fbm(n, n, seed, base=4), grime_map(n, n, seed + 5, worn, False)) * tone[..., None]
    rgb[edge < 0.8] = np.array(col) * 0.32
    mm = np.zeros((n, n), bool)
    if team:
        yy, xx = np.mgrid[0:n, 0:n]
        T = TEAM[team]
        for cx, cy in ((10, 28), (44, 0), (52, 28)):
            hx = hexmask(wrapd(xx, cx, n), wrapd(yy, cy, n), 3.2)
            rgb[hx] = T['c2']
            rgb[hx & (wrapd(yy, cy, n) > 0)] = T['c1']
            mm |= hx
    MASK['m'] = mm
    return rgb


def pavers(seed, col):
    """Limestone pavers 32 x 32, worn edges, faint bands."""
    n = 64
    hm = HM(n, n)
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n]
    tone = np.ones((n, n))
    for r, y in enumerate((0, 32)):
        off = 16 if r else 0
        for x in (0, 32):
            hm.plate(x + off + 1, y + 1, x + off + 32, y + 32, 1.0, 1)
            X = (xx - x - off) % n
            tone[(yy >= y) & (yy < y + 32) & (X < 32)] = 1 + 0.07 * (rng.random() * 2 - 1)
    rgb = colorize(col, hm.shade(1.0), fbm(n, n, seed, base=4), grime_map(n, n, seed + 5, 0.14, False)) * tone[..., None]
    rgb[hm.H < 0.1] = np.array(col) * 0.4
    return rgb * 0.92


def gravel(seed, col=GRAVEL, n=64):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n]
    pts = np.stack([rng.uniform(0, n, 90), rng.uniform(0, n, 90)], 1)
    d1 = np.full((n, n), 1e9)
    d2 = np.full((n, n), 1e9)
    idn = np.zeros((n, n), int)
    for k, (px, py) in enumerate(pts):
        d = np.hypot(wrapd(xx, px, n), wrapd(yy, py, n))
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        idn = np.where(closer, k, idn)
        d1 = np.minimum(d1, d)
    tone = 0.75 + 0.45 * rng.random(len(pts))[idn]
    rgb = np.array(col, float) * tone[..., None] * (0.6 + 0.4 * np.clip((d2 - d1) / 2.5, 0, 1))[..., None] * 0.84
    return rgb


def pit_floor(seed):
    """Pit floor: gravel with broken slate slabs."""
    n = 64
    rgb = gravel(seed, (76, 74, 72))
    fl = flags(seed + 1, SLATE, n, worn=0.2)
    MASK.pop('m', None)
    m = fbm(n, n, seed + 2, base=2, octaves=3) > 0.52
    rgb[m] = fl[m]
    return rgb


def rails(seed):
    """Inlay down the middle of each undercroft: sleepers across, two rails along x (64 x 64)."""
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    rgb = gravel(seed, (64, 62, 60))
    sl = ((xx % 16) >= 2) & ((xx % 16) < 11) & (yy >= 12) & (yy < 52)
    grain = fbm(n, n, seed + 1, base=4, octaves=3, sy=1, sx=4)
    rgb[sl] = (np.array(TIMBER_D, float) * (0.8 + 0.4 * grain)[..., None] * 0.84)[sl]
    for ry in (20, 43):
        rgb[(yy >= ry) & (yy < ry + 2)] = np.array(IRON_L) * 1.15
        rgb[(yy == ry + 2)] = np.array(IRON) * 0.7
        rgb[(yy == ry - 1)] = np.array(IRON) * 0.6
        rgb[(yy >= ry - 2) & (yy < ry + 4) & ((xx % 16) == 6) & sl.any(0)[None, :].repeat(n, 0)] = np.array(IRON) * 0.5
    return rgb


# ------------------------------------------------------------------ ceilings
def lagging(seed, team=None):
    """Mine roof: timber lagging planks with a heavy cross beam every 64."""
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    hm = HM(n, n)
    for x in range(0, n, 8):
        hm.plate(x + 1, 0, x + 8, n, 0.6, 1)
    hm.plate(0, 0, n, 16, 2.4, 2)
    grain = fbm(n, n, seed, base=4, octaves=4, sy=8, sx=1)
    rgb = colorize(TIMBER_D, hm.shade(1.0), grain, grime_map(n, n, seed + 2, 0.15, False))
    beam = yy < 16
    rgb[beam] = colorize(TIMBER, hm.shade(1.0), fbm(n, n, seed + 3, base=4, octaves=4, sy=1, sx=8))[beam]
    rgb[(yy >= 16) & (yy < 18)] *= 0.4
    mm = np.zeros((n, n), bool)
    if team:                                   # team-painted iron girder instead of the timber beam
        T = TEAM[team]
        g = (yy >= 2) & (yy < 14)
        rgb[g] = np.array(T['c1']) * 0.55
        rgb[(yy >= 2) & (yy < 4)] = np.array(T['c1']) * 0.8
        rgb[(yy >= 12) & (yy < 14)] = np.array(T['c1']) * 0.35
        rgb[g & ((xx % 16) == 8) & ((yy == 5) | (yy == 10))] = IRON_L
        mm |= g
    MASK['m'] = mm
    return rgb


def soffit(seed):
    """Underside of the bridge slab: iron girders every 32, timber planks between."""
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    grain = fbm(n, n, seed, base=4, octaves=4, sy=8, sx=1)
    rgb = np.array(TIMBER_D, float) * (0.7 + 0.35 * grain)[..., None] * 0.84
    rgb[(xx % 8) == 0] *= 0.6
    gird = (yy % 32) < 8
    rgb[gird] = np.array(IRON) * 0.84
    rgb[((yy % 32) == 0) | ((yy % 32) == 7)] = np.array(IRON) * 0.5
    rgb[gird & ((xx % 16) == 4) & (((yy % 32) == 2) | ((yy % 32) == 5))] = IRON_L
    return rgb


def lime_ceil(seed):
    """Hewn limestone roof with a timber prop beam every 64."""
    n = 64
    rgb, hm = hewn(n, n, seed, np.array(GREYL) * 0.8, lam=9, chip=3, k=1.0)
    yy, xx = np.mgrid[0:n, 0:n]
    beam = yy < 12
    rgb[beam] = colorize(TIMBER, np.ones((n, n)), fbm(n, n, seed + 3, base=4, octaves=4, sy=1, sx=8))[beam]
    rgb[(yy >= 12) & (yy < 14)] *= 0.4
    return rgb


# ------------------------------------------------------------------ fixtures, details
def tread(seed):
    n = 32
    hm = HM(n, n)
    hm.plate(0, 1, n, n, 0.5, 4)
    return colorize((96, 98, 104), hm.shade(1.0), fbm(n, n, seed, base=4), grime_map(n, n, seed, 0.15, False))


def riser(seed):
    h, w = 16, 32
    yy, xx = np.mgrid[0:h, 0:w]
    grain = fbm(h, w, seed, base=2, octaves=4, sy=4, sx=1)
    rgb = np.array(TIMBER, float) * (0.7 + 0.4 * grain)[..., None] * 0.84
    rgb[0:2] = np.array(IRON_L) * 0.9                     # iron nosing
    rgb[2] = np.array(IRON) * 0.4
    return rgb


def pillar(seed):
    """Rock left standing (room-and-pillar): slate, iron strap bands (128 x 64)."""
    h, w = 128, 64
    rgb, hm = hewn(h, w, seed, SLATE, lam=6.0, chip=5)
    yy, xx = np.mgrid[0:h, 0:w]
    for b in (20, 84):
        rgb[(yy >= b) & (yy < b + 6)] = np.array(IRON) * 0.84
        rgb[(yy == b)] = np.array(IRON_L) * 0.9
        rgb[(yy == b + 6)] = np.array(IRON) * 0.4
        rgb[(yy >= b + 1) & (yy < b + 5) & ((xx % 16) == 8)] = IRON_L
    return rgb


def crib(seed):
    """Pillar cap: timber cribbing, stacked squared logs (64 x 64)."""
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    grain = fbm(n, n, seed, base=2, octaves=4, sy=4, sx=1)
    rgb = np.array(TIMBER, float) * (0.7 + 0.4 * grain)[..., None] * 0.84
    rgb[(yy % 16) == 0] *= 0.35
    rgb[(yy % 16) == 1] *= 1.2
    ends = ((xx % 32) < 14) & (((yy // 16) % 2) == 0)
    rgb[ends & ((yy % 16) > 1)] = (np.array(TIMBER, float) * 1.15 * (0.85 + 0.2 * np.sin(np.hypot((xx % 32) - 7, (yy % 16) - 8) * 1.6))[..., None])[ends & ((yy % 16) > 1)]
    return rgb


def planks(seed):
    """Perch: scaffold boards with iron edge brackets (64)."""
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    grain = fbm(n, n, seed, base=4, octaves=4, sy=1, sx=8)
    rgb = np.array(TIMBER, float) * (0.75 + 0.4 * grain)[..., None] * 0.84
    rgb[(yy % 16) == 0] *= 0.45
    rgb[((xx % 32) < 3)] = np.array(IRON) * 0.84
    rgb[((yy % 16) == 8) & ((xx % 32) == 1)] = IRON_L
    return rgb


def beam_side(seed, top=False):
    """Timber beam across the pit, iron straps every 64 (64 x 32)."""
    h, w = 32, 64
    yy, xx = np.mgrid[0:h, 0:w]
    grain = fbm(h, w, seed, base=2, octaves=4, sy=4, sx=1)
    rgb = np.array(TIMBER, float) * (0.72 + 0.4 * grain)[..., None] * 0.84
    if not top:
        rgb[0:2] *= 1.2
        rgb[30:32] *= 0.5
    strap = (xx >= 26) & (xx < 38)
    rgb[strap] = np.array(IRON) * 0.84
    rgb[strap & ((xx == 26) | (xx == 37))] = np.array(IRON) * 0.5
    rgb[strap & ((yy % 16) == 8) & ((xx == 29) | (xx == 34))] = IRON_L
    return rgb


def lampbox(seed):
    h, w = 16, 32
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = np.zeros((h, w, 3)) + np.array(IRON) * 0.84
    rgb[(xx % 8) == 0] = np.array(IRON) * 0.4
    rgb[0:2] = np.array(IRON_L) * 0.84
    return rgb


def light(seed):
    """Ceiling lamp underside: a caged warm bulb."""
    yy, xx = np.mgrid[0:32, 0:32]
    dx, dy = xx - 15.5, yy - 15.5
    r = np.hypot(dx, dy)
    idx = np.full((32, 32), q1((40, 40, 44)), np.uint8)
    idx[r < 13] = 236
    idx[r < 9] = 238
    idx[r < 5] = 253
    idx[r < 2.5] = 254
    cage = (r < 14) & ((np.abs(dx) < 0.8) | (np.abs(dy) < 0.8) | (np.abs(r - 9.5) < 0.7))
    idx[cage] = q1((30, 30, 32))
    idx[(r >= 13) & (r < 15)] = q1((60, 60, 64))
    return idx


def wlamp(seed, team):
    """Wall bulkhead lamp: iron frame, caged glass (32 x 32)."""
    core, edge = TEAM[team]['lamp']
    yy, xx = np.mgrid[0:32, 0:32]
    hm = HM(32, 32)
    hm.plate(0, 0, 32, 32, 1.5, 3)
    idx = R.quantize(colorize(IRON, hm.shade(), fbm(32, 32, seed)))
    dx, dy = (xx - 15.5) / 11.0, (yy - 15.5) / 8.5
    g = dx * dx + dy * dy < 1
    idx[g] = edge
    idx[g & (dx * dx + dy * dy < 0.45)] = core
    bars = g & ((np.abs(xx - 15.5) < 0.6) | (np.abs(xx - 8.5) < 0.6) | (np.abs(xx - 22.5) < 0.6) | (np.abs(yy - 15.5) < 0.6))
    idx[bars] = q1((26, 26, 28))
    for cx, cy in ((3, 3), (28, 3), (3, 28), (28, 28)):
        idx[cy - 1:cy + 1, cx - 1:cx + 1] = q1(IRON_L)
    return idx


def stand(seed, team):
    """Flag / Quad plate (128): an agate geode slice - wavy concentric bands in team colours round a
    crystal-lined hollow, set in a rough rock rim."""
    n = 128
    T = TEAM[team]
    yy, xx = np.mgrid[0:n, 0:n]
    dx, dy = xx - 63.5, yy - 63.5
    r = np.hypot(dx, dy)
    a = np.arctan2(dy, dx)
    wob = 3.5 * np.sin(a * 5 + 0.7) + 2.0 * np.sin(a * 11 + 2.1) + 1.2 * np.sin(a * 17)
    rr = r + wob
    rgb = gravel(seed, (70, 70, 74), n)
    rim = (rr >= 54) & (rr < 60)
    rgb[rim] = np.array(SLATE_D) * 0.9
    body = rr < 54
    ph = (rr / 5.0) % 3
    c_dark = np.array(T['c1']) * 0.55
    c_mid = np.array(T['c1'])
    c_pale = np.array(T['c2']) if team != 'n' else np.array((214, 208, 190))
    band = np.where(ph < 1, 0, np.where(ph < 2, 1, 2))
    cols = np.stack([c_dark, c_mid, c_pale])
    rgb[body] = cols[band[body]]
    thin = body & (np.abs((rr % 5.0) - 2.5) < 0.35)
    rgb[thin] = c_pale * 0.9
    hol = rr < 15
    rng = np.random.default_rng(seed)
    sp = rng.random((n, n))
    rgb[hol] = np.where((sp[hol] > 0.55)[:, None], c_pale * 1.1, c_mid * 0.7)
    rgb[(rr < 8)] = c_dark * 0.6
    MASK['m'] = body | hol
    return rgb


# ------------------------------------------------------------------ b4: direction signs
GLYPH = {
    'B': ['11110', '10001', '10001', '11110', '10001', '10001', '11110'],
    'L': ['10000', '10000', '10000', '10000', '10000', '10000', '11111'],
    'U': ['10001', '10001', '10001', '10001', '10001', '10001', '01110'],
    'E': ['11111', '10000', '10000', '11110', '10000', '10000', '11111'],
    'R': ['11110', '10001', '10001', '11110', '10100', '10010', '10001'],
    'D': ['11110', '10001', '10001', '10001', '10001', '10001', '11110'],
    '<': ['0001', '0011', '0111', '1111', '0111', '0011', '0001'],
    '>': ['1000', '1100', '1110', '1111', '1110', '1100', '1000'],
    ' ': ['00', '00', '00', '00', '00', '00', '00'],
}
PAINT = {'b': (244, 208), 'r': (250, 64)}       # (fullbright luminous paint, dark outline) palette indices


def text_mask(txt, sc):
    rows = [''.join(GLYPH[c][r] + '0' for c in txt)[:-1] for r in range(7)]
    m = np.array([[ch == '1' for ch in row] for row in rows], bool)
    return np.kron(m, np.ones((sc, sc), bool))


def board(w, h, seed):
    """Weathered timber sign board, iron bolts in the corners (palette indices)."""
    yy, xx = np.mgrid[0:h, 0:w]
    grain = fbm(h, w, seed, base=2, octaves=4, sy=max(1, h // 16), sx=1)
    rgb = np.array(TIMBER_D, float) * (0.62 + 0.3 * grain)[..., None] * 0.84
    rgb[(yy % 16) == 0] *= 0.5
    rgb[(xx < 2) | (xx >= w - 2) | (yy < 2) | (yy >= h - 2)] = np.array(IRON) * 0.5
    idx = R.quantize(rgb)
    for cx, cy in ((4, 4), (w - 5, 4), (4, h - 5), (w - 5, h - 5)):
        idx[cy - 1:cy + 1, cx - 1:cx + 1] = q1(IRON_L)
    return idx


def stamp(idx, m, x0, y0, team):
    core, dark = PAINT[team]
    h, w = m.shape
    pad = np.zeros((h + 2, w + 2), bool)
    pad[1:-1, 1:-1] = m
    out = pad | np.roll(pad, 1, 0) | np.roll(pad, -1, 0) | np.roll(pad, 1, 1) | np.roll(pad, -1, 1)
    sub = idx[y0 - 1:y0 + h + 1, x0 - 1:x0 + w + 1]
    sub[out & ~pad] = dark
    sub[pad] = core


def sign_two(seed, left, right):
    """192 x 32 two-ended sign: '< LEFT' on the left half, 'RIGHT >' on the right, iron strap between."""
    idx = board(192, 32, seed)
    name = {'b': 'BLUE', 'r': 'RED'}
    for half, team in ((0, left), (1, right)):
        txt = ('< ' + name[team]) if half == 0 else (name[team] + ' >')
        m = text_mask(txt, 2)
        x0 = half * 96 + (96 - m.shape[1]) // 2
        stamp(idx, m, x0, (32 - m.shape[0]) // 2, team)
    idx[:, 95:97] = q1(IRON)
    return idx


def sign_tag(seed, team, w=128, h=32, sc=3):
    """'BLUE' / 'RED' board: that way lies that base (tags face along the route; big ones in the pit)."""
    idx = board(w, h, seed)
    m = text_mask({'b': 'BLUE', 'r': 'RED'}[team], sc)
    stamp(idx, m, (w - m.shape[1]) // 2, (h - m.shape[0]) // 2, team)
    core = PAINT[team][0]
    if h >= 64:                                   # big pit boards: a luminous stripe top and bottom
        idx[5:8, 6:w - 6] = core
        idx[h - 8:h - 5, 6:w - 6] = core
    return idx


def iron_edge(seed):
    n = 16
    return colorize(IRON, np.ones((n, n)), fbm(n, n, seed, base=4))


def sky(seed):
    """Quarry night: dark slate-violet, haze low on the horizon band, sparse stars; thin drifting
    cloud in front (left half = front layer, index 0 transparent)."""
    n = 128
    back = fbm(n, n, seed, base=3, octaves=5)
    c0, c1 = np.array([8, 9, 16]), np.array([34, 32, 50])
    bi = R.quantize(c0 + (c1 - c0) * np.clip(back * 0.9 - 0.1, 0, 1)[..., None])
    rng = np.random.default_rng(seed)
    for _ in range(110):
        x, y = int(rng.integers(0, n)), int(rng.integers(0, n))
        bi[y, x] = [254, 253, 246, 245][int(rng.integers(0, 4))] if rng.random() < 0.5 else q1((110, 110, 126))
    front = fbm(n, n, seed + 50, base=4, octaves=4, sy=1, sx=2)
    fa = np.clip((front - 0.56) * 3.0, 0, 1)
    fi = R.quantize(np.array([22, 22, 32]) * (0.8 + 0.3 * fa[..., None]))
    fi = np.where(fi == 0, 1, fi)
    fi = np.where(fa > 0.58, fi, 0)
    return np.concatenate([fi, bi], 1)


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    names = []

    def put(name, img, pal=None):
        if img.ndim == 2:
            MASK.pop('m', None)
            idx = img
        else:
            idx = q(img, pal, len(names))
        R.save(outdir, name, idx)
        names.append(name)

    LIME = STONE
    put('sd_slate', slate_wall(101), SLATE_SET)               # lower halls; pit + bases below the seam
    put('sd_slateu', slate_wall(102, bolts=True), SLATE_SET)  # undercrofts: rockbolted
    put('sd_chalk', limestone(103, CHALK, 'chalk'), LIME)     # north decks
    put('sd_irons', limestone(104, IRONSTONE, 'iron'), LIME)  # south decks: banded ironstone
    put('sd_greyl', limestone(105, GREYL, 'grey'), LIME)      # well rooms
    put('sd_pit', pit_wall(106), LIME)                        # pit, above the seam
    put('sd_seam', seam(107), SLATE_SET)
    put('sd_blue_lo', slate_wall(108, team='b'), SLATE_SET)
    put('sd_red_lo', slate_wall(109, team='r'), SLATE_SET)
    put('sd_blue_hi', team_lime(110, 'b'), LIME + list(range(32, 48)))
    put('sd_red_hi', team_lime(111, 'r'), LIME)
    put('sd_ballast', ballast(112), SLATE_SET)
    put('sd_lmbase', lime_base(113, GREYL), LIME)
    put('sd_trim', timber_trim(114), LIME)
    put('sd_cable', cable(115, 'n'))
    put('sd_cable_b', cable(116, 'b'))
    put('sd_cable_r', cable(117, 'r'))
    put('sd_slflr', flags(118, SLATE), SLATE_SET)
    put('sd_ugflr', gravel(119), SLATE_SET)
    put('sd_rails', rails(120), LIME)
    put('sd_pitflr', pit_floor(121), SLATE_SET)
    put('sd_chflr', pavers(122, CHALK), LIME)
    put('sd_irflr', pavers(123, (140, 112, 86)), LIME)
    put('sd_grflr', pavers(124, GREYL), LIME)
    put('sd_blue_flr', flags(125, SLATE, team='b'), SLATE_SET)
    put('sd_red_flr', flags(126, SLATE, team='r'), SLATE_SET)
    put('sd_lagging', lagging(127), LIME)
    put('sd_blue_ceil', lagging(128, 'b'), LIME)
    put('sd_red_ceil', lagging(129, 'r'), LIME)
    put('sd_soffit', soffit(130), LIME)
    put('sd_lmceil', lime_ceil(131), LIME)
    put('sd_tread', tread(132), SLATE_SET)
    put('sd_riser', riser(133), LIME)
    put('sd_pillar', pillar(134), SLATE_SET)
    put('sd_pbase', ballast(135), SLATE_SET)
    put('sd_crib', crib(136), LIME)
    put('sd_planks', planks(137), LIME)
    put('sd_beam', beam_side(138), LIME)
    put('sd_beamt', beam_side(139, True), LIME)
    put('sd_lampbox', lampbox(140), SLATE_SET)
    put('sd_light', light(141))
    put('sd_wlamp', wlamp(142, 'n'))
    put('sd_wlamp_b', wlamp(143, 'b'))
    put('sd_wlamp_r', wlamp(144, 'r'))
    put('sd_stand_b', stand(145, 'b'))
    put('sd_stand_r', stand(146, 'r'))
    put('sd_stand_q', stand(147, 'n'))
    put('sd_iron', iron_edge(148))
    put('sky_dig', sky(149))
    put('sd_sign_rb', sign_two(150, 'r', 'b'))      # '< RED | BLUE >'
    put('sd_sign_br', sign_two(151, 'b', 'r'))      # '< BLUE | RED >'
    put('sd_tag_b', sign_tag(152, 'b'))
    put('sd_tag_r', sign_tag(153, 'r'))
    put('sd_board_b', sign_tag(154, 'b', 128, 64, 4))
    put('sd_board_r', sign_tag(155, 'r', 128, 64, 4))
    open('wad_args.txt', 'w').write('\n'.join(f'{nm}={outdir}/{nm}.png' for nm in names) + '\n')
    print(len(names), 'textures')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'dtex')
