"""Gameplay and layout checks on the generator's column grid and prism list.

- every spawn stands on floor with player clearance, spacing, and mutual sightlines
- walking/jumping/teleport/push graph: every spawn reaches every other
- unreached floor at all heights (excluding hook-only perches)
- item floor margins, reachability, overlaps, and hook-only perches
- one-way traps: reachable floor with no walk/jump route back to spawns
- blind pockets: reachable floor with one way in/out, no item or spawn, and depth > opening width
- stair/ramp foot clearance and 16-unit player-blocking slots
- prism separation: distance from every prism() footprint to other prisms, fill() rects, and walls (< 64)
"""
import itertools
import json
import math
import sys
from collections import Counter, deque

STEP, HEAD = 18, 56
DEFAULT_MIN_PRISM_SEP = 64


# ------------------------------------------------------------------ 2D polygon geometry
def poly_pt_dist(pts, x, y):
    """Exact 2D distance from point (x, y) to convex CCW polygon pts (0.0 if inside/on)."""
    n = len(pts)
    inside = True
    best = 1e18
    for k in range(n):
        ax, ay = pts[k]
        bx, by = pts[(k + 1) % n]
        dx, dy = bx - ax, by - ay
        if dx * (y - ay) - dy * (x - ax) < -1e-9:
            inside = False
        L2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2)) if L2 > 0 else 0.0
        d = math.hypot(x - (ax + t * dx), y - (ay + t * dy))
        if d < best:
            best = d
    return 0.0 if inside else best


def _seg_seg_dist(a, b, c, d):
    def cross(o, u, v):
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])

    def on_seg(o, u, p):
        return (min(o[0], u[0]) - 1e-9 <= p[0] <= max(o[0], u[0]) + 1e-9
                and min(o[1], u[1]) - 1e-9 <= p[1] <= max(o[1], u[1]) + 1e-9)

    c1, c2 = cross(a, b, c), cross(a, b, d)
    c3, c4 = cross(c, d, a), cross(c, d, b)
    if c1 * c2 < 0 and c3 * c4 < 0:
        return 0.0
    if abs(c1) < 1e-9 and on_seg(a, b, c):
        return 0.0
    if abs(c2) < 1e-9 and on_seg(a, b, d):
        return 0.0
    if abs(c3) < 1e-9 and on_seg(c, d, a):
        return 0.0
    if abs(c4) < 1e-9 and on_seg(c, d, b):
        return 0.0

    def pt_seg(p, u, v):
        dx, dy = v[0] - u[0], v[1] - u[1]
        L2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((p[0] - u[0]) * dx + (p[1] - u[1]) * dy) / L2)) if L2 > 0 else 0.0
        return math.hypot(p[0] - (u[0] + t * dx), p[1] - (u[1] + t * dy))

    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def poly_poly_dist(P, Q):
    """Exact 2D Euclidean distance between two convex CCW polygons (0.0 if touching/overlapping)."""
    for x, y in P:
        if poly_pt_dist(Q, x, y) == 0.0:
            return 0.0
    for x, y in Q:
        if poly_pt_dist(P, x, y) == 0.0:
            return 0.0
    best = 1e18
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        for j in range(len(Q)):
            c, d = Q[j], Q[(j + 1) % len(Q)]
            dist = _seg_seg_dist(a, b, c, d)
            if dist < best:
                best = dist
    return best


def poly_clip_area(P, Q):
    """Intersection area of two convex CCW polygons (Sutherland-Hodgman)."""
    poly = list(P)
    for k in range(len(Q)):
        ax, ay = Q[k]
        bx, by = Q[(k + 1) % len(Q)]
        ex, ey = bx - ax, by - ay
        inp = poly
        poly = []
        if not inp:
            return 0.0
        s = inp[-1]
        for e in inp:
            se = ex * (e[1] - ay) - ey * (e[0] - ax)
            ss = ex * (s[1] - ay) - ey * (s[0] - ax)
            if se >= -1e-9:
                if ss < -1e-9:
                    denom = ss - se
                    t = ss / denom if abs(denom) > 1e-12 else 0.0
                    poly.append((s[0] + t * (e[0] - s[0]), s[1] + t * (e[1] - s[1])))
                poly.append(e)
            elif ss >= -1e-9:
                denom = ss - se
                t = ss / denom if abs(denom) > 1e-12 else 0.0
                poly.append((s[0] + t * (e[0] - s[0]), s[1] + t * (e[1] - s[1])))
            s = e
    if len(poly) < 3:
        return 0.0
    area = 0.0
    for k in range(len(poly)):
        x1, y1 = poly[k]
        x2, y2 = poly[(k + 1) % len(poly)]
        area += x1 * y2 - x2 * y1
    return 0.5 * abs(area)


# ------------------------------------------------------------------ grid helpers
def build_air(cols, NX, NY, BOT, TOP):
    out = []
    for i in range(NX):
        row = []
        for j in range(NY):
            segs = sorted((a, b) for a, b, _ in cols[i][j])
            col_air, z = [], BOT
            for a, b in segs:
                if a > z:
                    col_air.append((z, a))
                z = max(z, b)
            if z < TOP:
                col_air.append((z, TOP))
            row.append(col_air)
        out.append(row)
    return out


# ------------------------------------------------------------------ prism separation
def check_prism_separation(d, AIR, min_sep=DEFAULT_MIN_PRISM_SEP):
    """Distance from every prism() obstacle footprint to other prisms, fill() rects, and walls at
    walkable player heights. Flags separations below min_sep (default 64).

    Walkable bridge slabs (kind == 'bridge') are skipped. Wall-attached structural prisms
    (kind None, e.g. chamfer() / diag_wall()) are allowed flush contact with their mounting wall
    half-planes and edge/vertex contact with another structural prism without interior overlap;
    freestanding prisms (e.g. 'pillar', 'crate') fail at dist < min_sep including 0.
    """
    prisms = d.get('prisms', [])
    if not prisms:
        return []
    C, XMIN, YMIN, NX, NY, BOT = (d[k] for k in ('C', 'XMIN', 'YMIN', 'NX', 'NY', 'BOT'))
    cols = d['cols']
    probs = []
    meta = []
    for P, z0, z1, kind in prisms:
        xs = [p[0] for p in P]
        ys = [p[1] for p in P]
        meta.append((min(xs), min(ys), max(xs), max(ys), sum(xs) / len(xs), sum(ys) / len(ys)))

    for idx, (P, z0, z1, kind) in enumerate(prisms):
        if kind == 'bridge':
            continue
        x0, y0, x1, y1, cx, cy = meta[idx]
        pad = min_sep + C
        i0 = max(0, int((x0 - pad - XMIN) // C))
        i1 = min(NX, int((x1 + pad - XMIN) // C) + 1)
        j0 = max(0, int((y0 - pad - YMIN) // C))
        j1 = min(NY, int((y1 + pad - YMIN) // C) + 1)
        floors = set()
        for i in range(i0, i1):
            for j in range(j0, j1):
                for a, b in AIR[i][j]:
                    if a > BOT and b - a >= HEAD and z0 < a + HEAD and z1 > a + STEP:
                        floors.add(a)
        if not floors:
            continue
        attached_kind = kind in (None, 'bridge')
        klabel = kind or 'wall'

        # 1. Prism vs every other prism overlapping vertically at a walkable floor
        for jdx in range(idx + 1, len(prisms)):
            Q, qz0, qz1, qkind = prisms[jdx]
            if qkind == 'bridge':
                continue
            if qz1 <= z0 or qz0 >= z1:
                continue
            qx0, qy0, qx1, qy1, qcx, qcy = meta[jdx]
            if qx1 + min_sep < x0 or qx0 - min_sep > x1 or qy1 + min_sep < y0 or qy0 - min_sep > y1:
                continue
            shared_f = [f for f in floors if qz0 < f + HEAD and qz1 > f + STEP]
            if not shared_f:
                continue
            dist = poly_poly_dist(P, Q)
            if dist < min_sep - 1e-6:
                if dist <= 1e-6 and attached_kind and qkind in (None, 'bridge') and poly_clip_area(P, Q) < 1.0:
                    continue
                qklabel = qkind or 'wall'
                probs.append(
                    f'prism #{idx} ({klabel} @ {cx:.0f},{cy:.0f}) <-> prism #{jdx} '
                    f'({qklabel} @ {qcx:.0f},{qcy:.0f}) z={min(shared_f)}: dist {dist:.1f} < {min_sep}'
                )

        # 2. Prism vs non-prism grid solids (walls, fill() rects, stairs) at each nearby floor
        best_grid = None
        for f in sorted(floors):
            zlo, zhi = f + STEP, f + HEAD
            solid_cells = {}
            for i in range(i0, i1):
                for j in range(j0, j1):
                    bx, by = XMIN + i * C, YMIN + j * C
                    box = [(bx, by), (bx + C, by), (bx + C, by + C), (bx, by + C)]
                    for a, b, m in cols[i][j]:
                        if b <= zlo or a >= zhi:
                            continue
                        if m == 'diag':
                            continue
                        # Skip interior stand-in cells wholly inside any prism of matching kind
                        is_prism_cell = False
                        for p2_idx, (P2, p2z0, p2z1, p2k) in enumerate(prisms):
                            if m == p2k and p2z0 <= a and p2z1 >= b:
                                px0, py0, px1, py1, _, _ = meta[p2_idx]
                                if (bx >= px0 - 1e-6 and bx + C <= px1 + 1e-6
                                        and by >= py0 - 1e-6 and by + C <= py1 + 1e-6):
                                    if all(poly_pt_dist(P2, u, v) <= 1e-6 for u, v in box):
                                        is_prism_cell = True
                                        break
                        if is_prism_cell:
                            continue
                        solid_cells[(i, j)] = (m or 'wall', box)
                        break

            # Wall-attached prisms (chamfers, diagonal walls, bridges) sit flush on their
            # mounting walls: ignore cells flush-touching P (dist <= 0.5) and backing-wall
            # cells lying completely behind any mounted edge's outward half-plane.
            mounted_planes = []
            if attached_kind:
                n_v = len(P)
                for k in range(n_v):
                    ax, ay = P[k]
                    bx, by = P[(k + 1) % n_v]
                    L = math.hypot(bx - ax, by - ay)
                    if L <= 1e-9:
                        continue
                    enx, eny = (by - ay) / L, -(bx - ax) / L
                    steps = max(2, int(math.ceil(L / C)))
                    if any((int((ax + (bx - ax) * t / steps + enx * 2.0 - XMIN) // C),
                            int((ay + (by - ay) * t / steps + eny * 2.0 - YMIN) // C)) in solid_cells
                           for t in range(1, steps)):
                        mounted_planes.append((ax, ay, enx, eny))

            for cell, (mat, box) in solid_cells.items():
                dist = poly_poly_dist(P, box)
                if attached_kind:
                    if dist <= 0.5:
                        continue
                    if any(all((u - ax) * enx + (v - ay) * eny >= -1e-6 for u, v in box)
                           for ax, ay, enx, eny in mounted_planes):
                        continue
                if dist < min_sep - 1e-6:
                    if best_grid is None or dist < best_grid[0]:
                        best_grid = (dist, f, mat, XMIN + cell[0] * C, YMIN + cell[1] * C)

        if best_grid is not None:
            dist, f, mat, gx, gy = best_grid
            probs.append(
                f'prism #{idx} ({klabel} @ {cx:.0f},{cy:.0f}) <-> {mat} @ ({gx},{gy}) z={f}: '
                f'dist {dist:.1f} < {min_sep}'
            )
    return probs


# ------------------------------------------------------------------ blind pocket check
def check_pockets(d, reach, neighbours_fn, max_opening=512):
    """Find blind pockets: reachable floor with exactly one way in/out (counting walk, jump,
    drop, teleports, and push pads), holding no item and no spawn, whose geodesic depth from
    the opening exceeds its opening width."""
    if len(reach) < 4:
        return []
    C, XMIN, YMIN = d['C'], d['XMIN'], d['YMIN']
    reach_set = set(reach)

    # Undirected adjacency: any drop, jump, teleport, or push pad OUT or IN is a second route
    adj = {}
    for n in reach_set:
        adj.setdefault(n, set())
        for m in neighbours_fn(n, 40):
            if m in reach_set:
                adj[n].add(m)
                adj.setdefault(m, set()).add(n)

    # Points of interest: spawns, team spawns, items
    pois = set()
    for sp in d.get('spawns', []):
        pi, pj, pz = int((sp[0] - XMIN) // C), int((sp[1] - YMIN) // C), sp[2]
        for di in (-1, 0):
            for dj in (-1, 0):
                if (pi + di, pj + dj, pz) in reach_set:
                    pois.add((pi + di, pj + dj, pz))
    for ts in d.get('team_spawns', []):
        pi, pj, pz = int((ts[0] - XMIN) // C), int((ts[1] - YMIN) // C), ts[2]
        for di in (-1, 0):
            for dj in (-1, 0):
                if (pi + di, pj + dj, pz) in reach_set:
                    pois.add((pi + di, pj + dj, pz))
    for it in d.get('items', []):
        pi, pj, pz = int((it[1] - XMIN) // C), int((it[2] - YMIN) // C), it[3]
        for di in (-1, 0):
            for dj in (-1, 0):
                if (pi + di, pj + dj, pz) in reach_set:
                    pois.add((pi + di, pj + dj, pz))

    by_z = {}
    for i, j, z in reach_set:
        by_z.setdefault(z, set()).add((i, j))

    def find_strips(axis):
        strips = []
        for z, pts in by_z.items():
            by_pos = {}
            for i, j in pts:
                by_pos.setdefault(i if axis == 'x' else j, []).append(j if axis == 'x' else i)
            runs = {}
            for pos, coords in sorted(by_pos.items()):
                coords.sort()
                s = e = coords[0]
                for v in coords[1:]:
                    if v == e + 1:
                        e = v
                    else:
                        runs.setdefault((s, e), []).append(pos)
                        s = e = v
                runs.setdefault((s, e), []).append(pos)
            for (lo, hi), plist in runs.items():
                if (hi - lo + 1) * C > max_opening:
                    continue
                plist.sort()
                cur = [plist[0]]
                for p in plist[1:]:
                    if p == cur[-1] + 1:
                        cur.append(p)
                    else:
                        strips.append((axis, z, lo, hi, cur))
                        cur = [p]
                strips.append((axis, z, lo, hi, cur))
        return strips

    def make_slice(axis, z, lo, hi, pos):
        if axis == 'x':
            return [(pos, j, z) for j in range(lo, hi + 1)]
        return [(i, pos, z) for i in range(lo, hi + 1)]

    def test_cut(cut_cells):
        cut_set = set(cut_cells)
        nbs = set()
        for c in cut_cells:
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
                if not queues[idx]:
                    alive.discard(idx)
                    finished.append(idx)
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
                        queues[idx].append(v)
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
    for axis, z, lo, hi, plist in find_strips('x') + find_strips('y'):
        w = (hi - lo + 1) * C
        mid = plist[len(plist) // 2]
        if not test_cut(make_slice(axis, z, lo, hi, mid)):
            continue
        # Strip disconnects a branch: sweep positions along it to find maximal empty pocket
        for pos in plist:
            sl = make_slice(axis, z, lo, hi, pos)
            r2 = test_cut(sl)
            if not r2:
                continue
            for comp in r2:
                if comp & pois:
                    continue
                depth = pocket_depth(sl, comp)
                if depth > w:
                    pockets.append((depth, w, comp))

    # Keep maximal non-overlapping pockets
    pockets.sort(key=lambda x: (len(x[2]), x[0]), reverse=True)
    kept, used = [], set()
    for depth, w, comp in pockets:
        if len(comp & used) > len(comp) * 0.25:
            continue
        xs = [XMIN + i * C for i, j, _ in comp]
        ys = [YMIN + j * C for i, j, _ in comp]
        zs = [zz for _, _, zz in comp]
        kept.append(dict(
            depth=depth, width=w, cells=len(comp),
            x0=min(xs), x1=max(xs) + C, y0=min(ys), y1=max(ys) + C,
            zlo=min(zs), zhi=max(zs),
        ))
        used |= comp
    return kept


# ------------------------------------------------------------------ main check runner
def check_map(d, min_prism_sep=DEFAULT_MIN_PRISM_SEP, quiet=False):
    C, XMIN, YMIN, NX, NY, BOT, TOP = (d[k] for k in ('C', 'XMIN', 'YMIN', 'NX', 'NY', 'BOT', 'TOP'))
    cols = d['cols']
    AIR = build_air(cols, NX, NY, BOT, TOP)

    def out(*args, **kw):
        if not quiet:
            print(*args, **kw)

    def solid_at(x, y, z):
        i, j = int((x - XMIN) // C), int((y - YMIN) // C)
        if not (0 <= i < NX and 0 <= j < NY):
            return True
        return not any(a < z < b for a, b in AIR[i][j])

    nodes = set()
    for i in range(NX):
        for j in range(NY):
            for a, b in AIR[i][j]:
                if a > BOT and b - a >= HEAD:
                    nodes.add((i, j, a))

    TELEPORTS = {}
    for (r, z, dx, dy, dz, ang) in d.get('teleports', []) + d.get('pushes', []):
        dest = (int((dx - XMIN) // C), int((dy - YMIN) // C), dz)
        for i in range((r[0] - XMIN) // C, (r[2] - XMIN) // C):
            for j in range((r[1] - YMIN) // C, (r[3] - YMIN) // C):
                TELEPORTS[(i, j, z)] = dest

    def _neighbours_walk(n, step=STEP):
        i, j, z = n
        top_here = next((b for a, b in AIR[i][j] if a == z), None)
        if top_here is None:          # not a floor cell (e.g. a spawn placed inside solid)
            return
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            a2, b2 = i + di, j + dj
            if not (0 <= a2 < NX and 0 <= b2 < NY):
                continue
            for a, b in AIR[a2][b2]:
                if a <= BOT or a > z + step:
                    continue
                if b < max(a, z) + HEAD or top_here < a + HEAD:
                    continue
                if (a2, b2, a) in nodes:
                    yield (a2, b2, a)
        if step > STEP:
            # running jump across a real gap (floor at least 24 lower), up to 96 units, onto a landing <= +8
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                for dist in range(2, 7):
                    p, q = i + dist * di, j + dist * dj
                    if not (0 <= p < NX and 0 <= q < NY):
                        break
                    land = [a for a, b in AIR[p][q] if z - 128 <= a <= z + 8 and b - a >= HEAD and (p, q, a) in nodes]
                    mid_ok = all(any(a <= z - 24 and b >= z + HEAD for a, b in AIR[i + k * di][j + k * dj])
                                 for k in range(1, dist))
                    if not mid_ok:
                        break
                    for a in land:
                        yield (p, q, a)

    def neighbours(n, step=STEP):
        yield from _neighbours_walk(n, step)
        if n in TELEPORTS and TELEPORTS[n] in nodes:
            yield TELEPORTS[n]

    def bfs(start, step=STEP):
        seen = {start: 0}
        q = deque([start])
        while q:
            n = q.popleft()
            for m in neighbours(n, step):
                if m not in seen:
                    seen[m] = seen[n] + 1
                    q.append(m)
        return seen

    spawns = d['spawns']
    problems = []
    snodes = []
    for x, y, z, ang, lab in spawns:
        i, j = int((x - XMIN) // C), int((y - YMIN) // C)
        ok = True
        for di in (-1, 0):
            for dj in (-1, 0):
                if (i + di, j + dj, z) not in nodes:
                    ok = False
        if not ok:
            problems.append(f'spawn {lab} at {x},{y},{z} lacks floor/clearance')
        if (i, j, z) not in nodes:                    # v2: inside solid / off the floor - report, don't crash
            alt = [(i + di, j + dj, z) for di in (-1, 0) for dj in (-1, 0) if (i + di, j + dj, z) in nodes]
            problems.append(f'spawn {lab} at {x},{y},{z} is not on a floor cell' + (' (using a neighbour)' if alt else ''))
            snodes.append(alt[0] if alt else (i, j, z))
            continue
        snodes.append((i, j, z))

    reach_list = [bfs(s) for s in snodes]
    for (s, lab), r in zip(zip(snodes, [s[4] for s in spawns]), reach_list):
        missing = [spawns[k][4] for k, t in enumerate(snodes) if t not in r]
        if missing:
            problems.append(f'from {lab} cannot walk to: {missing}')

    r0 = reach_list[0] if reach_list else {}
    area = len(r0) * C * C
    _perch = lambda n: any(r[0] <= XMIN + n[0] * C < r[2] and r[1] <= YMIN + n[1] * C < r[3] and n[2] == pz
                           for r, pz in d.get('perches', []))
    unreached = [n for n in nodes if n not in r0 and n[2] > BOT and not _perch(n)]
    out(f'walkable floor reachable on foot: {area / 1e6:.2f} M sq units ({len(r0)} cells); '
        f'unreached floor cells: {len(unreached)}')
    if unreached:
        zs = {}
        for n in unreached:
            zs[n[2]] = zs.get(n[2], 0) + 1
        out('  unreached by height:', dict(sorted(zs.items())))

    # sightlines between spawns (eye = origin+22 = floor+46)
    vis_pairs = []
    for (a, b) in itertools.combinations(range(len(spawns)), 2):
        xa, ya, za = spawns[a][:3]
        xb, yb, zb = spawns[b][:3]
        za += 46
        zb += 46
        dist = math.dist((xa, ya, za), (xb, yb, zb))
        steps = max(1, int(dist // 4))
        clear = all(not solid_at(xa + (xb - xa) * t / steps, ya + (yb - ya) * t / steps, za + (zb - za) * t / steps)
                    for t in range(1, steps))
        if clear:
            vis_pairs.append((spawns[a][4], spawns[b][4], int(dist)))
    if len(spawns) >= 2:
        min_d = min((math.dist(p[:2], q[:2]), p[4], q[4]) for p, q in itertools.combinations(spawns, 2))
        out(f'spawns: {len(spawns)}; closest pair {min_d[1]} / {min_d[2]} at {min_d[0]:.0f} units')
    else:
        out(f'spawns: {len(spawns)}')
    out(f'spawn pairs with line of sight: {len(vis_pairs)}')
    for p in vis_pairs:
        out('   ', p)
    out('PROBLEMS:' if problems else 'no spawn/connectivity problems')
    for p in problems:
        out('  -', p)

    # ---------------------------------------------------------------- items
    items = d.get('items', [])
    iprob = []
    if items and snodes:
        jump = bfs(snodes[0], step=40)
        for cls, x, y, z, flags, lab in items:
            i, j = int((x - XMIN) // C), int((y - YMIN) // C)
            cells_ = [(i + di, j + dj, z) for di in (-1, 0) for dj in (-1, 0)]
            margin = [(i + di, j + dj, z) for di in (-2, -1, 0, 1) for dj in (-2, -1, 0, 1)]
            if not all(c in nodes for c in cells_):
                iprob.append(f'{lab} at {x},{y},{z}: no floor/clearance under item')
            elif not all(c in nodes for c in margin):
                iprob.append(f'{lab} at {x},{y},{z}: touches a wall/step edge (servers drop such items)')
            elif any(r[0] <= x < r[2] and r[1] <= y < r[3] and z == pz for r, pz in d.get('perches', [])):
                out(f'  note: {lab} at {x},{y},{z} is on a hook-only perch (by design)')
            elif not any(c in jump for c in cells_):
                iprob.append(f'{lab} at {x},{y},{z}: unreachable even with jumps')
            elif not any(c in r0 for c in cells_):
                out(f'  note: {lab} at {x},{y},{z} needs a jump')
        for r, pz in d.get('perches', []):
            pc = [(i, j, pz) for i in range(int((r[0] - XMIN) // C), int((r[2] - XMIN) // C))
                  for j in range(int((r[1] - YMIN) // C), int((r[3] - YMIN) // C))]
            if not any(c in nodes for c in pc):
                iprob.append(f'perch {r} @{pz}: no standing room')
            elif any(c in jump for c in pc):
                iprob.append(f'perch {r} @{pz}: reachable with a plain jump (not hook-only)')
        for a, b in itertools.combinations(items, 2):
            if a[3] == b[3] and math.dist(a[1:3], b[1:3]) < 48:
                iprob.append(f'items overlap: {a[5]} {a[1:4]} / {b[5]} {b[1:4]}')
        for it in items:
            for sp in spawns:
                if abs(it[3] - sp[2]) < 48 and math.dist(it[1:3], sp[:2]) < 72:
                    iprob.append(f'{it[5]} at {it[1:4]} sits on spawn {sp[4]}')
        out('items:', dict(Counter(it[5] for it in items)))
        groups = {}
        for cls, x, y, z, flags, lab in items:
            if cls.startswith('weapon_') or lab in ('RA', 'YA', 'MH', 'QUAD'):
                i, j = int((x - XMIN) // C), int((y - YMIN) // C)
                groups.setdefault(lab, []).append((i, j, z))
        out('walk distance from each spawn to nearest (units, jumps allowed):')
        hdr = sorted(groups)
        out('   %-12s' % 'spawn' + ''.join('%6s' % h for h in hdr))
        for sn, sp in zip(snodes, spawns):
            dist = bfs(sn, step=40)
            row = []
            for h in hdr:
                ds = [dist[c] for g in groups[h] for c in [(g[0] + di, g[1] + dj, g[2]) for di in (-1, 0) for dj in (-1, 0)] if c in dist]
                row.append('%6d' % (min(ds) * C) if ds else '     -')
            out('   %-12s' % sp[4] + ''.join(row))
        out('ITEM PROBLEMS:' if iprob else 'no item problems')
        for p in iprob:
            out('  -', p)

    # ---------------------------------------------------------------- traps
    reach = bfs(snodes[0], step=40) if snodes else {}
    trap_groups = []
    if snodes:
        radj = {}
        for n in reach:
            for m in neighbours(n, 40):
                radj.setdefault(m, []).append(n)
        back = {snodes[0]}
        q = deque([snodes[0]])
        while q:
            n = q.popleft()
            for m in radj.get(n, []):
                if m not in back:
                    back.add(m)
                    q.append(m)
        traps = [n for n in reach if n not in back]
        if not traps:
            out('no traps: every reachable spot has a walk/jump route back')
        else:
            trapset = set(traps)
            seen = set()
            for t in traps:
                if t in seen:
                    continue
                grp, qq = [], deque([t])
                seen.add(t)
                while qq:
                    n = qq.popleft()
                    grp.append(n)
                    i, j, z = n
                    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        m = (i + di, j + dj, z)
                        if m in trapset and m not in seen:
                            seen.add(m)
                            qq.append(m)
                trap_groups.append(grp)
            out(f'TRAPS: {len(trap_groups)} area(s) you can get into but not out of without a rocket jump:')
            for g in sorted(trap_groups, key=len, reverse=True):
                xs = [XMIN + i * C for i, j, z in g]
                ys = [YMIN + j * C for i, j, z in g]
                out(f'  - floor {g[0][2]}: x {min(xs)}..{max(xs) + C}, y {min(ys)}..{max(ys) + C} ({len(g)} cells)')

    # ---------------------------------------------------------------- stair feet & 16-unit slots
    def floor_cells(rect, z):
        bad = []
        for x in range(rect[0], rect[2], C):
            for y in range(rect[1], rect[3], C):
                i, j = int((x - XMIN) // C), int((y - YMIN) // C)
                if not (0 <= i < NX and 0 <= j < NY) or not any(a == z and b - a >= HEAD for a, b in AIR[i][j]):
                    bad.append((x, y))
        return bad

    foot_bad = []
    for rect, z in d.get('feet', []):
        b = floor_cells(rect, z)
        if b:
            foot_bad.append(f'stair foot {rect} @ {z}: {len(b)} of {((rect[2]-rect[0])//C)*((rect[3]-rect[1])//C)} cells blocked, e.g. {b[:3]}')

    def wall_at(i, j, z):
        if not (0 <= i < NX and 0 <= j < NY):
            return True
        return not any(a <= z + STEP and b >= z + HEAD for a, b in AIR[i][j])

    slots = set()
    for (i, j, z) in nodes:
        if any(wall_at(i + di, j + dj, z) and wall_at(i - di, j - dj, z) for di, dj in ((1, 0), (0, 1))):
            slots.add((XMIN + i * C, YMIN + j * C, z))
    out('stair feet: ' + (f'{len(foot_bad)} PROBLEMS' if foot_bad else f'all {len(d.get("feet", []))} clear'))
    for t in foot_bad:
        out('  - ' + t)
    out('16-unit slots: ' + (f'{len(slots)} PROBLEM cells, e.g. {sorted(slots)[:6]}' if slots else 'none'))

    # ---------------------------------------------------------------- prism separation
    prisms = d.get('prisms', [])
    prism_bad = check_prism_separation(d, AIR, min_sep=min_prism_sep)
    if not prisms:
        out(f'prism separation (< {min_prism_sep:g}): none (no prisms)')
    elif prism_bad:
        out(f'prism separation (< {min_prism_sep:g}): {len(prism_bad)} PROBLEMS')
        for p in prism_bad:
            out('  - ' + p)
    else:
        out(f'prism separation (< {min_prism_sep:g}): all {len(prisms)} clear')

    # ---------------------------------------------------------------- blind pockets
    pockets = check_pockets(d, reach, neighbours) if snodes else []
    if not pockets:
        out('blind pockets (depth > width, no item/spawn): none')
    else:
        out(f'BLIND POCKETS: {len(pockets)} empty dead-end(s) deeper than their opening is wide:')
        for pk in pockets:
            zr = f"{pk['zlo']}" if pk['zlo'] == pk['zhi'] else f"{pk['zlo']}..{pk['zhi']}"
            out(f"  - floor {zr}: x {pk['x0']}..{pk['x1']}, y {pk['y0']}..{pk['y1']} "
                f"(depth {pk['depth']} > opening {pk['width']}, {pk['cells']} cells)")

    return dict(
        problems=problems,
        item_problems=iprob,
        traps=trap_groups,
        stair_feet=foot_bad,
        slots=sorted(slots),
        prism_separation=prism_bad,
        pockets=pockets,
    )


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    min_prism_sep = DEFAULT_MIN_PRISM_SEP
    if '--min-prism-sep' in args:
        idx = args.index('--min-prism-sep')
        min_prism_sep = float(args[idx + 1])
        del args[idx:idx + 2]
    if not args:
        print('usage: check.py <map.json> [--min-prism-sep 64]', file=sys.stderr)
        sys.exit(1)
    with open(args[0]) as fh:
        d = json.load(fh)
    return check_map(d, min_prism_sep=min_prism_sep)


if __name__ == '__main__':
    main()
