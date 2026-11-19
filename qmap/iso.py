"""Cutaway 3D view of a generated map (the .json the generator writes): an isometric 'dollhouse'
with everything above a cut height removed, so you see each level's floors, walls and drops at
once. Floors are coloured by height (the vprofile / section colours). One image per cut.

    python3 iso.py map.json out.png [cut=200 cut=480 ...] [view=sw|se|nw|ne] [scale=0.25]

Use one cut just under each upper floor's ceiling to see that level with the ones below it.
Drawn from the 16-unit grid: prisms (chamfers, diagonal walls) show as their stepped stand-ins.
"""
import json
import math
import sys

from PIL import Image, ImageDraw


def turbo(t):
    t = min(max(t, 0.0), 1.0)
    r = 34.61 + t * (1172.33 - t * (10793.56 - t * (33300.12 - t * (38394.49 - t * 14825.05))))
    g = 23.31 + t * (557.33 + t * (1225.33 - t * (3574.96 - t * (1073.77 + t * 707.56))))
    b = 27.2 + t * (3211.1 - t * (15327.97 - t * (27814.0 - t * (22569.18 - t * 6838.66))))
    return tuple(int(min(max(v, 0), 255)) for v in (r, g, b))


def render(J, cut, view='sw', sc=0.25):
    C, X0, Y0, NX, NY, BOT, TOP = J['C'], J['XMIN'], J['YMIN'], J['NX'], J['NY'], J['BOT'], J['TOP']
    cols = J['cols']

    def air(col):
        out, z = [], BOT
        for a, b, _ in sorted(col):
            if a > z:
                out.append((z, a))
            z = max(z, b)
        if z < TOP:
            out.append((z, TOP))
        return out
    A = [[air(cols[i][j]) for j in range(NY)] for i in range(NX)]
    has = [[any(a > BOT for a, b in A[i][j]) for j in range(NY)] for i in range(NX)]
    near = [[any(has[a][b] for a in range(max(0, i - 2), min(NX, i + 3)) for b in range(max(0, j - 2), min(NY, j + 3)))
             for j in range(NY)] for i in range(NX)]
    fl = [a for i in range(NX) for j in range(NY) if has[i][j] for a, b in A[i][j] if a > BOT and b - a >= 56]
    lo, hi = (min(fl), max(fl)) if fl else (0, 1)          # one colour scale for every cut
    zfloor = min(fl) - 32 if fl else 0
    # view: the viewer's corner; flip axes so that the viewer is always at -x, -y in the math
    fx = -1 if view in ('se', 'ne') else 1
    fy = -1 if view in ('nw', 'ne') else 1
    c30, s30 = math.cos(math.radians(30)), math.sin(math.radians(30))

    def P(x, y, z):
        x, y = x * fx, y * fy
        return ((x - y) * c30 * sc, -((x + y) * s30 + (z - zfloor)) * sc)
    boxes = []
    for i in range(NX):
        for j in range(NY):
            if not near[i][j]:
                continue
            solids, z = [], max(BOT, zfloor)
            for a, b in A[i][j]:
                if a > z:
                    solids.append((z, a))
                z = b
            if z < TOP:
                solids.append((z, TOP))
            for a, b in solids:
                b2 = min(b, cut)
                if b2 <= max(a, zfloor):
                    continue
                boxes.append((i, j, max(a, zfloor), b2, b > cut))
    if not boxes:
        return None
    x0s = [X0 + i * C for i, j, *_ in boxes]
    y0s = [Y0 + j * C for i, j, *_ in boxes]
    corners = [P(x, y, z) for x in (min(x0s), max(x0s) + C) for y in (min(y0s), max(y0s) + C) for z in (zfloor, cut)]
    ux, uy = min(p[0] for p in corners), min(p[1] for p in corners)
    W = int(max(p[0] for p in corners) - ux) + 20
    H = int(max(p[1] for p in corners) - uy) + 20
    im = Image.new('RGB', (W, H), (20, 20, 22))
    d = ImageDraw.Draw(im)
    Q = lambda x, y, z: (P(x, y, z)[0] - ux + 10, P(x, y, z)[1] - uy + 10)
    # painter's order: far (large x*fx + y*fy) first, low first
    boxes.sort(key=lambda b: (-((X0 + b[0] * C) * fx + (Y0 + b[1] * C) * fy), b[2]))
    for i, j, a, b, cutface in boxes:
        x, y = X0 + i * C, Y0 + j * C
        xa, xb = (x, x + C) if fx > 0 else (x + C, x)          # near-to-viewer edges first
        ya, yb = (y, y + C) if fy > 0 else (y + C, y)
        # the two faces turned to the viewer (at xa and at ya), then the top
        for poly, shade in (([Q(xa, ya, a), Q(xa, yb, a), Q(xa, yb, b), Q(xa, ya, b)], 0.55),
                            ([Q(xa, ya, a), Q(xb, ya, a), Q(xb, ya, b), Q(xa, ya, b)], 0.72)):
            d.polygon(poly, fill=tuple(int(v * shade) for v in (150, 150, 158)))
        top = [Q(xa, ya, b), Q(xb, ya, b), Q(xb, yb, b), Q(xa, yb, b)]
        if cutface:
            d.polygon(top, fill=(70, 70, 76))                    # cut wall: flat dark
        else:
            c = turbo(0.12 + 0.85 * (b - lo) / max(1, hi - lo))
            d.polygon(top, fill=c)
    return im


if __name__ == '__main__':
    J = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    cuts, view, sc = [], 'sw', 0.25
    for a in sys.argv[3:]:
        k, v = a.split('=')
        if k == 'cut':
            cuts.append(int(v))
        elif k == 'view':
            view = v
        elif k == 'scale':
            sc = float(v)
    cuts = cuts or [J['TOP']]
    ims = [im for im in (render(J, c, view, sc) for c in cuts) if im]
    W = sum(im.width for im in ims) + 8 * (len(ims) - 1)
    H = max(im.height for im in ims)
    sheet = Image.new('RGB', (W, H), (20, 20, 22))
    x = 0
    for im in ims:
        sheet.paste(im, (x, 0))
        x += im.width + 8
    sheet.save(out)
    print('wrote', out, sheet.size)
