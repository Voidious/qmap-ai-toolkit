"""CTF layout and route-independence diagnostics on compiled Quake maps (BSP29).

Measures flag-to-flag distance/symmetry, visually independent (LOS-separated) routes
across midfield (0.30..0.70) and base-to-base (0.15..0.85) geodesic bands, sampled
single-vantage midfield chokes, heuristic flag-room exits, flag sightline exposure, and
both hook-off (walk/jump/tele/pad/swim) and hook-on (grapple swing/climb) flag routes on
the compiled BSP29 collision hulls.

    python3 ctfprofile.py map.bsp [more.bsp ...] [--json out.json] [--png-dir figs/] [--no-hook]

Treats outputs as design diagnostics, not release gates. Movement model: walk/step 18,
jump 44, running gaps up to 128, drops, teleporters (0.15 s), push pads, and water swimming
(220 u/s) for hook-off, plus uncalibrated kinematic grapple swings/climbs anchored to solid
or sky (650 u/s pull + 0.35 s latch) for hook-on. Moving brush entities are omitted from
static collision (matching vprofile.py): func_door brushes count as always open (optimistic
for button-locked doors), while func_plat lifts are absent (pessimistic for lift climbs).
"""
import argparse
import heapq
import json
import math
import os
import sys
from collections import Counter, defaultdict, deque

import numpy as np
from numba import njit

import vprofile

EYE = vprofile.EYE
BODY = vprofile.BODY
C = vprofile.C

WALK_SPEED = 320.0
SWIM_SPEED = 220.0
HOOK_SPEED = 650.0
HOOK_LATCH_S = 0.35
TELE_COST_S = 0.15
HOOK_MIN_RANGE = 96.0
HOOK_MAX_RANGE = 1024.0
LOS_ROUTE_RANGE = 1200.0
VANTAGE_LOS_RANGE = 1500.0


# ------------------------------------------------------------------ numba kernels
@njit(cache=True)
def _los_multi(roots0, nplane, nchild, lcont, pn, pd, ax, ay, az, bx, by, bz):
    """True when ray (a -> b) is clear across world hull 0 and all func_wall hull-0 trees."""
    for r0 in roots0:
        if not vprofile._los(r0, nplane, nchild, lcont, pn, pd, ax, ay, az, bx, by, bz):
            return False
    return True


@njit(cache=True)
def _is_anchor_leaf(roots0, nplane, nchild, lcont, pn, pd, x, y, z):
    """True when (x, y, z) lies inside solid (-2) or sky (-6) in world or func_wall hull 0."""
    for r0 in roots0:
        c = vprofile._leaf(r0, nplane, nchild, lcont, pn, pd, x, y, z)
        if c == -2 or c == -6:
            return True
    return False


@njit(cache=True)
def _los_mask_from_point(roots0, nplane, nchild, lcont, pn, pd,
                         vx, vy, vz, P, idx_arr, max_range):
    """Boolean mask over idx_arr where (vx, vy, vz+EYE) sees P[m]+(0,0,BODY) within max_range."""
    M = len(idx_arr)
    out = np.zeros(M, np.bool_)
    r2 = max_range * max_range
    ez = vz + EYE
    for k in range(M):
        m = idx_arr[k]
        mx, my, mz = P[m, 0], P[m, 1], P[m, 2]
        dx = mx - vx
        dy = my - vy
        dz = mz - vz
        if dx * dx + dy * dy + dz * dz <= r2:
            if _los_multi(roots0, nplane, nchild, lcont, pn, pd,
                          vx, vy, ez, mx, my, mz + BODY):
                out[k] = True
    return out


@njit(cache=True)
def _los_mask_from_points(roots0, nplane, nchild, lcont, pn, pd,
                          src_pts, P, idx_arr, max_range):
    """Boolean mask over idx_arr where ANY point in src_pts sees P[m] within max_range."""
    M = len(idx_arr)
    S = len(src_pts)
    out = np.zeros(M, np.bool_)
    r2 = max_range * max_range
    for k in range(M):
        m = idx_arr[k]
        mx, my, mz = P[m, 0], P[m, 1], P[m, 2]
        tbz = mz + BODY
        for s in range(S):
            sx, sy, sz = src_pts[s, 0], src_pts[s, 1], src_pts[s, 2]
            dx = mx - sx
            dy = my - sy
            dz = mz - sz
            if dx * dx + dy * dy + dz * dz <= r2:
                if _los_multi(roots0, nplane, nchild, lcont, pn, pd,
                              sx, sy, sz + EYE, mx, my, tbz):
                    out[k] = True
                    break
    return out


@njit(cache=True)
def _max_los_to_target(roots0, nplane, nchild, lcont, pn, pd, P, idx_arr, tx, ty, tz):
    """Longest 2D distance from any node in idx_arr with direct eye-to-body LOS to (tx, ty, tz)."""
    best = 0.0
    tbz = tz + BODY
    for k in range(len(idx_arr)):
        m = idx_arr[k]
        mx, my, mz = P[m, 0], P[m, 1], P[m, 2]
        d = math.sqrt((mx - tx) ** 2 + (my - ty) ** 2)
        if d <= best:
            continue
        if _los_multi(roots0, nplane, nchild, lcont, pn, pd,
                      mx, my, mz + EYE, tx, ty, tbz):
            best = d
    return best


@njit(cache=True)
def _hull1_clear(roots, cplane, cchild, pn, pd, x1, y1, z1, x2, y2, z2):
    """True when player hull 1 can sweep linearly from p1 to p2 with zero solid hit."""
    for r in roots:
        code, _, _, _, _, _ = vprofile._rcheck_iter(
            r, cplane, cchild, pn, pd, x1, y1, z1, x2, y2, z2
        )
        if code != 0:
            return False
    return True


@njit(cache=True)
def _has_hook_anchor(roots0, nplane, nchild, lcont, pn, pd,
                     ax, ay, az, bx, by, bz, max_range):
    """True when a hook ray from A's eye can latch onto solid (-2) or sky (-6) behind or above B
    within total distance `max_range` from A's eye."""
    ex, ey, ez = ax, ay, az + EYE
    # 1. Ray through B+(0,0,48) continuing up to 448u past B, capped at total distance max_range
    tx, ty, tz = bx, by, bz + 48.0
    dx, dy, dz = tx - ex, ty - ey, tz - ez
    L = math.sqrt(dx * dx + dy * dy + dz * dz)
    if 1.0 < L <= max_range and _los_multi(roots0, nplane, nchild, lcont, pn, pd, ex, ey, ez, tx, ty, tz):
        ux, uy, uz = dx / L, dy / L, dz / L
        for step in range(1, 29):
            dist = step * 16.0
            if L + dist > max_range:
                break
            if _is_anchor_leaf(roots0, nplane, nchild, lcont, pn, pd,
                               tx + ux * dist, ty + uy * dist, tz + uz * dist):
                return True
    # 2. Ceiling/wall anchor above B (96..384u above B's floor) visible from A_eye within max_range
    max2 = max_range * max_range
    for h_off in (96.0, 160.0, 256.0, 384.0):
        cz = bz + h_off
        cdx = bx - ex
        cdy = by - ey
        cdz = cz - ez
        if cdx * cdx + cdy * cdy + cdz * cdz > max2:
            continue
        if _is_anchor_leaf(roots0, nplane, nchild, lcont, pn, pd, bx, by, cz):
            # Check ray from A_eye to just below this anchor is unobstructed
            if _los_multi(roots0, nplane, nchild, lcont, pn, pd, ex, ey, ez, bx, by, cz - 16.0):
                return True
    return False


@njit(cache=True)
def _build_hook_edges(roots, cplane, cchild, roots0, nplane, nchild, lcont, pn, pd,
                      P, wp_ids, min_range, max_range):
    """Compute valid grapple swing/climb edges between waypoint floor nodes.
    Keeps up to one longest clear edge per (12 azimuth x 3 vertical) sector per
    source waypoint plus all edges landing on the first two waypoints (the flags),
    bounding graph degree while preserving long swings and vertical climbs."""
    W = len(wp_ids)
    min2 = min_range * min_range
    max2 = max_range * max_range
    out_u = []
    out_v = []
    out_d = []
    # 12 azimuth bins x 3 elevation bins (down < -32, level, up > +32)
    NBINS = 36
    best_v = np.full(NBINS, -1, np.int64)
    best_d = np.zeros(NBINS, np.float64)
    for a in range(W):
        u = wp_ids[a]
        ax, ay, az = P[u, 0], P[u, 1], P[u, 2]
        a_clear = _hull1_clear(roots, cplane, cchild, pn, pd, ax, ay, az + 25.0, ax, ay, az + 40.0)
        if not a_clear:
            continue
        for k in range(NBINS):
            best_v[k] = -1
            best_d[k] = 0.0
        for b in range(W):
            if a == b:
                continue
            v = wp_ids[b]
            bx, by, bz = P[v, 0], P[v, 1], P[v, 2]
            dx = bx - ax
            dy = by - ay
            dz = bz - az
            d2 = dx * dx + dy * dy + dz * dz
            if d2 < min2 or d2 > max2:
                continue
            d = math.sqrt(d2)
            # Determine sector bin
            az_bin = int(math.floor((math.atan2(dy, dx) + math.pi) / (2.0 * math.pi) * 12.0)) % 12
            el_bin = 0 if dz < -32.0 else (2 if dz > 32.0 else 1)
            sec = az_bin * 3 + el_bin
            # Skip expensive traces if a longer valid edge already fills this sector (except flags at b < 2)
            if b >= 2 and d <= best_d[sec]:
                continue
            if not _hull1_clear(roots, cplane, cchild, pn, pd, bx, by, bz + 25.0, bx, by, bz + 40.0):
                continue
            flight_ok = _hull1_clear(roots, cplane, cchild, pn, pd,
                                     ax, ay, az + 40.0, bx, by, bz + 40.0)
            if not flight_ok and dz > 24.0:
                hi_z = bz + 40.0
                if (_hull1_clear(roots, cplane, cchild, pn, pd, ax, ay, az + 25.0, ax, ay, hi_z)
                        and _hull1_clear(roots, cplane, cchild, pn, pd, ax, ay, hi_z, bx, by, hi_z)):
                    flight_ok = True
            if not flight_ok:
                continue
            if not _has_hook_anchor(roots0, nplane, nchild, lcont, pn, pd,
                                    ax, ay, az, bx, by, bz, max_range):
                continue
            if b < 2:
                out_u.append(u)
                out_v.append(v)
                out_d.append(d)
            elif d > best_d[sec]:
                best_d[sec] = d
                best_v[sec] = v
        for k in range(NBINS):
            if best_v[k] >= 0:
                out_u.append(u)
                out_v.append(best_v[k])
                out_d.append(best_d[k])
    return out_u, out_v, out_d


# ------------------------------------------------------------------ graph helpers
def _add_water_swim_edges(B, adj, nodes, x0, y0, colof, nid, S1, LC):
    """Connect water-submerged floor nodes to adjacent ledges reachable by swimming up."""
    in_water = []
    for n, (i, j, f) in enumerate(nodes):
        x, y = x0 + i * C + 8, y0 + j * C + 8
        if LC(x, y, f + 8) == -3 or LC(x, y, f + 32) == -3:
            in_water.append(n)
    if not in_water:
        return 0
    added = 0
    D8 = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
    for n in in_water:
        i, j, f = nodes[n]
        x, y = x0 + i * C + 8, y0 + j * C + 8
        z_top = f + 8.0
        while z_top < f + 512.0 and LC(x, y, z_top) == -3 and not S1(x, y, z_top + 24.0):
            z_top += 16.0
        for di, dj in D8:
            fl = colof.get((i + di, j + dj))
            if not fl:
                continue
            nx_, ny_ = x0 + (i + di) * C + 8, y0 + (j + dj) * C + 8
            for k, g in enumerate(fl):
                if f + 18.0 < g <= z_top + 32.0 and not S1(nx_, ny_, g + 25.0):
                    m = nid[(i + di, j + dj, k)]
                    cost = C * math.hypot(di, dj) + (g - f) * 1.2
                    adj[n].append((m, cost, 'swim'))
                    added += 1
    return added


def _dijk_single(adj, start, goal, forbidden=None):
    """Shortest path from start to goal avoiding forbidden node ids (except start/goal)."""
    dist = {start: 0.0}
    prev = {}
    prev_kind = {}
    h = [(0.0, start)]
    while h:
        d, u = heapq.heappop(h)
        if u == goal:
            path = [u]
            kinds = []
            while path[-1] != start:
                kinds.append(prev_kind[path[-1]])
                path.append(prev[path[-1]])
            path.reverse()
            kinds.reverse()
            return d, path, kinds
        if d > dist.get(u, 1e18):
            continue
        for v, c, k in adj[u]:
            if forbidden and v in forbidden and v != goal and v != start:
                continue
            nd = d + c
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = u
                prev_kind[v] = k
                heapq.heappush(h, (nd, v))
    return None, None, None


def _dijk_all(adj, start):
    """Single-source shortest-path distances from start."""
    dist = {start: 0.0}
    h = [(0.0, start)]
    while h:
        d, u = heapq.heappop(h)
        if d > dist.get(u, 1e18):
            continue
        for v, c, _ in adj[u]:
            nd = d + c
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                heapq.heappush(h, (nd, v))
    return dist


def _shell_exit_components(adj_undir, dist, radius, target_node=None, cont_margin=256.0):
    """Return sorted sizes of shell components at `radius` that continue outward.

    Dead-end room corners/alcoves are pruned by requiring each shell component
    to have a path staying outside (`d >= radius - 24`) to `target_node` (when
    reachable) or at least `radius + cont_margin` from the flag.
    """
    outer = {u for u, d in dist.items() if d >= radius - 24.0}
    shell = {u for u, d in dist.items() if radius - 24.0 <= d <= radius + 40.0}
    if not shell:
        return []
    use_target = (target_node is not None) and (target_node in outer)
    far_thresh = radius + cont_margin
    seen = set()
    sizes = []
    for u in shell:
        if u in seen:
            continue
        comp = []
        st = [u]
        seen.add(u)
        while st:
            x = st.pop()
            comp.append(x)
            for v, _ in adj_undir[x]:
                if v in shell and v not in seen:
                    seen.add(v)
                    st.append(v)
        if len(comp) < 3:
            continue
        vis_out = set(comp)
        st_out = list(comp)
        reaches_out = False
        while st_out:
            x = st_out.pop()
            if (use_target and x == target_node) or (not use_target and dist[x] >= far_thresh):
                reaches_out = True
                break
            for v, _ in adj_undir[x]:
                if v in outer and v not in vis_out:
                    vis_out.add(v)
                    st_out.append(v)
        if reaches_out:
            sizes.append(len(comp))
    sizes.sort(reverse=True)
    return sizes


def _count_flag_exits(adj_undir, flag_node, radius=None, target_node=None):
    """Estimate distinct passage exits leaving a flag room via outward-pruned geodesic shells.

    When `radius` is None (default), starts at 384u and advances through (512, 640, 768)
    only while the shell remains a single wide open-room interior (>= 64 cells, wider than
    a ~256u corridor), avoiding undercounting large open flag rooms without chasing
    downstream forks past a narrow single doorway. Pass an explicit `radius` for a fixed-
    radius shell check.
    """
    radii = (384.0, 512.0, 640.0, 768.0) if radius is None else (float(radius),)
    cont_margin = 256.0 if radius is None else min(256.0, max(48.0, 0.4 * float(radius)))
    max_d = None if target_node is not None else (max(radii) + cont_margin + 64.0)

    dist = {flag_node: 0.0}
    h = [(0.0, flag_node)]
    while h:
        d, u = heapq.heappop(h)
        if d > dist[u]:
            continue
        if max_d is not None and d > max_d:
            continue
        for v, c in adj_undir[u]:
            nd = d + c
            if nd < dist.get(v, 1e18) and (max_d is None or nd <= max_d):
                dist[v] = nd
                heapq.heappush(h, (nd, v))

    last_count = 0
    for r in radii:
        sizes = _shell_exit_components(
            adj_undir, dist, r, target_node=target_node, cont_margin=cont_margin
        )
        if not sizes:
            break
        last_count = len(sizes)
        if last_count >= 2:
            return last_count
        # Single component narrower than a wide open room (< 64 cells in a 64u-thick shell):
        # we have already passed through a single doorway/corridor, so stop here.
        if sizes[0] < 64:
            return 1
    return last_count


def _geodesic_progress(adj_undir, f1, f2, N):
    """Harmonic/geodesic progress g in [0, 1] between f1 (0) and f2 (1).
    Works identically on straight, curved, L-shaped, and U-shaped CTF layouts."""
    d1 = _dijk_all(adj_undir, f1)
    d2 = _dijk_all(adj_undir, f2)
    g = np.full(N, -1.0, dtype=np.float64)
    for u in range(N):
        if u in d1 and u in d2:
            denom = d1[u] + d2[u]
            g[u] = 0.5 if denom <= 1e-6 else d1[u] / denom
    return g


def _sample_path_points(P, path, band_set, min_step=48.0):
    """Subsample points along the portion of path inside band_set (always keeping endpoints)."""
    in_band = [n for n in path if n in band_set]
    if not in_band:
        return np.zeros((0, 3), dtype=np.float64)
    kept = [in_band[0]]
    last = P[in_band[0]]
    for n in in_band[1:-1]:
        if np.linalg.norm(P[n] - last) >= min_step:
            kept.append(n)
            last = P[n]
    if in_band[-1] != kept[-1]:
        kept.append(in_band[-1])
    return P[kept]


def analyze_band_routes(adj, f1, f2, P, band_nodes, los_fn_points, los_fn_single,
                        spatial_radius=384.0, max_los_routes=4, max_sp_routes=4,
                        vantage_grid=128.0):
    """Analyze LOS-separated routes, spatially-separated routes, and single-vantage chokes
    within a given geodesic band (e.g. midfield [0.30, 0.70] or full [0.15, 0.85]).

    Single-vantage checks are sampled deterministically across every ~`vantage_grid`-unit
    3D cell in the band plus waypoints along the shortest route (diagnostic sample, not an
    exhaustive proof over every 16u cell).

    los_fn_points(src_pts, band_nodes) -> bool array over band_nodes
    los_fn_single(v_pt, band_nodes) -> bool array over band_nodes
    """
    band_arr = np.asarray(band_nodes, dtype=np.int64)
    band_set = set(int(x) for x in band_arr)

    # 1. Iterative LOS-separated routes
    los_routes = []
    forb = set()
    for _ in range(max_los_routes):
        cost, path, kinds = _dijk_single(adj, f1, f2, forb)
        if cost is None:
            break
        los_routes.append((float(cost), path, kinds))
        src_pts = _sample_path_points(P, path, band_set, min_step=64.0)
        if len(src_pts) == 0 or len(band_arr) == 0:
            break
        mask = los_fn_points(src_pts, band_arr)
        for idx in np.nonzero(mask)[0]:
            forb.add(int(band_arr[idx]))

    # 2. Iterative spatially-separated routes (3D radius exclusion)
    sp_routes = []
    forb_sp = set()
    band_pts = P[band_arr] if len(band_arr) else np.zeros((0, 3))
    r2 = spatial_radius * spatial_radius
    for _ in range(max_sp_routes):
        cost, path, kinds = _dijk_single(adj, f1, f2, forb_sp)
        if cost is None:
            break
        sp_routes.append((float(cost), path, kinds))
        src_pts = _sample_path_points(P, path, band_set, min_step=48.0)
        if len(src_pts) == 0 or len(band_pts) == 0:
            break
        # Chunked distance check to avoid huge peak memory on very large maps
        blocked = np.zeros(len(band_arr), dtype=bool)
        for s0 in range(0, len(src_pts), 64):
            sub = src_pts[s0:s0 + 64]
            d2 = np.min(
                (band_pts[:, None, 0] - sub[None, :, 0]) ** 2
                + (band_pts[:, None, 1] - sub[None, :, 1]) ** 2
                + (band_pts[:, None, 2] - sub[None, :, 2]) ** 2,
                axis=1,
            )
            blocked |= (d2 <= r2)
        for idx in np.nonzero(blocked)[0]:
            forb_sp.add(int(band_arr[idx]))

    # 3. Single-vantage choke test (sampled): test ~20 route-1 points plus every ~128u
    # spatial voxel in the band to check if one standing defender sees every crossing.
    vantage_cuts_all = False
    worst_bypass = None
    worst_vantage_pos = None
    if los_routes and len(band_arr):
        base_cost = los_routes[0][0]
        p1_set = set(los_routes[0][1])
        worst_bypass = base_cost
        p1_band = [n for n in los_routes[0][1] if n in band_set]
        cands = []
        if p1_band:
            stride = max(1, len(p1_band) // 20)
            cands.extend(p1_band[::stride])
        seen_cells = set()
        for n_id in band_arr:
            idx_n = int(n_id)
            cell = (
                int(round(P[idx_n, 0] / vantage_grid)),
                int(round(P[idx_n, 1] / vantage_grid)),
                int(round(P[idx_n, 2] / vantage_grid)),
            )
            if cell not in seen_cells:
                seen_cells.add(cell)
                cands.append(idx_n)
        cands = list(dict.fromkeys(cands))
        for v_id in cands:
            mask = los_fn_single(P[v_id], band_arr)
            seen_v = set(int(band_arr[idx]) for idx in np.nonzero(mask)[0])
            if not seen_v or seen_v.isdisjoint(p1_set):
                continue
            cv, _, _ = _dijk_single(adj, f1, f2, seen_v)
            if cv is None:
                vantage_cuts_all = True
                worst_bypass = None
                worst_vantage_pos = tuple(round(float(x)) for x in P[v_id])
                break
            if cv > worst_bypass:
                worst_bypass = float(cv)
                worst_vantage_pos = tuple(round(float(x)) for x in P[v_id])

    # 4. Lateral & vertical separation between first two LOS-separated routes
    lat_sep = 0.0
    vert_sep = 0.0
    if len(los_routes) >= 2:
        p1b = [n for n in los_routes[0][1] if n in band_set]
        p2b = [n for n in los_routes[1][1] if n in band_set]
        if p1b and p2b:
            pts1 = P[p1b]
            pts2 = P[p2b]
            # Median 2D distance from each point on route 2 to closest point on route 1
            dxy = np.min(
                np.hypot(pts2[:, None, 0] - pts1[None, :, 0],
                         pts2[:, None, 1] - pts1[None, :, 1]),
                axis=1,
            )
            lat_sep = float(np.median(dxy))
            vert_sep = float(abs(np.median(pts2[:, 2]) - np.median(pts1[:, 2])))

    return dict(
        los_routes=los_routes,
        sp_routes=sp_routes,
        vantage_cuts_all=vantage_cuts_all,
        worst_bypass=worst_bypass,
        worst_vantage_pos=worst_vantage_pos,
        lat_sep=lat_sep,
        vert_sep=vert_sep,
    )


def _find_flag_node(B, cl, P, R_mask):
    """Locate the floor node closest to a CTF flag entity."""
    for e in B.ents:
        if e.get('classname') == cl:
            o = vprofile.origin(e)
            cand = np.nonzero(R_mask)[0]
            if len(cand) == 0:
                cand = np.arange(len(P))
            # Prefer close in XY and near feet height
            dx = P[cand, 0] - o[0]
            dy = P[cand, 1] - o[1]
            dz = np.abs(P[cand, 2] - (o[2] - 16.0))
            near = (np.abs(dx) <= 64.0) & (np.abs(dy) <= 64.0) & (dz <= 96.0)
            if np.any(near):
                sub = cand[near]
                sc = np.hypot(P[sub, 0] - o[0], P[sub, 1] - o[1]) + np.abs(P[sub, 2] - (o[2] - 16.0))
                return int(sub[int(np.argmin(sc))]), o
            d3 = np.linalg.norm(P[cand] - o, axis=1)
            return int(cand[int(np.argmin(d3))]), o
    return None, None


def _build_walk_time_graph(adj_walk):
    """Build a time-weighted (seconds) graph for walk/jump/drop/pad (320 u/s),
    water swimming (220 u/s), and teleporters (0.15 s)."""
    adj_t = defaultdict(list)
    for u, edges in adj_walk.items():
        for v, c, k in edges:
            if k == 'tele':
                t = TELE_COST_S
            elif k == 'swim':
                t = c / SWIM_SPEED
            else:
                t = c / WALK_SPEED
            adj_t[u].append((v, t, k))
    return adj_t


def _build_hook_time_graph(adj_walk_t, nodes, P, R_walk, f1, f2,
                           roots, B, roots0):
    """Extend a walk+swim+tele time graph (seconds) with grapple hook swings/climbs
    between spatial waypoints."""
    adj_t = defaultdict(list, {u: list(edges) for u, edges in adj_walk_t.items()})

    # Select waypoints: ~128u spatial stride across all floor nodes (including ledges
    # unreachable on foot so hook-only climbs and hook-gated routes are modeled),
    # with flags always placed first at indices 0 and 1.
    wp_extra = set()
    for n, (i, j, _f) in enumerate(nodes):
        if (i % 8 == 0) and (j % 8 == 0) and n not in (f1, f2):
            wp_extra.add(n)
    wp_ids = np.array([f1, f2] + sorted(wp_extra), dtype=np.int64)

    hu, hv, hd = _build_hook_edges(
        roots, B.cplane, B.cchild, roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd,
        P, wp_ids, HOOK_MIN_RANGE, HOOK_MAX_RANGE,
    )
    for u, v, d in zip(hu, hv, hd):
        t = HOOK_LATCH_S + d / HOOK_SPEED
        adj_t[int(u)].append((int(v), t, 'hook'))

    return adj_t, len(hu)


# ------------------------------------------------------------------ main profile
def ctf_profile(path, name=None, with_hook=True):
    """Profile a compiled CTF BSP29 map for route topology, flag exposure, and hook/walk travel."""
    name = name or os.path.splitext(os.path.basename(path))[0]
    vp = vprofile.profile(path, name=name, with_navigation=True)
    nav = vp.pop('_navigation')
    draw_d = vp.pop('_draw')
    vp.pop('_check')
    B = nav['bsp']
    adj_walk = nav['adjacency']
    nodes = draw_d['nodes']
    x0, y0 = draw_d['x0'], draw_d['y0']
    R_init = np.array(draw_d['R'], dtype=bool)
    N = len(nodes)

    P = np.zeros((N, 3), dtype=np.float64)
    for n, (i, j, f) in enumerate(nodes):
        P[n, 0] = x0 + i * C + 8.0
        P[n, 1] = y0 + j * C + 8.0
        P[n, 2] = f

    # Reconstruct column index and clip/leaf lookups for water swim + hook kernels
    colof = defaultdict(list)
    nid = {}
    for n, (i, j, f) in enumerate(nodes):
        colof[(i, j)].append(f)
    for key in colof:
        colof[key].sort()
    for n, (i, j, f) in enumerate(nodes):
        nid[(i, j, colof[(i, j)].index(f))] = n

    m0 = B.models[0]
    roots = [int(m0['h'][1])]
    roots0 = [int(m0['h'][0])]
    for e in B.ents:
        if e.get('classname') == 'func_wall' and vprofile.model_index(e):
            mi = vprofile.model_index(e)
            roots.append(int(B.models[mi]['h'][1]))
            orig_s = e.get('origin', '').strip()
            if not orig_s or all(abs(float(t)) < 1e-6 for t in orig_s.split()[:3]):
                roots0.append(int(B.models[mi]['h'][0]))
    roots = np.array(roots, np.int64)
    roots0 = np.array(roots0, np.int64)
    root0 = int(m0['h'][0])
    S1 = lambda x, y, z: vprofile._solid1(roots, B.cplane, B.cchild, B.pn, B.pd, x, y, z)
    LC = lambda x, y, z: vprofile._leaf(root0, B.nplane, B.nchild, B.lcont, B.pn, B.pd, x, y, z)

    swim_edges = _add_water_swim_edges(B, adj_walk, nodes, x0, y0, colof, nid, S1, LC)

    f1, o1 = _find_flag_node(B, 'item_flag_team1', P, R_init)
    f2, o2 = _find_flag_node(B, 'item_flag_team2', P, R_init)
    if f1 is None or f2 is None:
        raise ValueError(f'{path}: missing item_flag_team1 or item_flag_team2')

    # Walk+swim reachability expanded from flags and spawns
    R_walk = R_init.copy()
    dq = deque(int(x) for x in np.nonzero(R_walk)[0])
    for fn in (f1, f2):
        if not R_walk[fn]:
            R_walk[fn] = True
            dq.append(fn)
    while dq:
        u = dq.popleft()
        for v, _, _ in adj_walk[u]:
            if not R_walk[v]:
                R_walk[v] = True
                dq.append(v)

    # Undirected walk graph (excluding teleporters for exits, including all for geodesic progress)
    adj_u_all = defaultdict(list)
    adj_u_notele = defaultdict(list)
    for u in range(N):
        if not R_walk[u]:
            continue
        for v, c, k in adj_walk[u]:
            if not R_walk[v]:
                continue
            adj_u_all[u].append((v, c, k))
            adj_u_all[v].append((u, c, k))
            if k != 'tele':
                adj_u_notele[u].append((v, c))
                adj_u_notele[v].append((u, c))

    gap2d = float(np.hypot(P[f2, 0] - P[f1, 0], P[f2, 1] - P[f1, 1]))
    gap3d = float(np.linalg.norm(P[f2] - P[f1]))

    L12, path12, _ = _dijk_single(adj_walk, f1, f2)
    L21, path21, _ = _dijk_single(adj_walk, f2, f1)
    walk_connected = (L12 is not None) and (L21 is not None)

    adj_walk_t = _build_walk_time_graph(adj_walk)
    WT12, _, _ = _dijk_single(adj_walk_t, f1, f2)
    WT21, _, _ = _dijk_single(adj_walk_t, f2, f1)

    exits1 = _count_flag_exits(adj_u_notele, f1, target_node=f2)
    exits2 = _count_flag_exits(adj_u_notele, f2, target_node=f1)

    reach_idx = np.nonzero(R_walk)[0].astype(np.int64)
    flag1_los = float(_max_los_to_target(
        roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd, P, reach_idx, P[f1, 0], P[f1, 1], P[f1, 2]
    ))
    flag2_los = float(_max_los_to_target(
        roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd, P, reach_idx, P[f2, 0], P[f2, 1], P[f2, 2]
    ))
    flags_mut_los = bool(_los_multi(
        roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd,
        P[f1, 0], P[f1, 1], P[f1, 2] + EYE,
        P[f2, 0], P[f2, 1], P[f2, 2] + BODY,
    ))

    # Fast numba LOS closures (world + func_wall hull 0; func_door remains open/transparent)
    def los_pts(src_pts, b_arr):
        return _los_mask_from_points(
            roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd, src_pts, P, b_arr, LOS_ROUTE_RANGE
        )

    def los_one(v_pt, b_arr):
        return _los_mask_from_point(
            roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd,
            float(v_pt[0]), float(v_pt[1]), float(v_pt[2]), P, b_arr, VANTAGE_LOS_RANGE
        )

    g_walk = _geodesic_progress(adj_u_all, f1, f2, N)
    mid_nodes_walk = np.nonzero(R_walk & (g_walk >= 0.30) & (g_walk <= 0.70))[0]
    full_nodes_walk = np.nonzero(R_walk & (g_walk >= 0.15) & (g_walk <= 0.85))[0]

    # Check if any central-mid node (0.35..0.65) can see either flag
    center_mid = np.nonzero(R_walk & (g_walk >= 0.35) & (g_walk <= 0.65))[0].astype(np.int64)
    mid_sees_f1 = bool(np.any(_los_mask_from_point(
        roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd,
        P[f1, 0], P[f1, 1], P[f1, 2], P, center_mid, 4096.0
    ))) if len(center_mid) else False
    mid_sees_f2 = bool(np.any(_los_mask_from_point(
        roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd,
        P[f2, 0], P[f2, 1], P[f2, 2], P, center_mid, 4096.0
    ))) if len(center_mid) else False

    walk_mid = None
    walk_full = None
    if walk_connected:
        walk_mid = analyze_band_routes(adj_walk, f1, f2, P, mid_nodes_walk, los_pts, los_one)
        walk_full = analyze_band_routes(adj_walk, f1, f2, P, full_nodes_walk, los_pts, los_one)

    # Hook-assisted analysis
    hook_info = None
    hook_draw = None
    if with_hook:
        adj_hook, hook_edge_count = _build_hook_time_graph(
            adj_walk_t, nodes, P, R_walk, f1, f2, roots, B, roots0
        )
        T12, hpath12, hkinds12 = _dijk_single(adj_hook, f1, f2)
        T21, hpath21, hkinds21 = _dijk_single(adj_hook, f2, f1)
        hook_connected = (T12 is not None) and (T21 is not None)

        hook_mid = None
        if hook_connected:
            # Geodesic progress on hook graph
            R_hook = np.zeros(N, dtype=bool)
            dqh = deque([f1, f2])
            R_hook[f1] = R_hook[f2] = True
            while dqh:
                u = dqh.popleft()
                for v, _, _ in adj_hook[u]:
                    if not R_hook[v]:
                        R_hook[v] = True
                        dqh.append(v)
            adj_hu = defaultdict(list)
            for u in range(N):
                if not R_hook[u]:
                    continue
                for v, c, k in adj_hook[u]:
                    if R_hook[v]:
                        adj_hu[u].append((v, c, k))
                        adj_hu[v].append((u, c, k))
            g_hook = _geodesic_progress(adj_hu, f1, f2, N)
            mid_nodes_hook = np.nonzero(R_hook & (g_hook >= 0.30) & (g_hook <= 0.70))[0]
            hook_mid = analyze_band_routes(adj_hook, f1, f2, P, mid_nodes_hook, los_pts, los_one)

            def path_len_3d(path, kinds):
                return float(sum(
                    32.0 if kinds[k] == 'tele' else np.linalg.norm(P[path[k + 1]] - P[path[k]])
                    for k in range(len(path) - 1)
                ))

            h1_swings = sum(1 for k in hkinds12 if k == 'hook')
            h1_len = path_len_3d(hpath12, hkinds12)
            hlens = [round(r[0], 1) for r in hook_mid['los_routes']]
            hratios = [round(r[0] / T12, 2) for r in hook_mid['los_routes']] if T12 > 0 else []
            hook_info = dict(
                connected=True,
                unlocks_flags=not walk_connected,
                hook_edges=hook_edge_count,
                f1_to_f2_s=round(T12, 1),
                f2_to_f1_s=round(T21, 1),
                f1_to_f2_units=round(h1_len),
                swings_on_shortest=h1_swings,
                speedup_vs_walk=(round(WT12 / T12, 2) if (walk_connected and WT12 is not None and T12 > 0) else None),
                mid_los_route_count=len(hook_mid['los_routes']),
                mid_los_route_s=hlens,
                mid_los_route_ratios=hratios,
                mid_single_vantage_cuts_all=hook_mid['vantage_cuts_all'],
                mid_single_vantage_bypass_s=(None if hook_mid['worst_bypass'] is None
                                             else round(hook_mid['worst_bypass'], 1)),
                mid_single_vantage_bypass_ratio=(None if (hook_mid['worst_bypass'] is None or T12 <= 0)
                                                 else round(hook_mid['worst_bypass'] / T12, 2)),
            )
            hook_draw = dict(
                R_hook=R_hook,
                los_routes=hook_mid['los_routes'],
                worst_vantage_pos=hook_mid['worst_vantage_pos'],
                vantage_cuts_all=hook_mid['vantage_cuts_all'],
                worst_bypass=hook_mid['worst_bypass'],
            )
        else:
            hook_info = dict(
                connected=False,
                unlocks_flags=False,
                hook_edges=hook_edge_count,
                f1_to_f2_s=None if T12 is None else round(T12, 1),
                f2_to_f1_s=None if T21 is None else round(T21, 1),
            )

    ents = Counter(e.get('classname', '') for e in B.ents)
    mh = sum(1 for e in B.ents if e.get('classname') == 'item_health' and (int(e.get('spawnflags', 0)) & 2))
    title = next((e.get('message', '') for e in B.ents if e.get('classname') == 'worldspawn'), '')

    walk_summary = dict(
        connected=walk_connected,
        f1_to_f2=None if L12 is None else round(L12),
        f2_to_f1=None if L21 is None else round(L21),
        f1_to_f2_s=None if WT12 is None else round(WT12, 1),
        f2_to_f1_s=None if WT21 is None else round(WT21, 1),
        asymmetry_ratio=(round(max(L12, L21) / max(min(L12, L21), 1.0), 2) if walk_connected else None),
        winding=(round(min(L12, L21) / max(gap2d, 1.0), 2) if walk_connected else None),
    )
    if walk_mid is not None:
        base_L = walk_mid['los_routes'][0][0]
        walk_summary.update(
            mid_los_route_count=len(walk_mid['los_routes']),
            mid_los_route_lens=[round(r[0]) for r in walk_mid['los_routes']],
            mid_los_route_ratios=[round(r[0] / base_L, 2) for r in walk_mid['los_routes']],
            mid_sp384_route_count=len(walk_mid['sp_routes']),
            mid_sp384_route_lens=[round(r[0]) for r in walk_mid['sp_routes']],
            mid_single_vantage_cuts_all=walk_mid['vantage_cuts_all'],
            mid_single_vantage_bypass_L=(None if walk_mid['worst_bypass'] is None
                                         else round(walk_mid['worst_bypass'])),
            mid_single_vantage_bypass_ratio=(None if walk_mid['worst_bypass'] is None
                                             else round(walk_mid['worst_bypass'] / base_L, 2)),
            mid_lat_sep=round(walk_mid['lat_sep']),
            mid_vert_sep=round(walk_mid['vert_sep']),
        )
    if walk_full is not None:
        base_L = walk_full['los_routes'][0][0]
        walk_summary.update(
            full_los_route_count=len(walk_full['los_routes']),
            full_los_route_lens=[round(r[0]) for r in walk_full['los_routes']],
            full_single_vantage_cuts_all=walk_full['vantage_cuts_all'],
            full_single_vantage_bypass_ratio=(None if walk_full['worst_bypass'] is None
                                              else round(walk_full['worst_bypass'] / base_L, 2)),
        )

    res = dict(
        map=name,
        title=title,
        # Scale & verticality from vprofile
        floor_area_k=vp['floor_area_k'],
        travel_median=vp['travel_median'],
        travel_p90=vp['travel_p90'],
        eff_levels=vp['eff_levels'],
        dominant_level=vp['dominant_level'],
        stacked_share=vp['stacked_share'],
        overlook_share=vp['overlook_share'],
        cross_level_sight=vp['cross_level_sight'],
        route_vert_per_1000=vp['route_vert_per_1000'],
        angled_walls=vp['angled_walls'],
        teleporters=vp['teleporters'],
        pads=vp['pads'],
        swim_edges=swim_edges,
        func_doors=ents['func_door'],
        func_plats=ents['func_plat'],
        # Spawns & items
        spawns=dict(team1=ents['info_player_team1'], team2=ents['info_player_team2'],
                    dm=ents['info_player_deathmatch']),
        items=dict(RL=ents['weapon_rocketlauncher'], LG=ents['weapon_lightning'],
                   GL=ents['weapon_grenadelauncher'], RA=ents['item_armorInv'],
                   YA=ents['item_armor2'], GA=ents['item_armor1'], MH=mh,
                   Quad=ents['item_artifact_super_damage'],
                   Pent=ents['item_artifact_invulnerability'],
                   Ring=ents['item_artifact_invisibility']),
        # Flags
        flag_gap_2d=round(gap2d),
        flag_gap_3d=round(gap3d),
        flag_exits=[exits1, exits2],
        flag_max_los=[round(flag1_los), round(flag2_los)],
        flags_mutual_los=flags_mut_los,
        mid_sees_flag=(mid_sees_f1 or mid_sees_f2),
        # Routes
        walk=walk_summary,
        hook=hook_info,
    )
    res['_draw'] = dict(
        P=P, R_walk=R_walk, f1=f1, f2=f2,
        walk_mid=walk_mid, hook_draw=hook_draw,
    )
    return res


def format_report(res):
    """Human-readable diagnostic summary for one CTF map."""
    w = res['walk']
    h = res.get('hook')
    lines = [f"CTF profile of {res['map']}" + (f" ({res['title']})" if res['title'] else '') + ':']
    lines.append(
        f"   scale: travel med {res['travel_median']} (p90 {res['travel_p90']}), "
        f"floor {res['floor_area_k']}k, eff_levels {res['eff_levels']}, "
        f"dom {res['dominant_level']}, stacked {res['stacked_share']}, "
        f"route_vert {res['route_vert_per_1000']}/1000u, teles {res['teleporters']}, pads {res['pads']}"
    )
    sp = res['spawns']
    it = res['items']
    lines.append(
        f"   spawns: {sp['team1']}v{sp['team2']} base + {sp['dm']} dm  |  "
        f"items: RL={it['RL']} LG={it['LG']} GL={it['GL']} RA={it['RA']} YA={it['YA']} "
        f"GA={it['GA']} MH={it['MH']} Quad={it['Quad']}"
    )
    lines.append(
        f"   flags: gap {res['flag_gap_2d']}u, exits (shell) {res['flag_exits'][0]}/{res['flag_exits'][1]}, "
        f"max sightline {res['flag_max_los'][0]}u/{res['flag_max_los'][1]}u, "
        f"mutual_los={res['flags_mutual_los']}, mid_sees_flag={res['mid_sees_flag']}"
    )
    if w['connected']:
        mid_v = ('CUTS ALL' if w['mid_single_vantage_cuts_all']
                 else f"bypass {w['mid_single_vantage_bypass_L']}u ({w['mid_single_vantage_bypass_ratio']}x)")
        full_v = ('CUTS ALL' if w['full_single_vantage_cuts_all']
                  else f"bypass {w['full_single_vantage_bypass_ratio']}x")
        lines.append(
            f"   walk (hook off): {w['f1_to_f2']}u ({w['f1_to_f2_s']}s) / {w['f2_to_f1']}u ({w['f2_to_f1_s']}s) "
            f"[asym {w['asymmetry_ratio']}x, winding {w['winding']}x]"
        )
        lines.append(
            f"     midfield (0.30..0.70): {w['mid_los_route_count']} LOS-indep routes {w['mid_los_route_lens']} "
            f"({w['mid_los_route_ratios']}x), {w['mid_sp384_route_count']} spatial-384 routes, "
            f"single-vantage (128u grid): {mid_v}, sep {w['mid_lat_sep']}u xy / {w['mid_vert_sep']}u z"
        )
        lines.append(
            f"     base-to-base (0.15..0.85): {w['full_los_route_count']} LOS-indep routes {w['full_los_route_lens']}, "
            f"single-vantage (128u grid): {full_v}"
        )
    else:
        lines.append(
            f"   walk (hook off): DISCONNECTED (f1->f2={w['f1_to_f2']}, f2->f1={w['f2_to_f1']}; "
            f"doors={res['func_doors']}, plats={res['func_plats']})"
        )
    if h is not None:
        if h['connected']:
            hv = ('CUTS ALL' if h['mid_single_vantage_cuts_all']
                  else f"bypass {h['mid_single_vantage_bypass_s']}s ({h['mid_single_vantage_bypass_ratio']}x)")
            note = ' [HOOK UNLOCKS FLAGS - check hook-off playability!]' if h['unlocks_flags'] else ''
            sp_txt = f", {h['speedup_vs_walk']}x faster than walk" if h['speedup_vs_walk'] else ''
            lines.append(
                f"   hook (model):    {h['f1_to_f2_s']}s / {h['f2_to_f1_s']}s "
                f"({h['f1_to_f2_units']}u, {h['swings_on_shortest']} swings{sp_txt}){note}"
            )
            lines.append(
                f"     midfield (0.30..0.70): {h['mid_los_route_count']} LOS-indep routes {h['mid_los_route_s']}s "
                f"({h['mid_los_route_ratios']}x), single-vantage (128u grid): {hv}"
            )
        else:
            t12 = 'None' if h['f1_to_f2_s'] is None else f"{h['f1_to_f2_s']}s"
            t21 = 'None' if h['f2_to_f1_s'] is None else f"{h['f2_to_f1_s']}s"
            lines.append(
                f"   hook (hook on):  DISCONNECTED (f1->f2={t12}, f2->f1={t21})"
            )
    return '\n'.join(lines)


def draw(res, out):
    """Render two-panel CTF route-independence diagnostic figure (walk vs. hook)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    D = res['_draw']
    P = D['P']
    f1, f2 = D['f1'], D['f2']
    R_walk = D['R_walk']
    walk_mid = D['walk_mid']
    hook_draw = D['hook_draw']

    ncols = 2 if hook_draw is not None else 1
    fig, axes = plt.subplots(1, ncols, figsize=(8.5 * ncols, 6.2), facecolor='#18191b')
    if ncols == 1:
        axes = [axes]
    colors = ['#ffffff', '#ff55ff', '#00ff88', '#ffaa00']

    # Panel 1: hook-off midfield LOS-independent routes
    ax = axes[0]
    ax.set_facecolor('#0d0d0e')
    ax.scatter(P[R_walk, 0], P[R_walk, 1], c=P[R_walk, 2], cmap='turbo', s=1.0, alpha=0.65, linewidths=0)
    if walk_mid is not None:
        for idx, (cost, path, _kinds) in enumerate(walk_mid['los_routes']):
            pts = P[path]
            ax.plot(pts[:, 0], pts[:, 1], '-', color=colors[idx % len(colors)],
                    lw=2.3 if idx == 0 else 1.7, label=f'LOS #{idx + 1}: {round(cost)}u ({cost / WALK_SPEED:.1f}s)')
        if walk_mid['worst_vantage_pos']:
            vx, vy, _ = walk_mid['worst_vantage_pos']
            vlab = ('worst mid vantage (CUTS ALL)' if walk_mid['vantage_cuts_all']
                    else f"worst mid vantage (bypass {round(walk_mid['worst_bypass'])}u)")
            ax.plot(vx, vy, 'x', color='#ffff00', ms=11, mew=2.4, label=vlab)
    ax.plot(P[f1, 0], P[f1, 1], '*', color='#ff4444', ms=13, mec='white')
    ax.plot(P[f2, 0], P[f2, 1], '*', color='#4488ff', ms=13, mec='white')
    ax.set_aspect('equal')
    ax.tick_params(colors='#888', labelsize=7)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(loc='best', fontsize=7, facecolor='#222', edgecolor='#555', labelcolor='white')
    w = res['walk']
    wt = (f"Walk (hook off): {w['f1_to_f2']}u | mid LOS-sep={w.get('mid_los_route_count', 0)}"
          if w['connected'] else 'Walk (hook off): DISCONNECTED')
    ax.set_title(wt, color='white', fontsize=9)

    # Panel 2: hook-on midfield LOS-independent routes
    if hook_draw is not None:
        bx = axes[1]
        bx.set_facecolor('#0d0d0e')
        R_hook = hook_draw['R_hook']
        bx.scatter(P[R_hook, 0], P[R_hook, 1], c=P[R_hook, 2], cmap='turbo', s=1.0, alpha=0.65, linewidths=0)
        for idx, (cost_s, path, kinds) in enumerate(hook_draw['los_routes']):
            col = colors[idx % len(colors)]
            # Draw walk segments solid, hook swings dashed cyan/highlight
            pts = P[path]
            bx.plot(pts[:, 0], pts[:, 1], '-', color=col, lw=1.6 if idx > 0 else 2.0,
                    alpha=0.85, label=f'Hook LOS #{idx + 1}: {cost_s:.1f}s')
            for k, kd in enumerate(kinds):
                if kd == 'hook':
                    bx.plot([P[path[k], 0], P[path[k + 1], 0]],
                            [P[path[k], 1], P[path[k + 1], 1]],
                            '--', color='#00e5ff' if idx == 0 else col, lw=2.4)
        if hook_draw['worst_vantage_pos']:
            vx, vy, _ = hook_draw['worst_vantage_pos']
            vlab = ('worst mid vantage (CUTS ALL)' if hook_draw['vantage_cuts_all']
                    else f"worst mid vantage (bypass {hook_draw['worst_bypass']:.1f}s)")
            bx.plot(vx, vy, 'x', color='#ffff00', ms=11, mew=2.4, label=vlab)
        bx.plot(P[f1, 0], P[f1, 1], '*', color='#ff4444', ms=13, mec='white')
        bx.plot(P[f2, 0], P[f2, 1], '*', color='#4488ff', ms=13, mec='white')
        bx.set_aspect('equal')
        bx.tick_params(colors='#888', labelsize=7)
        bx.legend(loc='best', fontsize=7, facecolor='#222', edgecolor='#555', labelcolor='white')
        h = res['hook']
        bx.set_title(
            f"Hook (hook on): {h['f1_to_f2_s']}s ({h['swings_on_shortest']} swings, cyan dashed) | mid LOS-sep={h['mid_los_route_count']}",
            color='white', fontsize=9,
        )

    fig.suptitle(f"{res['map']} — {res['title']} (midfield geodesic band 0.30..0.70)", color='white', fontsize=10.5)
    plt.tight_layout()
    fig.savefig(out, dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description='CTF layout and route-independence diagnostics on BSP29 maps.')
    ap.add_argument('maps', nargs='+', help='Compiled BSP29 map file(s) containing item_flag_team1/2')
    ap.add_argument('--json', dest='json_out', help='Write structured JSON report to path')
    ap.add_argument('--png-dir', dest='png_dir', help='Write route-independence diagnostic figures to directory')
    ap.add_argument('--no-hook', action='store_true', help='Skip grapple hook route simulation')
    args = ap.parse_args(argv)

    results = []
    skipped = 0
    for p in args.maps:
        try:
            r = ctf_profile(p, with_hook=not args.no_hook)
        except ValueError as exc:
            print(f'warning: skipping {exc}', file=sys.stderr)
            skipped += 1
            continue
        if args.png_dir:
            os.makedirs(args.png_dir, exist_ok=True)
            draw(r, os.path.join(args.png_dir, r['map'] + '.ctf.png'))
        r.pop('_draw')
        print(format_report(r))
        results.append(r)

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=1)
            f.write('\n')

    if skipped and not results:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
