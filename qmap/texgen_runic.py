"""Original procedural 'runic iron' textures for ca_crucible (all generated from code).

Quake 1 metal / rune episode feel: blackened riveted iron, brass and copper,
rust, verdigris, glowing rune bands (fullbright), lava.
Zones (callout colour):
  iron  - blackened iron   foundry     rune glow: orange
  brass - brass plate      halls       rune glow: gold
  rust  - rusted iron      furnaces    rune glow: red-orange
  verd  - verdigris copper conduits    rune glow: pale blue
  gun   - gunmetal         corridors   rune glow: pale blue
Usage: python3 texgen_runic.py outdir
"""
import os
import sys

import numpy as np
from PIL import Image

import texgen as T  # noqa: E402
from texgen import HM, fbm, vnoise, colorize, grime_map  # noqa: E402

PAL = T.PAL
T.ALBEDO = 0.84


def quantize(rgb, fb_mask=None):
    idx = T.quantize(rgb, False)
    if fb_mask is not None and fb_mask.any():
        full = T.quantize(rgb, True)
        idx[fb_mask] = np.where(full[fb_mask] == 255, idx[fb_mask], full[fb_mask])
    return idx


#           wall             floor            ceiling         glyph glow
ZONES = {
    'iron':  ((70, 72, 78), (66, 66, 70), (40, 40, 44), (255, 140, 40)),
    'brass': ((128, 104, 58), (100, 84, 56), (58, 50, 38), (255, 210, 80)),
    'rust':  ((110, 62, 44), (90, 64, 52), (56, 40, 34), (255, 90, 30)),
    'verd':  ((64, 102, 88), (60, 80, 72), (36, 50, 46), (140, 190, 255)),
    'gun':   ((70, 76, 92), (62, 66, 78), (38, 40, 48), (140, 190, 255)),
}
COPPER = (150, 84, 46)
IRON = (54, 54, 58)


def rivet_row(hm, y, x0, x1, step, r=1.6, h=1.0):
    for x in range(x0, x1, step):
        hm.dome(x, y, r, h)


def tex_wall(z, seed):
    wall = ZONES[z][0]
    n = 128
    hm = HM(n, n)
    if z == 'iron':          # heavy plates, double rivet seams
        for y in (0, 64):
            for x in (0, 64):
                hm.plate(x + 1, y + 1, x + 64, y + 64, 1.4, 2)
            rivet_row(hm, y + 5, 4, 128, 10)
            rivet_row(hm, y + 59, 4, 128, 10)
    elif z == 'brass':       # tall panels with a raised rune medallion
        for x in range(0, 128, 64):
            hm.plate(x + 1, 1, x + 64, 128, 1.2, 3)
            hm.plate(x + 8, 8, x + 57, 120, 0.5, 2, mode='add')
            hm.dome(x + 32, 64, 12, 1.4)
            hm.dome(x + 32, 64, 7, -0.8)
            rivet_row(hm, 4, x + 6, x + 60, 12)
            rivet_row(hm, 124, x + 6, x + 60, 12)
    elif z == 'rust':        # rough plates in staggered courses
        for r, y in enumerate(range(0, 128, 32)):
            off = 32 if r % 2 else 0
            for x in range(0, 128, 64):
                hm.plate(x + off + 1, y + 1, x + off + 64, y + 32, 1.3, 2)
            rivet_row(hm, y + 4, 6 + off % 64, 128, 16)
    elif z == 'verd':        # copper sheets with standing seams
        for x in range(0, 128, 32):
            hm.plate(x, 0, x + 32, 128, 0.8, 4)
            hm.plate(x + 14, 0, x + 18, 128, 1.6, 1)
        rivet_row(hm, 64, 8, 128, 16, 1.4)
    elif z == 'gun':         # machined blocks with vents
        for r, y in enumerate(range(0, 128, 64)):
            for x in range(0, 128, 64):
                hm.plate(x + 1, y + 1, x + 64, y + 64, 1.4, 3)
                for v in range(y + 40, y + 58, 5):
                    hm.groove(x + 10, v, x + 54, v + 2, 1.2)
    var = fbm(n, n, seed, base=4)
    g = grime_map(n, n, seed + 3, 0.22 if z in ('rust', 'iron') else 0.14)
    rgb = colorize(wall, hm.shade(1.0), var, g)
    if z == 'rust':          # rust streaks
        s = np.clip(fbm(n, n, seed + 8, base=8, octaves=2, sy=0, sx=1) - 0.5, 0, 1) * 1.6
        rgb = rgb * (1 - s[..., None] * 0.4) + np.array([130, 50, 20]) * s[..., None] * 0.4
    if z == 'verd':          # patina blotches
        p = np.clip(fbm(n, n, seed + 9, base=4) - 0.55, 0, 1) * 2.5
        rgb = rgb * (1 - p[..., None] * 0.5) + np.array([90, 160, 130]) * p[..., None] * 0.5
    return rgb


def tex_floor(z, seed):
    fl = ZONES[z][1]
    hm = HM(64, 64)
    if z in ('iron', 'gun'):     # diamond tread
        for y in range(0, 64, 8):
            for x in range(0, 64, 8):
                ox = 4 if (y // 8) % 2 else 0
                hm.plate(x + ox + 2, y + 2, x + ox + 6, y + 4, 0.8, 1)
        hm.groove(0, 0, 64, 1, 0.8)
        hm.groove(0, 0, 1, 64, 0.8)
    else:                        # riveted plates
        hm.plate(1, 1, 64, 64, 1.2, 2)
        for cx, cy in ((5, 5), (59, 5), (5, 59), (59, 59), (32, 5), (32, 59), (5, 32), (59, 32)):
            hm.dome(cx, cy, 1.7, 1.0)
    rgb = colorize(fl, hm.shade(1.0), fbm(64, 64, seed, base=4), grime_map(64, 64, seed + 5, 0.16, False))
    return rgb


def tex_ceil(z, seed):
    ce = ZONES[z][2]
    hm = HM(64, 64)
    hm.plate(2, 2, 64, 64, 1.2, 3)
    hm.groove(0, 31, 64, 33, 0.8)
    hm.groove(31, 0, 33, 64, 0.8)
    rivet_row(hm, 6, 6, 64, 13, 1.4)
    return colorize(ce, hm.shade(0.8), fbm(64, 64, seed, base=4))


def glyph(rng, size=12):
    """A random angular rune on a small grid: 2-4 strokes between grid points."""
    m = np.zeros((size, size), bool)
    pts = [(1, 1), (1, size // 2), (1, size - 2), (size // 2, 1), (size // 2, size // 2),
           (size // 2, size - 2), (size - 2, 1), (size - 2, size // 2), (size - 2, size - 2)]
    for _ in range(int(rng.integers(2, 5))):
        (y0, x0), (y1, x1) = [pts[i] for i in rng.choice(len(pts), 2, replace=False)]
        for t in np.linspace(0, 1, 2 * size):
            m[int(round(y0 + (y1 - y0) * t)), int(round(x0 + (x1 - x0) * t))] = True
    return m


def tex_rune(z, seed):
    """64x16 band: dark iron frame, recessed channel with glowing runes (fullbright)."""
    glow = np.array(ZONES[z][3], float)
    hm = HM(16, 64)
    hm.plate(0, 0, 64, 16, 1.4, 2)
    hm.groove(0, 2, 64, 14, 1.0)
    rgb = colorize(IRON, hm.shade(1.0), fbm(16, 64, seed, base=4))
    rgb[2:14] = rgb[2:14] * 0.45
    rng = np.random.default_rng(seed)
    fb = np.zeros((16, 64), bool)
    for k in range(4):
        g = glyph(rng, 12)
        x = 2 + k * 16
        sub = fb[2:14, x:x + 12]
        sub |= g
    rgb[fb] = glow
    rgb[0] = rgb[15] = np.array(COPPER) * 0.9
    return quantize(rgb, fb)


def tex_base(seed):
    hm = HM(32, 64)
    hm.plate(0, 4, 64, 32, 1.3, 2)
    rivet_row(hm, 11, 6, 64, 12)
    rivet_row(hm, 26, 6, 64, 12)
    rgb = colorize((52, 50, 50), hm.shade(), fbm(32, 64, seed, base=4), grime_map(32, 64, seed, 0.2, False))
    rgb[0:3] = np.array(COPPER)
    rgb[3] = (30, 28, 26)
    return rgb


def tex_trim(seed):              # copper cornice with rivets
    hm = HM(16, 64)
    hm.plate(0, 1, 64, 15, 1.6, 4)
    rivet_row(hm, 8, 4, 64, 8, 1.5)
    return colorize(COPPER, hm.shade(1.1), fbm(16, 64, seed, base=4))


def tex_tread(seed):
    hm = HM(32, 32)
    for y in range(0, 32, 8):
        for x in range(0, 32, 8):
            ox = 4 if (y // 8) % 2 else 0
            hm.plate(x + ox + 2, y + 2, x + ox + 6, y + 4, 0.8, 1)
    return colorize((76, 74, 74), hm.shade(1.0), fbm(32, 32, seed, base=4))


def tex_riser(seed):
    hm = HM(16, 32)
    hm.plate(0, 3, 32, 16, 1.0, 2)
    rgb = colorize((50, 48, 48), hm.shade(), fbm(16, 32, seed, base=4))
    rgb[0:2] = np.array(COPPER) * 1.15       # copper nosing on every step edge
    rgb[2] = (26, 24, 22)
    return rgb


def tex_pillar(seed):            # iron column, banded with copper
    hm = HM(64, 64)
    for x in range(0, 64, 16):
        hm.plate(x + 1, 0, x + 15, 64, 1.6, 5)
    rgb = colorize((62, 62, 66), hm.shade(), fbm(64, 64, seed, base=4), grime_map(64, 64, seed, 0.18))
    rgb[28:36] = np.array(COPPER) * (0.8 + 0.3 * hm.shade()[28:36, :, None] / 1.8)
    return rgb


def tex_block(seed, top=False, h=64):  # iron casting block with a rune seal; h = block height (side fits exactly)
    hm = HM(h, 64)
    hm.plate(0, 0, 64, h, 1.0, 1)
    hm.plate(5, 5, 59, h - 5, 0.5, 2, mode='add')
    for cx, cy in ((4, 4), (59, 4), (4, h - 5), (59, h - 5)):
        hm.dome(cx, cy, 2.2, 1.0)
    rgb = colorize((104, 96, 86), hm.shade(), fbm(h, 64, seed, base=4))
    fb = np.zeros((h, 64), bool)
    if not top:
        g = glyph(np.random.default_rng(seed), 12)
        y0 = h // 2 - 6
        fb[y0:y0 + 12, 26:38] = g
        rgb[fb] = (255, 120, 30)
    return quantize(rgb, fb)


def tex_grate(seed):
    hm = HM(64, 64)
    hm.H[:] = -1.5
    for k in range(0, 64, 8):
        hm.plate(k, 0, k + 3, 64, 1.5, 1)
        hm.plate(0, k, 64, k + 3, 1.2, 1)
    rgb = colorize((70, 68, 66), hm.shade(), fbm(64, 64, seed, base=4))
    rgb[hm.H < -1] = (90, 30, 8)         # lava glow showing through the grate
    return rgb


def tex_pad(seed):               # teleporter: rune circle, fullbright
    y, x = np.mgrid[0:64, 0:64]
    r = np.hypot(x - 31.5, y - 31.5)
    rgb = np.zeros((64, 64, 3)) + np.array(IRON)
    ring = (np.abs(r - 26) < 2.5) | (np.abs(r - 18) < 1.5)
    rng = np.random.default_rng(seed)
    fb = ring.copy()
    for k in range(6):
        a = k * np.pi / 3
        g = glyph(rng, 8)
        cx, cy = int(31.5 + 22 * np.cos(a)) - 4, int(31.5 + 22 * np.sin(a)) - 4
        fb[cy:cy + 8, cx:cx + 8] |= g
    core = r < 12
    rgb[core] = np.array([170, 210, 255])
    fb |= core
    rgb[fb & ~core] = (140, 190, 255)
    return quantize(rgb, fb)


def tex_cage(seed):
    hm = HM(16, 32)
    hm.plate(0, 2, 32, 14, 1.0, 2)
    return colorize(IRON, hm.shade(), fbm(16, 32, seed))


def tex_flame(seed):             # lamp underside: brazier glow behind iron bars
    y, x = np.mgrid[0:32, 0:32]
    glow = 1 - np.hypot(x - 15.5, y - 15.5) / 22
    rgb = np.array([255, 170, 70]) * np.clip(glow, 0.3, 1)[..., None]
    bars = ((x % 8) < 2) | (x < 3) | (x > 28) | (y < 3) | (y > 28)
    rgb[bars] = IRON
    return quantize(rgb, ~bars)


def _poly_mask(polys, n, ss=4):
    """Anti-aliased coverage of polygons (list of point lists in n-space) as float n x n."""
    from PIL import ImageDraw
    big = Image.new('L', (n * ss, n * ss), 0)
    d = ImageDraw.Draw(big)
    for p in polys:
        d.polygon([(x * ss, y * ss) for x, y in p], fill=255)
    return np.asarray(big.resize((n, n), Image.BOX)).astype(float) / 255


def _rot(pts, ang, cx, cy):
    c, s_ = np.cos(np.radians(ang)), np.sin(np.radians(ang))
    return [(cx + x * c - y * s_, cy + x * s_ + y * c) for x, y in pts]


def _shade(H, light=(-0.55, -0.65, 0.52), k=2.2):
    gy, gx = np.gradient(H)
    nx, ny, nz = -gx * k, -gy * k, np.ones_like(H)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    L = np.array(light) / np.linalg.norm(light)
    dif = np.clip((nx * L[0] + ny * L[1] + nz * L[2]) / ln, 0, 1)
    spec = dif ** 18
    return dif, spec


def emblem_shape(kind, n=256):
    """Polygons for the emblem relief, fitted inside the rune ring (radius ~80)."""
    c = n / 2
    def fit(polys, sc, dx=0, dy=0):
        return [[(c + (x * sc) + dx, c + (y * sc) + dy) for x, y in p] for p in polys]
    if kind == 'hammer':        # forging hammer: block face, wedge peen, wrapped grip; drawn upright, then tilted
        handle = [(-7, -8), (7, -8), (8, 92), (-8, 92)]
        grip = [[(-10, 58 + k * 9), (10, 58 + k * 9), (10, 63 + k * 9), (-10, 63 + k * 9)] for k in range(4)]
        knob = [(-11, 92), (11, 92), (9, 100), (-9, 100)]
        face = [(10, -44), (50, -46), (54, -42), (54, -14), (50, -10), (10, -12)]
        cheek = [(-14, -40), (14, -42), (14, -12), (-14, -14)]
        peen = [(-14, -40), (-46, -32), (-62, -27), (-62, -25), (-46, -20), (-14, -14)]
        collar = [(-12, -14), (12, -14), (10, -2), (-10, -2)]
        polys = [handle, knob, face, cheek, peen, collar] + grip
        polys = [_rot(p, 40, 0, 0) for p in polys]
        det = [_rot(p, 40, 0, 0) for p in grip]
        cx_off = -np.mean([x for p in polys for x, _ in p])
        cy_off = -np.mean([y for p in polys for _, y in p])
        return fit(polys, 1.0, cx_off, cy_off), fit(det, 1.0, cx_off, cy_off)
    def centred(polys, det, sc):
        xs = [x for p in polys for x, _ in p]
        ys = [y for p in polys for _, y in p]
        dx, dy = -(min(xs) + max(xs)) / 2 * sc, -(min(ys) + max(ys)) / 2 * sc
        return fit(polys, sc, dx, dy), fit(det, sc, dx, dy)
    if kind == 'anvil':         # b7: classic silhouette - long thick horn, squared heel, arched feet
        body = [(-112, -38), (-44, -46), (92, -46), (94, -10), (62, -6), (32, 6), (24, 30), (42, 44),
                (78, 52), (82, 66), (16, 66), (8, 54), (0, 50), (-8, 54), (-16, 66), (-82, 66),
                (-78, 52), (-42, 44), (-24, 30), (-32, 6), (-52, -6), (-84, -20), (-112, -34)]
        hardy = [(54, -46), (66, -46), (66, -36), (54, -36)]
        return centred([body], [hardy, [(-44, -46), (92, -46), (92, -40), (-44, -40)]], 0.74)
    if kind == 'sword':         # broadsword, point up
        blade = [(0, -100), (12, -82), (12, 28), (-12, 28), (-12, -82)]
        guard = [(-44, 28), (44, 28), (50, 36), (44, 42), (-44, 42), (-50, 36)]
        grip = [(-7, 42), (7, 42), (7, 80), (-7, 80)]
        pommel = [(-6, 80), (6, 80), (13, 87), (13, 95), (6, 102), (-6, 102), (-13, 95), (-13, 87)]
        fuller = [(-3, -70), (3, -70), (3, 20), (-3, 20)]
        wraps = [[(-8, 48 + k * 9), (8, 48 + k * 9), (8, 52 + k * 9), (-8, 52 + k * 9)] for k in range(4)]
        return centred([blade, guard, grip, pommel], [fuller] + wraps, 0.78)
    if kind == 'axe':           # single-bit war axe, tilted the other way from the hammer
        handle = [(-6, -70), (6, -70), (8, 96), (-8, 96)]
        blade = [(4, -66), (30, -60), (58, -84), (72, -52), (74, -14), (62, 18), (30, -4), (4, -10)]
        wraps = [[(-9, 58 + k * 9), (9, 58 + k * 9), (9, 62 + k * 9), (-9, 62 + k * 9)] for k in range(4)]
        polys = [_rot(p, -38, 0, 0) for p in [handle, blade] + wraps]
        det = [_rot(p, -38, 0, 0) for p in wraps]
        return centred(polys, det, 0.95)
    if kind == 'flame':
        outer = [(0, -100), (16, -62), (40, -84), (40, -40), (64, -30), (66, 14), (52, 52), (22, 72),
                 (-22, 72), (-52, 52), (-66, 14), (-58, -26), (-36, -14), (-40, -64), (-14, -42)]
        inner = [(2, -40), (16, -10), (26, 22), (14, 48), (-14, 48), (-26, 22), (-18, -6)]
        return centred([outer], [inner], 0.82)
    raise ValueError(kind)


def tex_sigil(kind, seed):
    """256x256 cast-metal medallion: riveted copper plaque, iron field, glowing rune ring,
    raised shaded emblem (brass hammer / steel anvil) with a fullbright molten outline."""
    from scipy.ndimage import distance_transform_edt as edt
    n = 256
    y, x = np.mgrid[0:n, 0:n].astype(float)
    r = np.hypot(x - 127.5, y - 127.5)
    glow = np.array([255, 150, 40])          # b6: same forge-hot palette for both sides
    # --- height: plaque frame, recessed field, medallion disk, rune groove
    H = np.zeros((n, n))
    frame = np.minimum(np.minimum(x, n - 1 - x), np.minimum(y, n - 1 - y))
    H += np.clip(frame / 3, 0, 1) * 3.0 - np.clip((frame - 14) / 2, 0, 1) * 2.2
    disk = np.clip((112 - r) / 4, 0, 1)
    H += disk * 2.6
    groove = (r > 86) & (r < 104)
    H -= groove * 1.2 * disk
    noise = fbm(n, n, seed, base=8, octaves=3)
    H += noise * 0.35
    # --- emblem relief with rounded bevel
    polys, detail = emblem_shape(kind, n)
    cov = _poly_mask(polys, n)
    inside = cov > 0.5
    dist = edt(inside)
    E = np.clip(dist / 7.0, 0, 1) ** 0.6 * 4.0
    det = _poly_mask(detail, n) > 0.5
    E = E - det * 0.9
    H = H + E * cov
    dif, spec = _shade(H)
    # --- colours
    iron = np.array([62, 62, 68]) * (0.85 + 0.3 * noise[..., None])
    copper = np.array(COPPER, float)
    base = np.where((frame < 14)[..., None], copper, iron)
    base = np.where((disk > 0.5)[..., None] & ~groove[..., None], np.array([46, 46, 52]) * (0.9 + 0.2 * noise[..., None]), base)
    rgb = base * (0.30 + 0.95 * dif[..., None])
    em = inside[..., None]
    # b6: forge-hot metal - white-yellow core cooling to orange and deep red at the edges
    heat = np.clip(dist / 14.0, 0, 1)[..., None]
    c_edge, c_mid, c_core = np.array([150, 30, 8]), np.array([255, 120, 20]), np.array([255, 236, 150])
    hot = np.where(heat < 0.5, c_edge + (c_mid - c_edge) * (heat / 0.5), c_mid + (c_core - c_mid) * ((heat - 0.5) / 0.5))
    hot = hot * (0.72 + 0.38 * dif[..., None]) + 60 * spec[..., None]
    rgb = np.where(em, hot, rgb)
    # rivets on the frame
    for t in range(14, n, 26):
        for (cx, cy) in ((t, 7), (t, n - 8), (7, t), (n - 8, t)):
            m = np.hypot(x - cx, y - cy) < 3
            rgb[m] = copper * 1.25
    # --- fullbright: molten outline around the emblem, runes in the ring groove
    fb = np.zeros((n, n), bool)
    fb |= inside & (heat[..., 0] > 0.15)     # the hot metal glows
    outline = (edt(~inside) <= 2.2) & ~inside
    rgb[outline] = (24, 18, 16)              # dark forge-scale edge
    rng = np.random.default_rng(seed)
    for k in range(14):
        a = 2 * np.pi * k / 14 - np.pi / 2
        gx, gy = int(127.5 + 95 * np.cos(a)) - 6, int(127.5 + 95 * np.sin(a)) - 6
        g = glyph(rng, 12)
        fb[gy:gy + 12, gx:gx + 12] |= g
        sub = rgb[gy:gy + 12, gx:gx + 12]
        sub[g] = glow * 0.9
    ring = (np.abs(r - 112) < 1.2)
    fb |= ring
    rgb[ring] = glow * 0.8
    return quantize(np.clip(rgb, 0, 255), fb)


def save(outdir, name, idx):
    assert len(name) <= 15, name
    im = Image.fromarray(idx.astype(np.uint8), 'P')
    im.putpalette(PAL.astype(np.uint8).flatten().tolist())
    im.save(os.path.join(outdir, name + '.png'))


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    names = []

    def put(name, img):
        save(outdir, name, img if img.ndim == 2 else quantize(img))
        names.append(name)

    for k, z in enumerate(ZONES):
        s = 5000 + 43 * k
        put(f'cr_{z}_wall', tex_wall(z, s))
        put(f'cr_{z}_flr', tex_floor(z, s + 1))
        put(f'cr_{z}_ceil', tex_ceil(z, s + 2))
        put(f'cr_{z}_rune', tex_rune(z, s + 3))
    put('cr_base', tex_base(51))
    put('cr_trim', tex_trim(52))
    put('cr_tread', tex_tread(53))
    put('cr_riser', tex_riser(54))
    put('cr_pillar', tex_pillar(55))
    put('cr_block', tex_block(56))
    put('cr_blocktop', tex_block(57, top=True))
    put('cr_block48', tex_block(56, h=48))
    put('cr_grate', tex_grate(58))
    put('cr_pad', tex_pad(59))
    put('cr_cage', tex_cage(60))
    put('cr_flame', tex_flame(61))
    put('cr_sig_hammer', tex_sigil('hammer', 62))
    put('cr_sig_anvil', tex_sigil('anvil', 63))
    for k, extra in enumerate(('sword', 'axe', 'flame')):
        save(outdir, f'cand_{extra}', tex_sigil(extra, 70 + k))   # candidates (not packed)
    print(' '.join(names))


if __name__ == '__main__':
    main(sys.argv[1])
