"""Vertical sections through a generated map (the .json the generator writes): the view that shows
which spaces sit over which, where you go up and down, and what overlooks what. Draw these FIRST
when designing for height, and look at them with every blockout.

    python3 section.py map.json out.png y=0 y=544 x=1200 [--pad 64]

Each slice is a cut along a line (y=... runs along x; x=... runs along y). Solid is grey, air is
coloured by height of its floor (same colours as vprofile's height map), walkable floors are white
lines, ramps show as slopes, items / spawns within --pad units of the cut are marked.
"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

S = 4                 # units per pixel


def turbo(t):
    t = min(max(t, 0.0), 1.0)
    r = 34.61 + t * (1172.33 - t * (10793.56 - t * (33300.12 - t * (38394.49 - t * 14825.05))))
    g = 23.31 + t * (557.33 + t * (1225.33 - t * (3574.96 - t * (1073.77 + t * 707.56))))
    b = 27.2 + t * (3211.1 - t * (15327.97 - t * (27814.0 - t * (22569.18 - t * 6838.66))))
    return tuple(int(min(max(v, 0), 255)) for v in (r, g, b))


def air_of(col, bot, top):
    out, z = [], bot
    for a, b, _ in sorted(col):
        if a > z:
            out.append((z, a))
        z = max(z, b)
    if z < top:
        out.append((z, top))
    return out


def section(J, axis, at, pad=64):
    C, X0, Y0, NX, NY, BOT, TOP = J['C'], J['XMIN'], J['YMIN'], J['NX'], J['NY'], J['BOT'], J['TOP']
    cols = J['cols']
    floors = [a for i in range(NX) for j in range(NY) for a, b in air_of(cols[i][j], BOT, TOP)
              if a > BOT and any(True for _ in [0])]
    lo, hi = (np.percentile(floors, 2), np.percentile(floors, 98)) if floors else (0, 1)
    if axis == 'y':
        j = int((at - Y0) // C)
        line = [(i, j) for i in range(NX)]
        u0 = X0
    else:
        i = int((at - X0) // C)
        line = [(i, j) for j in range(NY)]
        u0 = Y0
    used = [k for k, (i, j) in enumerate(line) if air_of(cols[i][j], BOT, TOP)[:1] and air_of(cols[i][j], BOT, TOP)[0][0] > BOT]
    if not used:
        return None
    k0, k1 = max(0, min(used) - 2), min(len(line), max(used) + 3)
    zs = [a for k in range(k0, k1) for a, b in air_of(cols[line[k][0]][line[k][1]], BOT, TOP)]
    zlo = int(min(zs) - 48) // 16 * 16
    zhi = int(max(b for k in range(k0, k1) for a, b in air_of(cols[line[k][0]][line[k][1]], BOT, TOP)) + 48)
    W, H = (k1 - k0) * C // S, (zhi - zlo) // S
    im = Image.new('RGB', (W, H + 18), (40, 40, 44))
    d = ImageDraw.Draw(im)
    Y = lambda z: H - (z - zlo) / S
    for k in range(k0, k1):
        i, j = line[k]
        x = (k - k0) * C / S
        for a, b in air_of(cols[i][j], BOT, TOP):
            if a <= BOT or b > TOP:
                continue
            a2, b2 = max(a, zlo), min(b, zhi)
            if b2 <= a2:
                continue
            c = turbo(0.12 + 0.85 * (a - lo) / max(1, hi - lo))
            c = tuple(int(v * 0.55 + 0.45 * 215) for v in c)       # pastel: air reads as air
            d.rectangle([x, Y(b2), x + C / S - 1, Y(a2)], fill=c)
            if b - a >= 56:
                d.line([x, Y(a), x + C / S - 1, Y(a)], fill=(255, 255, 255), width=2)
    for (r, ax_, sg, z0, z1, _b) in J.get('ramps', []):         # ramps as slopes
        x0, y0, x1, y1 = r
        on = (y0 <= at < y1) if axis == 'y' else (x0 <= at < x1)
        if not on or ax_ != ('x' if axis == 'y' else 'y'):
            continue
        a0, a1 = (x0, x1) if axis == 'y' else (y0, y1)
        if sg > 0:
            pts = [(a0, z0), (a1, z1), (a1, z0)]
        else:
            pts = [(a0, z1), (a1, z0), (a0, z0)]
        P = [((u - u0) / S - k0 * C / S, Y(z)) for u, z in pts]
        d.polygon(P, fill=(40, 40, 44))
        d.line(P[:2], fill=(255, 255, 255), width=2)
    marks = [(it[1], it[2], it[3], it[0].replace('item_', '').replace('weapon_', '')[:8]) for it in J.get('items', [])] + \
            [(s[0], s[1], s[2], 'spawn') for s in J.get('spawns', [])]
    for x_, y_, z_, lab in marks:
        off = (y_ - at) if axis == 'y' else (x_ - at)
        if abs(off) > pad:
            continue
        u = ((x_ if axis == 'y' else y_) - u0) / S - k0 * C / S
        col = (150, 20, 20) if lab != 'spawn' else (10, 60, 160)
        d.ellipse([u - 3, Y(z_ + 16) - 3, u + 3, Y(z_ + 16) + 3], fill=col)
        d.text((u + 4, Y(z_ + 16) - 12), lab, fill=col)
    for z in range((zlo + 127) // 128 * 128, zhi, 128):
        d.line([0, Y(z), 6, Y(z)], fill=(120, 120, 120))
        d.text((8, Y(z) - 6), str(z), fill=(150, 150, 150))
    d.rectangle([0, H, W, H + 18], fill=(24, 24, 26))
    span = (u0 + k0 * C, u0 + k1 * C)
    d.text((4, H + 3), f"{'y' if axis == 'y' else 'x'} = {at}   (along {'x' if axis == 'y' else 'y'} {span[0]} .. {span[1]}; "
                       f"1 px = {S} units; white = floor you can stand on)", fill=(230, 230, 230))
    return im


if __name__ == '__main__':
    J = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    pad = 64
    cuts = []
    for a in sys.argv[3:]:
        if a.startswith('--pad'):
            continue
        if '=' in a:
            k, v = a.split('=')
            cuts.append((k, int(v)))
        elif a.isdigit():
            pad = int(a)
    ims = [im for im in (section(J, k, v, pad) for k, v in cuts) if im]
    W = max(im.width for im in ims)
    sheet = Image.new('RGB', (W, sum(im.height + 6 for im in ims)), (18, 18, 20))
    y = 0
    for im in ims:
        sheet.paste(im, (0, y))
        y += im.height + 6
    sheet.save(out)
    print('wrote', out, sheet.size)
