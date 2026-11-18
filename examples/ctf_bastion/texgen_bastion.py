"""Original procedural 'rival fortresses' textures for ctf_bastion (all generated from code).

Dark castle stone and iron. Every surface tells you whose half you are in:
  mid - neutral pale grey limestone, warm-white light strips
  b*  - blue team: blue-grey granite family, ice-blue strips   (bh hall, bk keep, br routes, bl low)
  r*  - red team:  red-brown sandstone family, forge-red strips (rh hall, rk keep, rr routes, rl low)
Team emblems: an ice crystal (blue) and a flame (red) on cast-iron medallions.
Usage: python3 texgen_bastion.py outdir
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..', '..', 'qmap'] if 'examples' in os.path.abspath(__file__) else ['..', 'qmap'] if 'demos' in os.path.abspath(__file__) else [])))
import texgen_runic as R  # noqa: E402  (quantize / save / glyph / emblem tools)
from texgen import HM, fbm, colorize, grime_map  # noqa: E402
from texgen_cistern import ashlar, stains  # noqa: E402

R.T.ALBEDO = 0.84
rivet_row = R.rivet_row
IRON = (58, 58, 64)

#          wall             floor            ceiling         strip (core, edge)   style
ZONES = {
    'mid': ((30, 30, 30), (98, 96, 92), (31, 31, 31), (252, 241), 'basalt'),   # b9: one charcoal family with the Quad plate
    'bh':  ((86, 96, 116), (74, 80, 94), (42, 46, 56), (245, 244), 'granite'),
    'bk':  ((92, 104, 128), (78, 86, 104), (44, 50, 62), (246, 245), 'panel'),
    'br':  ((80, 88, 104), (70, 76, 88), (42, 46, 54), (245, 244), 'brick'),
    'bl':  ((62, 72, 86), (58, 64, 74), (36, 40, 48), (244, 244), 'rubble'),
    'rh':  ((118, 84, 70), (94, 74, 66), (56, 42, 38), (251, 249), 'granite'),
    'rk':  ((128, 88, 72), (100, 78, 68), (60, 44, 38), (251, 250), 'panel'),
    'rr':  ((108, 80, 70), (88, 70, 62), (54, 42, 38), (251, 249), 'brick'),
    'rl':  ((86, 64, 58), (72, 58, 54), (44, 36, 34), (249, 249), 'rubble'),
}


def tex_wall(z, seed):
    wall, style = ZONES[z][0], ZONES[z][4]
    n = 128
    nh = 96 if style == 'panel' else 128
    hm = HM(nh, n)
    tm = None
    if style == 'ashlar':           # big pale blocks, 4 courses
        tm = ashlar(hm, 4, 32, 64, 1.0, 2, jitter=1, seed=seed, tone=0.10)
    elif style == 'basalt':         # dark polished basalt blocks with fine pale joints
        tm = ashlar(hm, 4, 32, 64, 1.0, 1, jitter=0, seed=seed, tone=0.07)
    elif style == 'granite':        # large rough blocks
        tm = ashlar(hm, 4, 32, 128, 1.2, 3, jitter=1, seed=seed, tone=0.14)
    elif style == 'brick':          # smaller dressed blocks
        tm = ashlar(hm, 8, 16, 64, 1.0, 2, jitter=1, seed=seed, tone=0.12)
    elif style == 'rubble':         # irregular small stones
        tm = ashlar(hm, 8, 16, 32, 1.0, 1, jitter=1, seed=seed, tone=0.18)
    else:                           # keep: dressed panels (48 tall) in iron frames
        for y in (0, 48):
            for x in (0, 64):
                hm.plate(x, y, x + 64, y + 48, 1.4, 1)
                hm.plate(x + 6, y + 6, x + 58, y + 42, -1.0, 2, mode='add')
                for cx, cy in ((x + 3, y + 3), (x + 61, y + 3), (x + 3, y + 45), (x + 61, y + 45)):
                    hm.dome(cx, cy, 1.4, 0.8)
    var = fbm(nh, n, seed, base=4)
    g = grime_map(nh, n, seed + 3, 0.22 if style in ('rubble', 'brick') else 0.15)
    rgb = colorize(wall, hm.shade(1.0), var, g)
    if tm is not None:
        rgb = rgb * tm[..., None]
    if style == 'basalt':           # pale mortar lines read as a crisp grid on the dark stone
        rgb[hm.H < 0.15] = np.array((118, 114, 104))
    if style == 'panel':
        fr = np.ones((nh, n), bool)
        for y in (0, 48):
            for x in (0, 64):
                fr[y + 6:y + 42, x + 6:x + 58] = False
        rgb[fr] = rgb[fr] / np.array(wall) * np.array(IRON) * 1.1
    if style == 'basalt':           # b9: no water stains in mid - they quantised to green specks
        return rgb
    return stains(rgb, seed + 9, 0.25, tuple(int(c * 0.45) for c in wall))


def tex_floor(z, seed):
    fl, style = ZONES[z][1], ZONES[z][4]
    hm = HM(64, 64)
    if style in ('ashlar', 'granite', 'panel'):   # big flagstones, staggered
        hm.plate(1, 1, 64, 32, 0.8, 2)
        hm.plate(33, 33, 64 + 32, 64, 0.8, 2)
    else:                                          # small setts
        for y in range(0, 64, 16):
            off = 16 if (y // 16) % 2 else 0
            for x in range(0, 64, 32):
                hm.plate(x + off + 1, y + 1, x + off + 32, y + 16, 0.9, 1)
    return colorize(fl, hm.shade(1.0), fbm(64, 64, seed, base=4), grime_map(64, 64, seed + 5, 0.18, False))


def tex_mid_floor(seed):          # 128 tile: pale limestone, black basalt diamond inlay, gold boss
    n = 128
    y, x = np.mgrid[0:n, 0:n].astype(float)
    hm = HM(n, n)
    for yy in (0, 64):
        for xx in (0, 64):
            hm.plate(xx + 1, yy + 1, xx + 64, yy + 64, 0.8, 2)
    rgb = colorize((104, 100, 92), hm.shade(1.0), fbm(n, n, seed, base=4), grime_map(n, n, seed + 5, 0.12, False))
    d = np.abs(x - 63.5) + np.abs(y - 63.5)
    dia = (d < 46) & (d > 34)
    rgb[dia] = np.array((24, 24, 24)) * (0.9 + 0.2 * fbm(n, n, seed + 2, base=6)[dia][:, None])   # b12: basalt black
    rgb[(d >= 33) & (d <= 34)] = (168, 132, 58)                                                  # gold pin-line inside
    corner = np.minimum(np.minimum(x, n - 1 - x), np.minimum(y, n - 1 - y))
    cd = np.hypot(np.minimum(x, n - 1 - x), np.minimum(y, n - 1 - y))
    rgb[cd < 10] = np.array((24, 24, 24))
    rgb[np.hypot(x - 63.5, y - 63.5) < 7] = (168, 132, 58)
    rgb[np.abs(np.hypot(x - 63.5, y - 63.5) - 7) < 1] = (90, 70, 34)
    return rgb


def tex_ceil(z, seed):
    ce = ZONES[z][2]
    hm = HM(64, 64)
    for y in (0, 32):
        for x in (0, 32):
            hm.plate(x + 2, y + 2, x + 32, y + 32, 1.0, 3)       # coffers
    return colorize(ce, hm.shade(0.8), fbm(64, 64, seed, base=4))


def tex_strip(z, seed):
    """64x16 band: iron housing with clamps, glowing glass between (fullbright core, team colour)."""
    core_i, edge_i = ZONES[z][3]
    hm = HM(16, 64)
    hm.plate(0, 0, 64, 16, 1.4, 2)
    hm.groove(0, 3, 64, 13, 1.0)
    rivet_row(hm, 1, 8, 64, 16, r=1.0)
    rivet_row(hm, 14, 8, 64, 16, r=1.0)
    rgb = colorize(IRON, hm.shade(1.0), fbm(16, 64, seed, base=4))
    rgb[3:13] *= 0.35
    idx = R.quantize(rgb)
    x = np.arange(64)
    clamp = ((x % 32) >= 13) & ((x % 32) < 19)
    for row, pi in ((5, edge_i), (6, core_i), (7, core_i), (8, core_i), (9, core_i), (10, edge_i)):
        idx[row, ~clamp] = pi
    idx[3:13, clamp] = R.quantize(np.zeros((1, 1, 3)) + np.array(IRON) * 1.3)[0, 0]
    return idx


def tex_base(seed):                # kickplate: dark plinth stone with an iron lip
    hm = HM(32, 64)
    hm.plate(0, 4, 64, 32, 1.3, 2)
    rgb = colorize((50, 50, 54), hm.shade(), fbm(32, 64, seed, base=4), grime_map(32, 64, seed, 0.25, False))
    rgb[0:3] = np.array(IRON) * 1.4
    rgb[3] = (20, 20, 22)
    return rgb


def tex_trim(seed):                # cornice: iron band, rivets, a bead
    hm = HM(16, 64)
    hm.plate(0, 1, 64, 15, 1.6, 4)
    hm.groove(0, 7, 64, 8, 0.8)
    rivet_row(hm, 4, 4, 64, 16, r=1.4)
    rivet_row(hm, 11, 12, 64, 16, r=1.4)
    return colorize((84, 84, 90), hm.shade(1.1), fbm(16, 64, seed, base=4))


def tex_tread(seed):
    hm = HM(32, 32)
    hm.plate(1, 0, 32, 32, 0.5, 4)
    return colorize((88, 86, 84), hm.shade(1.0), fbm(32, 32, seed, base=6), grime_map(32, 32, seed, 0.14, False))


def tex_riser(seed):               # stone riser with an iron nosing
    hm = HM(16, 32)
    hm.plate(0, 3, 32, 16, 1.0, 2)
    rgb = colorize((58, 58, 60), hm.shade(), fbm(16, 32, seed, base=4))
    rgb[0:2] = np.array(IRON) * 1.6
    rgb[2] = (16, 16, 18)
    return rgb


def tex_pillar(seed, w=64, mid=False, stone=None):
    """Column face exactly w wide: stacked drums, each one stone across the whole face (so every
    face of a column starts and ends on a stone edge); a metal ring every 128."""
    hm = HM(128, w)
    for y in range(0, 128, 32):
        hm.plate(1, y + 1, w, y + 32, 1.0, 2)
    hm.plate(0, 0, w, 10, 2.2, 1)
    rivet_row(hm, 5, 4, w, 8, r=1.2)
    stone = stone or ((36, 36, 36) if mid else (104, 102, 98))
    ring = (168, 132, 58) if mid else (88, 88, 96)
    rgb = colorize(stone, hm.shade(), fbm(128, w, seed, base=4), grime_map(128, w, seed, 0.10))
    if mid:
        rgb[hm.H < 0.15] = np.array((118, 114, 104))
    rgb[0:10] = rgb[0:10] / np.array(stone) * np.array(ring)
    return rgb


def tex_quad(seed):                # Quad dais top (128): basalt plate, gold ring, gold boss
    n = 128
    y, x = np.mgrid[0:n, 0:n].astype(float)
    r = np.hypot(x - 63.5, y - 63.5)
    hm = HM(n, n)
    hm.plate(0, 0, n, n, 1.0, 3)
    hm.plate(8, 8, n - 8, n - 8, 0.5, 2, mode='add')
    hm.dome(63.5, 63.5, 12, 2.0)
    rgb = colorize((18, 18, 18), hm.shade(), fbm(n, n, seed, base=4))
    rgb[r < 12] = rgb[r < 12] / np.array((18, 18, 18)) * np.array((168, 132, 58))
    idx = R.quantize(rgb)
    idx[np.abs(r - 44) < 2.2] = 252
    idx[(np.abs(r - 44) >= 2.2) & (np.abs(r - 44) < 3.6)] = 241
    return idx


def tex_lampbox(seed):
    hm = HM(16, 32)
    hm.plate(0, 2, 32, 14, 1.0, 2)
    return colorize(IRON, hm.shade(), fbm(16, 32, seed))


def tex_light(seed):               # ceiling lantern underside: warm glass behind an iron cross-grille
    y, x = np.mgrid[0:32, 0:32]
    idx = np.full((32, 32), 253, np.uint8)
    idx[np.hypot(x - 15.5, y - 15.5) < 6] = 254
    ir = R.quantize(np.zeros((1, 1, 3)) + np.array(IRON))[0, 0]
    idx[(x < 3) | (x > 28) | (y < 3) | (y > 28)] = ir
    idx[(abs(x - 15.5) < 1.2) | (abs(y - 15.5) < 1.2)] = ir
    return idx


def tex_wlamp(seed):               # wall lantern 32x32: iron frame, warm glass, cross-bar
    y, x = np.mgrid[0:32, 0:32]
    hm = HM(32, 32)
    hm.plate(0, 0, 32, 32, 1.5, 3)
    rivet_row(hm, 2, 2, 32, 28, r=1.0)
    rivet_row(hm, 29, 2, 32, 28, r=1.0)
    idx = R.quantize(colorize(IRON, hm.shade(), fbm(32, 32, seed)))
    glass = (x >= 7) & (x < 25) & (y >= 6) & (y < 26)
    idx[glass] = 253
    idx[glass & ((x == 7) | (x == 24) | (y == 6) | (y == 25))] = 252
    idx[glass & (abs(x - 15.5) < 1)] = R.quantize(np.zeros((1, 1, 3)) + np.array(IRON))[0, 0]
    return idx


def crystal_shape(n=256):
    """Six-armed ice crystal: a hexagonal core, six arms each with two pairs of side barbs."""
    c = n / 2
    polys, det = [], []
    def arm_poly(a, r0, r1, w):
        ca, sa = np.cos(a), np.sin(a)
        px, py = -sa, ca
        return [(c + ca * r0 + px * w, c + sa * r0 + py * w), (c + ca * r1 + px * w * 0.55, c + sa * r1 + py * w * 0.55),
                (c + ca * (r1 + 10), c + sa * (r1 + 10)),
                (c + ca * r1 - px * w * 0.55, c + sa * r1 - py * w * 0.55), (c + ca * r0 - px * w, c + sa * r0 - py * w)]
    for k in range(6):
        a = np.pi / 2 + k * np.pi / 3
        polys.append(arm_poly(a, 0, 66, 12))
        for rb, L in ((30, 22), (50, 15)):
            for s in (-1, 1):
                b = a + s * np.pi / 3
                bx, by = c + np.cos(a) * rb, c + np.sin(a) * rb
                cb, sb = np.cos(b), np.sin(b)
                px, py = -sb, cb
                polys.append([(bx + px * 4, by + py * 4), (bx + cb * L + px * 2.5, by + sb * L + py * 2.5),
                              (bx + cb * (L + 5), by + sb * (L + 5)),
                              (bx + cb * L - px * 2.5, by + sb * L - py * 2.5), (bx - px * 4, by - py * 4)])
        det.append(arm_poly(a, 6, 56, 2.2))       # a groove down each arm
    hexa = [(c + 20 * np.cos(np.pi / 6 + k * np.pi / 3), c + 20 * np.sin(np.pi / 6 + k * np.pi / 3)) for k in range(6)]
    polys.append(hexa)
    return polys, det


def tex_sigil(kind, seed):
    """256x256 cast-iron medallion with a raised team emblem; glowing rune ring in team colour."""
    from scipy.ndimage import distance_transform_edt as edt
    n = 256
    y, x = np.mgrid[0:n, 0:n].astype(float)
    r = np.hypot(x - 127.5, y - 127.5)
    if kind == 'crystal':
        glow = np.array([150, 220, 255])
        c_edge, c_mid, c_core = np.array([20, 50, 130]), np.array([90, 170, 255]), np.array([225, 250, 255])
        polys, detail = crystal_shape(n)
    else:
        glow = np.array([255, 70, 30])
        c_edge, c_mid, c_core = np.array([130, 12, 6]), np.array([235, 50, 20]), np.array([255, 190, 90])
        polys, detail = R.emblem_shape('flame', n)
    H = np.zeros((n, n))
    frame = np.minimum(np.minimum(x, n - 1 - x), np.minimum(y, n - 1 - y))
    H += np.clip(frame / 3, 0, 1) * 3.0 - np.clip((frame - 14) / 2, 0, 1) * 2.2
    disk = np.clip((112 - r) / 4, 0, 1)
    H += disk * 2.6
    groove = (r > 86) & (r < 104)
    H -= groove * 1.2 * disk
    noise = fbm(n, n, seed, base=8, octaves=3)
    H += noise * 0.35
    cov = R._poly_mask(polys, n)
    inside = cov > 0.5
    dist = edt(inside)
    E = np.clip(dist / 6.0, 0, 1) ** 0.6 * 4.0
    det = R._poly_mask(detail, n) > 0.5
    H = H + (E - det * 0.9) * cov
    dif, spec = R._shade(H)
    iron = np.array([62, 62, 68]) * (0.85 + 0.3 * noise[..., None])
    base = np.where((frame < 14)[..., None], np.array([82, 82, 90]), iron)
    base = np.where((disk > 0.5)[..., None] & ~groove[..., None], np.array([44, 44, 50]) * (0.9 + 0.2 * noise[..., None]), base)
    rgb = base * (0.30 + 0.95 * dif[..., None])
    heat = np.clip(dist / (4.0 if kind == 'crystal' else 10.0), 0, 1)[..., None]
    hot = np.where(heat < 0.5, c_edge + (c_mid - c_edge) * (heat / 0.5), c_mid + (c_core - c_mid) * ((heat - 0.5) / 0.5))
    hot = hot * (0.72 + 0.38 * dif[..., None]) + 50 * spec[..., None]
    rgb = np.where(inside[..., None], hot, rgb)
    for t in range(14, n, 26):
        for (cx, cy) in ((t, 7), (t, n - 8), (7, t), (n - 8, t)):
            rgb[np.hypot(x - cx, y - cy) < 3] = (110, 110, 118)
    fb = inside & (heat[..., 0] > 0.15)
    rgb[(edt(~inside) <= 2.2) & ~inside] = (16, 16, 20)
    rng = np.random.default_rng(seed)
    for k in range(14):
        a = 2 * np.pi * k / 14 - np.pi / 2
        gx, gy = int(127.5 + 95 * np.cos(a)) - 6, int(127.5 + 95 * np.sin(a)) - 6
        g = R.glyph(rng, 12)
        fb[gy:gy + 12, gx:gx + 12] |= g
        rgb[gy:gy + 12, gx:gx + 12][g] = glow * 0.9
    ring = np.abs(r - 112) < 1.2
    fb |= ring
    rgb[ring] = glow * 0.8
    return R.quantize(np.clip(rgb, 0, 255), fb)


def tex_stand(team, seed):         # flag stand top (128 = the stand): iron plate, team-glow ring, centre boss
    n = 128
    y, x = np.mgrid[0:n, 0:n].astype(float)
    r = np.hypot(x - 63.5, y - 63.5)
    hm = HM(n, n)
    hm.plate(0, 0, n, n, 1.0, 3)
    hm.plate(8, 8, n - 8, n - 8, 0.5, 2, mode='add')
    hm.dome(63.5, 63.5, 14, 2.0)
    rgb = colorize((70, 70, 76), hm.shade(), fbm(n, n, seed, base=4))
    idx = R.quantize(rgb)
    core, edge = (246, 245) if team == 'b' else (251, 249)
    idx[np.abs(r - 40) < 2.2] = core
    idx[(np.abs(r - 40) >= 2.2) & (np.abs(r - 40) < 3.6)] = edge
    return idx


NEUTRAL = ('bs_mid_wall', 'bs_mid_ceil', 'bs_pmid96', 'bs_quad', 'bs_mid_flr')
_PAL = R.PAL.astype(int) if hasattr(R, 'PAL') else None


def neutralize(idx):
    """b10: map every low-saturation, non-fullbright pixel onto the pure grey ramp (indices 0-15),
    so mid's dark stone carries no blue tint (the 32-47 ramp is the blue base's family)."""
    pal = _PAL
    col = pal[idx]
    sat = col.max(-1) - col.min(-1)
    m = (sat <= 16) & (idx < 224)
    lum = col.mean(-1)
    greys = pal[0:16].mean(-1)
    near = np.abs(lum[..., None] - greys[None, None, :]).argmin(-1)
    out = idx.copy()
    out[m] = near[m]
    return out


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    names = []

    def put(name, img):
        idx = img if img.ndim == 2 else R.quantize(img)
        if name in NEUTRAL:
            idx = neutralize(idx)
        R.save(outdir, name, idx)
        names.append(name)

    for k, z in enumerate(ZONES):
        s = 12100 + 61 * k
        put(f'bs_{z}_wall', tex_wall(z, s))
        put(f'bs_{z}_flr', tex_mid_floor(s + 1) if z == 'mid' else tex_floor(z, s + 1))
        put(f'bs_{z}_ceil', tex_ceil(z, s + 2))
        put(f'bs_{z}_cond', tex_strip(z, s + 3))
    put('bs_base', tex_base(121))
    put('bs_trim', tex_trim(122))
    put('bs_tread', tex_tread(123))
    put('bs_riser', tex_riser(124))
    put('bs_pillar', tex_pillar(125))
    put('bs_pmid96', tex_pillar(125, w=96, mid=True))
    put('bs_pillar_b', tex_pillar(134, stone=(84, 94, 116)))      # b17: team-coloured columns inside each base
    put('bs_pillar_r', tex_pillar(135, stone=(116, 84, 72)))
    put('bs_quad', tex_quad(133))
    put('bs_lampbox', tex_lampbox(126))
    put('bs_light', tex_light(127))
    put('bs_wlamp', tex_wlamp(128))
    put('bs_sig_ice', tex_sigil('crystal', 129))
    put('bs_sig_fire', tex_sigil('flame', 130))
    put('bs_stand_b', tex_stand('b', 131))
    put('bs_stand_r', tex_stand('r', 132))
    open(os.path.join(outdir, '..', 'btex_names.txt'), 'w').write('\n'.join(names) + '\n')
    print(' '.join(names))


if __name__ == '__main__':
    main(sys.argv[1])
