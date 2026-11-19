"""Verticality profile of a compiled Quake map (BSP29), from its collision hulls alone, so any map can
be measured the same way - ours and the classics.

    python3 vprofile.py map.bsp [more.bsp ...] [--targets] [--json out.json] [--png-dir figs/]

--targets prints each measure against the range of five classic QW maps (REFERENCE below);
build.sh runs it on every build (VPROFILE=0 to skip). The figure (--png-dir) is a height map plus
floor area by height.

What it measures (all on floor a player can stand on and reach from the spawns):
  floor area, footprint, STACKING (floor area / footprint; share of footprint with two floors >= 64 apart),
  height span, EFFECTIVE LEVELS (exp of the entropy of floor area over 64-unit height bands),
  GRADED floor (stairs and ramps), SLOPED floor faces, ANGLED walls (non-axial wall faces),
  OVERLOOKS (share of floor from which you can see floor >= 64 below, within 1200 units),
  CROSS-LEVEL SIGHT (of everything visible from a spot, the share >= 64 above or below it),
  VERTICAL LINKS (stair/ramp runs, drop-off sites, jump-up sites, teleporters, push pads),
  ROUTES between the main items: height changed per 1000 units travelled, share of item pairs whose
  shortest route changes level, and how spread out in height the items are,
  SKILL FLOOR: floor reachable only with a rocket jump (or not at all).
Movement model: walk/step 18, standing jump-up 44, running gap jumps up to 128, drops, teleporters,
push pads (simulated). Doors and plats count as open; func_wall counts as solid.
"""
import json
import math
import os
import re
import struct
import sys
from collections import defaultdict, deque

import numpy as np
from numba import njit

C = 16                     # grid
STEP, JUMP, RJ = 18, 44, 240
EYE, BODY = 46, 32


# ------------------------------------------------------------------ BSP
class BSP:
    def __init__(self, path):
        d = open(path, 'rb').read()
        ver = struct.unpack_from('<i', d, 0)[0]
        assert ver == 29, f'{path}: BSP version {ver}, only 29 supported'
        L = [struct.unpack_from('<ii', d, 4 + 8 * k) for k in range(15)]
        lump = lambda k: d[L[k][0]:L[k][0] + L[k][1]]
        self.ents = parse_ents(lump(0).decode('latin1'))
        pl = np.frombuffer(lump(1), dtype=np.dtype([('n', '<f4', 3), ('d', '<f4'), ('t', '<i4')]))
        self.pn, self.pd = pl['n'].astype(np.float64), pl['d'].astype(np.float64)
        nd = np.frombuffer(lump(5), dtype=np.dtype([('p', '<i4'), ('c', '<i2', 2), ('mn', '<i2', 3), ('mx', '<i2', 3), ('f', '<u2'), ('nf', '<u2')]))
        self.nplane, self.nchild = nd['p'].astype(np.int64), nd['c'].astype(np.int64)
        cn = np.frombuffer(lump(9), dtype=np.dtype([('p', '<i4'), ('c', '<i2', 2)]))
        self.cplane, self.cchild = cn['p'].astype(np.int64), cn['c'].astype(np.int64)
        lf = np.frombuffer(lump(10), dtype=np.dtype([('c', '<i4'), ('v', '<i4'), ('mn', '<i2', 3), ('mx', '<i2', 3), ('ms', '<u2'), ('nm', '<u2'), ('a', 'u1', 4)]))
        self.lcont = lf['c'].astype(np.int64)
        md = np.frombuffer(lump(14), dtype=np.dtype([('mn', '<f4', 3), ('mx', '<f4', 3), ('o', '<f4', 3), ('h', '<i4', 4), ('vl', '<i4'), ('ff', '<i4'), ('nf', '<i4')]))
        self.models = md
        # faces, for slope / angled-wall shares (world model only)
        fc = np.frombuffer(lump(7), dtype=np.dtype([('p', '<u2'), ('s', '<u2'), ('fe', '<i4'), ('ne', '<u2'), ('ti', '<u2'), ('st', 'u1', 4), ('lo', '<i4')]))
        ed = np.frombuffer(lump(12), dtype=np.dtype([('v', '<u2', 2)]))['v']
        se = np.frombuffer(lump(13), dtype='<i4')
        vx = np.frombuffer(lump(3), dtype='<f4').reshape(-1, 3).astype(np.float64)
        ti = np.frombuffer(lump(6), dtype=np.dtype([('v', '<f4', 8), ('m', '<i4'), ('f', '<i4')]))
        mt = lump(2)
        nmt = struct.unpack_from('<i', mt, 0)[0]
        offs = struct.unpack_from(f'<{nmt}i', mt, 4)
        names = [mt[o:o + 16].split(b'\0')[0].decode('latin1').lower() if o >= 0 else '' for o in offs]
        self.faces = []
        m0 = md[0]
        for k in range(m0['ff'], m0['ff'] + m0['nf']):
            f = fc[k]
            n = self.pn[f['p']] * (-1 if f['s'] else 1)
            tex = names[ti[f['ti']]['m']] if ti[f['ti']]['m'] < len(names) else ''
            idx = [ed[e][0] if e >= 0 else ed[-e][1] for e in se[f['fe']:f['fe'] + f['ne']]]
            P = vx[idx]
            a = 0.5 * np.linalg.norm(np.sum(np.cross(P - P[0], np.roll(P, -1, 0) - P[0]), 0))
            self.faces.append((n, a, tex))


def parse_ents(s):
    out = []
    for b in re.findall(r'\{([^}]*)\}', s):
        out.append(dict(re.findall(r'"([^"]*)"\s*"([^"]*)"', b)))
    return out


@njit(cache=True)
def _clip(root, cplane, cchild, pn, pd, x, y, z):
    n = root
    while n >= 0:
        p = cplane[n]
        d = pn[p, 0] * x + pn[p, 1] * y + pn[p, 2] * z - pd[p]
        n = cchild[n, 0] if d >= 0 else cchild[n, 1]
    return n


@njit(cache=True)
def _leaf(root, nplane, nchild, lcont, pn, pd, x, y, z):
    n = root
    while n >= 0:
        p = nplane[n]
        d = pn[p, 0] * x + pn[p, 1] * y + pn[p, 2] * z - pd[p]
        n = nchild[n, 0] if d >= 0 else nchild[n, 1]
    return lcont[-1 - n]


@njit(cache=True)
def _solid1(roots, cplane, cchild, pn, pd, x, y, z):
    """player-hull solid at origin: world or any func_wall"""
    for r in roots:
        if _clip(r, cplane, cchild, pn, pd, x, y, z) == -2:
            return True
    return False


@njit(cache=True)
def _scan(roots, cplane, cchild, pn, pd, x0, y0, nx, ny, zlo, zhi):
    """standable player origins per column: solid just below, empty at the origin"""
    out = []
    K = int((zhi - zlo) / 4) + 2
    for i in range(nx):
        x = x0 + i * 16 + 8
        for j in range(ny):
            y = y0 + j * 16 + 8
            prev = True
            for k in range(K):
                z = zlo + k * 4
                s = _solid1(roots, cplane, cchild, pn, pd, x, y, z)
                if prev and not s:
                    a, b = z - 4.0, z
                    for _ in range(5):
                        m = 0.5 * (a + b)
                        if _solid1(roots, cplane, cchild, pn, pd, x, y, m):
                            a = m
                        else:
                            b = m
                    out.append((i, j, b))
                prev = s
    return out


@njit(cache=True)
def _los(root, nplane, nchild, lcont, pn, pd, ax, ay, az, bx, by, bz):
    L = math.sqrt((bx - ax) ** 2 + (by - ay) ** 2 + (bz - az) ** 2)
    n = int(L / 8) + 1
    for t in range(1, n):
        f = t / n
        c = _leaf(root, nplane, nchild, lcont, pn, pd, ax + (bx - ax) * f, ay + (by - ay) * f, az + (bz - az) * f)
        if c == -2 or c == -6:
            return False
    return True


# ------------------------------------------------------------------ profile
def model_index(e):
    m = e.get('model', '')
    return int(m[1:]) if m.startswith('*') else None


def origin(e):
    return np.array([float(v) for v in e.get('origin', '0 0 0').split()])


def profile(path, name=None):
    B = BSP(path)
    name = name or os.path.splitext(os.path.basename(path))[0]
    m0 = B.models[0]
    roots = [int(m0['h'][1])]
    for e in B.ents:
        if e.get('classname') == 'func_wall' and model_index(e):
            roots.append(int(B.models[model_index(e)]['h'][1]))
    roots = np.array(roots, np.int64)
    S1 = lambda x, y, z: _solid1(roots, B.cplane, B.cchild, B.pn, B.pd, x, y, z)
    root0 = int(m0['h'][0])
    LC = lambda x, y, z: _leaf(root0, B.nplane, B.nchild, B.lcont, B.pn, B.pd, x, y, z)
    mn, mx = m0['mn'], m0['mx']
    x0, y0 = math.floor(mn[0] / C) * C, math.floor(mn[1] / C) * C
    nx, ny = int(math.ceil((mx[0] - x0) / C)), int(math.ceil((mx[1] - y0) / C))
    raw = _scan(roots, B.cplane, B.cchild, B.pn, B.pd, float(x0), float(y0), nx, ny, float(mn[2]) - 8, float(mx[2]) + 40)
    cols = defaultdict(list)
    for i, j, oz in raw:
        x, y = x0 + i * C + 8, y0 + j * C + 8
        c = LC(x, y, oz - 20)                     # contents at the feet
        if c in (-4, -5):                         # slime, lava: not floor
            continue
        cols[(i, j)].append(oz - 24.0)
    nodes = []
    nid = {}
    for (i, j), fl in cols.items():
        for k, f in enumerate(sorted(fl)):
            nid[(i, j, k)] = len(nodes)
            nodes.append((i, j, f))
    N = len(nodes)
    F = np.array([n[2] for n in nodes])
    colof = {}
    for (i, j), fl in cols.items():
        colof[(i, j)] = sorted(fl)
    def cxy(i, j):
        return x0 + i * C + 8, y0 + j * C + 8
    def floor_at(i, j, zmax):
        """highest floor in column (i,j) at or below zmax (feet height)"""
        fl = colof.get((i, j))
        if not fl:
            return None
        best = None
        for k, f in enumerate(fl):
            if f <= zmax + 0.5:
                best = k
        return None if best is None else nid[(i, j, best)]
    def node_near(x, y, z):
        i, j = int((x - x0) // C), int((y - y0) // C)
        for di, dj in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            n = floor_at(i + di, j + dj, z - 24 + 12)
            if n is not None and z - 24 - F[n] < 96:
                return n
        return None

    # --- edges
    adj = defaultdict(list)                # n -> [(m, cost, kind)]
    kinds = defaultdict(int)
    drops, jumps, graded = set(), set(), set()
    D8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
    for n, (i, j, f) in enumerate(nodes):
        x, y = cxy(i, j)
        for di, dj in D8:
            fl = colof.get((i + di, j + dj))
            if not fl:
                continue
            nx_, ny_ = cxy(i + di, j + dj)
            h = C * math.hypot(di, dj)
            # walk / step up (stepped position must be clear)
            for k, g in enumerate(fl):
                dz = g - f
                if -STEP <= dz <= STEP:
                    if di and dj and (S1(nx_, y, max(f, g) + 24 + 1) or S1(x, ny_, max(f, g) + 24 + 1)):
                        continue
                    m = nid[(i + di, j + dj, k)]
                    adj[n].append((m, h, 'walk'))
                    if 2 <= abs(dz):
                        graded.add(n)
                elif STEP < dz <= JUMP and not S1(x, y, f + 24 + dz + 4) and not S1(nx_, ny_, g + 24):
                    m = nid[(i + di, j + dj, k)]
                    adj[n].append((m, h + 32, 'jump'))
                    jumps.add(n)
            # drop: walk off the edge at our height, fall to the first floor below
            if not S1(nx_, ny_, f + 24 + 1):
                m = floor_at(i + di, j + dj, f)
                if m is not None and F[m] < f - STEP:
                    adj[n].append((m, h, 'drop'))
                    if F[m] < f - 40:
                        drops.add(n)
        # running gap jumps (2..8 cells) over a lower gap
        for di, dj in D8:
            for s in range(2, 9):
                ti, tj = i + di * s, j + dj * s
                if C * s * math.hypot(di, dj) > 128:
                    break
                m = floor_at(ti, tj, f + 8)
                if m is None or F[m] < f - 64:
                    continue
                ok = True
                for t in range(1, s):
                    mi, mj = i + di * t, j + dj * t
                    px, py = cxy(mi, mj)
                    if S1(px, py, f + 24 + 24):
                        ok = False
                        break
                    mm = floor_at(mi, mj, f + 8)
                    if mm is not None and F[mm] > f - 24:
                        ok = False         # not a gap: plain floor, walk covers it
                        break
                if ok:
                    adj[n].append((m, C * s * math.hypot(di, dj) + 16, 'gap'))
                break
    # teleporters
    tele = 0
    dest = {e.get('targetname'): origin(e) for e in B.ents if e.get('classname') in ('info_teleport_destination', 'info_notnull', 'info_null') and e.get('targetname')}
    for e in B.ents:
        if e.get('classname') != 'trigger_teleport' or model_index(e) is None:
            continue
        o = dest.get(e.get('target'))
        if o is None:
            continue
        tele += 1
        M = B.models[model_index(e)]
        d = node_near(o[0], o[1], o[2])
        if d is None:
            continue
        for n, (i, j, f) in enumerate(nodes):
            x, y = cxy(i, j)
            if M['mn'][0] - 16 <= x <= M['mx'][0] + 16 and M['mn'][1] - 16 <= y <= M['mx'][1] + 16 and M['mn'][2] - 56 <= f <= M['mx'][2]:
                adj[n].append((d, 0, 'tele'))
    # push pads: simulate the launch
    pads = 0
    for e in B.ents:
        if e.get('classname') != 'trigger_push' or model_index(e) is None:
            continue
        pads += 1
        M = B.models[model_index(e)]
        sp = float(e.get('speed', 1000)) * 10
        if 'angles' in e:
            p, yw, _ = [float(v) for v in e['angles'].split()]
        else:
            a = float(e.get('angle', 0))
            p, yw = (-90, 0) if a == -1 else (90, 0) if a == -2 else (0, a)
        pr, yr = math.radians(-p), math.radians(yw)
        v = np.clip(np.array([math.cos(pr) * math.cos(yr), math.cos(pr) * math.sin(yr), math.sin(pr)]) * sp, -2000, 2000)
        cx, cy = (M['mn'][0] + M['mx'][0]) / 2, (M['mn'][1] + M['mx'][1]) / 2
        src = [n for n, (i, j, f) in enumerate(nodes) if M['mn'][0] - 8 <= cxy(i, j)[0] <= M['mx'][0] + 8
               and M['mn'][1] - 8 <= cxy(i, j)[1] <= M['mx'][1] + 8 and M['mn'][2] - 56 <= f <= M['mx'][2]]
        pos = np.array([cx, cy, max(M['mx'][2], min((F[s] for s in src), default=M['mn'][2]) + 24)], float)
        land = None
        for _ in range(400):
            v[2] -= 800 * 0.01
            nxt = pos + v * 0.01
            if S1(*nxt):
                if v[2] < 0:
                    land = node_near(nxt[0], nxt[1], pos[2])
                    break
                if S1(pos[0], pos[1], nxt[2]):
                    v[2] = 0
                else:
                    v[0] = v[1] = 0
                continue
            pos = nxt
        if land is not None:
            for s in src:
                adj[s].append((land, 64, 'pad'))
    # spawns
    spn = []
    for e in B.ents:
        if e.get('classname') in ('info_player_deathmatch', 'info_player_start', 'info_player_team1', 'info_player_team2', 'info_player_coop'):
            o = origin(e)
            n = node_near(o[0], o[1], o[2])
            if n is not None:
                spn.append(n)
    def bfs(extra=None):
        seen = np.zeros(N, bool)
        dq = deque(spn)
        seen[spn] = True
        while dq:
            n = dq.popleft()
            for m, _, k in adj[n]:
                if not seen[m]:
                    seen[m] = True
                    dq.append(m)
            if extra:
                for m in extra(n):
                    if not seen[m]:
                        seen[m] = True
                        dq.append(m)
        return seen
    R = bfs()
    def rj(n):                       # rocket jump: up to RJ above, within 192 horizontally
        i, j, f = nodes[n]
        out = []
        for di in range(-12, 13):
            for dj in range(-12, 13):
                if di * di + dj * dj > 144:
                    continue
                fl = colof.get((i + di, j + dj))
                if not fl:
                    continue
                for k, g in enumerate(fl):
                    if JUMP < g - f <= RJ:
                        out.append(nid[(i + di, j + dj, k)])
        return out
    RR = bfs(rj)

    # --- metrics on reachable floor
    reach = np.nonzero(R)[0]
    A = len(reach) * C * C
    colsR = defaultdict(list)
    for n in reach:
        i, j, f = nodes[n]
        colsR[(i, j)].append(f)
    foot = len(colsR) * C * C
    stacked = sum(1 for fl in colsR.values() if max(fl) - min(fl) >= 64) * C * C
    FR = F[reach]
    lo = np.percentile(FR, 0)
    bands = np.floor((FR - lo) / 64).astype(int)
    p = np.bincount(bands) / len(FR)
    p = p[p > 0]
    eff_levels = float(np.exp(-(p * np.log(p)).sum()))
    # faces
    wa = fa = sl = ang = 0.0
    for n, a, tex in B.faces:
        if tex.startswith('sky') or tex.startswith('*') or tex.startswith('trigger') or tex == 'clip':
            continue
        if n[2] >= 0.7:
            fa += a
            if n[2] < 0.995:
                sl += a
        elif abs(n[2]) < 0.3:
            wa += a
            if min(abs(n[0]), abs(n[1])) > 0.02:
                ang += a
    # overlooks and cross-level sight (sampled)
    rng = np.random.default_rng(1)
    smp = reach if len(reach) <= 900 else rng.choice(reach, 900, replace=False)
    P = np.array([(cxy(nodes[n][0], nodes[n][1])[0], cxy(nodes[n][0], nodes[n][1])[1], F[n]) for n in smp])
    over = np.zeros(len(smp), bool)
    vis_all = vis_x = 0
    for a in range(len(smp)):
        d = np.hypot(P[:, 0] - P[a, 0], P[:, 1] - P[a, 1])
        cand = np.nonzero((d <= 1200) & (d > 0))[0]
        for b in cand:
            if _los(root0, B.nplane, B.nchild, B.lcont, B.pn, B.pd, P[a, 0], P[a, 1], P[a, 2] + EYE, P[b, 0], P[b, 1], P[b, 2] + BODY):
                vis_all += 1
                dz = P[b, 2] - P[a, 2]
                if abs(dz) >= 64:
                    vis_x += 1
                if dz <= -64:
                    over[a] = True
    # vertical link sites: connected groups of cells
    def groups(cells):
        cells = {(nodes[n][0], nodes[n][1]) for n in cells if R[n]}
        seen, g = set(), 0
        for c in cells:
            if c in seen:
                continue
            g += 1
            st = [c]
            seen.add(c)
            while st:
                i, j = st.pop()
                for di, dj in D8:
                    q = (i + di, j + dj)
                    if q in cells and q not in seen:
                        seen.add(q)
                        st.append(q)
        return g
    # stair/ramp runs: groups of graded floor whose height range is >= 48
    gr = {(nodes[n][0], nodes[n][1]): F[n] for n in graded if R[n]}
    runs = 0
    seen = set()
    for c in gr:
        if c in seen:
            continue
        st, comp = [c], []
        seen.add(c)
        while st:
            q = st.pop()
            comp.append(gr[q])
            for di, dj in D8:
                r = (q[0] + di, q[1] + dj)
                if r in gr and r not in seen and abs(gr[r] - gr[q]) <= STEP:
                    seen.add(r)
                    st.append(r)
        if max(comp) - min(comp) >= 48:
            runs += 1
    # routes between the main items
    ITEMS = {'item_armorInv': 'RA', 'item_armor2': 'YA', 'item_armor1': 'GA', 'item_artifact_super_damage': 'Quad',
             'item_artifact_invulnerability': 'Pent', 'item_artifact_invisibility': 'Ring', 'weapon_rocketlauncher': 'RL',
             'weapon_lightning': 'LG', 'weapon_grenadelauncher': 'GL', 'item_flag_team1': 'flag', 'item_flag_team2': 'flag'}
    keys = []
    for e in B.ents:
        cl = e.get('classname')
        lab = ITEMS.get(cl) or ('MH' if cl == 'item_health' and int(e.get('spawnflags', 0)) & 2 else None)
        if lab:
            o = origin(e)
            n = node_near(o[0] + (16 if cl.startswith('item_a') else 0), o[1] + (16 if cl.startswith('item_a') else 0), o[2] + 24)
            if n is not None and R[n]:
                keys.append((lab, n))
    import heapq
    def dijk(s):
        dist = {s: 0.0}
        prev = {}
        h = [(0.0, s)]
        while h:
            d, n = heapq.heappop(h)
            if d > dist.get(n, 1e18):
                continue
            for m, c, k in adj[n]:
                nd = d + c
                if nd < dist.get(m, 1e18):
                    dist[m] = nd
                    prev[m] = n
                    heapq.heappush(h, (nd, m))
        return dist, prev
    vchg = hlen = 0.0
    lvl_pairs = pairs = 0
    for a in range(len(keys)):
        dist, prev = dijk(keys[a][1])
        for b in range(a + 1, len(keys)):
            t = keys[b][1]
            if t not in dist:
                continue
            path = [t]
            while path[-1] != keys[a][1]:
                path.append(prev[path[-1]])
            hs = F[path]
            vchg += np.abs(np.diff(hs)).sum()
            hlen += dist[t]
            pairs += 1
            if hs.max() - hs.min() >= 64:
                lvl_pairs += 1
    item_h = np.array([F[n] for _, n in keys]) if keys else np.zeros(1)
    span = float(np.percentile(FR, 95) - np.percentile(FR, 5))
    srt = np.sort(FR)                          # dominant level: most floor within any 48-unit height window
    dom = max(np.searchsorted(srt, h + 48, 'right') - k for k, h in enumerate(srt[::max(1, len(srt) // 400)]) for k in [np.searchsorted(srt, h, 'left')])
    res = dict(
        map=name, spawns=len(spn),
        floor_area_k=round(A / 1000), footprint_k=round(foot / 1000),
        stacking=round(A / foot, 2), stacked_share=round(stacked / foot, 2),
        height_span=round(span), height_full=round(float(FR.max() - FR.min())),
        eff_levels=round(eff_levels, 2), dominant_level=round(dom / len(FR), 2),
        graded_share=round(float(np.mean([n in graded for n in reach])), 2),
        sloped_floor_faces=round(sl / fa, 2) if fa else 0, angled_walls=round(ang / wa, 2) if wa else 0,
        overlook_share=round(float(over.mean()), 2), cross_level_sight=round(vis_x / vis_all, 2) if vis_all else 0,
        stair_runs=runs, drop_sites=groups(drops), jump_sites=groups(jumps), teleporters=tele, pads=pads,
        route_vert_per_1000=round(1000 * vchg / hlen) if hlen else 0, route_level_pairs=round(lvl_pairs / pairs, 2) if pairs else 0,
        item_height_spread=round(float(np.std(item_h)) / span, 2) if span else 0, key_items=len(keys),
        skill_floor_share=round(float((RR & ~R).sum() / max(1, RR.sum())), 3),
        unreached_share=round(float((~RR).sum() / N), 3),
    )
    res['_draw'] = dict(x0=x0, y0=y0, nx=nx, ny=ny, nodes=nodes, F=F.tolist(), R=R.tolist(), RR=RR.tolist(),
                        keys=[(l, n) for l, n in keys], spawns=spn)
    return res


# ------------------------------------------------------------------ targets
# The range of five well-liked QW maps (aerowalk, ztndm3, dapak12, naked3, naked4), measured with
# this tool in Nov 2026 (see gallery/profiles). They are 1on1 / small-team maps; scale-free measures
# carry over to bigger maps, counts (teleporters, sites) grow with size. (lo, hi, which way is better)
REFERENCE = {
    'stacked_share':       (0.19, 0.21, 'up',   'floor with another floor directly over or under it'),
    'eff_levels':          (3.88, 5.15, 'up',   'effective number of levels (64-unit bands)'),
    'dominant_level':      (0.28, 0.41, 'down', 'share of floor on the single biggest level'),
    'overlook_share':      (0.46, 0.62, 'up',   'floor that can see floor >= 64 below it'),
    'cross_level_sight':   (0.31, 0.42, 'up',   'of what you can see, share >= 64 above or below'),
    'route_vert_per_1000': (251, 551,   'up',   'height changed per 1000 units, item to item'),
    'route_level_pairs':   (0.89, 0.96, 'up',   'item pairs whose route changes level'),
    'angled_walls':        (0.03, 0.22, 'up',   'wall area that is not axis-aligned'),
    'teleporters':         (2, 5,       'up',   'teleporters'),
}


def targets(res):
    """Print each measure against the reference range: ok / LOW / HIGH."""
    print(f"verticality profile of {res['map']} (reference range from five classic QW maps):")
    for k, (lo, hi, way, desc) in REFERENCE.items():
        v = res[k]
        verdict = 'ok' if lo <= v <= hi else ('LOW' if v < lo else 'HIGH')
        if verdict == 'HIGH' and way == 'up' or verdict == 'LOW' and way == 'down':
            verdict = 'ok+'                    # past the range in the good direction
        print(f'   {k:20s} {str(v):>6s}   ref {lo}-{hi:<6}  {verdict:4s}  {desc}')


# ------------------------------------------------------------------ figure
def draw(res, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    D = res['_draw']
    nodes, F, R, RR = D['nodes'], np.array(D['F']), np.array(D['R']), np.array(D['RR'])
    top = np.full((D['ny'], D['nx']), np.nan)
    cnt = np.zeros((D['ny'], D['nx']), int)
    grey = np.zeros((D['ny'], D['nx']), bool)
    for n, (i, j, f) in enumerate(nodes):
        if R[n]:
            top[j, i] = f if np.isnan(top[j, i]) else max(top[j, i], f)
            cnt[j, i] += 1
        elif RR[n]:
            grey[j, i] = True
    FR = F[R]
    lo, hi = np.percentile(FR, 1), np.percentile(FR, 99)
    fig = plt.figure(figsize=(10, 5.2), facecolor='#18191b')
    ax = fig.add_axes([0.01, 0.02, 0.62, 0.86])
    ax.set_facecolor('#0d0d0e')
    g = np.where(grey & np.isnan(top), 1.0, np.nan)
    ax.imshow(g, origin='lower', cmap='gray', vmin=0, vmax=3, interpolation='nearest')
    ax.imshow(top, origin='lower', cmap='turbo', vmin=lo, vmax=hi, interpolation='nearest')
    jj, ii = np.nonzero(cnt >= 2)
    ax.scatter(ii, jj, s=0.6, c='white', marker='.', linewidths=0)
    for lab, n in D['keys']:
        i, j, _ = nodes[n]
        ax.text(i, j, lab, color='white', fontsize=6, ha='center', va='center', bbox=dict(boxstyle='round,pad=0.1', fc='black', ec='none', alpha=0.6))
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(f"{res['map']}: highest floor per spot (colour = height); white dots = two floors stacked; grey = rocket-jump only",
                 color='w', fontsize=7.5, loc='left')
    bx = fig.add_axes([0.69, 0.12, 0.29, 0.74])
    bx.set_facecolor('#0d0d0e')
    rel = FR - FR.min()
    bins = np.arange(0, rel.max() + 33, 32)
    hgt, _ = np.histogram(rel, bins)
    bx.barh(bins[:-1] + 16, hgt * C * C / 1000, height=28, color=plt.cm.turbo(np.clip((bins[:-1] + FR.min() - lo) / max(1, hi - lo), 0, 1)))
    bx.set_xlabel('floor area (k sq units)', color='w', fontsize=8)
    bx.set_ylabel('height above lowest floor', color='w', fontsize=8)
    bx.tick_params(colors='w', labelsize=7)
    for s in bx.spines.values():
        s.set_color('#555')
    t = (f"levels {res['eff_levels']}  span {res['height_span']}\nstacked {int(100*res['stacked_share'])}%  overlooks {int(100*res['overlook_share'])}%\n"
         f"route height {res['route_vert_per_1000']}/1000u")
    bx.set_title(t, color='w', fontsize=8, loc='left')
    fig.savefig(out, dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)


if __name__ == '__main__':
    args = sys.argv[1:]
    js = args[args.index('--json') + 1] if '--json' in args else None
    pd_ = args[args.index('--png-dir') + 1] if '--png-dir' in args else None
    paths = [a for a in args if a.endswith('.bsp')]
    allres = []
    for p in paths:
        nm = os.path.splitext(os.path.basename(p))[0]
        r = profile(p, nm)
        if pd_:
            os.makedirs(pd_, exist_ok=True)
            draw(r, os.path.join(pd_, nm + '.png'))
        r.pop('_draw')
        if '--targets' in args:
            targets(r)
        else:
            print(json.dumps(r))
        allres.append(r)
    if js:
        json.dump(allres, open(js, 'w'), indent=1)
