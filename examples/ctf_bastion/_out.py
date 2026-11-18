# =========================================================================
# OUTPUT
# =========================================================================
def resolve_themes():
    """Structural solid takes the theme of the nearest carved cell (2D BFS)."""
    from collections import deque
    zone = [[theme[i][j] for j in range(NY)] for i in range(NX)]
    q = deque((i, j) for i in range(NX) for j in range(NY) if zone[i][j])
    while q:
        i, j = q.popleft()
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a, b = i + di, j + dj
            if 0 <= a < NX and 0 <= b < NY and zone[a][b] is None:
                zone[a][b] = zone[i][j]
                q.append((a, b))
    return zone


def _air(col):
    out, z = [], BOT
    for a, b, _ in sorted(col):
        if a > z:
            out.append((z, a))
        z = max(z, b)
    if z < TOP:
        out.append((z, TOP))
    return out


ROLE_RANK = {'wall': 0, 'glass': 1, 'strp': 1, 'base': 2, 'trim': 3}


def room_theme(i, j, f, zmap):
    """Theme of the room whose air starts at height f in column (i, j): rooms can stack."""
    best, dbest = None, None
    for z0, z1, th, door in rooms.get((i, j), []):
        if z0 <= f < z1:
            if door:
                dbest = th            # b9: a doorway keeps the stone of the room it was cut for
            else:
                best = th
    return best or dbest or zmap[i][j] or 'atrium'


def door_only(p, q, f):
    """True when the air starting at f in (p, q) belongs only to a doorway passage."""
    d = n = False
    for z0, z1, th, door in rooms.get((p, q), []):
        if z0 <= f < z1:
            if door:
                d = True
            else:
                n = True
    return d and not n


def room_floor(p, q, f):
    """Floor of the (non-door) room that the air starting at f in (p, q) belongs to."""
    zs = [z0 for z0, z1, th, door in rooms.get((p, q), []) if not door and z0 <= f < z1]
    return max(zs) if zs else f


DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))          # +x, -x, +y, -y
PERIOD = {'wall': 128, 'base': 32, 'strp': 16, 'trim': 16, 'glass': 96, None: 128}


def detail_pieces():
    """b12: per-face texturing. Each wall piece is cut at every band edge of every
    neighbouring air, then EACH SIDE FACE is textured from the air it looks at:
    room air gets that room's bands (kickplate / frieze / glass / cornice), air that
    belongs only to a doorway gets one plain stone (the doorway's room) so passage
    reveals read as a single surface. Kickplate follows stairs up and down.
    Yields (i, j, a, b, kind, top_tex, bot_tex, faces[4]) with faces = (tex, yoff) or None."""
    air = [[_air(cols[i][j]) for j in range(NY)] for i in range(NX)]
    zmap = resolve_themes()

    def solid_at(i, j, z):
        return 0 <= i < NX and 0 <= j < NY and not any(f < z < c for f, c in air[i][j])

    def info(p, q, f, c):
        mats = {(a2, b2): m2 for a2, b2, m2 in cols[p][q]}
        th = room_theme(p, q, f, zmap)
        cm = next((m2 for (a2, b2), m2 in mats.items() if a2 == c), None)
        fm = next((m2 for (a2, b2), m2 in mats.items() if b2 == f), None)
        if fm == 'bridge':
            foot = None
        elif fm == 'stair' and th not in STEP_KICK:
            rf = room_floor(p, q, f)
            foot = rf + 32 if rf + 32 > f else None     # level with the room floor; steps climb in front
        else:
            foot = f + 32
            if th not in STEP_KICK and room_floor(p, q, f) < f:
                foot = None          # b15: no kickplate on raised platforms (dais, landing, mezzanine, lofts)
        return dict(f=f, c=c, th=th, sz=strip_z(th, f), nocap=(cm == 'bridge' or (p, q, c) in NOCAP), foot=foot,
                    door=door_only(p, q, f), tz=TRIM_Z.get(th))

    def proxy(i, j, d, n, a, b):
        """Room air in front of a coplanar wall next to this door-only face (flush door):
        its bands continue across this face."""
        di, dj = DIRS[d]
        ai, aj = dj, di
        zm = (max(n['f'], a) + min(n['c'], b)) / 2
        for k in range(1, 9):
            for s in (1, -1):
                if not all(solid_at(i + s * t * ai, j + s * t * aj, zm) for t in range(1, k + 1)):
                    continue
                p, q = i + s * k * ai + di, j + s * k * aj + dj
                if not (0 <= p < NX and 0 <= q < NY):
                    continue
                for f2, c2 in air[p][q]:
                    if f2 < n['c'] and c2 > n['f'] and not door_only(p, q, f2):
                        return info(p, q, f2, c2)
        return None

    def band_cuts(n):
        cs = {n['f'], n['c']}
        if n['foot'] is not None:
            cs.add(n['foot'])
        if not n['nocap']:
            cs.add(n['c'] - 16)
        if n['f'] <= n['sz'] and n['sz'] + 16 < n['c']:
            cs |= {n['sz'], n['sz'] + 16}
        if n['tz'] is not None and n['f'] <= n['tz'] and n['tz'] + 16 < n['c'] - 16:
            cs |= {n['tz'], n['tz'] + 16}
        gz = GLASS_Z.get(n['th'])
        if gz is not None and n['f'] + 32 <= gz and gz + 96 <= n['c'] - 16:
            cs |= {gz, gz + 96}
        return cs

    for i in range(NX):
        for j in range(NY):
            for a, b, m in cols[i][j]:
                own = {(f, c): room_theme(i, j, f, zmap) for f, c in air[i][j]}
                ztop = next((t for (f, c), t in own.items() if f == b), None)
                zbot = next((t for (f, c), t in own.items() if c == a), None)
                nbs = []                                  # per direction: list of air infos overlapping [a, b]
                for di, dj in DIRS:
                    p, q = i + di, j + dj
                    lst = []
                    if 0 <= p < NX and 0 <= q < NY:
                        lst = [info(p, q, f, c) for f, c in air[p][q] if f < b and c > a]
                        for n in lst:
                            if n['door'] and m is None:
                                n['proxy'] = proxy(i, j, len(nbs), n, a, b)
                    nbs.append(lst)
                allair = [n for lst in nbs for n in lst]
                act = [n for n in allair if not n['door']]
                zside = (act or allair)[0]['th'] if allair else (zmap[i][j] or 'atrium')
                if m is not None:
                    faces = []
                    for lst in nbs:
                        if not lst:
                            faces.append(None)
                            continue
                        n = max(lst, key=lambda n: min(n['c'], b) - max(n['f'], a))
                        t = textures(m, n['th'], None)[2]
                        yo = ZONE_FLOOR[n['th']] if m == 'ledge' else b
                        faces.append((t, yo % 128))
                    yield (i, j, a, b, m, textures(m, ztop or zside, None)[0],
                           textures(m, zbot or zside, None)[1], faces)
                    continue
                cuts = {a, b}
                for n in allair:
                    cuts |= {n['f'], n['c']}
                    if not n['door']:
                        cuts |= band_cuts(n)
                    elif n.get('proxy'):
                        cuts |= {z for z in band_cuts(n['proxy']) if n['f'] < z < n['c']}
                cuts = sorted(z for z in cuts if a <= z <= b)
                for p, q in zip(cuts, cuts[1:]):
                    mid = (p + q) / 2
                    faces = []
                    for d, lst in enumerate(nbs):
                        n = next((n for n in lst if n['f'] < mid < n['c']), None)
                        if n is None:
                            faces.append(None)
                            continue
                        if n['door']:
                            P = n.get('proxy')
                            if P and P['f'] < mid < P['c']:
                                n = P                      # flush with a room wall: carry its bands across
                            else:
                                th = n['th']
                                faces.append((f'bs_{ZONE_OF.get(th, "mid")}_wall', ZONE_FLOOR[th] % 128))
                                continue
                        th = n['th']
                        f, c, sz = n['f'], n['c'], n['sz']
                        gz = GLASS_Z.get(th)
                        di, dj = DIRS[d]
                        if mid >= c - 16 and not n['nocap']:
                            role, anc = 'trim', c
                        elif n['foot'] is not None and mid < n['foot']:
                            role, anc = 'base', n['foot']
                        elif n['tz'] is not None and n['tz'] <= mid < n['tz'] + 16 and n['tz'] + 16 < c - 16:
                            role, anc = 'trim', n['tz'] + 16
                        elif sz <= mid < sz + 16:
                            role, anc = 'strp', sz + 16
                        elif (gz is not None and f + 32 <= gz and gz + 96 <= c - 16 and gz <= mid < gz + 96
                              and all(solid_at(i + k * dj, j + k * di, mid) and not solid_at(i + k * dj + di, j + k * di + dj, mid)
                                      for k in (-2, -1, 1, 2))):
                            role, anc = 'glass', gz + 96   # only on straight runs wide enough for a window
                        else:
                            role, anc = 'wall', ZONE_FLOOR[th]
                        faces.append((textures('wall', th, role)[2], anc % PERIOD[role]))
                    zt = ztop if q == b and ztop else None
                    zb = zbot if p == a and zbot else None
                    yield (i, j, p, q, 'wall', textures('wall', zt or zside, 'wall')[0],
                           textures('wall', zb or zside, 'wall')[1], faces)


def _merge(cs, facemap):
    """Greedy rectangles over cells; edge faces of a rectangle must agree per direction."""
    out = []
    cs = set(cs)

    def ok(i0, j0, i1, j1):
        edges = (((i1, j) for j in range(j0, j1 + 1)), ((i0, j) for j in range(j0, j1 + 1)),
                 ((i, j1) for i in range(i0, i1 + 1)), ((i, j0) for i in range(i0, i1 + 1)))
        for d, cells_ in enumerate(edges):
            vals = {facemap[c][d] for c in cells_} - {None}
            if len(vals) > 1:
                return False
        return True

    while cs:
        i0, j0 = min(cs)
        i1 = i0
        while (i1 + 1, j0) in cs and ok(i0, j0, i1 + 1, j0):
            i1 += 1
        j1 = j0
        while all((i, j1 + 1) in cs for i in range(i0, i1 + 1)) and ok(i0, j0, i1, j1 + 1):
            j1 += 1
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                cs.discard((i, j))
        faces = []
        for d, cells_ in enumerate(((i1, j0), (i0, j0), (i0, j1), (i0, j0))):
            pass
        edge = [[facemap[(i1, j)][0] for j in range(j0, j1 + 1)], [facemap[(i0, j)][1] for j in range(j0, j1 + 1)],
                [facemap[(i, j1)][2] for i in range(i0, i1 + 1)], [facemap[(i, j0)][3] for i in range(i0, i1 + 1)]]
        faces = [next((v for v in e if v), None) for e in edge]
        out.append((i0, j0, i1, j1, faces))
    return out


def brushes():
    groups, facemaps = {}, {}
    floor_at = [[{f for f, c in _air(cols[i][j]) if c - f >= 56} for j in range(NY)] for i in range(NX)]
    for i, j, a, b, kind, top, bot, faces in detail_pieces():
        if kind == 'crate':
            parts = [(a, b, True)]            # b4: iron blocks share the floor light minimum (were near-black)
        elif b in floor_at[i][j] and b - a > 8:
            # b8: walkable top surface -> 8-unit skin brush in a func_group with its own minlight
            parts = [(a, b - 8, False), (b - 8, b, True)]
        else:
            parts = [(a, b, b in floor_at[i][j])]
        for a2, b2, skin in parts:
            key = (a2, b2, kind, top, bot, skin)
            groups.setdefault(key, set()).add((i, j))
            facemaps.setdefault(key, {})[(i, j)] = tuple(faces)
    out = []
    for key, cs in groups.items():
        a, b, kind, top, bot, skin = key
        for i0, j0, i1, j1, faces in _merge(cs, facemaps[key]):
            out.append((XMIN + i0 * C, YMIN + j0 * C, a, XMIN + (i1 + 1) * C, YMIN + (j1 + 1) * C, b,
                        (kind, top, bot, faces), skin))
    return out


def _cs(face):
    """b16: light strips shifted half a clamp period - clamps fall on 32-unit step corners."""
    return 16 if face[0].endswith('_cond') else 0


def brush_text(x1, y1, z1, x2, y2, z2, m):
    kind, top, bot, faces = m
    dflt = next((f for f in faces if f), (bot, z2))
    px, nx_, py, ny_ = [f or dflt for f in faces]      # +x, -x, +y, -y
    fx, fy = (-x1, y2) if kind == 'lamp' else (0, 0)   # light panels centred on the fixture
    if top == 'bs_mid_flr':           # b8: half-tile shift - a diamond edge, not a stud, meets each base entrance
        fx = 64
        if z2 == 192:                 # b11: mid ledges - one whole row of tiles between kickplate and top step
            fy = 64
    if kind in ('stand_b', 'stand_r', 'stand_q'):  # flag stand top: the 128 plate fits the stand exactly
        fx, fy = -x1, y2
    if kind == 'pillar':              # b7/b18: each face starts on the whole column's corner, even when the
        pr = next((p for p in pillar_rects if p[0] <= x1 < p[2] and p[1] <= y1 < p[3]), (x1, y1, 0, 0, z2))
        sx_y, sx_x = -pr[1], -pr[0]   # column is built from several brushes - stones wrap cleanly
        tv = pr[4] % 128              # b19: and vertically from the column's top, so drums and bands line up
        nx_, px, ny_, py = (nx_[0], tv), (px[0], tv), (ny_[0], tv), (py[0], tv)
    elif kind in ('crate', 'machine'):  # b6: boxes textured from their own corner - every side alike
        fx, fy = -x1, y2
        nx_, px = (nx_[0], z2), (px[0], z2)
        ny_, py = (ny_[0], z2), (py[0], z2)
        sx_y, sx_x = -y1, -x1
    elif kind != 'pillar':
        sx_y = sx_x = 0


    def f(p, q, r, t, xo, yo):
        return '( %d %d %d ) ( %d %d %d ) ( %d %d %d ) %s %d %d 0 1 1' % (*p, *q, *r, t, xo, yo)
    return '\n'.join([
        '{',
        f((x1, y1, z1), (x1, y1 + 1, z1), (x1, y1, z1 + 1), nx_[0], sx_y + _cs(nx_), nx_[1]),
        f((x1, y1, z1), (x1, y1, z1 + 1), (x1 + 1, y1, z1), ny_[0], sx_x + _cs(ny_), ny_[1]),
        f((x1, y1, z1), (x1 + 1, y1, z1), (x1, y1 + 1, z1), bot, fx, fy),
        f((x2, y2, z2), (x2, y2 + 1, z2), (x2 + 1, y2, z2), top, fx, fy),
        f((x2, y2, z2), (x2 + 1, y2, z2), (x2, y2, z2 + 1), py[0], sx_x + _cs(py), py[1]),
        f((x2, y2, z2), (x2, y2, z2 + 1), (x2, y2 + 1, z2), px[0], sx_y + _cs(px), px[1]),
        '}'])


def ent(kv, body=''):
    s = '{\n' + ''.join('"%s" "%s"\n' % (k, v) for k, v in kv.items())
    return s + body + ('\n' if body else '') + '}\n'


USE_TORCHES = True
FLOOR_MINLIGHT = 30       # b8: no walkable floor goes black (players are lit from the floor)
TORCH_LIGHT = 165
TORCH_SPACING = 256


def torches():
    """b5: wall lamps on straight runs of room wall only (never pillars, crates, ledges or
    machinery), spaced evenly and centred on each run, >= 32 clear of corners and doorways,
    at one height per run chosen to miss the light strip, the cornice, the kickplate and pipes."""
    air = [[_air(cols[i][j]) for j in range(NY)] for i in range(NX)]
    zmap = resolve_themes()

    def wall_ok(p, q, z0, z1):           # structural room wall (mat None) solid over [z0, z1]
        if not (0 <= p < NX and 0 <= q < NY):
            return False
        segs = [(a, b, m) for a, b, m in cols[p][q] if a < z1 and b > z0]
        if not segs or any(m is not None for a, b, m in segs):
            return False
        return not any(a < z1 and b > z0 for a, b in air[p][q])

    def blocked(th, f, c, z, box):
        lo, hi = z - 16, z + 16
        if lo < f + 40 or hi > c - 24:
            return True
        sz = strip_z(th, f) if th in STRIPE_Z else 10 ** 6
        if lo < sz + 16 + 8 and hi > sz - 8:
            return True
        tz = TRIM_Z.get(th)
        if tz is not None and lo < tz + 24 and hi > tz - 8:
            return True
        x0, y0, x1, y1 = box
        return any(px0 - 8 < x1 and px1 + 8 > x0 and py0 - 8 < y1 and py1 + 8 > y0 and pz0 - 8 < hi and pz1 + 8 > lo
                   for px0, py0, pz0, px1, py1, pz1 in pipes)

    # 1. wall cells: (direction, floor, plane, line coordinate) -> list of along-wall cell indices
    runs = {}
    for i in range(NX):
        for j in range(NY):
            for f, c in air[i][j]:
                if f <= BOT or c - f < 112:
                    continue
                if door_only(i, j, f):
                    continue
                th = room_theme(i, j, f, zmap)
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if not wall_ok(i + di, j + dj, f, min(c, f + 160)):
                        continue
                    if di:
                        key = (di, dj, f, c, th, i)
                        runs.setdefault(key, []).append(j)
                    else:
                        key = (di, dj, f, c, th, j)
                        runs.setdefault(key, []).append(i)
    out = []
    for (di, dj, f, c, th, line), idx in runs.items():
        idx.sort()
        groups, cur = [], [idx[0]]
        for k in idx[1:]:
            if k == cur[-1] + 1:
                cur.append(k)
            else:
                groups.append(cur); cur = [k]
        groups.append(cur)
        for g in groups:
            L = len(g) * C
            n = int(L // TORCH_SPACING) + (1 if L % TORCH_SPACING >= 96 else 0)
            n = min(n, int(L // 96))
            if n < 1 or L < 96:
                continue
            s0 = (XMIN if dj else YMIN) + g[0] * C
            centers = [s0 + L * (m + 0.5) / n for m in range(n)]
            if di:
                wx = XMIN + (line + 1) * C if di > 0 else XMIN + line * C
                boxes = [(wx - 4, cc - 16, wx, cc + 16) if di > 0 else (wx, cc - 16, wx + 4, cc + 16) for cc in centers]
            else:
                wy = YMIN + (line + 1) * C if dj > 0 else YMIN + line * C
                boxes = [(cc - 16, wy - 4, cc + 16, wy) if dj > 0 else (cc - 16, wy, cc + 16, wy + 4) for cc in centers]
            if any(any(d[0] - 64 <= (bx[0] + bx[2]) / 2 <= d[3] + 64 and d[1] - 64 <= (bx[1] + bx[3]) / 2 <= d[4] + 64
                       for d in decals) for bx in boxes):
                continue
            zc = next((z for z in (f + 96, f + 144, f + 160, f + 128, f + 112, f + 80, f + 64, f + 56, f + 176)
                       if not any(blocked(th, f, c, z, bx) for bx in boxes)
                       and all(wall_ok(i_, j_, z - 16, z + 16) for i_, j_ in
                               [((line + di, k) if di else (k, line + dj)) for k in g])), None)
            if zc is None:
                continue
            for bx in boxes:
                out.append((bx, zc, di, dj))
    return out


def write_map(path):
    bs = brushes()
    world = {
        'classname': 'worldspawn',
        'message': 'Bastion (CTF, beta 19)',
        'wad': 'ctf_bastion_b19.wad',
        'worldtype': '2',
        'sounds': '0',
        '_bounce': '0',
        '_dirt': '1',
        '_dirtscale': '2.0',
        '_sunlight': '160',
        '_sun_mangle': '35 -62 0',
        '_sunlight2': '40',
    }
    parts = [ent(world, '\n'.join(brush_text(*b[:7]) for b in bs if not b[7]))]
    # walkable floor skins: merged into the world by qbsp, lit with a floor-only minimum
    parts.append(ent({'classname': 'func_group', '_minlight': FLOOR_MINLIGHT},
                     '\n'.join(brush_text(*b[:7]) for b in bs if b[7])))
    # liquids (lava): plain world brushes; qbsp gives '*lava' textures lava contents
    def box(x1, y1, z1, x2, y2, z2, t):
        f = lambda p, q, r: '( %d %d %d ) ( %d %d %d ) ( %d %d %d ) %s 0 0 0 1 1' % (*p, *q, *r, t)
        return '\n'.join(['{', f((x1, y1, z1), (x1, y1 + 1, z1), (x1, y1, z1 + 1)),
                           f((x1, y1, z1), (x1, y1, z1 + 1), (x1 + 1, y1, z1)),
                           f((x1, y1, z1), (x1 + 1, y1, z1), (x1, y1 + 1, z1)),
                           f((x2, y2, z2), (x2, y2 + 1, z2), (x2 + 1, y2, z2)),
                           f((x2, y2, z2), (x2 + 1, y2, z2), (x2, y2, z2 + 1)),
                           f((x2, y2, z2), (x2, y2, z2 + 1), (x2, y2 + 1, z2)), '}'])
    lq = [box(r[0], r[1], z0, r[2], r[3], z1, t) for r, z0, z1, t in liquids]
    parts[0] = parts[0][:-2] + ('\n' + '\n'.join(lq) if lq else '') + '\n}\n'
    # emblem panels: non-solid detail brushes, emblem on both x faces, copper trim elsewhere
    def panel(x1, y1, z1, x2, y2, z2, t):
        """Emblem (256 texture at scale 0.5 = 128 units) on both x faces, oriented the right way
        round from whichever side you look at it; copper trim on the edges."""
        def f(p, q, r, tx, xo, yo, sx=1.0, sy=1.0):
            return '( %d %d %d ) ( %d %d %d ) ( %d %d %d ) %s %g %g 0 %g %g' % (*p, *q, *r, tx, xo, yo, sx, sy)
        sc = (y2 - y1) / 256.0
        return '\n'.join(['{',
            f((x1, y1, z1), (x1, y1 + 1, z1), (x1, y1, z1 + 1), t, y2 / sc, z2 / sc, -sc, sc),   # -x face
            f((x1, y1, z1), (x1, y1, z1 + 1), (x1 + 1, y1, z1), 'bs_trim', 0, z2),
            f((x1, y1, z1), (x1 + 1, y1, z1), (x1, y1 + 1, z1), 'bs_trim', 0, 0),
            f((x2, y2, z2), (x2, y2 + 1, z2), (x2 + 1, y2, z2), 'bs_trim', 0, 0),
            f((x2, y2, z2), (x2 + 1, y2, z2), (x2, y2, z2 + 1), 'bs_trim', 0, z2),
            f((x2, y2, z2), (x2, y2, z2 + 1), (x2, y2 + 1, z2), t, -y1 / sc, z2 / sc, sc, sc),   # +x face
            '}'])
    if decals:
        parts.append(ent({'classname': 'func_detail_illusionary'}, '\n'.join(panel(*d) for d in decals)))
    for (r, z, dx, dy, dz, speed, angles) in pushes:
        parts.append(ent({'classname': 'trigger_push', 'angles': angles, 'speed': speed},
                         box(r[0], r[1], z, r[2], r[3], z + 48, 'bs_trim')))
    for n, (r, z, dx, dy, dz, ang) in enumerate(teleports):
        parts.append(ent({'classname': 'trigger_teleport', 'target': f'tele{n}'},
                         box(r[0], r[1], z, r[2], r[3], z + 72, 'bs_trim')))
        parts.append(ent({'classname': 'info_teleport_destination', 'targetname': f'tele{n}',
                          'origin': f'{dx} {dy} {dz + 32}', 'angle': ang}))
    for L in lights:
        x, y, z, v = L[:4]
        parts.append(ent({'classname': 'light', 'origin': f'{x} {y} {z}', 'light': v,
                          'wait': str(L[4]) if len(L) > 4 else '0.75'}))
    # b5: wall lamps (non-solid fixture + light) instead of flame torches
    wl = []
    for ((x0, y0, x1, y1), z, di, dj) in (torches() if USE_TORCHES else []):
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        z0, z1 = z - 16, z + 16
        f = lambda p, q, r, xo, yo: '( %d %d %d ) ( %d %d %d ) ( %d %d %d ) bs_wlamp %d %d 0 1 1' % (*p, *q, *r, xo, yo)
        wl.append('\n'.join(['{', f((x0, y0, z0), (x0, y0 + 1, z0), (x0, y0, z0 + 1), -y0, z1),
                              f((x0, y0, z0), (x0, y0, z0 + 1), (x0 + 1, y0, z0), -x0, z1),
                              f((x0, y0, z0), (x0 + 1, y0, z0), (x0, y0 + 1, z0), 0, 0),
                              f((x1, y1, z1), (x1, y1 + 1, z1), (x1 + 1, y1, z1), 0, 0),
                              f((x1, y1, z1), (x1 + 1, y1, z1), (x1, y1, z1 + 1), -x0, z1),
                              f((x1, y1, z1), (x1, y1, z1 + 1), (x1, y1 + 1, z1), -y0, z1), '}']))
        lx, ly = (x0 + x1) / 2 - di * 20, (y0 + y1) / 2 - dj * 20
        parts.append(ent({'classname': 'light', 'origin': f'{lx:g} {ly:g} {z}', 'light': TORCH_LIGHT,
                          'wait': '1.2', '_color': '225 235 255'}))
    if wl:
        parts.append(ent({'classname': 'func_detail_illusionary'}, '\n'.join(wl)))
    for x, y, z, ang, team in team_spawns:      # CTF: match-start spawns in each base (+ KTX based-spawn mode 2)
        for cls in (f'info_player_team{team}', f'info_player_team{team}_deathmatch'):
            parts.append(ent({'classname': cls, 'origin': f'{x} {y} {z + 24}', 'angle': ang}))
    for n, (x, y, z, ang, lab) in enumerate(spawns):
        parts.append(ent({'classname': 'info_player_deathmatch', 'origin': f'{x} {y} {z + 24}', 'angle': ang}))
    for cls, x, y, z, flags, lab in items:
        if cls in CORNER:
            ox, oy, oz = x - 16, y - 16, z + 8
        elif cls.startswith('item_artifact'):
            ox, oy, oz = x, y, z + 32
        else:
            ox, oy, oz = x, y, z + 8
        kv = {'classname': cls, 'origin': f'{ox} {oy} {oz}'}
        if flags:
            kv['spawnflags'] = flags
        parts.append(ent(kv))
    x, y, z, ang, _ = spawns[0]
    parts.append(ent({'classname': 'info_player_start', 'origin': f'{x} {y} {z + 24}', 'angle': ang}))
    parts.append(ent({'classname': 'info_intermission', 'origin': '-380 -380 420', 'mangle': '25 45 0'}))
    open(path, 'w').write(''.join(parts))
    return len(bs)


def dump(path):
    json.dump({'C': C, 'XMIN': XMIN, 'YMIN': YMIN, 'NX': NX, 'NY': NY, 'BOT': BOT, 'TOP': TOP,
               'cols': [[[[a, b, m] for a, b, m in cols[i][j]] for j in range(NY)] for i in range(NX)],
               'theme': theme, 'spawns': spawns, 'team_spawns': team_spawns, 'perches': perches, 'items': items, 'lights': lights, 'labels': labels,
               'teleports': teleports, 'liquids': liquids,
               'pushes': [(r, z, dx, dy, dz, 90) for r, z, dx, dy, dz, s, a in pushes]}, open(path, 'w'))


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    n = write_map(f'{out}/{NAME}.map')
    dump(f'{out}/{NAME}.json')
    print(f'{n} brushes, {len(lights)} lights, {len(spawns)} spawns, {len(items)} items')
