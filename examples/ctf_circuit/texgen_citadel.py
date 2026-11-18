"""Original procedural 'desert citadel' textures for ctf_circuit (all generated from code, quantized
to the Quake palette as distributed with LibreQuake, BSD-3).

Two rival sandstone forts at dusk. Team colour lives in the glazed tilework (zellige):
lapis + sky-blue for blue, cinnabar + terracotta for red, gold + black in the neutral middle.
Zones: bf/rf forecourt + rear, bk/rk flag hall, bh/rh north arc (gatehouse, aqueduct),
bl/rl south arc (cellar, undercroft), bs/rs spine, md mid chamber, nc north court, sc south court.
Usage: python3 texgen_citadel.py outdir
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
import texgen_runic as R  # noqa: E402
from texgen import HM, fbm, colorize, grime_map  # noqa: E402
from fsq import fs_quantize, STONE, q1  # noqa: E402

R.T.ALBEDO = 0.84

A = R.T.ALBEDO
TAU = 2 * np.pi
SAND = (170, 136, 92)          # warm sandstone
SAND_D = (128, 98, 66)
PLASTER = (178, 160, 128)
LIME = (132, 124, 108)         # cool vault stone
CEDAR = (92, 60, 38)
BRASS = (150, 112, 48)
BRASS_D = (88, 62, 28)
GOLD = (196, 160, 70)
CREAM = (184, 172, 146)
INK = (34, 28, 26)
TEAM = {'b': dict(c1=(48, 62, 150), c2=(104, 124, 176), glow=(244, 245), ban=(44, 54, 132)),      # lapis, sky blue
        'r': dict(c1=(160, 44, 30), c2=(170, 96, 56), glow=(234, 232), ban=(136, 34, 26)),        # cinnabar, terracotta
        'n': dict(c1=(184, 148, 60), c2=(40, 36, 34), glow=(252, 241), ban=(150, 112, 40))}       # gold, black


def star_mask(dx, dy, r):
    """8-point star: union of a square and a diamond of the same 'radius'."""
    return (np.maximum(np.abs(dx), np.abs(dy)) < r) | ((np.abs(dx) + np.abs(dy)) < r * 1.41)


def wrapd(v, c, n):
    return ((v - c + n / 2) % n) - n / 2


def sandstone(h, w, seed, col=SAND, course=32, block=64, stagger=None, k=1.0):
    hm = HM(h, w)
    rng = np.random.default_rng(seed)
    tm = np.ones((h, w))
    stagger = block // 2 if stagger is None else stagger
    for r in range(h // course):
        off = stagger if r % 2 else 0
        for x in range(-block, w + block, block):
            hm.plate(x + off + 1, r * course + 1, x + off + block, r * course + course, 1.0, 2)
            X = (hm.X - (x + off)) % w
            tm[(X < block) & (hm.Y >= r * course) & (hm.Y < r * course + course)] = 1 + 0.08 * (rng.random() * 2 - 1)
    streak = fbm(h, w, seed + 9, base=4, octaves=3, sy=4, sx=1)
    rgb = colorize(col, hm.shade(k), streak, grime_map(h, w, seed + 3, 0.14))
    return rgb * tm[..., None]


def zellige(n, seed, team, scale=1.0, period=64):
    """Star-and-cross glazed tiles: team-colour stars on a lattice, cream crosses between,
    a second-colour dot in each star, dark grout outlines."""
    T = TEAM[team]
    yy, xx = np.mgrid[0:n, 0:n]
    p = period
    r = 18 * p / 64
    s1 = star_mask(wrapd(xx, p / 2 - 0.5, p), wrapd(yy, p / 2 - 0.5, p), r)
    s2 = star_mask(wrapd(xx, -0.5, p), wrapd(yy, -0.5, p), r)
    rgb = np.zeros((n, n, 3)) + np.array(CREAM)
    rgb[s1] = T['c1']
    rgb[s2] = T['c2']
    d1 = np.hypot(wrapd(xx, p / 2 - 0.5, p), wrapd(yy, p / 2 - 0.5, p))
    d2 = np.hypot(wrapd(xx, -0.5, p), wrapd(yy, -0.5, p))
    rgb[d1 < r * 0.28] = T['c2'] if team != 'n' else CREAM
    rgb[d2 < r * 0.28] = T['c1'] if team != 'n' else GOLD
    edge = np.zeros((n, n), bool)
    for m in (s1, s2):
        edge |= m ^ np.roll(m, 1, 0) | m ^ np.roll(m, 1, 1)
    rgb[edge] = INK
    gl = 0.96 + 0.08 * fbm(n, n, seed, base=8, octaves=2)
    return rgb * gl[..., None] * A


MASK = {}      # functions that mix glazed tile into stone set MASK['m'] (True = glazed pixel)


def q(img, stone=False, seed=0):
    img = np.clip(img, 0, 255)
    m = MASK.pop('m', None)
    if not stone:
        return R.quantize(img)
    base = fs_quantize(img, STONE, 0.9, seed=seed)
    if m is not None:
        base = np.where(m, R.quantize(img), base).astype(np.uint8)
    return base


# ------------------------------------------------------------------ walls
def wall_sand(seed, col=SAND):                 # forecourt / north arc: big sandstone ashlar
    return sandstone(128, 128, seed, col) * A


def wall_plaster(seed, team):                  # flag hall / mid: carved plaster panels, interlaced stars
    n = 128
    yy, xx = np.mgrid[0:n, 0:n]
    hm = HM(n, n)
    hm.plate(0, 0, n, n, 1.0, 1)
    for cx, cy in ((32, 32), (96, 96), (96, 32), (32, 96)):
        m = star_mask(wrapd(xx, cx, n), wrapd(yy, cy, n), 26) & ~star_mask(wrapd(xx, cx, n), wrapd(yy, cy, n), 21)
        hm.H[m] += 1.2
        m2 = star_mask(wrapd(xx, cx, n), wrapd(yy, cy, n), 9)
        hm.H[m2] += 0.8
    hm.H[(xx % 64 == 0) | (yy % 64 == 0)] -= 0.6
    rgb = colorize(PLASTER, hm.shade(1.1), fbm(n, n, seed, base=4), grime_map(n, n, seed + 1, 0.12))
    T = TEAM[team]
    cc = T['c1'] if team != 'n' else GOLD
    mm = np.zeros((n, n), bool)
    for cx, cy in ((32, 32), (96, 96), (96, 32), (32, 96)):
        m2 = star_mask(wrapd(xx, cx, n), wrapd(yy, cy, n), 7)
        rgb[m2] = np.array(cc) * A
        mm |= m2
    MASK['m'] = mm
    return rgb


def wall_vault(seed, col=LIME):                # south arc: cool limestone blocks, damp streaks
    rgb = sandstone(128, 128, seed, col, course=32, block=48, k=0.9)
    damp = fbm(128, 128, seed + 4, base=6, octaves=3, sy=6, sx=1)
    rgb *= (1 - 0.18 * np.clip(damp - 0.45, 0, 1) * 2)[..., None]
    return rgb * A


def wall_tiles(seed, team):                    # spine: zellige panels in sandstone frames
    n = 128
    rgb = sandstone(n, n, seed, SAND_D, course=32, block=64) * A
    z = zellige(n, seed + 1, team, period=32)
    yy, xx = np.mgrid[0:n, 0:n]
    inner = ((xx % 64) >= 8) & ((xx % 64) < 56) & (yy >= 12) & (yy < 116)
    rgb[inner] = z[inner]
    edge = inner ^ np.roll(inner, 1, 0) | inner ^ np.roll(inner, 1, 1)
    rgb[edge] = np.array(BRASS) * A
    MASK['m'] = inner | edge
    return rgb


# ------------------------------------------------------------------ floors
def floor_flags(seed, col=SAND, team=None, n=64):
    """Sandstone flags; with a team, a small glazed tile where four flags meet."""
    hm = HM(n, n)
    hm.plate(1, 1, 32, 32, 0.8, 2); hm.plate(33, 1, 64, 32, 0.8, 2)
    hm.plate(1, 33, 32, 64, 0.8, 2); hm.plate(33, 33, 64, 64, 0.8, 2)
    rgb = colorize(col, hm.shade(1.0), fbm(n, n, seed, base=4), grime_map(n, n, seed + 5, 0.16, False))
    rgb[hm.H < 0.1] = np.array(col) * 0.4
    if team:
        yy, xx = np.mgrid[0:n, 0:n]
        d = np.abs(wrapd(xx, -0.5, 64)) + np.abs(wrapd(yy, -0.5, 64))
        rgb[d < 7] = np.array(TEAM[team]['c1']) * A
        rgb[(d >= 7) & (d < 8.5)] = np.array(INK)
        MASK['m'] = d < 8.5
    return rgb


def floor_bricks(seed, col=SAND):              # north arc: herringbone sandstone bricks
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    u = (xx + yy) % 64
    v = (xx - yy) % 64
    k = ((xx // 8 + yy // 8) % 2 == 0)
    joint = np.where(k, (u % 16 == 0) | (v % 32 == 0), (v % 16 == 0) | (u % 32 == 0))
    g = fbm(n, n, seed, base=8, octaves=3)
    rgb = np.array(col, float) * (0.82 + 0.25 * g)[..., None] * A
    rgb[joint] *= 0.55
    return rgb


def floor_stars(seed, team):                   # flag halls / mid: zellige floor
    return zellige(64, seed, team)


# ------------------------------------------------------------------ ceilings
def ceil_cedar(seed, team=None):
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    hm = HM(n, n)
    for y in range(0, n, 8):
        hm.plate(0, y + 1, n, y + 8, 0.6, 1)
    hm.plate(0, 0, n, 14, 2.4, 2)
    rgb = colorize(CEDAR, hm.shade(1.0), fbm(n, n, seed, base=4, octaves=4, sy=1, sx=8), grime_map(n, n, seed + 2, 0.12, False))
    rgb[(yy >= 14) & (yy < 16)] *= 0.45
    if team:                                    # painted beam soffit
        rgb[4:10] = np.array(TEAM[team]['c1']) * 0.8 * A
        rgb[6:8] = np.array(GOLD) * A
    return rgb


def ceil_vault(seed, col=LIME):
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    hm = HM(n, n)
    hm.plate(0, 0, n, n, 0.5, 1)
    hm.plate(0, 0, 10, n, 2.0, 3, mode='max')
    hm.plate(0, 0, n, 10, 2.0, 3, mode='max')
    return colorize(col, hm.shade(1.0), fbm(n, n, seed, base=4), grime_map(n, n, seed + 2, 0.2, False))


def ceil_coffer(seed, team):                   # flag hall / mid: painted cedar coffers with a star
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    hm = HM(n, n)
    hm.plate(0, 0, n, n, 2.0, 1)
    hm.plate(8, 8, 56, 56, -1.0, 2, mode='add')
    rgb = colorize(CEDAR, hm.shade(1.0), fbm(n, n, seed, base=4, octaves=4, sy=1, sx=8))
    T = TEAM[team]
    inner = (xx >= 10) & (xx < 54) & (yy >= 10) & (yy < 54)
    rgb[inner] = np.array(T['c1'] if team != 'n' else (40, 36, 60)) * 0.55 * A
    st = star_mask(xx - 31.5, yy - 31.5, 12)
    rgb[st] = np.array(GOLD) * A
    rgb[star_mask(xx - 31.5, yy - 31.5, 4)] = np.array(T['c2'] if team != 'n' else CREAM) * A
    return rgb


# ------------------------------------------------------------------ bands, trims
def dado(seed, team):                          # kickplate: glazed tile band with a brass lip
    h, w = 32, 64
    T = TEAM[team]
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = np.zeros((h, w, 3)) + np.array(CREAM)
    for cx in (16, 48):
        m = star_mask(xx - cx + 0.5, yy - 17.5, 9)
        rgb[m] = T['c1']
        rgb[np.hypot(xx - cx + 0.5, yy - 17.5) < 2.6] = T['c2'] if team != 'n' else CREAM
    for cx in (0, 32, 64):
        m = (np.abs(xx - cx + 0.5) + np.abs(yy - 17.5)) < 6
        rgb[m] = T['c2']
    edge = np.zeros((h, w), bool)
    for cx in (16, 48):
        m = star_mask(xx - cx + 0.5, yy - 17.5, 9)
        edge |= m ^ np.roll(m, 1, 0) | m ^ np.roll(m, 1, 1)
    rgb[edge] = INK
    rgb[0:3] = BRASS
    rgb[1] = np.array(BRASS) * 1.25
    rgb[3] = INK
    rgb[30:32] = INK
    return rgb * (0.92 + 0.16 * fbm(h, w, seed, base=8)[..., None]) * A


def strip(seed, team):                         # pierced brass lamp band: star-shaped openings glow
    core, edge = TEAM[team]['glow']
    hm = HM(16, 64)
    hm.plate(0, 0, 64, 16, 1.4, 2)
    rgb = colorize(BRASS, hm.shade(1.0), fbm(16, 64, seed, base=4))
    idx = R.quantize(rgb)
    yy, xx = np.mgrid[0:16, 0:64]
    for cx in (16, 48):
        m = star_mask(xx - cx + 0.5, yy - 7.5, 5.2)
        idx[m] = core
        e = m ^ np.roll(m, 1, 0) | m ^ np.roll(m, 1, 1)
        idx[e & m] = edge
    for cx in (0, 32):
        m = np.hypot(wrapd(xx, cx - 0.5, 64), yy - 7.5) < 2.2
        idx[m] = edge
    idx[0] = q1(np.array(BRASS) * 1.2)
    idx[15] = q1(BRASS_D)
    return idx


def trim(seed):                                # cornice: carved plaster frieze, zigzag, gold line
    h, w = 16, 64
    yy, xx = np.mgrid[0:h, 0:w]
    hm = HM(h, w)
    hm.plate(0, 0, 64, 4, 1.8, 1)
    zig = np.abs(((xx % 16) - 8)) * 0.75 + 5
    hm.H[(yy >= 5) & (yy < 13) & (np.abs(yy - zig) < 1.3)] += 1.2
    rgb = colorize(PLASTER, hm.shade(1.2), fbm(h, w, seed, base=4))
    rgb[4] = np.array(GOLD) * A
    rgb[13:16] *= 0.7
    return rgb


def tread(seed):
    n = 32
    hm = HM(n, n)
    hm.plate(0, 1, n, n, 0.5, 4)
    return colorize(SAND, hm.shade(1.0), fbm(n, n, seed, base=4), grime_map(n, n, seed, 0.12, False))


def riser(seed):
    h, w = 16, 32
    rgb = colorize(SAND_D, np.ones((h, w)), fbm(h, w, seed, base=4))
    rgb[0:2] *= 1.3
    rgb[2] *= 0.45
    return rgb


def pillar(seed):                              # sandstone drums with a carved band at each drum top
    h, w = 128, 64
    hm = HM(h, w)
    for y0 in range(0, h, 64):
        hm.plate(0, y0 + 1, w, y0 + 64, 1.0, 2)
        hm.plate(0, y0 + 2, w, y0 + 12, 1.6, 1)
    rgb = colorize(SAND, hm.shade(1.0), fbm(h, w, seed, base=4, sy=4), grime_map(h, w, seed + 1, 0.12))
    yy, xx = np.mgrid[0:h, 0:w]
    band = ((yy % 64) >= 4) & ((yy % 64) < 10)
    chev = np.abs(((xx % 12) - 6)) * 0.6 + 4 + (yy // 64) * 64
    rgb[band & (np.abs(yy - chev) < 1.0)] *= 0.55
    rgb[(yy % 64) == 11] = np.array(GOLD) * A
    return rgb


def stand(seed, team):                         # 128 flag / Quad plate: a glazed star medallion
    n = 128
    T = TEAM[team]
    yy, xx = np.mgrid[0:n, 0:n]
    dx, dy = xx - 63.5, yy - 63.5
    rgb = np.zeros((n, n, 3)) + np.array(SAND_D)
    r = np.hypot(dx, dy)
    rgb[r < 60] = INK
    rgb[r < 57] = CREAM
    rgb[star_mask(dx, dy, 44)] = T['c1']
    rgb[star_mask(dx, dy, 30)] = GOLD
    rgb[star_mask(dx, dy, 18)] = T['c2'] if team != 'n' else INK
    rgb[r < 6] = GOLD
    for m in (star_mask(dx, dy, 44), star_mask(dx, dy, 30)):
        e = m ^ np.roll(m, 1, 0) | m ^ np.roll(m, 1, 1)
        rgb[e] = INK
    return rgb * A


def cedar_planks(seed):                        # perch slabs
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    rgb = colorize(CEDAR, np.ones((n, n)), fbm(n, n, seed, base=4, octaves=4, sy=1, sx=8))
    rgb[(yy % 16) == 0] *= 0.5
    rgb[((yy % 16) == 8) & ((xx % 32) == 4)] = BRASS
    return rgb


def lampbox(seed):
    hm = HM(16, 32)
    hm.plate(0, 2, 32, 14, 1.0, 2)
    return colorize(BRASS_D, hm.shade(), fbm(16, 32, seed))


def light(seed):                               # ceiling lantern underside: pierced brass star, amber
    yy, xx = np.mgrid[0:32, 0:32]
    dx, dy = xx - 15.5, yy - 15.5
    idx = np.full((32, 32), q1(BRASS_D), np.uint8)
    idx[star_mask(dx, dy, 13)] = q1(BRASS)
    idx[star_mask(dx, dy, 10)] = 237
    idx[star_mask(dx, dy, 6)] = 239
    idx[np.hypot(dx, dy) < 2] = 254
    return idx


def wlamp(seed, team):                         # wall lantern: brass frame, pierced star, team glass
    core, edge = TEAM[team]['glow']
    yy, xx = np.mgrid[0:32, 0:32]
    hm = HM(32, 32)
    hm.plate(0, 0, 32, 32, 1.5, 3)
    idx = R.quantize(colorize(BRASS, hm.shade(), fbm(32, 32, seed)))
    arch = (xx >= 7) & (xx < 25) & (yy >= 5) & (yy < 28) & ~((yy < 11) & (np.hypot(xx - 15.5, yy - 11) > 9))
    idx[arch] = edge
    idx[arch & star_mask(xx - 15.5, yy - 17, 6)] = core
    idx[arch & (np.hypot(xx - 15.5, yy - 17) < 1.8)] = 254
    return idx


def banner(seed, team):                        # 128 x 256 hanging banner: team cloth, gold border, star, fringe
    h, w = 256, 128
    T = TEAM[team]
    yy, xx = np.mgrid[0:h, 0:w]
    folds = 0.82 + 0.22 * np.cos(TAU * xx / 32 + 0.6 * fbm(h, w, seed, base=2, octaves=2) * 4)
    rgb = np.array(T['ban'], float) * folds[..., None]
    border = (xx < 8) | (xx >= 120) | ((yy >= 16) & (yy < 24))
    rgb[border & (yy >= 16)] = np.array(GOLD) * folds[border & (yy >= 16)][..., None]
    rgb[0:16] = np.array(CEDAR) * 1.1                 # the rod
    rgb[2:14] = np.array(BRASS)
    rgb[7:9] = np.array(BRASS) * 1.3
    dx, dy = xx - 63.5, yy - 116
    rgb[star_mask(dx, dy, 40)] = np.array(GOLD) * folds[star_mask(dx, dy, 40)][..., None]
    rgb[star_mask(dx, dy, 28)] = np.array(T['ban']) * 0.6 * folds[star_mask(dx, dy, 28)][..., None]
    rgb[star_mask(dx, dy, 12)] = np.array(T['c2'] if team != 'n' else CREAM) * folds[star_mask(dx, dy, 12)][..., None]
    for k in range(3):                                # gold chevrons below the star
        m = (np.abs(yy - (176 + 14 * k) - np.abs(xx - 63.5) * 0.35) < 2.5) & (np.abs(xx - 63.5) < 44)
        rgb[m] = np.array(GOLD) * 0.9
    tail = yy >= 232
    rgb[tail & ((xx % 8) >= 5)] = np.array(INK)       # fringe
    rgb[tail & ((xx % 8) < 5)] = np.array(GOLD) * 0.8
    return rgb * A


def canal(seed):                               # 64: glazed channel edges, water down the middle
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    rip = 0.5 + 0.5 * np.sin(TAU * (xx / 32 + 0.8 * fbm(n, n, seed, base=4, octaves=3)))
    rgb = (np.array((34, 64, 92)) * (0.75 + 0.4 * rip)[..., None])
    edge = (yy < 10) | (yy >= 54)
    z = zellige(n, seed + 1, 'b', period=32)
    rgb[edge] = z[edge] / A
    rgb[(yy == 10) | (yy == 53)] = BRASS
    rgb[(yy == 11) | (yy == 52)] = INK
    return rgb * A


def dome(seed):                                # 384 cupola: concentric gold star rings on night blue
    n = 384
    yy, xx = np.mgrid[0:n, 0:n]
    dx, dy = xx - 191.5, yy - 191.5
    r = np.hypot(dx, dy)
    ang = np.arctan2(dy, dx)
    rgb = np.array((30, 32, 64), float) * (0.85 + 0.25 * fbm(n, n, seed, base=6))[..., None]
    for rr, k in ((176, 16), (132, 16), (92, 8), (56, 8)):
        rho = rr * (1 - 0.12 * np.abs(np.cos(k * ang / 2)))
        ring = np.abs(r - rho) < 4
        rgb[ring] = GOLD
        rgb[np.abs(r - rho + 7) < 1.2] = BRASS_D
    cells = (r > 96) & (r < 128) & (np.abs(np.sin(8 * ang)) < 0.25)
    rgb[cells] = np.array(GOLD) * 0.8
    cells2 = (r > 136) & (r < 172) & (np.abs(np.sin(16 * ang)) < 0.2)
    rgb[cells2] = np.array(BRASS)
    rgb[star_mask(dx, dy, 40)] = GOLD
    rgb[star_mask(dx, dy, 26)] = (48, 62, 150)
    rgb[star_mask(dx, dy, 12)] = CREAM
    sq = np.maximum(np.abs(dx), np.abs(dy))
    rgb[sq > 184] = np.array(CEDAR) * 1.1
    rgb[(sq > 180) & (sq <= 184)] = GOLD
    return rgb * A


ZONES = {'bf': 'b', 'rf': 'r', 'bk': 'b', 'rk': 'r', 'bh': 'b', 'rh': 'r', 'bl': 'b', 'rl': 'r',
         'bs': 'b', 'rs': 'r', 'md': 'n', 'nc': 'n', 'sc': 'n'}


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    names = []

    def put(name, img, stone=False):
        if img.ndim == 2:
            MASK.pop('m', None)
        R.save(outdir, name, img if img.ndim == 2 else q(img, stone, len(names)))
        names.append(name)

    for k, (z, t) in enumerate(ZONES.items()):
        s = 9100 + 37 * k
        fam = z[1]
        if fam == 'f':                                          # forecourt + rear
            put(f'dc_{z}_wall', wall_sand(s), True)
            put(f'dc_{z}_flr', floor_flags(s + 1, SAND, t), True)
            put(f'dc_{z}_ceil', ceil_cedar(s + 2, t))
        elif fam == 'k':                                        # flag hall
            put(f'dc_{z}_wall', wall_plaster(s, t), True)
            put(f'dc_{z}_flr', floor_stars(s + 1, t))
            put(f'dc_{z}_ceil', ceil_coffer(s + 2, t))
        elif fam == 'h':                                        # north arc: gatehouse, aqueduct
            put(f'dc_{z}_wall', wall_sand(s, (176, 134, 88)), True)
            put(f'dc_{z}_flr', floor_bricks(s + 1), True)
            put(f'dc_{z}_ceil', ceil_cedar(s + 2, t))
        elif fam == 'l':                                        # south arc: cellar, undercroft
            put(f'dc_{z}_wall', wall_vault(s), True)
            put(f'dc_{z}_flr', floor_flags(s + 1, (118, 108, 92), t), True)
            put(f'dc_{z}_ceil', ceil_vault(s + 2), True)
        elif fam == 's':                                        # spine: tiled tunnels
            put(f'dc_{z}_wall', wall_tiles(s, t), True)
            put(f'dc_{z}_flr', floor_flags(s + 1, SAND_D, t), True)
            put(f'dc_{z}_ceil', ceil_vault(s + 2, (150, 130, 100)), True)
        elif z == 'md':                                         # mid chamber
            put('dc_md_wall', wall_plaster(s, 'n'), True)
            put('dc_md_flr', floor_stars(s + 1, 'n'))
            put('dc_md_ceil', ceil_coffer(s + 2, 'n'))
        elif z == 'nc':                                         # north court
            put('dc_nc_wall', wall_sand(s, (180, 140, 90)), True)
            put('dc_nc_flr', floor_flags(s + 1, SAND, 'n'), True)
            put('dc_nc_ceil', ceil_cedar(s + 2, 'n'))
        else:                                                   # south court
            put('dc_sc_wall', wall_vault(s, (128, 120, 104)), True)
            put('dc_sc_flr', floor_flags(s + 1, (118, 108, 92), 'n'), True)
            put('dc_sc_ceil', ceil_vault(s + 2), True)
        put(f'dc_{z}_strp', strip(s + 3, t))
    for t in 'brn':
        put(f'dc_{t}_dado', dado(70 + ord(t), t))
        put(f'dc_wlamp_{t}', wlamp(80 + ord(t), t))
    put('dc_trim', trim(71))
    put('dc_tread', tread(72), True)
    put('dc_riser', riser(73), True)
    put('dc_pillar', pillar(74), True)
    put('dc_stand_b', stand(75, 'b'))
    put('dc_stand_r', stand(76, 'r'))
    put('dc_stand_q', stand(77, 'n'))
    put('dc_cedar', cedar_planks(78))
    put('dc_lampbox', lampbox(79))
    put('dc_light', light(80))
    put('dc_ban_b', banner(81, 'b'))
    put('dc_ban_r', banner(82, 'r'))
    put('dc_canal', canal(83))
    put('dc_dome', dome(84))
    open(os.path.join(outdir, '..', 'ctex_names.txt'), 'w').write('\n'.join(names) + '\n')
    print(len(names), 'textures')


if __name__ == '__main__':
    main(sys.argv[1])
