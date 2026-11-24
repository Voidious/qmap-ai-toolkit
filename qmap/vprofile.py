"""Verticality profile of a compiled Quake map (BSP29), from its collision hulls alone, so any map can
be measured the same way - ours and the classics.

    python3 vprofile.py map.bsp [more.bsp ...] [--targets] [--ref duel|large] [--check] [--min-passage 64] [--json out.json] [--png-dir figs/]

--targets prints each measure against the reference range of classic QW maps (--ref duel, the default,
uses five compact duel/FFA classics; --ref large uses ten larger custom and 4v4 TDM classics);
--check reports cut-off spawns, one-way traps, narrow passages (where the player fits with less than
--min-passage effective width, default 64 = 32 spare on axial walls), blind pockets (floor with one way
in/out, no item/spawn, and depth > opening width), and unreachable items on the map's REAL player hull:
the authority on connectivity (check.py's grid can't see angled brushes or a 32-wide body on a step edge).
build.sh runs both on every build (VPROFILE=0 to skip). The figure (--png-dir) is a height map plus
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
DEFAULT_MIN_PASSAGE = 64.0


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
        self.solid_faces = []
        m0 = md[0]
        wall_models = [(0, 'world')]
        for e in self.ents:
            if e.get('classname') == 'func_wall':
                mi = model_index(e)
                if mi and mi < len(md):
                    wall_models.append((mi, f'func_wall*{mi}'))
        for mi, owner in wall_models:
            m = md[mi]
            for k in range(m['ff'], m['ff'] + m['nf']):
                f = fc[k]
                sgn = -1.0 if f['s'] else 1.0
                n = self.pn[f['p']] * sgn
                d_pl = float(self.pd[f['p']]) * sgn
                tex = names[ti[f['ti']]['m']] if ti[f['ti']]['m'] < len(names) else ''
                idx = [ed[e][0] if e >= 0 else ed[-e][1] for e in se[f['fe']:f['fe'] + f['ne']]]
                P = vx[idx]
                if mi == 0:
                    a = 0.5 * np.linalg.norm(np.sum(np.cross(P - P[0], np.roll(P, -1, 0) - P[0]), 0))
                    self.faces.append((n, a, tex))
                if abs(n[2]) < 0.7 and len(P) >= 3:
                    self.solid_faces.append((n, d_pl, P.min(0), P.max(0), tex, owner))


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


@njit(cache=True)
def _rcheck_iter(root, cplane, cchild, pn, pd, p1x, p1y, p1z, p2x, p2y, p2z):
    """Exact iterative Quake SV_RecursiveHullCheck on one clipnode tree.
    Returns (code, frac, nx, ny, nz, plane_idx):
      0 = all empty, 1 = all solid, 2 = empty->solid hit at frac (normal points into empty).
    """
    MAXD = 256
    st_num = np.empty(MAXD, np.int64)
    st_state = np.empty(MAXD, np.int64)
    st_side = np.empty(MAXD, np.int64)
    st_plane = np.empty(MAXD, np.int64)
    st_f1 = np.empty(MAXD, np.float64)
    st_f2 = np.empty(MAXD, np.float64)
    st_mf = np.empty(MAXD, np.float64)
    st_x1 = np.empty(MAXD, np.float64)
    st_y1 = np.empty(MAXD, np.float64)
    st_z1 = np.empty(MAXD, np.float64)
    st_x2 = np.empty(MAXD, np.float64)
    st_y2 = np.empty(MAXD, np.float64)
    st_z2 = np.empty(MAXD, np.float64)
    st_mx = np.empty(MAXD, np.float64)
    st_my = np.empty(MAXD, np.float64)
    st_mz = np.empty(MAXD, np.float64)

    sp = 0
    st_num[0] = root
    st_state[0] = 0
    st_f1[0] = 0.0
    st_f2[0] = 1.0
    st_x1[0] = p1x
    st_y1[0] = p1y
    st_z1[0] = p1z
    st_x2[0] = p2x
    st_y2[0] = p2y
    st_z2[0] = p2z

    ret_code = 0
    ret_frac = 1.0
    ret_nx = 0.0
    ret_ny = 0.0
    ret_nz = 0.0
    ret_pl = -1

    while sp >= 0:
        state = st_state[sp]
        num = st_num[sp]
        if state == 0:
            if num < 0:
                ret_code = 1 if num == -2 else 0
                ret_frac = 1.0
                ret_pl = -1
                sp -= 1
                continue
            p = cplane[num]
            nx = pn[p, 0]
            ny = pn[p, 1]
            nz = pn[p, 2]
            dist = pd[p]
            t1 = nx * st_x1[sp] + ny * st_y1[sp] + nz * st_z1[sp] - dist
            t2 = nx * st_x2[sp] + ny * st_y2[sp] + nz * st_z2[sp] - dist
            if t1 >= 0.0 and t2 >= 0.0:
                st_num[sp] = cchild[num, 0]
                continue
            if t1 < 0.0 and t2 < 0.0:
                st_num[sp] = cchild[num, 1]
                continue
            eps = 0.03125
            frac = (t1 + eps) / (t1 - t2) if t1 < 0.0 else (t1 - eps) / (t1 - t2)
            if frac < 0.0:
                frac = 0.0
            elif frac > 1.0:
                frac = 1.0
            mf = st_f1[sp] + (st_f2[sp] - st_f1[sp]) * frac
            mx = st_x1[sp] + (st_x2[sp] - st_x1[sp]) * frac
            my = st_y1[sp] + (st_y2[sp] - st_y1[sp]) * frac
            mz = st_z1[sp] + (st_z2[sp] - st_z1[sp]) * frac
            side = 1 if t1 < 0.0 else 0
            st_side[sp] = side
            st_plane[sp] = p
            st_mf[sp] = mf
            st_mx[sp] = mx
            st_my[sp] = my
            st_mz[sp] = mz
            st_state[sp] = 1
            if sp + 1 >= MAXD:
                return 0, 1.0, 0.0, 0.0, 0.0, -1
            c = sp + 1
            st_num[c] = cchild[num, side]
            st_state[c] = 0
            st_f1[c] = st_f1[sp]
            st_f2[c] = mf
            st_x1[c] = st_x1[sp]
            st_y1[c] = st_y1[sp]
            st_z1[c] = st_z1[sp]
            st_x2[c] = mx
            st_y2[c] = my
            st_z2[c] = mz
            sp = c
        elif state == 1:
            if ret_code == 2 or ret_code == 1:
                sp -= 1
                continue
            st_state[sp] = 2
            c = sp + 1
            st_num[c] = cchild[num, 1 - st_side[sp]]
            st_state[c] = 0
            st_f1[c] = st_mf[sp]
            st_f2[c] = st_f2[sp]
            st_x1[c] = st_mx[sp]
            st_y1[c] = st_my[sp]
            st_z1[c] = st_mz[sp]
            st_x2[c] = st_x2[sp]
            st_y2[c] = st_y2[sp]
            st_z2[c] = st_z2[sp]
            sp = c
        else:
            if ret_code == 1:
                p = st_plane[sp]
                sgn = 1.0 if st_side[sp] == 0 else -1.0
                ret_code = 2
                ret_frac = st_mf[sp]
                ret_nx = pn[p, 0] * sgn
                ret_ny = pn[p, 1] * sgn
                ret_nz = pn[p, 2] * sgn
                ret_pl = p
            sp -= 1
    return ret_code, ret_frac, ret_nx, ret_ny, ret_nz, ret_pl


@njit(cache=True)
def _trace_wall1(roots, cplane, cchild, pn, pd, x, y, f, dx, dy, maxd):
    """Trace horizontally along (dx, dy) in player hull 1 from floor f, stepping over
    walkable steps <= STEP (18u) so stair treads do not read as walls."""
    z_base = f + 25.0
    z_step = f + 24.0 + STEP + 0.5
    cur_d = 0.0
    z_cur = z_base
    for _ in range(4):
        if cur_d >= maxd:
            return False, maxd, 0.0, 0.0, 0.0, -1
        sx = x + dx * cur_d
        sy = y + dy * cur_d
        ex = x + dx * maxd
        ey = y + dy * maxd
        best_frac = 2.0
        best_nx = 0.0
        best_ny = 0.0
        best_nz = 0.0
        best_p = -1
        for r in roots:
            c, fr, nx, ny, nz, pl = _rcheck_iter(r, cplane, cchild, pn, pd, sx, sy, z_cur, ex, ey, z_cur)
            if c == 2 and fr < best_frac:
                best_frac = fr
                best_nx = nx
                best_ny = ny
                best_nz = nz
                best_p = pl
        if best_p < 0:
            return False, maxd, 0.0, 0.0, 0.0, -1
        hit_d = cur_d + best_frac * (maxd - cur_d)
        if z_cur == z_base:
            px = x + dx * (hit_d + 1.0)
            py = y + dy * (hit_d + 1.0)
            if not _solid1(roots, cplane, cchild, pn, pd, px, py, z_step):
                cur_d = hit_d + 1.0
                z_cur = z_step
                continue
        return True, hit_d, best_nx, best_ny, best_nz, best_p
    return False, maxd, 0.0, 0.0, 0.0, -1


@njit(cache=True)
def _scan_passages(roots, cplane, cchild, pn, pd, xs, ys, fs, max_spare):
    """Probe 8 opposing ray pairs per reachable player-hull node to find pinches where the
    32x32 player fits with < max_spare lateral clearance between two opposing vertical solids."""
    M = len(xs)
    dirs = np.zeros((8, 2), np.float64)
    for a in range(8):
        ang = a * math.pi / 8.0
        dirs[a, 0] = math.cos(ang)
        dirs[a, 1] = math.sin(ang)

    out_idx = []
    out_spare = []
    out_phys = []
    out_h1 = []
    out_h2 = []
    out_n1 = []
    out_n2 = []

    for k in range(M):
        x, y, f = xs[k], ys[k], fs[k]
        best_s = 1e9
        best_phys = 1e9
        best_h1 = (0.0, 0.0)
        best_h2 = (0.0, 0.0)
        best_n1 = (0.0, 0.0)
        best_n2 = (0.0, 0.0)
        found = False
        for a in range(8):
            dx, dy = dirs[a, 0], dirs[a, 1]
            hit1, d1, n1x, n1y, n1z, p1 = _trace_wall1(roots, cplane, cchild, pn, pd, x, y, f, dx, dy, max_spare)
            if not hit1 or d1 >= max_spare:
                continue
            if abs(n1z) >= 0.7:
                continue
            c1 = -(n1x * dx + n1y * dy)
            if c1 < 0.5:
                continue
            hit2, d2, n2x, n2y, n2z, p2 = _trace_wall1(roots, cplane, cchild, pn, pd, x, y, f, -dx, -dy, max_spare - d1)
            if not hit2:
                continue
            tot = d1 + d2
            if tot >= max_spare:
                continue
            if abs(n2z) >= 0.7:
                continue
            c2 = n2x * dx + n2y * dy
            if c2 < 0.5:
                continue
            if n1x * n2x + n1y * n2y > -0.5:
                continue
            e1 = 16.0 * (abs(n1x) + abs(n1y))
            e2 = 16.0 * (abs(n2x) + abs(n2y))
            h1x = x + dx * d1 - n1x * e1
            h1y = y + dy * d1 - n1y * e1
            h2x = x - dx * d2 - n2x * e2
            h2y = y - dy * d2 - n2y * e2
            phys = tot + e1 / c1 + e2 / c2
            if tot < best_s:
                best_s = tot
                best_phys = phys
                best_h1 = (h1x, h1y)
                best_h2 = (h2x, h2y)
                best_n1 = (n1x, n1y)
                best_n2 = (n2x, n2y)
                found = True
        if found:
            out_idx.append(k)
            out_spare.append(best_s)
            out_phys.append(best_phys)
            out_h1.append(best_h1)
            out_h2.append(best_h2)
            out_n1.append(best_n1)
            out_n2.append(best_n2)
    return out_idx, out_spare, out_phys, out_h1, out_h2, out_n1, out_n2


def _format_normal(nx, ny):
    if abs(nx) > 0.95:
        return '+x' if nx > 0 else '-x'
    if abs(ny) > 0.95:
        return '+y' if ny > 0 else '-y'
    return f'({nx:.1f},{ny:.1f})'


def _identify_solid(B, hx, hy, hz, nx, ny):
    """Best-matching BSP face texture and owner at surface point (hx, hy, hz) with normal (nx, ny)."""
    best = None
    for n, d_pl, mn, mx, tex, owner in B.solid_faces:
        if n[0] * nx + n[1] * ny < 0.9:
            continue
        pdist = abs(n[0] * hx + n[1] * hy + n[2] * hz - d_pl)
        if pdist > 4.0:
            continue
        if (mn[0] - 16 <= hx <= mx[0] + 16 and mn[1] - 16 <= hy <= mx[1] + 16
                and mn[2] - 24 <= hz <= mx[2] + 24):
            cx = 0.5 * (mn[0] + mx[0])
            cy = 0.5 * (mn[1] + mx[1])
            score = (pdist, math.hypot(hx - cx, hy - cy))
            if best is None or score < best[0]:
                best = (score, tex, owner)
    nlab = _format_normal(nx, ny)
    if best is None:
        return f'({round(hx)}, {round(hy)}) [{nlab} solid]'
    _, tex, owner = best
    label = f'{owner}/{tex}' if owner != 'world' else (tex or 'solid')
    return f'({round(hx)}, {round(hy)}) [{nlab} {label}]'


def _bsp_pockets(B, nodes, R, adj_dir, x0, y0, max_opening=512):
    """Find blind pockets on the real player-hull graph: reachable floor with one way in/out,
    no item or spawn, whose geodesic depth from the opening exceeds its physical opening width."""
    reach_set = set(int(n) for n in np.nonzero(R)[0])
    if len(reach_set) < 4:
        return []

    adj = defaultdict(set)
    for u in reach_set:
        for v, _, _ in adj_dir[u]:
            if v in reach_set:
                adj[u].add(v)
                adj[v].add(u)

    col_nodes = defaultdict(list)
    for n in reach_set:
        i, j, _ = nodes[n]
        col_nodes[(i, j)].append(n)

    pois = set()

    def mark_near(x, y, z):
        gi, gj = int((x - x0) // C), int((y - y0) // C)
        for di in (-2, -1, 0, 1, 2):
            for dj in (-2, -1, 0, 1, 2):
                for n in col_nodes.get((gi + di, gj + dj), ()):
                    nx = x0 + nodes[n][0] * C + 8
                    ny = y0 + nodes[n][1] * C + 8
                    if abs(nx - x) <= 24 and abs(ny - y) <= 24 and abs(nodes[n][2] - z) <= 32:
                        pois.add(n)

    for e in B.ents:
        cl = e.get('classname', '')
        if cl in ('info_player_deathmatch', 'info_player_start', 'info_player_team1', 'info_player_team2', 'info_player_coop'):
            o = origin(e)
            mark_near(o[0], o[1], o[2] - 24)
        elif cl.startswith(('item_', 'weapon_')):
            o = origin(e)
            ox = o[0] + (16 if cl.startswith(('item_armor', 'item_health')) else 0)
            oy = o[1] + (16 if cl.startswith(('item_armor', 'item_health')) else 0)
            mark_near(ox, oy, o[2])

    def build_strips(axis):
        by_pos = defaultdict(list)
        for n in reach_set:
            i, j, f = nodes[n]
            by_pos[i if axis == 'x' else j].append((j if axis == 'x' else i, n, f))
        runs = defaultdict(list)
        for pos, items in by_pos.items():
            in_pos = {n for _, n, _ in items}
            seen = set()
            for _, n, _ in items:
                if n in seen:
                    continue
                comp, st = [], [n]
                seen.add(n)
                while st:
                    u = st.pop()
                    comp.append(u)
                    for v in adj[u]:
                        if v in in_pos and v not in seen:
                            seen.add(v)
                            st.append(v)
                coords = [nodes[u][1] if axis == 'x' else nodes[u][0] for u in comp]
                lo, hi = min(coords), max(coords)
                if (hi - lo + 1) * C + BODY > max_opening:
                    continue
                z_key = round(min(nodes[u][2] for u in comp) / 16)
                runs[(lo, hi, z_key)].append((pos, comp))
        strips = []
        for (lo, hi, _), plist in runs.items():
            plist.sort(key=lambda x: x[0])
            cur = [plist[0]]
            for item in plist[1:]:
                if item[0] == cur[-1][0] + 1:
                    cur.append(item)
                else:
                    strips.append((axis, lo, hi, cur))
                    cur = [item]
            strips.append((axis, lo, hi, cur))
        return strips

    def test_cut(cut_nodes):
        cut_set = set(cut_nodes)
        nbs = set()
        for c in cut_nodes:
            for m in adj[c]:
                if m not in cut_set:
                    nbs.add(m)
        if len(nbs) < 2:
            return None
        seeds, seen_nb = [], set()
        for u in nbs:
            if u in seen_nb:
                continue
            comp, st = [], [u]
            seen_nb.add(u)
            while st:
                x = st.pop()
                comp.append(x)
                for y in adj[x]:
                    if y in nbs and y not in seen_nb:
                        seen_nb.add(y)
                        st.append(y)
            seeds.append(comp)
        if len(seeds) < 2:
            return None
        queues = [deque(s) for s in seeds]
        owner = {}
        comps = [set(s) for s in seeds]
        for idx, s in enumerate(seeds):
            for x in s:
                owner[x] = idx
        alive = set(range(len(seeds)))
        parent = list(range(len(seeds)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        finished = []
        while len(alive) > 1:
            for idx in list(alive):
                if idx not in alive:
                    continue
                if not queues[idx]:
                    alive.discard(idx)
                    finished.append(idx)
                    if len(alive) <= 1:
                        break
                    continue
                u = queues[idx].popleft()
                ru = find(idx)
                for v in adj[u]:
                    if v in cut_set:
                        continue
                    ov = owner.get(v)
                    if ov is None:
                        owner[v] = ru
                        comps[ru].add(v)
                        queues[ru].append(v)
                    else:
                        rv = find(ov)
                        if rv != ru:
                            if len(comps[ru]) < len(comps[rv]):
                                ru, rv = rv, ru
                            parent[rv] = ru
                            comps[ru] |= comps[rv]
                            queues[ru].extend(queues[rv])
                            queues[rv].clear()
                            alive.discard(rv)
                            if len(alive) <= 1:
                                break
                if len(alive) <= 1:
                    break
        out = []
        for idx in finished:
            r = find(idx)
            if r not in alive and len(comps[r]) < len(reach_set) // 2:
                out.append(comps[r])
        return out if out else None

    def pocket_depth(sl, comp):
        dist = {c: 0 for c in sl}
        dq = deque(sl)
        maxd = 0
        while dq:
            u = dq.popleft()
            for v in adj[u]:
                if v in comp and v not in dist:
                    dist[v] = dist[u] + 1
                    if dist[v] > maxd:
                        maxd = dist[v]
                    dq.append(v)
        return maxd * C

    pockets = []
    for axis, lo, hi, plist in build_strips('x') + build_strips('y'):
        w_phys = (hi - lo + 1) * C + BODY
        _, mid_sl = plist[len(plist) // 2]
        if not test_cut(mid_sl):
            continue
        for _, sl in plist:
            r2 = test_cut(sl)
            if not r2:
                continue
            for comp in r2:
                if comp & pois:
                    continue
                depth = pocket_depth(sl, comp)
                if depth > w_phys:
                    pockets.append((depth, w_phys, comp))

    pockets.sort(key=lambda x: (len(x[2]), x[0]), reverse=True)
    kept, used = [], set()
    for depth, w_phys, comp in pockets:
        if len(comp & used) > len(comp) * 0.25:
            continue
        xs = [x0 + nodes[n][0] * C for n in comp]
        ys = [y0 + nodes[n][1] * C for n in comp]
        zs = [round(nodes[n][2]) for n in comp]
        kept.append(dict(
            depth=depth, width=w_phys, cells=len(comp),
            x0=min(xs), x1=max(xs) + C, y0=min(ys), y1=max(ys) + C,
            zlo=min(zs), zhi=max(zs),
        ))
        used |= comp
    return kept


# ------------------------------------------------------------------ profile
def model_index(e):
    m = e.get('model', '')
    return int(m[1:]) if m.startswith('*') else None


def origin(e):
    return np.array([float(v) for v in e.get('origin', '0 0 0').split()])


def profile(path, name=None, with_navigation=False, min_passage=DEFAULT_MIN_PASSAGE):
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
                    # v3.1: the whole move happens at the higher of the two heights (step up in place,
                    # or walk on at our height before dropping): a step down into a low tunnel is
                    # blocked while the body still rests on the step above (ctf concept C's trench)
                    if S1(x, y, max(f, g) + 24 + 1) or S1(nx_, ny_, max(f, g) + 24 + 1):
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
    # push pads: simulate the launch. v3.1: trigger_push sets the velocity on EVERY frame the player
    # touches it, so a tall push volume keeps pushing to its top, and a second push volume on the way
    # (aerowalk's redirect at the top of its lift) takes over; start from standing on the pad.
    pads = 0
    PUSH = []
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
        PUSH.append((M, np.clip(np.array([math.cos(pr) * math.cos(yr), math.cos(pr) * math.sin(yr), math.sin(pr)]) * sp, -2000, 2000)))
    def in_push(pos):
        hit = None
        for M, v0 in PUSH:
            if (M['mn'][0] - 16 <= pos[0] <= M['mx'][0] + 16 and M['mn'][1] - 16 <= pos[1] <= M['mx'][1] + 16
                    and M['mn'][2] - 32 <= pos[2] <= M['mx'][2] + 24):
                hit = v0
        return hit
    for M, v0 in PUSH:
        cx, cy = (M['mn'][0] + M['mx'][0]) / 2, (M['mn'][1] + M['mx'][1]) / 2
        src = [n for n, (i, j, f) in enumerate(nodes) if M['mn'][0] - 8 <= cxy(i, j)[0] <= M['mx'][0] + 8
               and M['mn'][1] - 8 <= cxy(i, j)[1] <= M['mx'][1] + 8 and M['mn'][2] - 56 <= f <= M['mx'][2]]
        if not src:
            continue
        pos = np.array([cx, cy, min(F[s] for s in src) + 24 + 1], float)
        v = v0.copy()
        land = None
        for _ in range(600):
            pv = in_push(pos)
            if pv is not None:
                v = pv.copy()
            v[2] -= 800 * 0.01
            nxt = pos + v * 0.01
            if S1(*nxt):
                if v[2] < 0 and in_push(nxt) is None:
                    land = node_near(nxt[0], nxt[1], pos[2])
                    break
                if S1(pos[0], pos[1], nxt[2]):
                    v[2] = 0
                else:
                    v[0] = v[1] = 0
                continue
            pos = nxt
        if land is not None and land not in src:
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

    # --- v3.1 player-hull check: the compiled map's own collision, a 32x32x56 player, not the grid
    def bfs1(start, graph):
        seen = np.zeros(N, bool)
        seen[start] = True
        dq = deque([start])
        while dq:
            n = dq.popleft()
            for m in graph[n]:
                if not seen[m]:
                    seen[m] = True
                    dq.append(m)
        return seen
    fwd = {n: [m for m, _, _ in adj[n]] for n in range(N)}
    rev = defaultdict(list)
    for n in range(N):
        for m in fwd[n]:
            rev[m].append(n)
    spawn_ents = [e for e in B.ents if e.get('classname') in ('info_player_deathmatch', 'info_player_start', 'info_player_team1', 'info_player_team2', 'info_player_coop')]
    sp_nodes = [(origin(e), node_near(*origin(e)[:3])) for e in spawn_ents]
    reach_of = {n: bfs1(n, fwd) for _, n in sp_nodes if n is not None}
    chk = dict(
        spawns_off_floor=[tuple(int(v) for v in o) for o, n in sp_nodes if n is None],
        spawn_pairs_cut=[],
        trapped=[],
        items_unreached=[],
        narrow_passages=[],
        pockets=[],
        min_passage=float(min_passage),
    )
    if reach_of:
        back_of = {n: bfs1(n, rev) for n in reach_of}  # every spot from which that spawn can be reached
        main = max(reach_of, key=lambda n: (reach_of[n] & back_of[n]).sum())   # spawn in the biggest two-way area
        back = back_of[main]
        for o, n in sp_nodes:
            if n is not None and not (reach_of[main][n] and back[n]):
                chk['spawn_pairs_cut'].append(tuple(int(v) for v in o))
        trapped = [n for n in np.nonzero(R & ~back)[0]]
        seen_t = set()
        tset = {(nodes[n][0], nodes[n][1], round(F[n])): n for n in trapped}
        for key in tset:
            if key in seen_t:
                continue
            st, comp = [key], []
            seen_t.add(key)
            while st:
                q = st.pop()
                comp.append(q)
                for di, dj in D8:
                    for dz in range(-STEP, STEP + 1):
                        r = (q[0] + di, q[1] + dj, q[2] + dz)
                        if r in tset and r not in seen_t:
                            seen_t.add(r)
                            st.append(r)
            ci = np.mean([c[0] for c in comp]); cj = np.mean([c[1] for c in comp])
            chk['trapped'].append((len(comp) * C * C, round(x0 + ci * C + 8), round(y0 + cj * C + 8), round(min(c[2] for c in comp)), round(max(c[2] for c in comp))))
        chk['trapped'].sort(reverse=True)
        for e in B.ents:
            cl = e.get('classname', '')
            if cl.startswith(('item_', 'weapon_')):
                o = origin(e)
                n = node_near(o[0] + (16 if cl.startswith(('item_armor', 'item_health')) else 0), o[1] + (16 if cl.startswith(('item_armor', 'item_health')) else 0), o[2] + 24)
                if n is None or not R[n]:
                    chk['items_unreached'].append((cl, tuple(int(v) for v in o), n is not None and bool(RR[n])))

        # Passage width on real player hull: flag reachable spots where lateral clearance
        # (spare = hull-1 width) < min_passage - BODY (with 0.5u tolerance for clipnode epsilon).
        max_spare = float(min_passage) - BODY - 0.5
        reach_ids = np.nonzero(R)[0]
        if max_spare > 0 and len(reach_ids):
            rxs = np.array([x0 + nodes[n][0] * C + 8 for n in reach_ids], np.float64)
            rys = np.array([y0 + nodes[n][1] * C + 8 for n in reach_ids], np.float64)
            rfs = np.array([nodes[n][2] for n in reach_ids], np.float64)
            pidx, pspare, pphys, ph1, ph2, pn1, pn2 = _scan_passages(
                roots, B.cplane, B.cchild, B.pn, B.pd, rxs, rys, rfs, max_spare
            )
            cmap = {}
            for k in range(len(pidx)):
                ri = pidx[k]
                gi = int((rxs[ri] - x0) // C)
                gj = int((rys[ri] - y0) // C)
                gz = round(rfs[ri])
                cmap[(gi, gj, gz)] = (
                    float(pspare[k]), float(pphys[k]),
                    float(rxs[ri]), float(rys[ri]), float(rfs[ri]),
                    ph1[k], ph2[k], pn1[k], pn2[k],
                )
            seen_p = set()
            for key in cmap:
                if key in seen_p:
                    continue
                comp, st = [], [key]
                seen_p.add(key)
                while st:
                    u = st.pop()
                    comp.append(cmap[u])
                    for di in (-1, 0, 1):
                        for dj in (-1, 0, 1):
                            for dz in range(-24, 25):
                                v = (u[0] + di, u[1] + dj, u[2] + dz)
                                if v in cmap and v not in seen_p:
                                    seen_p.add(v)
                                    st.append(v)
                min_sp = min(c_[0] for c_ in comp)
                cx_ = sum(c_[2] for c_ in comp) / len(comp)
                cy_ = sum(c_[3] for c_ in comp) / len(comp)
                near_min = [c_ for c_ in comp if c_[0] <= min_sp + 0.5]
                sp, ph, px, py, pz, h1_, h2_, n1_, n2_ = min(
                    near_min, key=lambda c_: (math.hypot(c_[2] - cx_, c_[3] - cy_), c_[0])
                )
                s1 = _identify_solid(B, h1_[0], h1_[1], pz + 32.0, n1_[0], n1_[1])
                s2 = _identify_solid(B, h2_[0], h2_[1], pz + 32.0, n2_[0], n2_[1])
                chk['narrow_passages'].append(dict(
                    spare=round(sp, 1),
                    effective_width=round(sp + BODY, 1),
                    physical_width=round(ph, 1),
                    x=round(px), y=round(py), z=round(pz),
                    cells=len(comp),
                    solid1=s1, solid2=s2,
                ))
            chk['narrow_passages'].sort(key=lambda c_: (c_['spare'], c_['x'], c_['y'], c_['z']))

        # Blind pockets on real player hull (catches angled/prism-sealed dead-end halls too)
        chk['pockets'] = _bsp_pockets(B, nodes, R, adj, x0, y0)

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
    # v3.3: SIZE as players feel it - walking distance between random spots on reachable floor
    # (floor area alone overrates vertical maps: stacked floor adds area, not distance)
    rs = np.random.default_rng(7)
    smp_t = rs.choice(reach, min(60, len(reach)), replace=False) if len(reach) else []
    dd = []
    for a_ in smp_t:
        dist_, _ = dijk(int(a_))
        dd += [dist_[int(b_)] for b_ in smp_t if int(b_) != int(a_) and int(b_) in dist_]
    travel_med = float(np.median(dd)) if dd else 0.0
    travel_p90 = float(np.percentile(dd, 90)) if dd else 0.0
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
        travel_median=round(travel_med), travel_p90=round(travel_p90),
    )
    res['_check'] = chk
    res['_draw'] = dict(x0=x0, y0=y0, nx=nx, ny=ny, nodes=nodes, F=F.tolist(), R=R.tolist(), RR=RR.tolist(),
                        keys=[(l, n) for l, n in keys], spawns=spn)
    if with_navigation:
        res['_navigation'] = dict(bsp=B, adjacency=adj, shortest_paths=dijk)
    return res


# ------------------------------------------------------------------ targets
# The range of five well-liked compact QW maps (aerowalk, ztndm3, dapak12, naked3, naked4), measured
# with this tool in Nov 2026 (see gallery/profiles/profiles.json). (lo, hi, which way is better)
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

# The range of ten well-regarded larger QW maps: six custom multi-player classics (skull, bravado,
# spinev2, ultrav, schloss, cmt4) plus four canonical 4v4 TDM classics (dm3, e2m2tdm, cmt3, e1m2),
# measured with this tool in Nov 2026 (see gallery/profiles/large_refs.json).
REFERENCE_LARGE = {
    'stacked_share':       (0.07, 0.26, 'up',   'floor with another floor directly over or under it'),
    'eff_levels':          (4.30, 8.98, 'up',   'effective number of levels (64-unit bands)'),
    'dominant_level':      (0.22, 0.37, 'down', 'share of floor on the single biggest level'),
    'overlook_share':      (0.25, 0.66, 'up',   'floor that can see floor >= 64 below it'),
    'cross_level_sight':   (0.17, 0.47, 'up',   'of what you can see, share >= 64 above or below'),
    'route_vert_per_1000': (87, 215,    'up',   'height changed per 1000 units, item to item'),
    'route_level_pairs':   (0.75, 0.98, 'up',   'item pairs whose route changes level'),
    'angled_walls':        (0.03, 0.30, 'up',   'wall area that is not axis-aligned'),
    'teleporters':         (2, 7,       'up',   'teleporters'),
}


# v3.3: SIZE BY TRAVEL - median and 90th-percentile walking distance between random spots (teleporters,
# pads and drops included). Floor area overrates vertical maps; travel is what players feel. Measured
# Nov 2026 on maps with a known player count (see GUIDE, 'Sizing a map'):
SIZE_BANDS = [   # (travel median up to, label)
    (950,  'duel / FFA 2-6; Clan Arena 4-10 (like helix, relay, naked3, skull, aerowalk)'),
    (1160, 'duel / FFA 4-8; Clan Arena 6-12 (like bravado, spinev2, ultrav, dm6, lyceum, ztndm3)'),
    (1400, 'Clan Arena / TDM 8-12+ (like agora, vigil)'),
    (10 ** 9, 'large 4v4 TDM or CTF (like schloss, cmt4, dm3, e2m2tdm, cmt3, e1m2, bastion, strata, circuit)'),
]


def size_line(res):
    label = next(l for t, l in SIZE_BANDS if res['travel_median'] <= t)
    return (f"   size: travel median {res['travel_median']}, 90% {res['travel_p90']} units "
            f"(floor {res['floor_area_k']}k sq units) -> {label}")


def targets(res, ref='duel'):
    """Print each measure against the reference range: ok / LOW / HIGH.
    ref='duel' compares against the five compact QW classics; ref='large' compares against
    the ten larger custom and 4v4 TDM classics."""
    if ref == 'large':
        table, label = REFERENCE_LARGE, 'ten larger QW classics'
    elif ref == 'duel':
        table, label = REFERENCE, 'five compact QW classics'
    else:
        raise ValueError(f"unknown --ref {ref!r} (expected 'duel' or 'large')")
    print(f"verticality profile of {res['map']} (reference range from {label}):")
    print(size_line(res))
    for k, (lo, hi, way, desc) in table.items():
        v = res[k]
        verdict = 'ok' if lo <= v <= hi else ('LOW' if v < lo else 'HIGH')
        if verdict == 'HIGH' and way == 'up' or verdict == 'LOW' and way == 'down':
            verdict = 'ok+'                    # past the range in the good direction
        print(f'   {k:20s} {str(v):>6s}   ref {lo}-{hi:<6}  {verdict:4s}  {desc}')


def check_report(res):
    """Connectivity, traps, narrow passages, and blind pockets on the compiled map's player hull
    (32 wide, 56 tall). The grid checker (check.py) treats the player as one 16-unit cell and cannot
    see angled brushes or a ceiling that catches a player half on a step; this can. Walk 18, jump 44,
    gaps, drops, teleporters and pads; no rocket jumps."""
    c = res['_check']
    bad = False
    mp = c.get('min_passage', DEFAULT_MIN_PASSAGE)
    print(f"player-hull check of {res['map']} (real collision, 32x32x56 player, no rocket jumps):")
    for o in c['spawns_off_floor']:
        bad = True
        print(f'   SPAWN {o} is not standing on reachable floor')
    for o in c['spawn_pairs_cut']:
        bad = True
        print(f'   SPAWN {o} is cut off: it cannot reach the main area, or the main area cannot reach it')
    for area, x, y, zlo, zhi in c['trapped']:
        bad = True
        print(f'   TRAP: {area} sq units of floor near ({x}, {y}) at z {zlo}..{zhi}: you can get in but not back out')
    for np_ in c.get('narrow_passages', []):
        bad = True
        print(f"   NARROW PASSAGE (< {mp:g}): {np_['effective_width']:g}u eff / {np_['physical_width']:g}u gap "
              f"({np_['spare']:g}u spare) at ({np_['x']}, {np_['y']}, {np_['z']}) "
              f"between {np_['solid1']} and {np_['solid2']}")
    for pk in c.get('pockets', []):
        bad = True
        zr = f"{pk['zlo']}" if pk['zlo'] == pk['zhi'] else f"{pk['zlo']}..{pk['zhi']}"
        print(f"   BLIND POCKET: floor {zr}, x {pk['x0']}..{pk['x1']}, y {pk['y0']}..{pk['y1']} "
              f"(depth {pk['depth']} > opening {pk['width']}, no item/spawn)")
    rj = [(cl, o) for cl, o, r in c['items_unreached'] if r]
    for cl, o, r in c['items_unreached']:
        if not r:
            bad = True
            print(f'   ITEM {cl} at {o}: unreachable on foot or with a rocket jump (a hook-only perch?)')
    if rj:
        print(f'   note: {len(rj)} item(s) need the hook or a rocket jump (fine on perches): '
              + ', '.join(f"{cl.split('_', 1)[1]} {o}" for cl, o in rj[:6]) + (' ...' if len(rj) > 6 else ''))
    if not bad:
        print(f'   every spawn reaches every other; no traps; no narrow passages (< {mp:g}); no blind pockets; every item reachable')


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
    mp = float(args[args.index('--min-passage') + 1]) if '--min-passage' in args else DEFAULT_MIN_PASSAGE
    ref = args[args.index('--ref') + 1] if '--ref' in args else 'duel'
    paths = [a for a in args if a.endswith('.bsp')]
    allres = []
    for p in paths:
        nm = os.path.splitext(os.path.basename(p))[0]
        r = profile(p, nm, min_passage=mp)
        if pd_:
            os.makedirs(pd_, exist_ok=True)
            draw(r, os.path.join(pd_, nm + '.png'))
        r.pop('_draw')
        if '--check' in args:
            check_report(r)
        r.pop('_check')
        if '--targets' in args:
            targets(r, ref=ref)
        else:
            print(json.dumps(r))
        allres.append(r)
    if js:
        json.dump(allres, open(js, 'w'), indent=1)
