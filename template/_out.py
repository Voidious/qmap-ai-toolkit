# =========================================================================
# OUTPUT - .map and .json writer (template, qmap-toolkit v3)
#   Per-face texturing: every wall face is textured from the AIR it faces, cut into bands
#   (kickplate / wall / light strip / wall / cornice) at that room's heights. Detail (lamps,
#   panels) is func_detail_illusionary: never collision. Walkable tops get a minlight skin.
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
    return best or dbest or zmap[i][j] or 'room'


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
PERIOD = {'wall': 128, 'base': 32, 'strp': 16, 'trim': 16, 'glass': 96, None: 128, 'band': TRIM_H}
WALL_PERIOD = {}    # zone -> vertical period of its wall texture when not 128 (e.g. 80-tall panels)


EXTRA = {'world': [], 'skin': [], 'detail': []}    # v3: whole brushes written outside the grid


def band_role(n, mid):
    """Band of a wall face at height mid looking into air n (the main chain in detail_pieces, minus
    its glass / sill / step-edge special cases): (role, anchor z)."""
    th, f, c, sz = n['th'], n['f'], n['c'], n['sz']
    if mid >= c - 16 and not n['nocap']:
        return 'trim', c
    if n['foot'] is not None and mid < n['foot']:
        return 'base', n['foot']
    if sz <= mid < sz + 16:
        return 'strp', sz + 16
    tz = n['tz']
    if tz is not None and tz <= mid < tz + TRIM_H and tz + TRIM_H < c - 16:
        return 'band', tz + TRIM_H
    nsz = STRIPE_Z.get(th, sz)
    anc = nsz + 16 if mid > nsz + 16 else ZONE_FLOOR.get(th, 0) + 32
    return ('wall_lo' if mid < SPLIT_Z.get(th, -10 ** 6) else 'wall'), anc


def _plane_pts(n, p):
    """Three points on the plane (normal n, through p), in the winding the .map format wants."""
    L = math.sqrt(sum(v * v for v in n))
    n = [v / L for v in n]
    a = (n[1], -n[0], 0) if abs(n[2]) < 0.9 else (0, n[2], -n[1])
    la = math.sqrt(sum(v * v for v in a))
    a = [v / la * 64 for v in a]
    b = (a[1] * n[2] - a[2] * n[1], a[2] * n[0] - a[0] * n[2], a[0] * n[1] - a[1] * n[0])
    return [p, tuple(p[k] + a[k] for k in range(3)), tuple(p[k] + b[k] for k in range(3))]


def sface(n, p, tex, xo, yo):
    """A face in the standard format (texture projected on the nearest axis plane)."""
    P = _plane_pts(n, p)
    return ' '.join('( %.3f %.3f %.3f )' % q for q in P) + f' {tex} {xo:g} {yo:g} 0 1 1'


def vface(n, p, tex, U, uoff, V, voff, su=1, sv=1):
    """A face in Valve 220 format: texture axes U (across) and V (down) set explicitly, so a texture
    runs along an angled wall or a slope without stretching. qbsp reads the format per face."""
    P = _plane_pts(n, p)
    return (' '.join('( %.3f %.3f %.3f )' % q for q in P) +
            f' {tex} [ {U[0]:.6f} {U[1]:.6f} {U[2]:.6f} {uoff:.3f} ] [ {V[0]:.6f} {V[1]:.6f} {V[2]:.6f} {voff:.3f} ] 0 {su:.6f} {sv:.6f}')


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
        cx_, cy_ = XMIN + p * C + C / 2, YMIN + q * C + C / 2
        in_ramp = any(r[0] <= cx_ <= r[2] and r[1] <= cy_ <= r[3] and rz0 <= f <= rz1
                      for r, _, _, rz0, rz1, rbands in RAMPS if rbands)
        if fm == 'ramp' or in_ramp:
            return dict(f=f, c=c, th=th, sz=10 ** 6, nocap=(p, q, c) in NOCAP, foot=None,
                        door=door_only(p, q, f), tz=TRIM_Z.get(th), ramp=True)
        if fm == 'bridge':
            foot = None
        elif fm == 'stair' and th not in STEP_KICK:
            rf = room_floor(p, q, f)
            foot = rf + 32 if rf + 32 > f else None     # level with the room floor; steps climb in front
        else:
            foot = f + 32
            if th not in STEP_KICK and room_floor(p, q, f) < f:
                foot = None          # no kickplate on raised platforms (dais, landing, mezzanine, lofts)
            sunk = [z0 for z0, z1, th2, dr in rooms.get((p, q), []) if not dr and f < z0 <= f + 32]
            if foot is not None and sunk:
                foot = max(sunk) + 32  # sunken channel: the kickplate stays level with the room's
        return dict(f=f, c=c, th=th, sz=strip_z(th, f, p, q), nocap=(cm == 'bridge' or (p, q, c) in NOCAP), foot=foot,
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
        if n['tz'] is not None and n['f'] <= n['tz'] and n['tz'] + TRIM_H < n['c'] - 16:
            cs |= {n['tz'], n['tz'] + TRIM_H}
        gz = GLASS_Z.get(n['th'])
        if gz is not None and n['f'] + 32 <= gz and gz + 96 <= n['c'] - 16:
            cs |= {gz, gz + 96}
        return cs

    EXTRA['world'], EXTRA['skin'], EXTRA['detail'] = [], [], []
    for i in range(NX):
        for j in range(NY):
            for a, b, m in cols[i][j]:
                if m in ('ramp', 'diag'):
                    continue                              # v3 stand-ins: the ramp / prism brush is written instead
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
                zside = (act or allair)[0]['th'] if allair else (zmap[i][j] or 'room')
                if m is not None:
                    faces = []
                    for lst in nbs:
                        if not lst:
                            faces.append(None)
                            continue
                        n = max(lst, key=lambda n: min(n['c'], b) - max(n['f'], a))
                        t = textures(m, n['th'], None)[2]
                        yo = ZONE_FLOOR.get(n['th'], 0) if m == 'ledge' else b
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
                if ztop is not None and a < b - 16:
                    cuts.add(b - 16)                      # sill band under a raised opening
                if zbot is not None and a < b - 16:
                    cuts.add(a + 16)                      # architrave lintel at bottom of an overhang
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
                                faces.append((textures('wall', th, 'wall')[2],
                                              (ZONE_FLOOR.get(th, 0) + 32) % WALL_PERIOD.get(zone(th), 128)))
                                continue
                        th = n['th']
                        f, c, sz = n['f'], n['c'], n['sz']
                        gz = GLASS_Z.get(th)
                        di, dj = DIRS[d]
                        if ztop is not None and ztop == n['th'] and q == b and f < b and b - max(f, a) <= 16:
                            faces.append((textures('stair', th, None)[2], b % 16))   # a raised floor's edge only a step tall reads as a step
                            continue
                        if mid >= c - 16 and not n['nocap']:
                            role, anc = 'trim', c
                        elif ztop is not None and b - 16 <= mid < b and q == b and f < b and (f < b - 16 or ztop != n['th']):
                            role, anc = 'trim', b          # sill under a raised opening
                        elif n['foot'] is not None and mid < n['foot']:
                            role, anc = 'base', n['foot']
                        elif sz <= mid < sz + 16:
                            role, anc = 'strp', sz + 16      # (before band/architrave: never clobber a light strip)
                        elif zbot is not None and a <= mid < a + 16 and p == a and c > a and (c > a + 16 or zbot != n['th']):
                            role, anc = 'trim', a + 16       # architrave lintel framing overhang/doorway bottoms
                        elif n['tz'] is not None and n['tz'] <= mid < n['tz'] + TRIM_H and n['tz'] + TRIM_H < c - 16:
                            role, anc = 'band', n['tz'] + TRIM_H     # string course / seam (TRIM_H tall)
                        elif (gz is not None and f + 32 <= gz and gz + 96 <= c - 16 and gz <= mid < gz + 96
                              and all(solid_at(i + k * dj, j + k * di, mid) and not solid_at(i + k * dj + di, j + k * di + dj, mid)
                                      for k in (-2, -1, 1, 2))):
                            role, anc = 'glass', gz + 96   # only on straight runs wide enough for a window
                        else:
                            # stone sits on the band below it: the kickplate top, or the strip top above the strip
                            # anchor to the room's NOMINAL strip (and compare mid against it too) so walls beside
                            # stairs or above/beside ramps (where sz=10**6) stay aligned with the rest of the room
                            nsz = STRIPE_Z.get(th, sz)
                            role, anc = 'wall', (nsz + 16 if mid > nsz + 16 else ZONE_FLOOR.get(th, 0) + 32)
                            if mid < SPLIT_Z.get(th, -10 ** 6):
                                role = 'wall_lo'           # stratified rooms: a different stone below the split
                        per = WALL_PERIOD.get(zone(th), 128) if role in ('wall', 'wall_lo') else PERIOD[role]
                        faces.append((textures('wall', th, role)[2], anc % per))
                    zt = ztop if q == b and ztop else None
                    zb = zbot if p == a and zbot else None
                    yield (i, j, p, q, 'wall', textures('wall', zt or zside, 'wall')[0],
                           textures('wall', zb or zside, 'wall')[1], faces)

    # ---- v3: ramps, their sloped bands, prisms (written as whole brushes, outside the grid) ----
    def air_info(x, y, zlo, zhi):
        p, q = int((x - XMIN) // C), int((y - YMIN) // C)
        if not (0 <= p < NX and 0 <= q < NY):
            return None
        best = None
        for f, c in air[p][q]:
            ov = min(c, zhi) - max(f, zlo)
            if ov > 0 and (best is None or ov > best[0]):
                best = (ov, f, c)
        return info(p, q, best[1], best[2]) if best else None

    for rr, axis, sg, z0, z1, bands in RAMPS:
        x0, y0, x1, y1 = rr
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        nt = air_info(mx, my, z0, z1 + 64) or {'th': zmap[int((mx - XMIN) // C)][int((my - YMIN) // C)] or 'room'}
        th = nt['th']
        flr = textures('wall', th, 'wall')[0]
        side = textures('ledge', th, None)[2]
        rise = z1 - z0
        run = (x1 - x0) if axis == 'x' else (y1 - y0)
        h = (1, 0, 0) if axis == 'x' else (0, 1, 0)
        lo = ((x0, y0, z0) if sg > 0 else (x1, y0, z0)) if axis == 'x' else ((x0, y0, z0) if sg > 0 else (x0, y1, z0))
        top_n = (-sg * rise * h[0], -sg * rise * h[1], run)
        hi_n = (sg * h[0], sg * h[1], 0)
        hi_p = ((x1 if sg > 0 else x0), y0, z0) if axis == 'x' else (x0, (y1 if sg > 0 else y0), z0)
        lat = [((0, -1, 0), (x0, y0, z0)), ((0, 1, 0), (x0, y1, z0))] if axis == 'x' else \
              [((-1, 0, 0), (x0, y0, z0)), ((1, 0, 0), (x1, y0, z0))]
        # Probe adjacent air outside each lateral face: if a ramp's side is exposed to another room,
        # texture that face with the adjacent room's wall, carry its light strip across backed cells,
        # and emit the ramp in worldspawn so the wall lightmap matches the surrounding room.
        lat_faces = []
        exposed_to_other_room = False
        for n_, p_ in lat:
            ox_, oy_ = n_[0] * 8, n_[1] * 8
            n_cells = int(((x1 - x0) if axis == 'x' else (y1 - y0)) // C)
            adj_samples = []
            for k_ in range(n_cells):
                sx = (x0 + C / 2 + k_ * C) if axis == 'x' else (x0 if n_[0] < 0 else x1)
                sy = (y0 if n_[1] < 0 else y1) if axis == 'x' else (y0 + C / 2 + k_ * C)
                ai_ = air_info(sx + ox_, sy + oy_, z0, z1)
                if ai_ and ai_['th'] != th and not ai_['door']:
                    adj_samples.append((k_, sx, sy, ai_))
            if adj_samples:
                exposed_to_other_room = True
                adj_th = adj_samples[0][3]['th']
                l_tex = textures('wall', adj_th, 'wall')[2]
                l_yo = (ZONE_FLOOR.get(adj_th, 0) + 32) % WALL_PERIOD.get(zone(adj_th), 128)
                lat_faces.append(sface(n_, p_, l_tex, 0, l_yo))
                sz_adj = adj_samples[0][3]['sz']
                if sz_adj < 10 ** 6 and z0 <= sz_adj and sz_adj + 16 <= z1:
                    st_tex = textures('wall', adj_th, 'strp')[2]
                    backed = []
                    for k_, sx, sy, ai_ in adj_samples:
                        frac = ((sx - x0) / run if sg > 0 else (x1 - sx) / run) if axis == 'x' else \
                               ((sy - y0) / run if sg > 0 else (y1 - sy) / run)
                        if z0 + rise * frac >= sz_adj + 16 - 0.5:
                            backed.append(k_)
                    if backed:
                        k_lo, k_hi = min(backed), max(backed) + 1
                        if axis == 'x':
                            bx0, bx1 = x0 + k_lo * C, x0 + k_hi * C
                            by0, by1 = (y0 - 2, y0) if n_[1] < 0 else (y1, y1 + 2)
                        else:
                            bx0, bx1 = (x0 - 2, x0) if n_[0] < 0 else (x1, x1 + 2)
                            by0, by1 = y0 + k_lo * C, y0 + k_hi * C
                        sfs = [
                            sface((-1, 0, 0), (bx0, by0, sz_adj), st_tex if n_[0] < 0 else EDGE_TEX, 0, (sz_adj + 16) % 16),
                            sface((1, 0, 0), (bx1, by0, sz_adj), st_tex if n_[0] > 0 else EDGE_TEX, 0, (sz_adj + 16) % 16),
                            sface((0, -1, 0), (bx0, by0, sz_adj), st_tex if n_[1] < 0 else EDGE_TEX, 0, (sz_adj + 16) % 16),
                            sface((0, 1, 0), (bx0, by1, sz_adj), st_tex if n_[1] > 0 else EDGE_TEX, 0, (sz_adj + 16) % 16),
                            sface((0, 0, -1), (bx0, by0, sz_adj), EDGE_TEX, 0, 0),
                            sface((0, 0, 1), (bx0, by0, sz_adj + 16), EDGE_TEX, 0, 0),
                        ]
                        EXTRA['detail'].append('{\n' + '\n'.join(sfs) + '\n}')
            else:
                lat_faces.append(sface(n_, p_, side, 0, z1 % 128))
        fs = [sface((0, 0, -1), (x0, y0, z0), flr, 0, 0), sface(top_n, lo, flr, 0, 0),
              sface(hi_n, hi_p, side, 0, z1 % 128)] + lat_faces
        EXTRA['world' if exposed_to_other_room else 'skin'].append('{\n' + '\n'.join(fs) + '\n}')
        if not bands:
            continue
        # the rooms at the foot and at the head: the sloped strip runs from one's strip to the other's
        if axis == 'x':
            hd = (hi_p[0] + sg * 8, (y0 + y1) / 2)
            lo_c = (lo[0] - sg * 8, (y0 + y1) / 2)
        else:
            hd = ((x0 + x1) / 2, hi_p[1] + sg * 8)
            lo_c = ((x0 + x1) / 2, lo[1] - sg * 8)
        n0 = air_info(lo_c[0], lo_c[1], z0, z0 + 64)
        n1 = air_info(hd[0], hd[1], z1, z1 + 64)
        if not n0:
            continue
        bands_ = [(z0, z1, 32, 'base')]                      # kickplate: 32 above the slope, all the way
        if n0['sz'] < 10 ** 6:
            s0 = n0['sz']
            s1 = n1['sz'] if n1 and n1['sz'] < 10 ** 6 else z1 + (s0 - z0)
            bands_.append((s0, s1, 16, 'strp'))
        top_band = max(b_[1] + b_[2] for b_ in bands_)
        for (wn, wp) in lat:                                 # a wall along this side?
            ox, oy = wn[0] * 8, wn[1] * 8
            samples = [(x0 + C / 2 + k * C, (y0 if wn[1] < 0 else y1)) for k in range(int((x1 - x0) // C))] if axis == 'x' else \
                      [((x0 if wn[0] < 0 else x1), y0 + C / 2 + k * C) for k in range(int((y1 - y0) // C))]
            if not all(solid_at(int((sx + ox - XMIN) // C), int((sy + oy - YMIN) // C), zz)
                       for sx, sy in samples for zz in (z0 + 8, top_band - 8)):
                continue
            inward = (-wn[0], -wn[1], 0)
            fr = (wp[0] + inward[0] * 1, wp[1] + inward[1] * 1, 0)
            ends = [((-h[0], -h[1], 0), (x0, y0, 0)), ((h[0], h[1], 0), (x1, y1, 0))]
            for alo, ahi, hgt, role in bands_:
                R = ahi - alo
                Lb = math.hypot(run, R)
                ct, st = run / Lb, R / Lb
                U = (sg * h[0] * ct, sg * h[1] * ct, st)
                V = (sg * h[0] * st, sg * h[1] * st, -ct)
                tn = (-sg * R * h[0], -sg * R * h[1], run)
                tex = textures('wall', n0['th'], role)[2]
                pt = (lo[0], lo[1], alo + hgt)                # top edge at the foot: texture row 0
                voff = -(pt[0] * V[0] + pt[1] * V[1] + pt[2] * V[2]) / ct
                fs = [sface(wn, wp, EDGE_TEX, 0, 0),
                      vface(inward, fr, tex, U, 0, V, voff % PERIOD[role], 1, ct),
                      sface((-tn[0], -tn[1], -tn[2]), (lo[0], lo[1], alo), EDGE_TEX, 0, 0),
                      sface(tn, (lo[0], lo[1], alo + hgt), EDGE_TEX, 0, 0)] + \
                     [sface(n_, (p_[0], p_[1], 0), EDGE_TEX, 0, 0) for n_, p_ in ends]
                EXTRA['detail'].append('{\n' + '\n'.join(fs) + '\n}')

    for P, z0, z1, kind in PRISMS:
        k_ = len(P)
        faces_ = []
        for k in range(k_):
            (ax, ay), (bx, by) = P[k], P[(k + 1) % k_]
            L = math.hypot(bx - ax, by - ay)
            n_ = ((by - ay) / L, -(bx - ax) / L, 0)
            mx_, my_ = (ax + bx) / 2, (ay + by) / 2
            # Step past the prism's 16-unit 'diag' stand-in cells (diagonal = 22.6u) so chamfered
            # corners pick up the room's air, kickplate, light strip, cornice, and SPLIT_Z/TRIM_Z.
            ni = None
            for _d in (24, 32, 40, 12):
                ni = air_info(mx_ + n_[0] * _d, my_ + n_[1] * _d, z0, z1)
                if ni is not None:
                    break
            faces_.append(((ax, ay), n_, ((bx - ax) / L, (by - ay) / L, 0), ni))
        cuts = {z0, z1}
        for _, _, _, ni in faces_:
            if ni and kind is None:
                cuts |= {z for z in band_cuts(ni) if z0 < z < z1}
        cuts = sorted(cuts)
        cx, cy = sum(p_[0] for p_ in P) / k_, sum(p_[1] for p_ in P) / k_
        tht = (air_info(cx, cy, z1, z1 + 64) or {'th': zmap[int((cx - XMIN) // C)][int((cy - YMIN) // C)] or 'room'})['th']
        thb = (air_info(cx, cy, z0 - 64, z0) or {'th': tht})['th']
        for za, zb in zip(cuts, cuts[1:]):
            mid = (za + zb) / 2
            fs = [sface((0, 0, -1), (P[0][0], P[0][1], za), textures('wall', thb, 'wall')[1], 0, 0),
                  sface((0, 0, 1), (P[0][0], P[0][1], zb), textures('wall', tht, 'wall')[0], 0, 0)]
            for (ax, ay), n_, U, ni in faces_:
                if kind is not None:
                    tex, voff = textures(kind, (ni or {'th': tht})['th'], None)[2], z1 % 128
                elif ni is None or not (ni['f'] <= mid < ni['c']):
                    th2 = (ni or {'th': tht})['th']
                    tex, voff = textures('wall', th2, 'wall')[2], (ZONE_FLOOR.get(th2, 0) + 32) % 128
                else:
                    role, anc = band_role(ni, mid)
                    per = WALL_PERIOD.get(zone(ni['th']), 128) if role in ('wall', 'wall_lo') else PERIOD[role]
                    tex, voff = textures('wall', ni['th'], role)[2], anc % per
                fs.append(vface(n_, (ax, ay, za), tex, U, -(ax * U[0] + ay * U[1]) % 64, (0, 0, -1), voff, 1, 1))
            EXTRA['world'].append('{\n' + '\n'.join(fs) + '\n}')


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
        x, y = XMIN + i * C, YMIN + j * C
        for x0, y0, x1, y1, z, t in FLOOR_DECALS:
            if x0 <= x < x1 and y0 <= y < y1 and b == z and kind != 'sky':
                top = t
        for x0, y0, x1, y1, z, t in CEIL_DECALS:
            if x0 <= x < x1 and y0 <= y < y1 and a == z and kind != 'sky':
                bot = t
        if kind in ('crate', 'pillar', 'pbase', 'pcap'):
            parts = [(a, b, True)]            # free-standing blocks share the floor light minimum (no black sides)
        elif b in floor_at[i][j] and b - a > FLOOR_SKIN:
            # walkable top surface -> skin brush in a func_group with its own minlight
            parts = [(a, b - FLOOR_SKIN, False), (b - FLOOR_SKIN, b, True)]
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


STRIP_SHIFT = 0     # shift strip textures along the wall (e.g. 16 to land clamps on 32-unit step corners)


def _cs(face):
    return STRIP_SHIFT if face[0].endswith('_strp') else 0


def brush_text(x1, y1, z1, x2, y2, z2, m):
    kind, top, bot, faces = m
    dflt = next((f for f in faces if f), (bot, z2))
    px, nx_, py, ny_ = [f or dflt for f in faces]      # +x, -x, +y, -y
    fx, fy = (-x1, y2) if kind == 'lamp' else (0, 0)   # light panels centred on the fixture
    if kind.startswith(('stand', 'pad')):  # flag / item stand top: the plate fits the stand exactly
        fx, fy = -x1, y2
    if top in FLOOR_OFFSET:           # a floor pattern centred on its room
        fx, fy = FLOOR_OFFSET[top]
    if kind in ('pillar', 'pbase', 'pcap'):   # columns: every face starts on the whole column's corner
        pr = next((p for p in pillar_rects if p[0] <= x1 < p[2] and p[1] <= y1 < p[3]), (x1, y1, 0, 0, z2))
        sx_y, sx_x = -pr[1], -pr[0]   # (a column is several brushes) - stones wrap cleanly round it;
        tv = z2 % 128                 # each piece hangs from its own top, so drums, bases, capitals line up
        nx_, px, ny_, py = (nx_[0], tv), (px[0], tv), (ny_[0], tv), (py[0], tv)
    elif kind in ('crate', 'machine'):  # b6: boxes textured from their own corner - every side alike
        fx, fy = -x1, y2
        nx_, px = (nx_[0], z2), (px[0], z2)
        ny_, py = (ny_[0], z2), (py[0], z2)
        sx_y, sx_x = -y1, -x1
    elif kind not in ('pillar', 'pbase', 'pcap'):
        sx_y = sx_x = 0
    for d in FLOOR_DECALS + CEIL_DECALS:       # inlays textured from their own rect's corner
        if d[5] in (top, bot) and d[0] <= x1 < d[2] and d[1] <= y1 < d[3] and d[4] in (z1, z2):
            fx, fy = -d[0], d[3]


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
TORCH_LIGHT = 140
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
        x0_, y0_, x1_, y1_ = box                 # b5: the strip where this lamp would hang (ramps included)
        szs = {strip_z(th, f, int((xx - XMIN) // C), int((yy - YMIN) // C))
               for xx in (x0_ + 1, x1_ - 1) for yy in (y0_ + 1, y1_ - 1)}
        if any(lo < sz + 16 + 8 and hi > sz - 8 for sz in szs):
            return True
        tz = TRIM_Z.get(th)
        if tz is not None and lo < tz + TRIM_H + 8 and hi > tz - 8:
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
                out.append((bx, zc, di, dj, th))
    return out


def write_map(path):
    bs = brushes()
    world = {
        'classname': 'worldspawn',
        'message': TITLE,
        'wad': f'{NAME}.wad',
        'worldtype': '2',
        'sounds': '0',
        '_bounce': '0',
        '_dirt': '1',
        '_dirtscale': '2.0',
        **SUN,
    }
    parts = [ent(world, '\n'.join([brush_text(*b[:7]) for b in bs if not b[7]] + EXTRA['world']))]
    # walkable floor skins: merged into the world by qbsp, lit with a floor-only minimum (ramps too)
    parts.append(ent({'classname': 'func_group', '_minlight': FLOOR_MINLIGHT},
                     '\n'.join([brush_text(*b[:7]) for b in bs if b[7]] + EXTRA['skin'])))
    if EXTRA['detail']:
        parts.append(ent({'classname': 'func_detail_illusionary'}, '\n'.join(EXTRA['detail'])))
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
    # picture panels (emblems, banners): non-solid detail brushes, the picture on both broad faces,
    # the right way round from whichever side you look at it, scaled to the panel's width
    def panel(x1, y1, z1, x2, y2, z2, t, px):
        def f(p, q, r, tx, xo, yo, sx=1.0, sy=1.0):
            return '( %d %d %d ) ( %d %d %d ) ( %d %d %d ) %s %g %g 0 %g %g' % (*p, *q, *r, tx, xo, yo, sx, sy)
        E = EDGE_TEX
        if x2 - x1 <= y2 - y1:                     # thin in x: picture on the -x and +x faces
            sc = (y2 - y1) / px
            fx_ = [f((x1, y1, z1), (x1, y1 + 1, z1), (x1, y1, z1 + 1), t, y2 / sc, z2 / sc, -sc, sc),
                   f((x2, y2, z2), (x2, y2, z2 + 1), (x2, y2 + 1, z2), t, -y1 / sc, z2 / sc, sc, sc)]
            fy_ = [f((x1, y1, z1), (x1, y1, z1 + 1), (x1 + 1, y1, z1), E, 0, z2),
                   f((x2, y2, z2), (x2 + 1, y2, z2), (x2, y2, z2 + 1), E, 0, z2)]
        else:                                      # thin in y: picture on the -y and +y faces
            sc = (x2 - x1) / px
            fy_ = [f((x1, y1, z1), (x1, y1, z1 + 1), (x1 + 1, y1, z1), t, -x1 / sc, z2 / sc, sc, sc),
                   f((x2, y2, z2), (x2 + 1, y2, z2), (x2, y2, z2 + 1), t, x2 / sc, z2 / sc, -sc, sc)]
            fx_ = [f((x1, y1, z1), (x1, y1 + 1, z1), (x1, y1, z1 + 1), E, 0, z2),
                   f((x2, y2, z2), (x2, y2, z2 + 1), (x2, y2 + 1, z2), E, 0, z2)]
        return '\n'.join(['{', fx_[0], fy_[0],
                          f((x1, y1, z1), (x1 + 1, y1, z1), (x1, y1 + 1, z1), E, 0, 0),
                          f((x2, y2, z2), (x2, y2 + 1, z2), (x2 + 1, y2, z2), E, 0, 0),
                          fy_[1], fx_[1], '}'])
    if decals:
        parts.append(ent({'classname': 'func_detail_illusionary'}, '\n'.join(panel(*d) for d in decals)))
    for (r, z, dx, dy, dz, speed, angles) in pushes:
        parts.append(ent({'classname': 'trigger_push', 'angles': angles, 'speed': speed},
                         box(r[0], r[1], z, r[2], r[3], z + 48, EDGE_TEX)))
    for n, (r, z, dx, dy, dz, ang) in enumerate(teleports):
        parts.append(ent({'classname': 'trigger_teleport', 'target': f'tele{n}'},
                         box(r[0], r[1], z, r[2], r[3], z + 72, EDGE_TEX)))
        parts.append(ent({'classname': 'info_teleport_destination', 'targetname': f'tele{n}',
                          'origin': f'{dx} {dy} {dz + 32}', 'angle': ang}))
    zmap = resolve_themes()
    for L in lights:
        x, y, z, v = L[:4]
        i, j = min(max(int((x - XMIN) // C), 0), NX - 1), min(max(int((y - YMIN) // C), 0), NY - 1)
        parts.append(ent({'classname': 'light', 'origin': f'{x} {y} {z}', 'light': v,
                          '_color': light_color(zmap[i][j] or 'room'),
                          'wait': str(L[4]) if len(L) > 4 else '0.75'}))
    # b5: wall lamps (non-solid fixture + light) instead of flame torches
    wl = []
    for ((x0, y0, x1, y1), z, di, dj, th) in (torches() if USE_TORCHES else []):
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        z0, z1 = z - 16, z + 16
        wt = fixture_tex(th)
        f = lambda p, q, r, xo, yo: '( %d %d %d ) ( %d %d %d ) ( %d %d %d ) %s %d %d 0 1 1' % (*p, *q, *r, wt, xo, yo)
        wl.append('\n'.join(['{', f((x0, y0, z0), (x0, y0 + 1, z0), (x0, y0, z0 + 1), -y0, z1),
                              f((x0, y0, z0), (x0, y0, z0 + 1), (x0 + 1, y0, z0), -x0, z1),
                              f((x0, y0, z0), (x0 + 1, y0, z0), (x0, y0 + 1, z0), 0, 0),
                              f((x1, y1, z1), (x1, y1 + 1, z1), (x1 + 1, y1, z1), 0, 0),
                              f((x1, y1, z1), (x1 + 1, y1, z1), (x1, y1, z1 + 1), -x0, z1),
                              f((x1, y1, z1), (x1, y1, z1 + 1), (x1, y1 + 1, z1), -y0, z1), '}']))
        lx, ly = (x0 + x1) / 2 - di * 20, (y0 + y1) / 2 - dj * 20
        parts.append(ent({'classname': 'light', 'origin': f'{lx:g} {ly:g} {z}', 'light': TORCH_LIGHT,
                          'wait': '1.2', '_color': light_color(th)}))
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
    x, y, z, ang, _ = (spawns or [(0, 0, 0, 0, '')])[0]
    parts.append(ent({'classname': 'info_player_start', 'origin': f'{x} {y} {z + 24}', 'angle': ang}))
    parts.append(ent({'classname': 'info_intermission', 'origin': INTERMISSION[0], 'mangle': INTERMISSION[1]}))
    open(path, 'w').write(''.join(parts))
    return len(bs)


def dump(path):
    json.dump({'C': C, 'XMIN': XMIN, 'YMIN': YMIN, 'NX': NX, 'NY': NY, 'BOT': BOT, 'TOP': TOP,
               'cols': [[[[a, b, m] for a, b, m in cols[i][j]] for j in range(NY)] for i in range(NX)],
               'theme': theme, 'feet': stair_feet, 'spawns': spawns, 'team_spawns': team_spawns, 'perches': perches, 'items': items, 'lights': lights, 'labels': labels,
               'teleports': teleports, 'liquids': liquids, 'decals': decals, 'ramps': RAMPS, 'prisms': PRISMS,
               'pushes': [(r, z, dx, dy, dz, 90) for r, z, dx, dy, dz, s, a in pushes]}, open(path, 'w'))


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '.'
    n = write_map(f'{out}/{NAME}.map')
    dump(f'{out}/{NAME}.json')
    print(f'{n} brushes, {len(lights)} lights, {len(spawns)} spawns, {len(items)} items')
