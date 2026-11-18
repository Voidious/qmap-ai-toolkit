"""Original procedural textures for ca_agora (industrial base theme).

Everything here is generated from code (height maps + noise), then quantized to
the Quake palette and written as indexed PNGs that makewad.py packs into a WAD.

Zones and accent colours:
  court   steel   (silver)      upper  blue
  gallery bronze                hall   green
  annex   rust
Usage: python3 texgen.py outdir
"""
import os
import sys

import numpy as np
from PIL import Image

PAL = np.frombuffer(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'quake_palette.lmp'), 'rb').read(),
                    np.uint8).reshape(256, 3).astype(np.float32)
W8 = np.array([2.0, 4.0, 3.0], np.float32)


def quantize(rgb, fullbright=False):
    """rgb HxWx3 float -> HxW palette indices (nearest, weighted). No fullbrights unless asked."""
    h, w, _ = rgb.shape
    pal = PAL if fullbright else PAL[:224]
    # fine grain breaks up palette banding (stable per texture size)
    grain = np.random.default_rng(h * 1000 + w).normal(0, 3.2, (h, w, 1))
    px = np.clip((rgb + grain).reshape(-1, 3), 0, 255)
    out = np.empty(len(px), np.uint8)
    for s in range(0, len(px), 8192):
        d = (((px[s:s + 8192, None, :] - pal[None, :, :]) ** 2) * W8).sum(-1)
        out[s:s + 8192] = d.argmin(1)
    return out.reshape(h, w)


# ------------------------------------------------------------------ noise
def vnoise(h, w, cy, cx, seed):
    """Tileable value noise, cy x cx random lattice, smooth interpolation."""
    r = np.random.default_rng(seed).random((cy, cx))
    y = np.arange(h) * cy / h
    x = np.arange(w) * cx / w
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    fy = y - y0
    fx = x - x0
    fy = fy * fy * (3 - 2 * fy)
    fx = fx * fx * (3 - 2 * fx)
    y1 = (y0 + 1) % cy
    x1 = (x0 + 1) % cx
    a = r[y0][:, x0]
    b = r[y0][:, x1]
    c = r[y1][:, x0]
    d = r[y1][:, x1]
    top = a + (b - a) * fx[None, :]
    bot = c + (d - c) * fx[None, :]
    return top + (bot - top) * fy[:, None]


def fbm(h, w, seed, base=4, octaves=4, sy=1, sx=1):
    tot = np.zeros((h, w))
    amp, norm = 1.0, 0.0
    for o in range(octaves):
        f = base * 2 ** o
        cy, cx = max(1, min(h, f * sy)), max(1, min(w, f * sx))
        tot += amp * vnoise(h, w, cy, cx, seed + o * 101)
        norm += amp
        amp *= 0.5
    return tot / norm


# ------------------------------------------------------------------ height map tools
class HM:
    def __init__(self, h, w):
        self.h, self.w = h, w
        self.H = np.zeros((h, w))
        self.Y, self.X = np.mgrid[0:h, 0:w]

    def plate(self, x0, y0, x1, y1, height=1.0, bevel=2, mode='max'):
        """Raised rectangle (exclusive x1,y1) with sloped edges; wraps around edges."""
        X = (self.X - x0) % self.w
        Y = (self.Y - y0) % self.h
        ww, hh = x1 - x0, y1 - y0
        inside = (X < ww) & (Y < hh)
        d = np.minimum(np.minimum(X, ww - 1 - X), np.minimum(Y, hh - 1 - Y)).astype(float)
        v = height * np.clip((d + 1) / bevel, 0, 1)
        v = np.where(inside, v, 0)
        if mode == 'max':
            self.H = np.maximum(self.H, v)
        else:
            self.H += v

    def groove(self, x0, y0, x1, y1, depth=1.0):
        X = (self.X - x0) % self.w
        Y = (self.Y - y0) % self.h
        m = (X < x1 - x0) & (Y < y1 - y0)
        self.H = np.where(m, self.H - depth, self.H)

    def dome(self, cx, cy, r, height=1.0):
        dx = (self.X - cx + self.w / 2) % self.w - self.w / 2
        dy = (self.Y - cy + self.h / 2) % self.h - self.h / 2
        d2 = (dx * dx + dy * dy) / (r * r)
        self.H = np.maximum(self.H, np.where(d2 < 1, self.H + height * np.sqrt(np.clip(1 - d2, 0, 1)), self.H))

    def shade(self, k=0.9):
        gx = np.roll(self.H, -1, 1) - np.roll(self.H, 1, 1)
        gy = np.roll(self.H, -1, 0) - np.roll(self.H, 1, 0)
        s = 1 + k * (gx + gy) * 0.5
        # ambient occlusion-ish: low areas slightly darker
        lo = self.H - self.H.max()
        return np.clip(s, 0.35, 1.8) * (1 + 0.08 * np.clip(lo, -3, 0))


ALBEDO = 0.86   # global darkening so lightmaps, not textures, carry brightness


def colorize(albedo, shade, var, grime=None):
    """albedo rgb tuple or HxWx3; var noise in 0..1 modulates brightness."""
    a = np.asarray(albedo, float)
    if a.ndim == 1:
        a = np.broadcast_to(a, shade.shape + (3,))
    h, w = shade.shape
    fine = vnoise(h, w, h // 2, w // 2, int(var.sum() * 1000) % 99991)
    v = (0.88 + 0.16 * var + 0.10 * fine)[..., None]
    out = a * v * shade[..., None] * ALBEDO
    if grime is not None:
        out = out * (1 - grime[..., None])
    return out


def grime_map(h, w, seed, amount=0.25, streaks=True):
    g = np.clip(fbm(h, w, seed, base=2, octaves=3) - 0.45, 0, 1) * amount * 2
    if streaks:
        s = fbm(h, w, seed + 7, base=8, octaves=2, sy=0, sx=1)  # vertical streaks
        s = np.clip(s - 0.55, 0, 1) * amount * 1.6
        g = g + s
    return np.clip(g, 0, 0.6)


# ------------------------------------------------------------------ zones
ZONES = {
    #          wall albedo        accent (stripe)     floor albedo       ceiling
    'steel':  ((100, 104, 112), (176, 182, 194), (88, 90, 96), (58, 60, 66)),
    'blue':   ((72, 72, 106), (40, 40, 176), (64, 64, 90), (44, 44, 60)),
    'bronze': ((112, 84, 52), (186, 122, 46), (96, 74, 50), (62, 50, 38)),
    'green':  ((76, 92, 70), (118, 120, 22), (74, 82, 68), (50, 56, 48)),
    'rust':   ((112, 70, 50), (190, 70, 34), (92, 68, 54), (60, 46, 40)),
}


def tex_wall(zone, seed):
    wall, acc, _, _ = ZONES[zone]
    n = 128
    hm = HM(n, n)
    if zone == 'steel':          # big riveted plates
        for y in (0, 64):
            for x in (0, 64):
                hm.plate(x + 1, y + 1, x + 64, y + 64, 1.6, 2)
                for t in range(8, 60, 12):
                    hm.dome(x + 5, y + t, 1.6, 0.9)
                    hm.dome(x + 59, y + t, 1.6, 0.9)
        hm.groove(0, 30, 128, 32, 0.6)
        hm.groove(0, 94, 128, 96, 0.6)
    elif zone == 'blue':         # tall tech panels with vent slots
        for x in range(0, 128, 32):
            hm.plate(x + 1, 1, x + 32, 128, 1.4, 2)
            hm.plate(x + 6, 10, x + 27, 52, 0.6, 1, mode='add')
            for y in range(72, 116, 6):
                hm.groove(x + 8, y, x + 25, y + 2, 1.2)
    elif zone == 'bronze':       # horizontal ribbed bands
        for y in range(0, 128, 32):
            hm.plate(0, y + 1, 128, y + 32, 1.5, 3)
            hm.groove(0, y + 14, 128, y + 16, 0.7)
            for x in (8, 72):
                hm.dome(x, y + 7, 1.8, 1.0)
                hm.dome(x + 48, y + 24, 1.8, 1.0)
    elif zone == 'green':        # chamfered block bond
        for r, y in enumerate(range(0, 128, 32)):
            off = 32 if r % 2 else 0
            for x in range(0, 128, 64):
                hm.plate(x + off + 1, y + 1, x + off + 64, y + 32, 1.6, 3)
    elif zone == 'rust':         # corrugated sheet with bolted strips
        for x in range(0, 128, 8):
            hm.plate(x, 0, x + 6, 128, 1.0, 3)
        for y in (0, 64):
            hm.plate(0, y, 128, y + 10, 2.2, 2)
            for x in range(4, 128, 16):
                hm.dome(x, y + 5, 1.6, 0.8)
    var = fbm(n, n, seed, base=4)
    g = grime_map(n, n, seed + 3, 0.18)
    rgb = colorize(wall, hm.shade(), var, g)
    if zone == 'blue':           # small accent light strips on the tech panels
        for x in range(0, 128, 32):
            rgb[56:60, x + 10:x + 22] = np.array(acc) * 0.95
    return rgb


def tex_floor(zone, seed):
    _, acc, fl, _ = ZONES[zone]
    n = 64
    hm = HM(n, n)
    if zone == 'steel':          # diamond tread plate
        for y in range(0, 64, 8):
            for x in range(0, 64, 8):
                ox = 4 if (y // 8) % 2 else 0
                cx, cy = x + ox + 2, y + 2
                hm.plate(cx, cy, cx + 4, cy + 2, 0.8, 1)
        hm.groove(0, 0, 64, 1, 0.8)
        hm.groove(0, 0, 1, 64, 0.8)
    elif zone == 'blue':         # beveled tiles
        for y in (0, 32):
            for x in (0, 32):
                hm.plate(x + 1, y + 1, x + 32, y + 32, 1.2, 2)
    elif zone == 'bronze':       # riveted plates
        hm.plate(1, 1, 64, 64, 1.2, 2)
        for cx, cy in ((5, 5), (59, 5), (5, 59), (59, 59), (32, 5), (32, 59), (5, 32), (59, 32)):
            hm.dome(cx, cy, 1.7, 1.0)
    elif zone == 'green':        # concrete slabs
        hm.plate(1, 1, 64, 32, 1.0, 2)
        hm.plate(1, 33, 32, 64, 1.0, 2)
        hm.plate(33, 33, 64, 64, 1.0, 2)
    elif zone == 'rust':         # heavy cross-hatched plate
        hm.plate(1, 1, 64, 64, 1.0, 2)
        for k in range(0, 64, 8):
            hm.groove(k, 4, k + 2, 60, 0.6)
    var = fbm(n, n, seed, base=4)
    g = grime_map(n, n, seed + 5, 0.16, streaks=False)
    rgb = colorize(fl, hm.shade(1.0), var, g)
    return rgb


def tex_ceil(zone, seed):
    *_, ce = ZONES[zone]
    n = 64
    hm = HM(n, n)
    hm.plate(2, 2, 64, 64, 1.2, 3)
    hm.groove(0, 31, 64, 33, 0.8)
    hm.groove(31, 0, 33, 64, 0.8)
    var = fbm(n, n, seed, base=4)
    return colorize(ce, hm.shade(0.8), var)


def tex_stripe(zone, seed):
    _, acc, _, _ = ZONES[zone]
    hm = HM(16, 64)
    hm.plate(0, 2, 64, 14, 1.4, 2)
    for x in range(0, 64, 32):
        hm.groove(x, 2, x + 1, 14, 1.0)
    var = fbm(16, 64, seed, base=4)
    rgb = colorize(acc, hm.shade(1.1), var)
    rgb[0:2] = np.array(acc) * 0.25
    rgb[14:16] = np.array(acc) * 0.25
    return rgb


# ------------------------------------------------------------------ shared
GUN = (78, 80, 86)


def tex_base(seed):
    hm = HM(32, 64)
    hm.plate(0, 4, 64, 32, 1.2, 2)
    hm.groove(0, 18, 64, 20, 0.8)
    for x in range(8, 64, 16):
        hm.dome(x, 10, 1.6, 0.9)
        hm.dome(x, 26, 1.6, 0.9)
    var = fbm(32, 64, seed, base=4)
    rgb = colorize((70, 70, 74), hm.shade(), var, grime_map(32, 64, seed, 0.15, False))
    rgb[0:2] = (150, 150, 156)
    rgb[2:4] = (40, 40, 44)
    return rgb


def tex_trim(seed):
    hm = HM(16, 64)
    hm.plate(0, 1, 64, 15, 1.6, 4)
    for x in range(0, 64, 16):
        hm.groove(x, 1, x + 1, 15, 0.8)
    var = fbm(16, 64, seed, base=4)
    return colorize((100, 102, 108), hm.shade(1.1), var)


def tex_frame(seed):
    # door jambs/lintels: dark gunmetal with a vertical channel and hazard notches
    hm = HM(32, 32)
    hm.plate(1, 0, 15, 32, 1.6, 3)
    hm.plate(17, 0, 31, 32, 1.6, 3)
    var = fbm(32, 32, seed, base=4)
    rgb = colorize(GUN, hm.shade(1.1), var)
    for y in range(0, 32, 16):
        for k in range(8):
            rgb[y + k, 15 + (k // 4):17 + (k // 4)] = (190, 150, 40)
    return rgb


def tex_tread(seed):
    hm = HM(32, 32)
    for y in range(2, 32, 6):
        hm.plate(2, y, 30, y + 3, 1.0, 1)
    var = fbm(32, 32, seed, base=4)
    return colorize((96, 96, 100), hm.shade(1.0), var)


def tex_riser(seed):
    # 16 tall: aligned so row 0 is the top edge of every step
    hm = HM(16, 32)
    hm.plate(0, 3, 32, 16, 1.0, 2)
    var = fbm(16, 32, seed, base=4)
    rgb = colorize((66, 66, 70), hm.shade(), var)
    rgb[0:2] = (196, 160, 52)            # yellow nosing line on each step edge
    rgb[2] = (40, 40, 40)
    return rgb


def tex_pillar(seed):
    hm = HM(64, 64)
    for x in range(0, 64, 16):
        hm.plate(x + 1, 0, x + 15, 64, 1.8, 5)
    hm.groove(0, 30, 64, 34, 1.4)
    for x in range(8, 64, 16):
        hm.dome(x, 32, 2.2, 1.6)
    var = fbm(64, 64, seed, base=4)
    return colorize((88, 90, 96), hm.shade(), var, grime_map(64, 64, seed, 0.15))


def tex_ledge(seed):
    hm = HM(64, 64)
    for r, y in enumerate(range(0, 64, 16)):
        off = 16 if r % 2 else 0
        for x in range(0, 64, 32):
            hm.plate(x + off + 1, y + 1, x + off + 32, y + 16, 1.4, 2)
    var = fbm(64, 64, seed, base=4)
    return colorize((92, 90, 88), hm.shade(), var, grime_map(64, 64, seed, 0.2))


def tex_crate(seed, top=False):
    hm = HM(64, 64)
    hm.plate(0, 0, 64, 64, 1.0, 1)
    hm.plate(5, 5, 59, 59, 0.4, 1, mode='add')
    if not top:
        idx = np.arange(64)
        for d in range(-3, 4):
            m = (hm.Y == np.clip(idx + d, 0, 63)[None, :]) & (hm.X > 5) & (hm.X < 59)
            hm.H = np.where(m, hm.H + 0.9, hm.H)
    for cx, cy in ((3, 3), (60, 3), (3, 60), (60, 60)):
        hm.dome(cx, cy, 2, 1.0)
    var = fbm(64, 64, seed, base=4)
    rgb = colorize((120, 112, 70) if not top else (110, 104, 70), hm.shade(), var)
    return rgb


def tex_grate(seed):
    hm = HM(64, 64)
    hm.H[:] = -1.5
    for k in range(0, 64, 8):
        hm.plate(k, 0, k + 3, 64, 1.5, 1)
        hm.plate(0, k, 64, k + 3, 1.2, 1)
    var = fbm(64, 64, seed, base=4)
    rgb = colorize((96, 98, 104), hm.shade(), var)
    holes = hm.H < -1
    rgb[holes] = (24, 24, 28)
    return rgb


def tex_light(seed):
    """32x32 ceiling light: gunmetal housing, fullbright panel."""
    hm = HM(32, 32)
    hm.plate(0, 0, 32, 32, 1.5, 3)
    rgb = colorize(GUN, hm.shade(), fbm(32, 32, seed))
    y, x = np.mgrid[0:32, 0:32]
    inner = (x >= 5) & (x < 27) & (y >= 5) & (y < 27)
    glow = 1 - 0.25 * (np.abs(x - 15.5) + np.abs(y - 15.5)) / 22
    rgb[inner] = (np.array([255, 244, 200]) * glow[inner][:, None])
    rgb[(x >= 5) & (x < 27) & ((y == 15) | (y == 16))] = (110, 110, 110)  # cross bar
    rgb[((x == 15) | (x == 16)) & (y >= 5) & (y < 27)] = (110, 110, 110)
    return rgb, inner


def tex_housing(seed):
    hm = HM(16, 32)
    hm.plate(0, 2, 32, 14, 1.0, 2)
    return colorize(GUN, hm.shade(), fbm(16, 32, seed))


def tex_sky(seed):
    """256x128: left half = front (alpha, index 0 transparent), right = back layer."""
    back = fbm(128, 128, seed, base=3, octaves=5)
    back = np.clip((back - 0.3) * 1.6, 0, 1)
    c0 = np.array([34, 40, 62])
    c1 = np.array([128, 132, 158])
    brgb = c0 + (c1 - c0) * back[..., None]
    front = fbm(128, 128, seed + 50, base=4, octaves=4)
    fa = np.clip((front - 0.44) * 2.6, 0, 1)
    frgb = np.array([150, 150, 168]) * (0.6 + 0.4 * fa[..., None])
    bi = quantize(brgb)
    fi = quantize(frgb)
    fi = np.where(fi == 0, 1, fi)  # keep 0 for transparency only
    fi = np.where(fa > 0.12, fi, 0)
    return np.concatenate([fi, bi], 1)


ZONE_OF = {'court': 'steel', 'upper': 'blue', 'gallery': 'bronze', 'hall': 'green', 'annex': 'rust'}


def save(outdir, name, idx):
    assert len(name) <= 15, name
    im = Image.fromarray(idx.astype(np.uint8), 'P')
    im.putpalette(PAL.astype(np.uint8).flatten().tolist())
    im.save(os.path.join(outdir, name + '.png'))


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    names = []

    def put(name, rgb, fb=False):
        save(outdir, name, quantize(rgb, fb))
        names.append(name)

    for k, z in enumerate(ZONES):
        s = 1000 + 37 * k
        put(f'ag_{z}_wall', tex_wall(z, s))
        put(f'ag_{z}_flr', tex_floor(z, s + 1))
        put(f'ag_{z}_ceil', tex_ceil(z, s + 2))
        put(f'ag_{z}_strp', tex_stripe(z, s + 3))
    put('ag_base', tex_base(11))
    put('ag_trim', tex_trim(12))
    put('ag_frame', tex_frame(13))
    put('ag_tread', tex_tread(14))
    put('ag_riser', tex_riser(15))
    put('ag_pillar', tex_pillar(16))
    put('ag_ledge', tex_ledge(17))
    put('ag_crate', tex_crate(18))
    put('ag_cratetop', tex_crate(19, top=True))
    put('ag_grate', tex_grate(20))
    put('ag_housing', tex_housing(21))
    rgb, inner = tex_light(22)
    idx = quantize(rgb)
    idx[inner] = quantize(rgb, True)[inner]
    save(outdir, 'ag_light', idx)
    names.append('ag_light')
    save(outdir, 'sky_agora', tex_sky(23))
    names.append('sky_agora')
    print(' '.join(names))


if __name__ == '__main__':
    main(sys.argv[1])
