"""Original procedural 'drowned waterworks' textures for ca_cistern (all generated from code).

Old stone waterworks: weathered ashlar and brick, green bronze (verdigris) fittings, water
stains and algae, glowing glass light-strips. Zones (callout = wall stone + strip glow):
  hall   - great hall   pale limestone ashlar           cyan strip
  col    - colonnade    warm dressed sandstone panels   white strip
  tower  - tower        dark blue-grey granite blocks   cyan strip
  cist   - cistern      green-stained wet brick          cyan strip
  pump   - pump room    red-brown brick, iron bands      amber strip
  east   - east wing    slate panels in bronze frames    gold strip
  pass   - passages     rough dark brick                 (no strip)
Usage: python3 texgen_cistern.py outdir
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..', '..', 'qmap'] if 'examples' in os.path.abspath(__file__) else ['..', 'qmap'] if 'demos' in os.path.abspath(__file__) else [])))
import texgen_runic as R  # noqa: E402  (quantize / save / helpers)
from texgen import HM, fbm, colorize, grime_map  # noqa: E402

R.T.ALBEDO = 0.84
rivet_row = R.rivet_row

#           wall              floor            ceiling          strip (core idx, edge idx)
ZONES = {
    'hall':  ((140, 128, 106), (96, 90, 80), (54, 52, 48), (245, 244)),
    'col':   ((124, 106, 84), (100, 88, 72), (56, 50, 42), (254, 246)),
    'tower': ((82, 90, 106), (76, 78, 84), (44, 46, 52), (245, 244)),
    'cist':  ((74, 92, 80), (64, 76, 68), (40, 50, 44), (245, 244)),
    'pump':  ((104, 66, 52), (84, 70, 62), (50, 40, 36), (237, 235)),
    'east':  ((70, 74, 80), (78, 76, 72), (42, 44, 48), (252, 241)),
    'pass':  ((84, 76, 68), (72, 68, 62), (44, 40, 38), (245, 244)),
}
BRONZE = (78, 128, 106)     # verdigris
BRONZE_D = (46, 78, 66)
IRON = (54, 54, 58)


def stains(rgb, seed, amt=0.4, col=(40, 62, 46)):
    """Vertical water streaks running down the stone, tinted green."""
    n, m = rgb.shape[:2]
    s = np.clip(fbm(n, m, seed, base=8, octaves=2, sy=0, sx=1) - 0.45, 0, 1) * 1.8
    s = s * (0.6 + 0.4 * fbm(n, m, seed + 1, base=2, octaves=2))
    return rgb * (1 - s[..., None] * amt) + np.array(col) * s[..., None] * amt


def ashlar(hm, rows, course_h, block_w, h=1.0, bev=2, jitter=0, seed=0, tone=0.0):
    """Stone courses; returns a per-block brightness map (each stone a slightly different tone)."""
    rng = np.random.default_rng(seed)
    tmap = np.ones((hm.h, hm.w))
    for r in range(rows):
        y = r * course_h
        off = (block_w // 2) if r % 2 else 0
        for x in range(0, hm.w, block_w):
            hh = h * (0.85 + 0.3 * rng.random()) if jitter else h
            hm.plate(x + off + 1, y + 1, x + off + block_w, y + course_h, hh, bev)
            X = (hm.X - (x + off)) % hm.w
            tmap[(X < block_w) & (hm.Y >= y) & (hm.Y < y + course_h)] = 1 + tone * (rng.random() * 2 - 1)
    return tmap


def tex_wall(z, seed):
    wall = ZONES[z][0]
    n = 128
    nh = 96 if z in ('col', 'east') else 128   # b7: 48-tall panels - fit the walls between the bands
    hm = HM(nh, n)
    tm = None
    if z == 'hall':            # large limestone ashlar, slightly irregular faces
        tm = ashlar(hm, 4, 32, 64, 1.0, 2, jitter=1, seed=seed, tone=0.12)
    elif z == 'col':           # dressed sandstone: smooth panels with a sunk border
        for y in (0, 48):
            for x in (0, 64):
                hm.plate(x + 1, y + 1, x + 64, y + 48, 1.0, 2)
                hm.groove(x + 7, y + 7, x + 57, y + 9, 0.6)
                hm.groove(x + 7, y + 39, x + 57, y + 41, 0.6)
                hm.groove(x + 7, y + 7, x + 9, y + 41, 0.6)
                hm.groove(x + 55, y + 7, x + 57, y + 41, 0.6)
    elif z == 'tower':         # big granite blocks, 2 courses per 128
        tm = ashlar(hm, 4, 32, 128, 1.2, 3, jitter=1, seed=seed, tone=0.14)
    elif z == 'cist':          # small wet brick, stretcher bond
        tm = ashlar(hm, 8, 16, 32, 1.0, 2, jitter=1, seed=seed, tone=0.12)
    elif z == 'pump':          # brick with an iron band every 64
        tm = ashlar(hm, 8, 16, 32, 1.0, 2, jitter=1, seed=seed, tone=0.12)
        for y in (56, 120):
            hm.plate(0, y, 128, y + 8, 1.6, 1)
            rivet_row(hm, y + 4, 4, 128, 16)
    elif z == 'east':          # slate panels sunk in bronze frames
        for y in (0, 48):
            for x in (0, 64):
                hm.plate(x, y, x + 64, y + 48, 1.4, 1)
                hm.plate(x + 6, y + 6, x + 58, y + 42, -1.0, 2, mode='add')
    else:                      # passages: rough brick, uneven
        tm = ashlar(hm, 8, 16, 32, 1.0, 1, jitter=1, seed=seed, tone=0.15)
    var = fbm(nh, n, seed, base=4)
    g = grime_map(nh, n, seed + 3, 0.24 if z in ('cist', 'pass', 'pump') else 0.16)
    rgb = colorize(wall, hm.shade(1.0), var, g)
    if tm is not None:
        rgb = rgb * tm[..., None]
    if z == 'pump':            # iron bands
        for y in (56, 120):
            rgb[y:y + 8] = rgb[y:y + 8] / np.array(wall) * np.array(IRON) * 1.1
    if z == 'east':            # bronze frames
        fr = np.ones((nh, n), bool)
        for y in (0, 48):
            for x in (0, 64):
                fr[y + 6:y + 42, x + 6:x + 58] = False
        rgb[fr] = rgb[fr] / np.array(wall) * np.array(BRONZE)
    amt = {'cist': 0.55, 'pass': 0.4, 'hall': 0.35, 'tower': 0.35, 'pump': 0.3, 'col': 0.25, 'east': 0.25}[z]
    return stains(rgb, seed + 9, amt)


def tex_floor(z, seed):
    fl = ZONES[z][1]
    hm = HM(64, 64)
    if z in ('hall', 'col', 'tower'):      # flagstones, staggered
        hm.plate(1, 1, 64, 32, 0.8, 2)
        hm.plate(33, 33, 64 + 32, 64, 0.8, 2)
    elif z == 'east':                      # square tiles with bronze joints
        for y in (0, 32):
            for x in (0, 32):
                hm.plate(x + 2, y + 2, x + 32, y + 32, 1.0, 2)
    else:                                  # brick pavers, herringbone-ish
        for y in range(0, 64, 16):
            off = 16 if (y // 16) % 2 else 0
            for x in range(0, 64, 32):
                hm.plate(x + off + 1, y + 1, x + off + 32, y + 16, 0.9, 1)
    rgb = colorize(fl, hm.shade(1.0), fbm(64, 64, seed, base=4), grime_map(64, 64, seed + 5, 0.2, False))
    if z == 'east':
        jm = hm.H < 0.2
        rgb[jm] = np.array(BRONZE_D)
    if z in ('cist', 'pump', 'pass'):      # damp patches
        w = np.clip(fbm(64, 64, seed + 11, base=3) - 0.55, 0, 1) * 2
        rgb = rgb * (1 - 0.35 * w[..., None]) + np.array([30, 48, 40]) * 0.35 * w[..., None]
    return rgb


def tex_ceil(z, seed):
    ce = ZONES[z][2]
    hm = HM(64, 64)
    for y in (0, 32):
        for x in (0, 32):
            hm.plate(x + 2, y + 2, x + 32, y + 32, 1.0, 3)       # coffers
    return stains(colorize(ce, hm.shade(0.8), fbm(64, 64, seed, base=4)), seed, 0.3)


def tex_strip(z, seed):
    """64x16 band: verdigris bronze housing, glowing glass tube between clamps (fullbright core)."""
    core_i, edge_i = ZONES[z][3]
    hm = HM(16, 64)
    hm.plate(0, 0, 64, 16, 1.4, 2)
    hm.groove(0, 3, 64, 13, 1.0)
    rivet_row(hm, 1, 8, 64, 16, r=1.0)
    rivet_row(hm, 14, 8, 64, 16, r=1.0)
    rgb = colorize(BRONZE, hm.shade(1.0), fbm(16, 64, seed, base=4))
    rgb[3:13] *= 0.35
    idx = R.quantize(rgb)
    x = np.arange(64)
    clamp = ((x % 32) >= 13) & ((x % 32) < 19)
    for row, pi in ((5, edge_i), (6, core_i), (7, core_i), (8, core_i), (9, core_i), (10, edge_i)):
        idx[row, ~clamp] = pi
    cl = R.quantize(np.zeros((1, 1, 3)) + np.array(BRONZE) * 1.15)[0, 0]
    idx[3:13, clamp] = cl
    return idx


def tex_base(seed):                # kickplate: dark wet stone plinth with a bronze lip
    hm = HM(32, 64)
    hm.plate(0, 4, 64, 32, 1.3, 2)
    hm.groove(0, 18, 64, 19, 0.6)
    rgb = colorize((52, 56, 54), hm.shade(), fbm(32, 64, seed, base=4), grime_map(32, 64, seed, 0.3, False))
    rgb = stains(rgb, seed, 0.4)
    rgb[0:3] = BRONZE
    rgb[1] = np.array(BRONZE) * 1.2
    rgb[3] = (22, 26, 24)
    return rgb


def tex_trim(seed):                # cornice: verdigris bronze band with rivets and a bead
    hm = HM(16, 64)
    hm.plate(0, 1, 64, 15, 1.6, 4)
    hm.groove(0, 7, 64, 8, 0.8)
    rivet_row(hm, 4, 4, 64, 16, r=1.4)
    rivet_row(hm, 11, 12, 64, 16, r=1.4)
    rgb = colorize(BRONZE, hm.shade(1.1), fbm(16, 64, seed, base=4))
    return stains(rgb, seed, 0.25, (40, 50, 44))


def tex_tread(seed):               # worn stone step top: two slabs per 32, faint joint
    hm = HM(32, 32)
    hm.plate(1, 0, 32, 32, 0.5, 4)
    rgb = colorize((90, 88, 82), hm.shade(1.0), fbm(32, 32, seed, base=6), grime_map(32, 32, seed, 0.14, False))
    return rgb


def tex_riser(seed):               # stone riser with a bronze nosing on every step edge
    hm = HM(16, 32)
    hm.plate(0, 3, 32, 16, 1.0, 2)
    rgb = colorize((58, 58, 56), hm.shade(), fbm(16, 32, seed, base=4))
    rgb[0:2] = np.array(BRONZE) * 1.15
    rgb[2] = (18, 22, 20)
    return rgb


def tex_pillar(seed):              # fluted stone column, bronze collar every 128
    hm = HM(128, 64)
    for x in range(0, 64, 8):
        hm.plate(x + 1, 0, x + 7, 128, 1.4, 3)
    hm.plate(0, 0, 64, 10, 2.2, 1)
    rivet_row(hm, 5, 4, 64, 8, r=1.2)
    rgb = colorize((112, 108, 100), hm.shade(), fbm(128, 64, seed, base=4), grime_map(128, 64, seed, 0.12))
    rgb = stains(rgb, seed + 4, 0.2, (60, 66, 58))
    rgb[0:10] = rgb[0:10] / np.array((112, 108, 100)) * np.array(BRONZE)
    return rgb


def tex_block(seed, top=False):    # iron-bound timber crate
    hm = HM(64, 64)
    for x in range(0, 64, 16):
        hm.plate(x + 1, 0, x + 16, 64, 0.8, 1)                  # planks
    hm.plate(0, 0, 64, 6, 1.6, 1); hm.plate(0, 58, 64, 64, 1.6, 1)
    if not top:
        hm.plate(0, 0, 6, 64, 1.6, 1); hm.plate(58, 0, 64, 64, 1.6, 1)
    for cx, cy in ((3, 3), (60, 3), (3, 60), (60, 60), (32, 3), (32, 60)):
        hm.dome(cx, cy, 1.6, 1.0)
    rgb = colorize((96, 72, 50), hm.shade(), fbm(64, 64, seed, base=6, sy=4, sx=1), grime_map(64, 64, seed, 0.2))
    band = np.zeros((64, 64), bool)
    band[0:6] = band[58:64] = True
    if not top:
        band[:, 0:6] = band[:, 58:64] = True
    rgb[band] = rgb[band] / np.array((96, 72, 50)) * np.array(IRON)
    return rgb


def tex_machine(seed, top=False):  # pump housing: riveted iron, exactly 160 tall (= the housing) when a side
    if top:
        hm = HM(64, 64)
        for y in (0, 32):
            hm.plate(1, y + 1, 64, y + 32, 1.0, 2)
            rivet_row(hm, y + 4, 4, 64, 8, r=1.2)
        return stains(colorize((66, 68, 74), hm.shade(), fbm(64, 64, seed, base=4), grime_map(64, 64, seed, 0.25)), seed, 0.3)
    H = 160
    hm = HM(H, 64)
    for y0, y1 in ((8, 76), (84, 152)):
        hm.plate(1, y0 + 1, 64, y1, 1.0, 2)
        rivet_row(hm, y0 + 5, 4, 64, 8, r=1.2)
        rivet_row(hm, y1 - 5, 4, 64, 8, r=1.2)
        hm.dome(32, (y0 + y1) // 2, 7, 1.6)
    for y in (0, 76, 152):
        hm.plate(0, y, 64, y + 8, 1.8, 1)
    rgb = colorize((66, 68, 74), hm.shade(), fbm(H, 64, seed, base=4), grime_map(H, 64, seed, 0.25))
    yy, xx = np.mgrid[0:H, 0:64]
    band = (yy < 8) | ((yy >= 76) & (yy < 84)) | (yy >= 152)
    boss = (np.hypot(xx - 32, yy - 42) < 7) | (np.hypot(xx - 32, yy - 118) < 7)
    m = band | boss
    rgb[m] = rgb[m] / np.array((66, 68, 74)) * np.array(BRONZE)
    return stains(rgb, seed, 0.3)


def tex_grate(seed):               # bronze drain grate
    hm = HM(64, 64)
    hm.H[:] = -1.5
    for k in range(0, 64, 8):
        hm.plate(k, 0, k + 3, 64, 1.5, 1)
    hm.plate(0, 0, 64, 4, 1.5, 1)
    rgb = colorize(BRONZE_D, hm.shade(), fbm(64, 64, seed, base=4))
    rgb[hm.H < -1] = (10, 16, 14)
    return rgb


def tex_lampbox(seed):
    hm = HM(16, 32)
    hm.plate(0, 2, 32, 14, 1.0, 2)
    return colorize(BRONZE_D, hm.shade(), fbm(16, 32, seed))


def tex_light(seed):               # hanging lamp underside: warm glass behind a bronze cross-grille
    y, x = np.mgrid[0:32, 0:32]
    idx = np.full((32, 32), 253, np.uint8)
    r = np.hypot(x - 15.5, y - 15.5)
    idx[r < 6] = 254
    br = R.quantize(np.zeros((1, 1, 3)) + np.array(BRONZE_D))[0, 0]
    idx[(x < 3) | (x > 28) | (y < 3) | (y > 28)] = br
    idx[(abs(x - 15.5) < 1.2) | (abs(y - 15.5) < 1.2)] = br
    return idx


def tex_wlamp(seed):               # wall sconce 32x32: bronze frame, warm glass with a cross-bar
    y, x = np.mgrid[0:32, 0:32]
    hm = HM(32, 32)
    hm.plate(0, 0, 32, 32, 1.5, 3)
    rivet_row(hm, 2, 2, 32, 28, r=1.0)
    rivet_row(hm, 29, 2, 32, 28, r=1.0)
    idx = R.quantize(colorize(BRONZE, hm.shade(), fbm(32, 32, seed)))
    glass = (x >= 7) & (x < 25) & (y >= 6) & (y < 26)
    idx[glass] = 253
    idx[glass & ((x == 7) | (x == 24) | (y == 6) | (y == 25))] = 252
    idx[glass & (abs(y - 15.5) < 1)] = R.quantize(np.zeros((1, 1, 3)) + np.array(BRONZE_D))[0, 0]
    return idx


def _pipe(seed, vertical):
    n = 16
    t = np.linspace(-1, 1, n)
    prof = np.sqrt(np.clip(1 - t ** 2, 0, 1))                     # round tube shading across 16
    sh = 0.45 + 0.85 * prof - 0.25 * t                             # lit from above/left
    img = np.ones((n, 64)) * sh[:, None]
    col = np.arange(64)
    collar = (col % 64 >= 28) & (col % 64 < 36)
    img[:, collar] *= 1.18
    rgb = np.array(BRONZE)[None, None, :] * img[..., None] * (0.85 + 0.3 * fbm(n, 64, seed, base=4)[..., None])
    rgb[:, collar] = rgb[:, collar] / np.array(BRONZE) * np.array((96, 92, 70))
    rgb = rgb.clip(0, 255)
    return np.transpose(rgb, (1, 0, 2)) if vertical else rgb


def tex_water(seed):               # murky green-teal, slow ripples
    a = fbm(64, 64, seed, base=3, octaves=4)
    b = fbm(64, 64, seed + 6, base=6, octaves=3)
    v = np.clip(0.6 * a + 0.4 * b, 0, 1)
    c0, c1 = np.array([14, 38, 40]), np.array([60, 118, 108])
    return c0 + (c1 - c0) * v[..., None]


def tex_sky(seed):                 # dusk overcast: dim blue-grey back with a few stars, slate clouds
    back = R.fbm(128, 128, seed, base=3, octaves=5)
    c0, c1 = np.array([18, 24, 34]), np.array([52, 62, 78])
    bi = R.quantize(c0 + (c1 - c0) * np.clip(back * 1.3 - 0.2, 0, 1)[..., None])
    rng = np.random.default_rng(seed)
    for _ in range(30):
        bi[rng.integers(0, 128), rng.integers(0, 128)] = 254 if rng.random() < 0.3 else 245
    front = R.fbm(128, 128, seed + 50, base=4, octaves=4)
    fa = np.clip((front - 0.45) * 2.4, 0, 1)
    fi = R.quantize(np.array([58, 64, 72]) * (0.65 + 0.45 * fa[..., None]))
    fi = np.where(fi == 0, 1, fi)
    fi = np.where(fa > 0.12, fi, 0)
    return np.concatenate([fi, bi], 1)


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    names = []

    def put(name, img):
        R.save(outdir, name, img if img.ndim == 2 else R.quantize(img))
        names.append(name)

    for k, z in enumerate(ZONES):
        s = 9100 + 53 * k
        put(f'cs_{z}_wall', tex_wall(z, s))
        put(f'cs_{z}_flr', tex_floor(z, s + 1))
        put(f'cs_{z}_ceil', tex_ceil(z, s + 2))
        put(f'cs_{z}_cond', tex_strip(z, s + 3))
    put('cs_base', tex_base(91))
    put('cs_trim', tex_trim(92))
    put('cs_tread', tex_tread(93))
    put('cs_riser', tex_riser(94))
    put('cs_pillar', tex_pillar(95))
    put('cs_crate', tex_block(96))
    put('cs_cratetop', tex_block(97, top=True))
    put('cs_grate', tex_grate(98))
    put('cs_machine', tex_machine(107))
    put('cs_machtop', tex_machine(108, top=True))
    put('cs_lampbox', tex_lampbox(100))
    put('cs_light', tex_light(101))
    put('cs_wlamp', tex_wlamp(102))
    put('cs_pipeh', _pipe(105, False))
    put('cs_pipev', _pipe(106, True))
    put('*water_cs', tex_water(103))
    put('sky_cistern', tex_sky(104))
    open(os.path.join(outdir, '..', 'ctex_names.txt'), 'w').write('\n'.join(names) + '\n')
    print(' '.join(names))


if __name__ == '__main__':
    main(sys.argv[1])
