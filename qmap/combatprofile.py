"""3D BSP exposure, overlook asymmetry & disengage-time analyzer (BSP29).

Reuses vprofile.py's compiled-BSP hull-0 geometry and walkable 16-unit player-hull
floor nodes to measure per-cell combat visibility across all 3D azimuths and
elevations:
  - True 3D combat sightline lengths (replacing 2D axial-only blind spots).
  - Overlook asymmetry: floor area shooting DOWN at a cell (>= 64u above) vs.
    floor area the cell can overlook (>= 64u below), flagging uncountered kill
    boxes and oppressive high-ground perches.
  - Disengage / time-to-cover: minimum walking distance (and time at 320 u/s)
    from a cell to break LOS from its dominant overlooker or cut visible-floor
    exposure by >= 50%.

Usage:
    python3 qmap/combatprofile.py map.bsp [more.bsp ...] [--ref duel|large|all]
        [--json out.json] [--png out.png | --png-dir figs/] [--slices N]
    python3 qmap/combatprofile.py --diff map_b1.bsp map_b2.bsp [--ref duel|large|all]
        [--json diff.json] [--png diff.png | --png-dir figs/]

Diagnostics exit 0 by default (advisory); input errors exit 2.
See COMBATPROFILE.md for metric definitions, classic reference bands, and diff mode.
"""
import argparse
from collections import defaultdict
import json
import math
import os
import sys
import time

import numpy as np
from numba import njit, prange

import vprofile

C = vprofile.C
EYE = float(vprofile.EYE)       # 46u above feet
BODY = float(vprofile.BODY)     # 32u above feet (center of 56u player)
WALK_SPEED = 320.0              # QuakeWorld sv_maxspeed (u/s)
TELE_COST = 48.0                # 0.15s teleporter transit equivalent in walk units

DEFAULT_OVERLOOK_RANGE = 1200.0
DEFAULT_MAX_SIGHTLINE = 4096.0
DEFAULT_MAX_DISENGAGE = 1536.0
DEFAULT_OVERLOOK_DZ = 64.0
DEFAULT_OVERLOOK_REGION_RADIUS = 192.0  # horizontal neighborhood defining a dominant overlooker ledge
DEFAULT_OVERLOOK_REGION_DZ = 48.0       # max height spread within one overlooker ledge
DEFAULT_SHELTER_AREA_K = 64.0   # <= 64k sq u (~256x256) with no overlooker counts as sheltered cover
DEFAULT_SAMPLE_CAP = 1400
DEFAULT_MAX_SLICES = 4


# ------------------------------------------------------------------ numba kernels
@njit(cache=True)
def _los_tree_exact(root, nplane, nchild, lcont, pn, pd, ax, ay, az, bx, by, bz):
    """Exact iterative hull-0 BSP visibility test for segment a -> b.

    Returns True iff the segment never enters a solid (-2) or sky (-6) leaf.
    Falls back to 8u stepping if tree depth exceeds the local stack limit.
    """
    MAXD = 128
    st_num = np.empty(MAXD, np.int64)
    st_x1 = np.empty(MAXD, np.float64)
    st_y1 = np.empty(MAXD, np.float64)
    st_z1 = np.empty(MAXD, np.float64)
    st_x2 = np.empty(MAXD, np.float64)
    st_y2 = np.empty(MAXD, np.float64)
    st_z2 = np.empty(MAXD, np.float64)

    sp = 0
    num = root
    p1x, p1y, p1z = ax, ay, az
    p2x, p2y, p2z = bx, by, bz

    while True:
        while num >= 0:
            p = nplane[num]
            nx = pn[p, 0]
            ny = pn[p, 1]
            nz = pn[p, 2]
            dist = pd[p]
            t1 = nx * p1x + ny * p1y + nz * p1z - dist
            t2 = nx * p2x + ny * p2y + nz * p2z - dist
            if t1 >= 0.0 and t2 >= 0.0:
                num = nchild[num, 0]
                continue
            if t1 < 0.0 and t2 < 0.0:
                num = nchild[num, 1]
                continue
            denom = t1 - t2
            if denom == 0.0:
                num = nchild[num, 0]
                continue
            frac = t1 / denom
            if frac < 0.0:
                frac = 0.0
            elif frac > 1.0:
                frac = 1.0
            mx = p1x + (p2x - p1x) * frac
            my = p1y + (p2y - p1y) * frac
            mz = p1z + (p2z - p1z) * frac
            side = 1 if t1 < 0.0 else 0
            if sp >= MAXD:
                return vprofile._los(root, nplane, nchild, lcont, pn, pd, ax, ay, az, bx, by, bz)
            st_num[sp] = nchild[num, 1 - side]
            st_x1[sp] = mx
            st_y1[sp] = my
            st_z1[sp] = mz
            st_x2[sp] = p2x
            st_y2[sp] = p2y
            st_z2[sp] = p2z
            sp += 1
            num = nchild[num, side]
            p2x, p2y, p2z = mx, my, mz

        c = lcont[-1 - num]
        if c == -2 or c == -6:
            return False
        if sp == 0:
            return True
        sp -= 1
        num = st_num[sp]
        p1x = st_x1[sp]
        p1y = st_y1[sp]
        p1z = st_z1[sp]
        p2x = st_x2[sp]
        p2y = st_y2[sp]
        p2z = st_z2[sp]


@njit(cache=True)
def _los_multi_exact(roots0, nplane, nchild, lcont, pn, pd, ax, ay, az, bx, by, bz):
    """Exact hull-0 visibility across world model and all static func_wall submodels."""
    for k in range(len(roots0)):
        if not _los_tree_exact(roots0[k], nplane, nchild, lcont, pn, pd, ax, ay, az, bx, by, bz):
            return False
    return True


@njit(parallel=True, cache=True)
def _rep_overlook_power(roots0, nplane, nchild, lcont, pn, pd,
                        rep_pts, rep_w, overlook_range, overlook_dz):
    """Weighted floor area each observer representative can shoot down at (>= overlook_dz below)."""
    M = len(rep_pts)
    power = np.zeros(M, np.float64)
    r2 = overlook_range * overlook_range
    for j in prange(M):
        jx, jy, jz = rep_pts[j, 0], rep_pts[j, 1], rep_pts[j, 2]
        jez = jz + EYE
        acc = 0.0
        for k in range(M):
            if k == j:
                continue
            kz = rep_pts[k, 2]
            if jz - kz < overlook_dz:
                continue
            dx = rep_pts[k, 0] - jx
            dy = rep_pts[k, 1] - jy
            if dx * dx + dy * dy > r2:
                continue
            if _los_multi_exact(roots0, nplane, nchild, lcont, pn, pd,
                                jx, jy, jez, rep_pts[k, 0], rep_pts[k, 1], kz + BODY):
                acc += rep_w[k]
        power[j] = acc
    return power


@njit(parallel=True, cache=True)
def _compute_visibility_metrics(roots0, nplane, nchild, lcont, pn, pd,
                                pts, rep_pts, rep_w, rep_node_idx, rep_power,
                                overlook_range, max_sightline, overlook_dz):
    """Per-cell 3D sightlines, exposure, overlook counts, dominant overlooker, and obs_sees matrix."""
    N = len(pts)
    M = len(rep_pts)
    r_ov2 = overlook_range * overlook_range
    r_max2 = max_sightline * max_sightline

    max_sl_3d = np.zeros(N, np.float64)
    max_sl_2d = np.zeros(N, np.float64)
    max_sl_dz = np.zeros(N, np.float64)
    max_sl_tgt = np.full(N, -1, np.int64)
    sl_capped = np.zeros(N, np.uint8)

    exposure_w = np.zeros(N, np.float64)
    overlooked_by_w = np.zeros(N, np.float64)
    overlooks_w = np.zeros(N, np.float64)
    dom_obs = np.full(N, -1, np.int64)
    obs_sees = np.zeros((M, N), np.uint8)

    for i in prange(N):
        ix, iy, iz = pts[i, 0], pts[i, 1], pts[i, 2]
        iez = iz + EYE
        ibz = iz + BODY

        best_d3 = 0.0
        best_d2 = 0.0
        best_dz = 0.0
        best_tgt = -1
        capped_i = False

        exp_acc = 0.0
        ov_by_acc = 0.0
        ov_acc = 0.0
        best_threat = -1.0
        best_dom = -1

        for j in range(M):
            jx, jy, jz = rep_pts[j, 0], rep_pts[j, 1], rep_pts[j, 2]
            dx = jx - ix
            dy = jy - iy
            dz = jz - iz
            d2_sq = dx * dx + dy * dy
            d3_sq = d2_sq + dz * dz
            if d3_sq > r_max2:
                if (not capped_i) or (d3_sq > best_d3 * best_d3):
                    if (_los_multi_exact(roots0, nplane, nchild, lcont, pn, pd,
                                         jx, jy, jz + EYE, ix, iy, ibz)
                            or _los_multi_exact(roots0, nplane, nchild, lcont, pn, pd,
                                                ix, iy, iez, jx, jy, jz + BODY)):
                        best_d3 = math.sqrt(d3_sq)
                        best_d2 = math.sqrt(d2_sq)
                        best_dz = dz
                        best_tgt = rep_node_idx[j]
                        capped_i = True
                continue

            if rep_node_idx[j] == i:
                obs_sees[j, i] = 1
                exp_acc += rep_w[j]
                continue

            j_sees_i = _los_multi_exact(roots0, nplane, nchild, lcont, pn, pd,
                                        jx, jy, jz + EYE, ix, iy, ibz)
            if j_sees_i:
                obs_sees[j, i] = 1
                exp_acc += rep_w[j]
                d3 = math.sqrt(d3_sq)
                if d3 > best_d3:
                    best_d3 = d3
                    best_d2 = math.sqrt(d2_sq)
                    best_dz = dz
                    best_tgt = rep_node_idx[j]
                if dz >= overlook_dz and d2_sq <= r_ov2:
                    ov_by_acc += rep_w[j]
                    threat = (rep_power[j] + rep_w[j]) / (d3 + 128.0)
                    if threat > best_threat:
                        best_threat = threat
                        best_dom = j

            # Reverse ray (eye(i) -> body(j)) when i can overlook j or extend max sightline
            need_rev_ov = (-dz >= overlook_dz) and (d2_sq <= r_ov2)
            need_rev_sl = (not j_sees_i) and (d3_sq > best_d3 * best_d3)
            if need_rev_ov or need_rev_sl:
                i_sees_j = _los_multi_exact(roots0, nplane, nchild, lcont, pn, pd,
                                            ix, iy, iez, jx, jy, jz + BODY)
                if i_sees_j:
                    if need_rev_ov:
                        ov_acc += rep_w[j]
                    if d3_sq > best_d3 * best_d3:
                        best_d3 = math.sqrt(d3_sq)
                        best_d2 = math.sqrt(d2_sq)
                        best_dz = dz
                        best_tgt = rep_node_idx[j]

        max_sl_3d[i] = best_d3
        max_sl_2d[i] = best_d2
        max_sl_dz[i] = best_dz
        max_sl_tgt[i] = best_tgt
        if capped_i:
            sl_capped[i] = 1
        exposure_w[i] = exp_acc
        overlooked_by_w[i] = ov_by_acc
        overlooks_w[i] = ov_acc
        dom_obs[i] = best_dom

    return (max_sl_3d, max_sl_2d, max_sl_dz, max_sl_tgt, sl_capped,
            exposure_w, overlooked_by_w, overlooks_w, dom_obs, obs_sees)


@njit(cache=True)
def _compute_disengage(indptr, indices, weights, exposure_area, overlooked_by_area, dom_obs,
                       cell_sees, rep_w, rep_z, pts_z, reg_indptr, reg_indices,
                       overlook_dz, shelter_area, max_dist):
    """Per-cell bounded Dijkstra for minimum walk distance to reach real cover:
      - Break LOS from >= 50% of the dominant overlooker's high-ground region AND cut total
        overlooked-by area by >= 50% without stepping into significantly higher exposure (<= 1.15x),
      - Cut total visible-floor exposure area by >= 50%,
      - Break LOS from >= 50% of active watchers without stepping into higher exposure (<= 1.15x)
        or newly overlooked ground, or
      - Reach sheltered ground (not overlooked and exposure <= shelter_area).
    """
    N = len(exposure_area)
    M = len(rep_w)
    out_dist = np.zeros(N, np.float64)
    # 0=already_sheltered, 1=exp_cut, 2=ov_broken, 3=both, 4=capped, 5=reached_shelter
    out_reason = np.zeros(N, np.int8)

    dist = np.empty(N, np.float64)
    stamp = np.zeros(N, np.int64)
    vis_idx = np.empty(M, np.int64)
    dom_idx = np.empty(M, np.int64)
    cur_stamp = 0
    cell_area = float(C * C)

    cap = max(4096, N * 2)
    h_d = np.empty(cap, np.float64)
    h_u = np.empty(cap, np.int64)

    for s in range(N):
        ea = exposure_area[s]
        ov_s = overlooked_by_area[s]
        dom = dom_obs[s]
        if dom < 0 and ea <= shelter_area:
            out_dist[s] = 0.0
            out_reason[s] = 0
            continue
        exp_cut = 0.5 * ea
        nv = 0
        for j in range(M):
            if cell_sees[s, j] != 0:
                vis_idx[nv] = j
                nv += 1

        nd = 0
        dom_w_tot = 0.0
        if dom >= 0:
            sz = pts_z[s]
            rs = reg_indptr[dom]
            re = reg_indptr[dom + 1]
            for e in range(rs, re):
                j = reg_indices[e]
                if cell_sees[s, j] != 0 and rep_z[j] - sz >= overlook_dz:
                    dom_idx[nd] = j
                    nd += 1
                    dom_w_tot += rep_w[j]

        cur_stamp += 1
        stamp[s] = cur_stamp
        dist[s] = 0.0
        hsize = 1
        h_d[0] = 0.0
        h_u[0] = s

        found_d = max_dist
        found_r = 4

        while hsize > 0:
            d = h_d[0]
            u = h_u[0]
            hsize -= 1
            if hsize > 0:
                ld = h_d[hsize]
                lu = h_u[hsize]
                pos = 0
                while True:
                    left = 2 * pos + 1
                    if left >= hsize:
                        break
                    right = left + 1
                    sm = right if (right < hsize and h_d[right] < h_d[left]) else left
                    if h_d[sm] < ld:
                        h_d[pos] = h_d[sm]
                        h_u[pos] = h_u[sm]
                        pos = sm
                    else:
                        break
                h_d[pos] = ld
                h_u[pos] = lu

            if stamp[u] != cur_stamp or d > dist[u] + 1e-9:
                continue
            if d > max_dist:
                break

            if u != s:
                broke = False
                rem_dom_checked = False
                rem_dom_ok = False
                if (dom >= 0 and nd > 0
                        and overlooked_by_area[u] <= 0.5 * ov_s
                        and (exposure_area[u] <= ea * 1.15
                             or (dom_obs[u] < 0 and exposure_area[u] <= ea * 1.5))):
                    rem_dom = 0.0
                    for k in range(nd):
                        j = dom_idx[k]
                        if cell_sees[u, j] != 0:
                            rem_dom += rep_w[j]
                    rem_dom_checked = True
                    rem_dom_ok = (rem_dom <= 0.5 * dom_w_tot)
                    if rem_dom_ok:
                        broke = True
                cut = (ea > 0.0) and (exposure_area[u] <= exp_cut)
                sheltered = (dom_obs[u] < 0) and (exposure_area[u] <= shelter_area)
                if sheltered and dom >= 0 and nd > 0:
                    if not rem_dom_checked:
                        rem_dom = 0.0
                        for k in range(nd):
                            j = dom_idx[k]
                            if cell_sees[u, j] != 0:
                                rem_dom += rep_w[j]
                        rem_dom_ok = (rem_dom <= 0.5 * dom_w_tot)
                    if not rem_dom_ok:
                        sheltered = False
                if (not (broke or cut or sheltered)
                        and ea > 0.0
                        and exposure_area[u] <= ea * 1.15
                        and (dom >= 0 or dom_obs[u] < 0)):
                    shared = 0.0
                    for k in range(nv):
                        j = vis_idx[k]
                        if cell_sees[u, j] != 0:
                            shared += rep_w[j]
                    if shared * cell_area <= exp_cut:
                        cut = True
                if broke or cut or sheltered:
                    found_d = d
                    if broke and cut:
                        found_r = 3
                    elif broke:
                        found_r = 2
                    elif cut:
                        found_r = 1
                    else:
                        found_r = 5
                    break

            start = indptr[u]
            end = indptr[u + 1]
            for e in range(start, end):
                v = indices[e]
                ndist = d + weights[e]
                if ndist > max_dist:
                    continue
                if stamp[v] != cur_stamp or ndist < dist[v]:
                    stamp[v] = cur_stamp
                    dist[v] = ndist
                    if hsize >= cap:
                        new_cap = cap * 2
                        nd_arr = np.empty(new_cap, np.float64)
                        nu_arr = np.empty(new_cap, np.int64)
                        nd_arr[:cap] = h_d
                        nu_arr[:cap] = h_u
                        h_d = nd_arr
                        h_u = nu_arr
                        cap = new_cap
                    pos = hsize
                    hsize += 1
                    while pos > 0:
                        par = (pos - 1) // 2
                        if ndist < h_d[par]:
                            h_d[pos] = h_d[par]
                            h_u[pos] = h_u[par]
                            pos = par
                        else:
                            break
                    h_d[pos] = ndist
                    h_u[pos] = v

        out_dist[s] = found_d
        out_reason[s] = found_r

    return out_dist, out_reason


def _build_overlook_regions(rep_pts, radius=DEFAULT_OVERLOOK_REGION_RADIUS,
                            dz_max=DEFAULT_OVERLOOK_REGION_DZ):
    """Build CSR adjacency of local high-ground neighborhoods around each observer representative."""
    M = len(rep_pts)
    r2 = radius * radius
    indptr = np.zeros(M + 1, np.int64)
    idx_list = []
    for j in range(M):
        dx = rep_pts[:, 0] - rep_pts[j, 0]
        dy = rep_pts[:, 1] - rep_pts[j, 1]
        dz = np.abs(rep_pts[:, 2] - rep_pts[j, 2])
        nbrs = np.nonzero((dx * dx + dy * dy <= r2) & (dz <= dz_max))[0]
        idx_list.extend(nbrs.tolist())
        indptr[j + 1] = len(idx_list)
    return indptr, np.array(idx_list, np.int64)


# ------------------------------------------------------------------ lightweight walkable floor loader
def load_walkable_floor(path, name=None):
    """Build vprofile's exact reachable 16u walkable floor nodes & movement graph via
    vprofile.build_floor_graph(), skipping passage-width, blind-pocket, and overlook scans."""
    G = vprofile.build_floor_graph(str(path))
    name = name or os.path.splitext(os.path.basename(str(path)))[0]
    B = G['bsp']
    x0, y0, nx, ny = G['x0'], G['y0'], G['nx'], G['ny']
    nodes = G['nodes']
    adj = G['adj']
    N_all = G['N']

    reach_ids = np.nonzero(G['R'])[0]
    N = len(reach_ids)
    if N == 0:
        raise ValueError(f'{path}: no reachable floor nodes found from spawns')

    full_to_r = np.full(N_all, -1, np.int64)
    full_to_r[reach_ids] = np.arange(N, dtype=np.int64)
    nodes_reach = [nodes[int(n)] for n in reach_ids]
    pts = np.array([(x0 + gi * C + 8.0, y0 + gj * C + 8.0, float(f)) for gi, gj, f in nodes_reach], np.float64)

    indptr = np.zeros(N + 1, np.int64)
    edge_dst = []
    edge_w = []
    for r_u in range(N):
        for full_v, cost, kind in adj[int(reach_ids[r_u])]:
            r_v = int(full_to_r[full_v])
            if r_v >= 0 and r_v != r_u:
                edge_dst.append(r_v)
                eff_cost = TELE_COST if kind == 'tele' else float(cost)
                edge_w.append(max(eff_cost, 1.0))
        indptr[r_u + 1] = len(edge_dst)

    F = pts[:, 2]
    bands64 = np.floor((F - F.min()) / 64.0).astype(int)
    p = np.bincount(bands64) / len(F)
    p = p[p > 0]
    eff_levels = round(float(np.exp(-(p * np.log(p)).sum())), 2)

    return dict(
        map=name,
        bsp=B,
        roots0=G['roots0'],
        x0=float(x0), y0=float(y0), nx=nx, ny=ny,
        nodes_reach=nodes_reach,
        pts=pts,
        indptr=indptr,
        indices=np.array(edge_dst, np.int64),
        weights=np.array(edge_w, np.float64),
        floor_area_k=round(N * C * C / 1000.0),
        eff_levels=eff_levels,
        spawns=len(G['spn']),
    )


# ------------------------------------------------------------------ spatial helpers
def select_representatives(pts, sample_cap=DEFAULT_SAMPLE_CAP):
    """Deterministically bucket reachable 16u floor cells into <= sample_cap area-weighted
    3D representatives so every room and height layer is preserved."""
    N = len(pts)
    if N == 0:
        return np.empty((0, 3), np.float64), np.empty(0, np.float64), np.empty(0, np.int64), 16
    if N <= sample_cap:
        return pts.copy(), np.ones(N, np.float64), np.arange(N, dtype=np.int64), 16

    grid = 32
    for cand in (32, 48, 64, 80, 96, 128, 160, 192, 256):
        bx = np.floor(pts[:, 0] / cand).astype(np.int64)
        by = np.floor(pts[:, 1] / cand).astype(np.int64)
        bz = np.floor(pts[:, 2] / 48.0).astype(np.int64)
        buckets = defaultdict(list)
        for idx in range(N):
            buckets[(int(bx[idx]), int(by[idx]), int(bz[idx]))].append(idx)
        grid = cand
        if len(buckets) <= sample_cap:
            break

    keys = sorted(buckets.keys())
    M = len(keys)
    rep_pts = np.empty((M, 3), np.float64)
    rep_w = np.empty(M, np.float64)
    rep_idx = np.empty(M, np.int64)
    for k, key in enumerate(keys):
        members = buckets[key]
        sub = pts[members]
        mean = sub.mean(axis=0)
        d2 = np.sum((sub - mean) ** 2, axis=1)
        chosen = members[int(np.argmin(d2))]
        rep_pts[k] = pts[chosen]
        rep_w[k] = float(len(members))
        rep_idx[k] = chosen
    return rep_pts, rep_w, rep_idx, grid


def compute_floor_slices(F, max_slices=DEFAULT_MAX_SLICES):
    """Partition reachable floor heights into 1..max_slices natural Z-bands via 1D variance
    minimization (Jenks breaks) over 16u height bins so slice cuts land between storeys."""
    if len(F) == 0:
        return []
    zmin, zmax = float(F.min()), float(F.max())
    if max_slices <= 1 or zmax - zmin < 64.0:
        return [(math.floor(zmin), math.ceil(zmax))]

    b0 = int(math.floor(zmin / 16.0))
    b1 = int(math.floor(zmax / 16.0))
    nb = b1 - b0 + 1
    counts = np.zeros(nb, np.float64)
    zs = np.array([(b0 + k) * 16.0 + 8.0 for k in range(nb)], np.float64)
    idx = np.clip(np.floor(F / 16.0).astype(int) - b0, 0, nb - 1)
    np.add.at(counts, idx, 1.0)

    nz = np.nonzero(counts > 0)[0]
    if len(nz) <= 1:
        return [(math.floor(zmin), math.ceil(zmax))]

    bands64 = np.floor((F - zmin) / 64.0).astype(int)
    p = np.bincount(bands64) / len(F)
    p = p[p > 0]
    eff_lvls = float(np.exp(-(p * np.log(p)).sum()))
    k_target = min(max_slices, len(nz), max(2, min(max_slices, int(round(eff_lvls)))))
    if zmax - zmin < 128.0:
        k_target = min(k_target, 2)

    m = len(nz)
    w = counts[nz]
    v = zs[nz]

    pw = np.concatenate(([0.0], np.cumsum(w)))
    pv = np.concatenate(([0.0], np.cumsum(w * v)))
    pv2 = np.concatenate(([0.0], np.cumsum(w * v * v)))

    def seg_cost(a, b):
        wt = pw[b] - pw[a]
        if wt <= 0:
            return 0.0
        s1 = pv[b] - pv[a]
        s2 = pv2[b] - pv2[a]
        return max(0.0, s2 - (s1 * s1) / wt)

    INF = 1e30
    dp = np.full((k_target + 1, m + 1), INF, np.float64)
    back = np.zeros((k_target + 1, m + 1), np.int64)
    dp[0, 0] = 0.0
    for k in range(1, k_target + 1):
        for j in range(k, m + 1):
            best = INF
            best_i = k - 1
            for i in range(k - 1, j):
                c = dp[k - 1, i] + seg_cost(i, j)
                if c < best:
                    best = c
                    best_i = i
            dp[k, j] = best
            back[k, j] = best_i

    cuts = []
    cur = m
    for k in range(k_target, 0, -1):
        prev = int(back[k, cur])
        cuts.append((prev, cur - 1))
        cur = prev
    cuts.reverse()

    slices = []
    for s_idx, (a, b) in enumerate(cuts):
        lo_bin = nz[a]
        hi_bin = nz[b]
        lo_z = math.floor(zmin) if s_idx == 0 else int((b0 + lo_bin) * 16)
        if s_idx == len(cuts) - 1:
            hi_z = math.ceil(zmax)
        else:
            next_lo_bin = nz[cuts[s_idx + 1][0]]
            mid_z = int(round(((b0 + hi_bin + 1) * 16 + (b0 + next_lo_bin) * 16) / 2.0))
            hi_z = mid_z
        if s_idx > 0:
            lo_z = slices[-1][1]
        slices.append((lo_z, hi_z))
    return slices


def _cluster_cells(indices, nodes_reach, min_cells=8):
    """Connected-component clustering on 8-neighbor 16u columns within +-24u Z."""
    by_col = defaultdict(list)
    idx_set = set()
    for k in indices:
        ki = int(k)
        gi, gj, f = nodes_reach[ki]
        by_col[(gi, gj)].append((float(f), ki))
        idx_set.add(ki)
    seen = set()
    clusters = []
    for start in idx_set:
        if start in seen:
            continue
        comp = []
        st = [start]
        seen.add(start)
        while st:
            u = st.pop()
            comp.append(u)
            ui, uj, uz = nodes_reach[u]
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    if di == 0 and dj == 0:
                        continue
                    for vz, v in by_col.get((ui + di, uj + dj), ()):
                        if v not in seen and abs(vz - uz) <= 24.0:
                            seen.add(v)
                            st.append(v)
        if len(comp) >= min_cells:
            clusters.append(comp)
    return clusters


# ------------------------------------------------------------------ reference bands
# Calibrated from gallery/profiles/combat_refs.json (15 classic QW maps: 5 duel + 10 large).
# Each entry: (healthy_lo, healthy_hi, extreme_bound, direction, description)
#   direction='down': lower is safer; > healthy_hi -> HIGH, > extreme_bound -> EXTREME
#   direction='up':   higher (less negative) is safer; < healthy_lo -> HIGH, < extreme_bound -> EXTREME
REFERENCE_DUEL = {
    'sightline_3d_p90':           (936,   1236,  1550,  'down', '90th-pct 3D combat sightline (u)'),
    'sightline_3d_max':           (1176,  1585,  2000,  'down', 'longest 3D combat sightline (u)'),
    'exposure_p90':               (0.246, 0.322, 0.420, 'down', '90th-pct visible-floor exposure share'),
    'overlooked_by_area_k_p90':   (89.3,  177.5, 240.0, 'down', '90th-pct high-ground area shooting down (k sq u)'),
    'overlook_net_p05':           (-0.129, -0.072, -0.180, 'up', '5th-pct overlook asymmetry (kill-box tail)'),
    'overlook_net_p95':           (0.099, 0.134, 0.200, 'down', '95th-pct overlook asymmetry (perch tail)'),
    'killbox_share':              (0.061, 0.211, 0.300, 'down', 'floor share in kill boxes (high overlook + slow disengage)'),
    'perch_share':                (0.040, 0.074, 0.140, 'down', 'floor share on uncountered perches'),
    'disengage_p50_s':            (0.37,  0.50,  0.70,  'down', 'median disengage time to cover (s)'),
    'disengage_p90_s':            (0.89,  1.25,  1.70,  'down', '90th-pct disengage time to cover (s)'),
    'disengage_overlooked_p90_s': (0.84,  1.16,  1.55,  'down', '90th-pct disengage from overlooked floor (s)'),
}

# Ten larger QW classics (skull, bravado, spinev2, ultrav, schloss, cmt4, dm3, e2m2tdm, cmt3, e1m2).
REFERENCE_LARGE = {
    'sightline_3d_p90':           (979,   1312,  1700,  'down', '90th-pct 3D combat sightline (u)'),
    'sightline_3d_max':           (1298,  1888,  2400,  'down', 'longest 3D combat sightline (u)'),
    'exposure_p90':               (0.095, 0.302, 0.400, 'down', '90th-pct visible-floor exposure share'),
    'overlooked_by_area_k_p90':   (65.0,  187.6, 250.0, 'down', '90th-pct high-ground area shooting down (k sq u)'),
    'overlook_net_p05':           (-0.103, -0.022, -0.160, 'up', '5th-pct overlook asymmetry (kill-box tail)'),
    'overlook_net_p95':           (0.027, 0.147, 0.220, 'down', '95th-pct overlook asymmetry (perch tail)'),
    'killbox_share':              (0.026, 0.281, 0.380, 'down', 'floor share in kill boxes (high overlook + slow disengage)'),
    'perch_share':                (0.014, 0.098, 0.160, 'down', 'floor share on uncountered perches'),
    'disengage_p50_s':            (0.38,  0.47,  0.68,  'down', 'median disengage time to cover (s)'),
    'disengage_p90_s':            (0.92,  1.38,  1.85,  'down', '90th-pct disengage time to cover (s)'),
    'disengage_overlooked_p90_s': (0.73,  1.34,  1.75,  'down', '90th-pct disengage from overlooked floor (s)'),
}

REFERENCE_ALL = {
    k: (
        min(REFERENCE_DUEL[k][0], REFERENCE_LARGE[k][0]),
        max(REFERENCE_DUEL[k][1], REFERENCE_LARGE[k][1]),
        (min(REFERENCE_DUEL[k][2], REFERENCE_LARGE[k][2]) if REFERENCE_DUEL[k][3] == 'up'
         else max(REFERENCE_DUEL[k][2], REFERENCE_LARGE[k][2])),
        REFERENCE_DUEL[k][3],
        REFERENCE_DUEL[k][4],
    )
    for k in REFERENCE_DUEL
}

# Exact worst single-hotspot ceilings across each classic reference pool (matching the
# per-classic 'hotspots' records in gallery/profiles/combat_refs.json) so healthy classics
# emit zero false spatial kill-box or perch warnings while layouts exceeding classics do.
_HOTSPOT_CEILINGS_DUEL = dict(kb_overlooked_k=249.6, kb_area_k=233.5, pc_overlooks_k=386.0, pc_overlooks_share=0.288)
_HOTSPOT_CEILINGS_LARGE = dict(kb_overlooked_k=249.9, kb_area_k=458.8, pc_overlooks_k=661.5, pc_overlooks_share=0.252)
HOTSPOT_CEILINGS = {
    'duel': _HOTSPOT_CEILINGS_DUEL,
    'large': _HOTSPOT_CEILINGS_LARGE,
    'all': {k: max(_HOTSPOT_CEILINGS_DUEL[k], _HOTSPOT_CEILINGS_LARGE[k]) for k in _HOTSPOT_CEILINGS_DUEL},
}


def get_reference_table(ref='duel'):
    if ref == 'duel':
        return REFERENCE_DUEL, 'five compact QW classics'
    if ref == 'large':
        return REFERENCE_LARGE, 'ten larger QW classics'
    if ref == 'all':
        return REFERENCE_ALL, 'fifteen classic QW maps'
    raise ValueError(f"unknown --ref {ref!r} (expected 'duel', 'large', or 'all')")


def classify_metric(value, spec):
    """Classify value against (healthy_lo, healthy_hi, extreme_bound, direction, desc)."""
    lo, hi, extreme, way, _ = spec
    if way == 'down':
        if value > extreme:
            return 'EXTREME'
        if value > hi:
            return 'HIGH'
        if value < lo:
            return 'LOW'
        return 'ok'
    if value < extreme:
        return 'EXTREME'
    if value < lo:
        return 'HIGH'
    if value > hi:
        return 'LOW'
    return 'ok'


# ------------------------------------------------------------------ core analyzer
def combat_profile(path, name=None, *,
                   overlook_range=DEFAULT_OVERLOOK_RANGE,
                   max_sightline=DEFAULT_MAX_SIGHTLINE,
                   max_disengage=DEFAULT_MAX_DISENGAGE,
                   overlook_dz=DEFAULT_OVERLOOK_DZ,
                   shelter_area_k=DEFAULT_SHELTER_AREA_K,
                   sample_cap=DEFAULT_SAMPLE_CAP,
                   max_slices=DEFAULT_MAX_SLICES,
                   ref='duel'):
    """Run 3D combat visibility, overlook asymmetry, and disengage-time analysis on a BSP29."""
    if (overlook_range <= 0 or max_sightline <= 0 or max_disengage <= 0
            or overlook_dz <= 0 or shelter_area_k < 0 or sample_cap <= 0 or max_slices <= 0):
        raise ValueError('range, overlook_dz, sample_cap, and max_slices must be positive; shelter_area_k >= 0')
    ref_table, _ = get_reference_table(ref)

    t0 = time.perf_counter()
    loaded = load_walkable_floor(path, name=name)
    B = loaded['bsp']
    roots0 = loaded['roots0']
    pts = loaded['pts']
    F = pts[:, 2]
    N = len(pts)
    nodes_reach = loaded['nodes_reach']
    x0, y0, nx, ny = loaded['x0'], loaded['y0'], loaded['nx'], loaded['ny']

    # 3D spatially-stratified area-weighted observer/target sample
    rep_pts, rep_w, rep_node_idx, sample_grid = select_representatives(pts, sample_cap=sample_cap)
    total_w = float(rep_w.sum())
    cell_area = float(C * C)
    total_area = total_w * cell_area

    # 1. Observer overlook power (for identifying each cell's dominant overlooker)
    rep_power = _rep_overlook_power(
        roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd,
        rep_pts, rep_w, float(overlook_range), float(overlook_dz),
    )

    # 2. Full N x M 3D visibility pass
    (max_sl_3d_raw, max_sl_2d, max_sl_dz, max_sl_tgt, sl_capped,
     exposure_w, overlooked_by_w, overlooks_w, dom_obs, obs_sees) = _compute_visibility_metrics(
        roots0, B.nplane, B.nchild, B.lcont, B.pn, B.pd,
        pts, rep_pts, rep_w, rep_node_idx, rep_power,
        float(overlook_range), float(max_sightline), float(overlook_dz),
    )
    max_sl_3d = np.minimum(max_sl_3d_raw, float(max_sightline))
    sightline_capped_cells = int(sl_capped.sum())

    exposure_area = exposure_w * cell_area
    exposure_share = exposure_w / total_w
    overlooked_by_area_k = overlooked_by_w * cell_area / 1000.0
    overlooks_area_k = overlooks_w * cell_area / 1000.0
    overlooked_by_share = overlooked_by_w / total_w
    overlooks_share = overlooks_w / total_w
    overlook_net = overlooks_share - overlooked_by_share
    overlook_net_area_k = overlooks_area_k - overlooked_by_area_k

    # Effective shelter area capped to 15% of map area so tiny synthetic rooms still test disengage
    eff_shelter_area = min(float(shelter_area_k) * 1000.0, 0.15 * total_area)

    # 3. Per-cell bounded Dijkstra disengage distance/time
    overlooked_by_area = overlooked_by_w * cell_area
    reg_indptr, reg_indices = _build_overlook_regions(rep_pts)
    cell_sees = np.ascontiguousarray(obs_sees.T)
    disengage_dist, disengage_reason = _compute_disengage(
        loaded['indptr'], loaded['indices'], loaded['weights'],
        exposure_area, overlooked_by_area, dom_obs, cell_sees, rep_w,
        np.ascontiguousarray(rep_pts[:, 2]), np.ascontiguousarray(F),
        reg_indptr, reg_indices, float(overlook_dz), eff_shelter_area, float(max_disengage),
    )
    disengage_time = disengage_dist / WALK_SPEED

    # 4. Aggregate map metrics
    overlooked_mask = overlooked_by_share > 0.0
    exposed_mask = (disengage_reason != 0)
    ov_dis_p90 = float(np.percentile(disengage_time[overlooked_mask], 90)) if np.any(overlooked_mask) else 0.0
    exp_dis_p50 = float(np.percentile(disengage_time[exposed_mask], 50)) if np.any(exposed_mask) else 0.0
    exp_dis_p90 = float(np.percentile(disengage_time[exposed_mask], 90)) if np.any(exposed_mask) else 0.0

    # Scale-invariant + share-aware kill-box & oppressive-perch masks
    killbox_mask = (
        ((overlooked_by_area_k >= 80.0) | (overlooked_by_share >= 0.08))
        & ((overlook_net_area_k <= -50.0) | (overlook_net <= -0.05))
        & (disengage_time >= 0.35)
    )
    perch_mask = (
        ((overlooks_area_k >= 160.0) | (overlooks_share >= 0.15))
        & ((overlook_net_area_k >= 100.0) | (overlook_net >= 0.10))
        & (overlooked_by_area_k <= 25.0)
        & (overlooked_by_share <= 0.025)
    )
    capped_mask = (disengage_reason == 4)

    # 5. Top spatially distinct 3D sightlines (ranked by true traced 3D length)
    top_sightlines = []
    order_sl = np.argsort(-max_sl_3d_raw)
    for idx in order_sl:
        L = float(max_sl_3d_raw[idx])
        tgt = int(max_sl_tgt[idx])
        if L <= 0.0 or tgt < 0:
            break
        p1 = pts[idx]
        p2 = pts[tgt]
        dup = False
        for prev in top_sightlines:
            q1, q2 = prev['_p1'], prev['_p2']
            if ((np.linalg.norm(p1 - q1) < 256.0 and np.linalg.norm(p2 - q2) < 256.0)
                    or (np.linalg.norm(p1 - q2) < 256.0 and np.linalg.norm(p2 - q1) < 256.0)):
                dup = True
                break
        if dup:
            continue
        d2 = float(max_sl_2d[idx])
        dz = float(max_sl_dz[idx])
        elev = math.degrees(math.atan2(abs(dz), max(d2, 1e-6)))
        top_sightlines.append(dict(
            length_3d=round(L),
            length_2d=round(d2),
            dz=round(dz),
            elev_deg=round(elev, 1),
            capped=bool(sl_capped[idx]),
            start=[round(float(p1[0])), round(float(p1[1])), round(float(p1[2]))],
            end=[round(float(p2[0])), round(float(p2[1])), round(float(p2[2]))],
            _p1=p1, _p2=p2,
        ))
        if len(top_sightlines) >= 5:
            break
    for sl in top_sightlines:
        sl.pop('_p1', None)
        sl.pop('_p2', None)

    # 6. Clustered hotspots
    killboxes = []
    for comp in _cluster_cells(np.nonzero(killbox_mask)[0], nodes_reach, min_cells=8):
        sub = pts[comp]
        ov_by = overlooked_by_share[comp]
        ov_by_k = overlooked_by_area_k[comp]
        ov_out = overlooks_share[comp]
        dis = disengage_time[comp]
        worst_local = comp[int(np.argmax(ov_by_k))]
        dom_j = int(dom_obs[worst_local])
        dom_pos = [round(float(v)) for v in rep_pts[dom_j]] if dom_j >= 0 else None
        killboxes.append(dict(
            cells=len(comp),
            area_k=round(len(comp) * C * C / 1000.0, 1),
            center=[round(float(sub[:, 0].mean())), round(float(sub[:, 1].mean())), round(float(sub[:, 2].mean()))],
            bounds=dict(x0=round(float(sub[:, 0].min())), x1=round(float(sub[:, 0].max())),
                        y0=round(float(sub[:, 1].min())), y1=round(float(sub[:, 1].max())),
                        z0=round(float(sub[:, 2].min())), z1=round(float(sub[:, 2].max()))),
            mean_overlooked_by=round(float(ov_by.mean()), 3),
            max_overlooked_by=round(float(ov_by.max()), 3),
            max_overlooked_by_area_k=round(float(ov_by_k.max()), 1),
            mean_overlooks=round(float(ov_out.mean()), 3),
            mean_disengage_s=round(float(dis.mean()), 2),
            max_disengage_s=round(float(dis.max()), 2),
            dominant_overlooker=dom_pos,
        ))
    killboxes.sort(key=lambda c_: (c_['area_k'] * c_['max_overlooked_by_area_k']), reverse=True)
    killboxes = killboxes[:6]

    perches = []
    for comp in _cluster_cells(np.nonzero(perch_mask)[0], nodes_reach, min_cells=6):
        sub = pts[comp]
        ov_out = overlooks_share[comp]
        ov_out_k = overlooks_area_k[comp]
        ov_by = overlooked_by_share[comp]
        perches.append(dict(
            cells=len(comp),
            area_k=round(len(comp) * C * C / 1000.0, 1),
            center=[round(float(sub[:, 0].mean())), round(float(sub[:, 1].mean())), round(float(sub[:, 2].mean()))],
            bounds=dict(x0=round(float(sub[:, 0].min())), x1=round(float(sub[:, 0].max())),
                        y0=round(float(sub[:, 1].min())), y1=round(float(sub[:, 1].max())),
                        z0=round(float(sub[:, 2].min())), z1=round(float(sub[:, 2].max()))),
            mean_overlooks=round(float(ov_out.mean()), 3),
            max_overlooks=round(float(ov_out.max()), 3),
            max_overlooks_area_k=round(float(ov_out_k.max()), 1),
            mean_overlooked_by=round(float(ov_by.mean()), 3),
        ))
    perches.sort(key=lambda c_: (c_['max_overlooks_area_k'], c_['area_k']), reverse=True)
    perches = perches[:6]

    slow_thresh = ref_table['disengage_p90_s'][1]
    slow_mask = (disengage_time >= slow_thresh) & exposed_mask
    slow_zones = []
    for comp in _cluster_cells(np.nonzero(slow_mask)[0], nodes_reach, min_cells=8):
        sub = pts[comp]
        dis = disengage_time[comp]
        exp = exposure_share[comp]
        worst_local = comp[int(np.argmax(dis))]
        dom_j = int(dom_obs[worst_local])
        dom_pos = [round(float(v)) for v in rep_pts[dom_j]] if dom_j >= 0 else None
        slow_zones.append(dict(
            cells=len(comp),
            area_k=round(len(comp) * C * C / 1000.0, 1),
            center=[round(float(sub[:, 0].mean())), round(float(sub[:, 1].mean())), round(float(sub[:, 2].mean()))],
            mean_disengage_s=round(float(dis.mean()), 2),
            max_disengage_s=round(float(dis.max()), 2),
            mean_exposure=round(float(exp.mean()), 3),
            dominant_overlooker=dom_pos,
        ))
    slow_zones.sort(key=lambda c_: (c_['max_disengage_s'], c_['area_k']), reverse=True)
    slow_zones = slow_zones[:6]

    # 7. Floor slices summary
    slices = compute_floor_slices(F, max_slices=max_slices)
    slice_summaries = []
    for s_idx, (zlo, zhi) in enumerate(slices):
        mask = (F >= zlo) & (F <= zhi) if s_idx == len(slices) - 1 else (F >= zlo) & (F < zhi)
        cnt = int(mask.sum())
        if cnt == 0:
            continue
        slice_summaries.append(dict(
            z_lo=int(zlo), z_hi=int(zhi),
            cells=cnt,
            area_share=round(cnt / N, 3),
            sightline_3d_p90=round(float(np.percentile(max_sl_3d[mask], 90))),
            sightline_3d_max=round(float(max_sl_3d[mask].max())),
            exposure_median=round(float(np.median(exposure_share[mask])), 3),
            overlook_net_mean=round(float(overlook_net[mask].mean()), 3),
            overlook_net_min=round(float(overlook_net[mask].min()), 3),
            overlook_net_max=round(float(overlook_net[mask].max()), 3),
            disengage_p90_s=round(float(np.percentile(disengage_time[mask], 90)), 2),
        ))

    # 8. Core summary metrics
    metrics = dict(
        sightline_3d_p50=round(float(np.median(max_sl_3d))),
        sightline_3d_p90=round(float(np.percentile(max_sl_3d, 90))),
        sightline_3d_max=round(float(max_sl_3d.max())),
        exposure_median=round(float(np.median(exposure_share)), 3),
        exposure_p90=round(float(np.percentile(exposure_share, 90)), 3),
        exposure_area_k_p90=round(float(np.percentile(exposure_area, 90) / 1000.0), 1),
        overlook_share=round(float((overlooks_share > 0.0).mean()), 3),
        overlooked_share=round(float(overlooked_mask.mean()), 3),
        overlooked_by_p90=round(float(np.percentile(overlooked_by_share, 90)), 3),
        overlooks_p90=round(float(np.percentile(overlooks_share, 90)), 3),
        overlooked_by_area_k_p90=round(float(np.percentile(overlooked_by_area_k, 90)), 1),
        overlooks_area_k_p90=round(float(np.percentile(overlooks_area_k, 90)), 1),
        overlook_net_p05=round(float(np.percentile(overlook_net, 5)), 3),
        overlook_net_p95=round(float(np.percentile(overlook_net, 95)), 3),
        overlook_net_area_k_p05=round(float(np.percentile(overlook_net_area_k, 5)), 1),
        overlook_net_area_k_p95=round(float(np.percentile(overlook_net_area_k, 95)), 1),
        killbox_share=round(float(killbox_mask.mean()), 3),
        perch_share=round(float(perch_mask.mean()), 3),
        disengage_p50_u=round(float(np.median(disengage_dist))),
        disengage_p90_u=round(float(np.percentile(disengage_dist, 90))),
        disengage_p50_s=round(float(np.median(disengage_time)), 2),
        disengage_p90_s=round(float(np.percentile(disengage_time, 90)), 2),
        disengage_max_s=round(float(disengage_time.max()), 2),
        disengage_exposed_p50_s=round(exp_dis_p50, 2),
        disengage_exposed_p90_s=round(exp_dis_p90, 2),
        disengage_overlooked_p90_s=round(ov_dis_p90, 2),
        disengage_sheltered_share=round(float((disengage_reason == 0).mean()), 3),
        disengage_uncovered_share=round(float(capped_mask.mean()), 3),
    )

    verdicts = {k: classify_metric(metrics[k], spec) for k, spec in ref_table.items()}
    warnings = []
    for k, v in verdicts.items():
        if v in ('HIGH', 'EXTREME'):
            lo, hi, ext, _way, desc = ref_table[k]
            warnings.append(dict(
                severity=v.lower(),
                metric=k,
                value=metrics[k],
                healthy_band=[lo, hi],
                extreme_bound=ext,
                message=f"{k}={metrics[k]} ({v} vs {ref} ref {lo}..{hi}): {desc}",
            ))
    hs_ceil = HOTSPOT_CEILINGS[ref]
    if killboxes:
        kb = killboxes[0]
        if (verdicts['killbox_share'] in ('HIGH', 'EXTREME')
                or kb['max_overlooked_by_area_k'] > hs_ceil['kb_overlooked_k']
                or kb['area_k'] > hs_ceil['kb_area_k']):
            warnings.append(dict(
                severity='high',
                metric='killbox',
                value=kb['max_overlooked_by_area_k'],
                message=(f"uncountered kill box at {kb['center']} ({kb['area_k']}k sq u): "
                         f"up to {kb['max_overlooked_by_area_k']}k sq u ({int(round(100 * kb['max_overlooked_by']))}% floor) "
                         f"shoots down from above, disengage {kb['mean_disengage_s']}s..{kb['max_disengage_s']}s"
                         + (f" (dom overlooker {kb['dominant_overlooker']})" if kb['dominant_overlooker'] else '')),
            ))
    if perches:
        pc = perches[0]
        if (verdicts['perch_share'] in ('HIGH', 'EXTREME')
                or pc['max_overlooks_area_k'] > hs_ceil['pc_overlooks_k']
                or pc['max_overlooks'] > hs_ceil['pc_overlooks_share']):
            warnings.append(dict(
                severity='high',
                metric='oppressive-perch',
                value=pc['max_overlooks_area_k'],
                message=(f"oppressive perch at {pc['center']} ({pc['area_k']}k sq u): "
                         f"overlooks up to {pc['max_overlooks_area_k']}k sq u ({int(round(100 * pc['max_overlooks']))}% floor) "
                         f"with {int(round(100 * pc['mean_overlooked_by']))}% counter-overlook"),
            ))

    elapsed = time.perf_counter() - t0
    res = dict(
        map=loaded['map'],
        ref=ref,
        floor_area_k=loaded['floor_area_k'],
        eff_levels=loaded['eff_levels'],
        spawns=loaded['spawns'],
        reachable_cells=N,
        observer_samples=len(rep_pts),
        sample_grid=sample_grid,
        sightline_capped=bool(sightline_capped_cells > 0),
        sightline_capped_cells=sightline_capped_cells,
        settings=dict(
            overlook_range=float(overlook_range),
            max_sightline=float(max_sightline),
            max_disengage=float(max_disengage),
            overlook_dz=float(overlook_dz),
            shelter_area_k=float(shelter_area_k),
            sample_cap=int(sample_cap),
        ),
        metrics=metrics,
        verdicts=verdicts,
        warnings=warnings,
        top_sightlines=top_sightlines,
        killboxes=killboxes,
        perches=perches,
        slow_zones=slow_zones,
        slices=slice_summaries,
        elapsed_s=round(elapsed, 2),
    )
    res['_draw'] = dict(
        x0=x0, y0=y0, nx=nx, ny=ny,
        nodes_reach=nodes_reach,
        pts=pts,
        slices=slices,
        max_sl_3d=max_sl_3d,
        exposure_share=exposure_share,
        overlooked_by_share=overlooked_by_share,
        overlooks_share=overlooks_share,
        overlook_net=overlook_net,
        disengage_time=disengage_time,
        top_sightlines=top_sightlines,
        killboxes=killboxes,
        perches=perches,
        slow_zones=slow_zones,
    )
    return res


# ------------------------------------------------------------------ diff mode
# Per-metric noise floors below which layout diffs report 'unchanged' instead of jitter.
def _diff_tolerance(metric):
    if metric.endswith('_s'):
        return 0.03
    if '_area_k' in metric:
        return 8.0
    if metric.startswith('sightline_3d_') or metric.endswith('_u'):
        return 16.0
    return 0.01


def compare_profiles(before, after, ref=None):
    """Compare two combat_profile() results (_b1 vs _b2) for layout review."""
    ref_name = ref or after.get('ref') or before.get('ref') or 'duel'
    ref_table, _ = get_reference_table(ref_name)
    m1, m2 = before['metrics'], after['metrics']

    deltas = {}
    for k in m1:
        v1, v2 = m1[k], m2[k]
        diff = round(v2 - v1, 4)
        pct = round(100.0 * (v2 - v1) / abs(v1), 1) if abs(v1) > 1e-9 else None
        trend = 'unchanged'
        if k in ref_table:
            lo, hi, _ext, way, _desc = ref_table[k]
            if way == 'down':
                d1 = max(0.0, v1 - hi)
                d2 = max(0.0, v2 - hi)
                safer = v2 < v1
            else:
                d1 = max(0.0, lo - v1)
                d2 = max(0.0, lo - v2)
                safer = v2 > v1
            tol = _diff_tolerance(k)
            if abs(diff) > tol:
                if d2 < d1 - 1e-4:
                    trend = 'improved'
                elif d2 > d1 + 1e-4:
                    trend = 'regressed'
                elif safer:
                    trend = 'tighter'
                else:
                    trend = 'looser'
        deltas[k] = dict(before=v1, after=v2, delta=diff, pct=pct, trend=trend)

    return dict(
        before_map=before['map'],
        after_map=after['map'],
        ref=ref_name,
        deltas=deltas,
        before_warnings=len(before['warnings']),
        after_warnings=len(after['warnings']),
        before_killboxes=len(before['killboxes']),
        after_killboxes=len(after['killboxes']),
        before_perches=len(before['perches']),
        after_perches=len(after['perches']),
        before=dict(map=before['map'], floor_area_k=before['floor_area_k'],
                    metrics=m1, verdicts=before['verdicts'], warnings=before['warnings']),
        after=dict(map=after['map'], floor_area_k=after['floor_area_k'],
                   metrics=m2, verdicts=after['verdicts'], warnings=after['warnings']),
    )


# ------------------------------------------------------------------ formatting
def format_report(res):
    ref_table, ref_label = get_reference_table(res['ref'])
    m = res['metrics']
    lines = [
        f"combat profile of {res['map']} (ref: {ref_label}; "
        f"{res['floor_area_k']}k sq u, {res['reachable_cells']} cells, "
        f"{res['observer_samples']} obs @{res['sample_grid']}u, {res['elapsed_s']}s):"
    ]
    for k, (lo, hi, ext, _way, desc) in ref_table.items():
        v = m[k]
        verd = res['verdicts'][k]
        lines.append(f"   {k:27s} {str(v):>7s}   ref {lo}..{hi:<6} (ext {ext:<6})  {verd:7s}  {desc}")
    lines.append(
        f"   summary: sightline p50={m['sightline_3d_p50']}u p90={m['sightline_3d_p90']}u max={m['sightline_3d_max']}u | "
        f"exposure med={int(round(100*m['exposure_median']))}% p90={int(round(100*m['exposure_p90']))}% | "
        f"killbox={100*m['killbox_share']:.1f}% perch={100*m['perch_share']:.1f}% | "
        f"disengage p50={m['disengage_p50_s']}s p90={m['disengage_p90_s']}s ov90={m['disengage_overlooked_p90_s']}s"
    )
    if res.get('sightline_capped'):
        cap_u = int(round(res['settings']['max_sightline']))
        lines.append(
            f"   note: sightline cap hit ({cap_u}u) on {res['sightline_capped_cells']} cells — "
            f"raise --max-sightline to measure full unobstructed lengths"
        )
    if res['top_sightlines']:
        cap_u = int(round(res['settings']['max_sightline']))
        lines.append("   longest 3D sightlines:")
        for sl in res['top_sightlines'][:3]:
            suffix = f' [capped >{cap_u}u]' if sl.get('capped') else ''
            lines.append(
                f"     {sl['length_3d']}u 3D ({sl['length_2d']}u 2D, dz={sl['dz']:+d}u, {sl['elev_deg']} deg){suffix}: "
                f"{tuple(sl['start'])} -> {tuple(sl['end'])}"
            )
    if res['killboxes']:
        lines.append("   kill boxes (high overlook-from-above + slow disengage):")
        for kb in res['killboxes'][:3]:
            ov = f", dom overlooker {tuple(kb['dominant_overlooker'])}" if kb['dominant_overlooker'] else ''
            lines.append(
                f"     at {tuple(kb['center'])} ({kb['area_k']}k sq u): "
                f"shot down by up to {kb['max_overlooked_by_area_k']}k sq u ({int(round(100*kb['max_overlooked_by']))}% floor), "
                f"disengage {kb['mean_disengage_s']}s..{kb['max_disengage_s']}s{ov}"
            )
    if res['perches']:
        lines.append("   oppressive perches (high uncountered overlook):")
        for pc in res['perches'][:3]:
            lines.append(
                f"     at {tuple(pc['center'])} ({pc['area_k']}k sq u): "
                f"overlooks up to {pc['max_overlooks_area_k']}k sq u ({int(round(100*pc['max_overlooks']))}% floor, "
                f"counter-overlook {int(round(100*pc['mean_overlooked_by']))}%)"
            )
    if res['warnings']:
        lines.append("   WARNINGS:")
        for w in res['warnings']:
            lines.append(f"     [{w['severity'].upper()}] {w['message']}")
    else:
        lines.append("   no combat-exposure warnings against reference bands")
    return '\n'.join(lines)


def format_diff_report(diff):
    ref_table, ref_label = get_reference_table(diff['ref'])
    lines = [
        f"combat diff: {diff['before_map']} -> {diff['after_map']} (ref: {ref_label}):",
        f"   warnings: {diff['before_warnings']} -> {diff['after_warnings']} | "
        f"killboxes: {diff['before_killboxes']} -> {diff['after_killboxes']} | "
        f"perches: {diff['before_perches']} -> {diff['after_perches']}",
    ]
    for k in ref_table:
        d = diff['deltas'][k]
        sign = '+' if d['delta'] > 0 else ''
        pct = f" ({d['pct']:+.1f}%)" if d['pct'] is not None else ''
        lines.append(
            f"   {k:27s} {str(d['before']):>7s} -> {str(d['after']):>7s}  "
            f"[{sign}{d['delta']}{pct}]  {d['trend']}"
        )
    return '\n'.join(lines)


# ------------------------------------------------------------------ heatmaps
def _slice_grid(D, z_lo, z_hi, is_last, values, mode='max'):
    """Rasterize per-cell values into a (ny, nx) array for one Z slice."""
    grid = np.full((D['ny'], D['nx']), np.nan, np.float64)
    F = D['pts'][:, 2]
    mask = (F >= z_lo) & (F <= z_hi) if is_last else (F >= z_lo) & (F < z_hi)
    idxs = np.nonzero(mask)[0]
    nodes = D['nodes_reach']
    for k in idxs:
        gi, gj, _ = nodes[int(k)]
        val = float(values[int(k)])
        cur = grid[gj, gi]
        if math.isnan(cur):
            grid[gj, gi] = val
        elif mode == 'max':
            if val > cur:
                grid[gj, gi] = val
        elif mode == 'absmax':
            if abs(val) > abs(cur):
                grid[gj, gi] = val
    return grid


def _style_world_axes(ax, show_x, show_y):
    """Apply readable world-coordinate ticks and subtle gridlines on dark heatmap panels."""
    from matplotlib.ticker import MaxNLocator

    ax.xaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, integer=True))
    ax.tick_params(
        colors='#999', labelsize=6.5, length=2.5, pad=2,
        labelbottom=show_x, labelleft=show_y,
    )
    ax.grid(color='#ffffff', alpha=0.08, linewidth=0.5, linestyle='--')
    for sp in ax.spines.values():
        sp.set_color('#3a3d42')
        sp.set_linewidth(0.6)


def draw(res, out):
    """Render floor-sliced 3-column combat heatmap PNG (3D sightlines, overlook asymmetry, disengage time)."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    D = res['_draw']
    slices = D['slices']
    nrows = max(1, len(slices))
    aspect = D['ny'] / max(D['nx'], 1)
    col_w = 4.6
    row_h = max(2.8, min(4.6, col_w * aspect + 0.5))
    fig, axes = plt.subplots(nrows, 3, figsize=(col_w * 3 + 1.4, row_h * nrows + 1.2),
                             facecolor='#18191b', squeeze=False)

    sl_vmax = max(1200.0, float(np.percentile(D['max_sl_3d'], 99)))
    ov_vlim = max(0.12, float(np.percentile(np.abs(D['overlook_net']), 99)))
    dis_vmax = min(2.5, max(1.2, float(np.percentile(D['disengage_time'], 97))))
    extent = [D['x0'], D['x0'] + D['nx'] * C, D['y0'], D['y0'] + D['ny'] * C]

    m = res['metrics']
    fig.suptitle(
        f"{res['map']} — 3D Combat Profile  |  sightline p90 {m['sightline_3d_p90']}u (max {m['sightline_3d_max']}u)  |  "
        f"overlook net [{m['overlook_net_p05']:+.2f}, {m['overlook_net_p95']:+.2f}]  |  "
        f"disengage p50 {m['disengage_p50_s']}s / p90 {m['disengage_p90_s']}s\n"
        f"overlays: cyan dashed = longest 3D sightlines  |  yellow x = kill box  |  green ^ = perch  |  cyan o = slow disengage",
        color='white', fontsize=9.2, y=0.992,
    )

    col_titles = [
        '3D Sightline Length (u)',
        'Overlook Asymmetry (-killbox / +perch)',
        'Disengage / Time to Cover (s)',
    ]

    for r_idx, (zlo, zhi) in enumerate(slices):
        is_last = (r_idx == len(slices) - 1)
        g_sl = _slice_grid(D, zlo, zhi, is_last, D['max_sl_3d'], mode='max')
        g_ov = _slice_grid(D, zlo, zhi, is_last, D['overlook_net'], mode='absmax')
        g_ds = _slice_grid(D, zlo, zhi, is_last, D['disengage_time'], mode='max')

        specs = [
            (g_sl, 'inferno', 0.0, sl_vmax),
            (g_ov, 'RdBu', -ov_vlim, ov_vlim),
            (g_ds, 'magma', 0.0, dis_vmax),
        ]
        for c_idx, (g, cmap, vmin, vmax) in enumerate(specs):
            ax = axes[r_idx, c_idx]
            ax.set_facecolor('#0d0d0e')
            im = ax.imshow(g, origin='lower', extent=extent, cmap=cmap,
                           vmin=vmin, vmax=vmax, interpolation='nearest')
            _style_world_axes(ax, show_x=is_last, show_y=(c_idx == 0))
            if r_idx == 0:
                ax.set_title(col_titles[c_idx], color='white', fontsize=9)
            if c_idx == 0:
                ax.set_ylabel(f'y  (z {int(zlo)}..{int(zhi)})', color='#ccc', fontsize=8)
            if is_last:
                ax.set_xlabel('x (world u)', color='#999', fontsize=7.5)
            if c_idx == 0:
                for sl in D['top_sightlines'][:2]:
                    s_z, e_z = sl['start'][2], sl['end'][2]
                    if (zlo <= s_z <= zhi) or (zlo <= e_z <= zhi):
                        ax.plot(
                            [sl['start'][0], sl['end'][0]],
                            [sl['start'][1], sl['end'][1]],
                            '--', color='#00f0ff', lw=1.2, alpha=0.85,
                        )
            elif c_idx == 1:
                for kb in D['killboxes'][:3]:
                    if zlo <= kb['center'][2] <= zhi:
                        ax.plot(kb['center'][0], kb['center'][1],
                                'x', color='#ffff00', ms=7, mew=1.8)
                for pc in D['perches'][:3]:
                    if zlo <= pc['center'][2] <= zhi:
                        ax.plot(pc['center'][0], pc['center'][1],
                                '^', color='#00ff88', ms=6, mec='black', mew=0.6)
            elif c_idx == 2:
                for sz in D['slow_zones'][:3]:
                    if zlo <= sz['center'][2] <= zhi:
                        ax.plot(sz['center'][0], sz['center'][1],
                                'o', mfc='none', mec='#00f0ff', ms=7, mew=1.5)
            cb = fig.colorbar(im, ax=ax, fraction=0.042, pad=0.02)
            cb.ax.tick_params(colors='#bbb', labelsize=7)

    fig_h = row_h * nrows + 1.2
    top_rect = max(0.84, min(0.96, 1.0 - 0.64 / fig_h))
    plt.tight_layout(rect=[0, 0, 1, top_rect])
    fig.savefig(out, dpi=115, facecolor=fig.get_facecolor())
    plt.close(fig)


def draw_diff(before, after, diff, out):
    """Render floor-sliced spatial diff heatmap (_b2 - _b1) on shared 16u world coordinates."""
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.colors import LinearSegmentedColormap
    import matplotlib.pyplot as plt

    diff_cmap = LinearSegmentedColormap.from_list(
        'combat_diff',
        ['#16d96a', '#1b6d41', '#2c3036', '#8d2b2b', '#ff3b30'],
    )

    D1, D2 = before['_draw'], after['_draw']
    x0 = min(D1['x0'], D2['x0'])
    y0 = min(D1['y0'], D2['y0'])
    x1 = max(D1['x0'] + D1['nx'] * C, D2['x0'] + D2['nx'] * C)
    y1 = max(D1['y0'] + D1['ny'] * C, D2['y0'] + D2['ny'] * C)
    nx = int(round((x1 - x0) / C))
    ny = int(round((y1 - y0) / C))
    extent = [x0, x0 + nx * C, y0, y0 + ny * C]

    F_all = np.concatenate([D1['pts'][:, 2], D2['pts'][:, 2]])
    slices = compute_floor_slices(F_all, max_slices=max(len(D1['slices']), len(D2['slices'])))
    nrows = max(1, len(slices))
    aspect = ny / max(nx, 1)
    col_w = 4.6
    row_h = max(2.8, min(4.6, col_w * aspect + 0.5))
    fig, axes = plt.subplots(nrows, 3, figsize=(col_w * 3 + 1.4, row_h * nrows + 1.2),
                             facecolor='#18191b', squeeze=False)

    def raster_shared(D, zlo, zhi, is_last, values, mode='max'):
        g = np.full((ny, nx), np.nan, np.float64)
        F = D['pts'][:, 2]
        mask = (F >= zlo) & (F <= zhi) if is_last else (F >= zlo) & (F < zhi)
        off_i = int(round((D['x0'] - x0) / C))
        off_j = int(round((D['y0'] - y0) / C))
        nodes = D['nodes_reach']
        for k in np.nonzero(mask)[0]:
            gi, gj, _ = nodes[int(k)]
            ci, cj = gi + off_i, gj + off_j
            if 0 <= ci < nx and 0 <= cj < ny:
                val = float(values[int(k)])
                cur = g[cj, ci]
                if math.isnan(cur):
                    g[cj, ci] = val
                elif mode == 'max' and val > cur:
                    g[cj, ci] = val
                elif mode == 'absmax' and abs(val) > abs(cur):
                    g[cj, ci] = val
        return g

    d_sl_all = []
    d_ov_all = []
    d_ds_all = []
    slice_grids = []
    for r_idx, (zlo, zhi) in enumerate(slices):
        is_last = (r_idx == len(slices) - 1)
        g1_sl = raster_shared(D1, zlo, zhi, is_last, D1['max_sl_3d'], 'max')
        g2_sl = raster_shared(D2, zlo, zhi, is_last, D2['max_sl_3d'], 'max')
        g_sl = g2_sl - g1_sl
        g_ov = (np.abs(raster_shared(D2, zlo, zhi, is_last, D2['overlook_net'], 'absmax'))
                - np.abs(raster_shared(D1, zlo, zhi, is_last, D1['overlook_net'], 'absmax')))
        g_ds = (raster_shared(D2, zlo, zhi, is_last, D2['disengage_time'], 'max')
                - raster_shared(D1, zlo, zhi, is_last, D1['disengage_time'], 'max'))

        # Floor present in only one build (cyan = added in after, violet = removed from before)
        added = np.isfinite(g2_sl) & ~np.isfinite(g1_sl)
        removed = np.isfinite(g1_sl) & ~np.isfinite(g2_sl)
        chg_rgba = np.zeros((ny, nx, 4), np.float32)
        chg_rgba[added] = (0.22, 0.74, 0.97, 0.78)
        chg_rgba[removed] = (0.75, 0.52, 0.99, 0.72)

        slice_grids.append((zlo, zhi, g_sl, g_ov, g_ds, chg_rgba))
        if np.any(np.isfinite(g_sl)):
            d_sl_all.append(np.abs(g_sl[np.isfinite(g_sl)]))
        if np.any(np.isfinite(g_ov)):
            d_ov_all.append(np.abs(g_ov[np.isfinite(g_ov)]))
        if np.any(np.isfinite(g_ds)):
            d_ds_all.append(np.abs(g_ds[np.isfinite(g_ds)]))

    v_sl = max(128.0, float(np.percentile(np.concatenate(d_sl_all), 98))) if d_sl_all else 256.0
    v_ov = max(0.05, float(np.percentile(np.concatenate(d_ov_all), 98))) if d_ov_all else 0.15
    v_ds = max(0.25, float(np.percentile(np.concatenate(d_ds_all), 98))) if d_ds_all else 0.50

    dlt = diff['deltas']
    fig.suptitle(
        f"Combat Diff: {diff['before_map']} -> {diff['after_map']}  |  "
        f"sightline p90 {int(round(dlt['sightline_3d_p90']['delta'])):+d}u  |  "
        f"killbox p05 {dlt['overlook_net_p05']['delta']:+.3f}  |  "
        f"disengage p90 {dlt['disengage_p90_s']['delta']:+.2f}s\n"
        f"green = improved  |  dark slate = unchanged  |  red = worse  |  cyan = added floor  |  violet = removed floor",
        color='white', fontsize=9.2, y=0.992,
    )

    col_titles = [
        'Delta 3D Sightline (u)',
        'Delta |Overlook Asymmetry|',
        'Delta Disengage Time (s)',
    ]
    for r_idx, (zlo, zhi, g_sl, g_ov, g_ds, chg_rgba) in enumerate(slice_grids):
        is_last = (r_idx == len(slice_grids) - 1)
        for c_idx, (g, vlim) in enumerate(((g_sl, v_sl), (g_ov, v_ov), (g_ds, v_ds))):
            ax = axes[r_idx, c_idx]
            ax.set_facecolor('#0d0d0e')
            im = ax.imshow(g, origin='lower', extent=extent, cmap=diff_cmap,
                           vmin=-vlim, vmax=vlim, interpolation='nearest')
            if np.any(chg_rgba[:, :, 3] > 0):
                ax.imshow(chg_rgba, origin='lower', extent=extent, interpolation='nearest')
            _style_world_axes(ax, show_x=is_last, show_y=(c_idx == 0))
            if r_idx == 0:
                ax.set_title(col_titles[c_idx], color='white', fontsize=9)
            if c_idx == 0:
                ax.set_ylabel(f'y  (z {int(zlo)}..{int(zhi)})', color='#ccc', fontsize=8)
            if is_last:
                ax.set_xlabel('x (world u)', color='#999', fontsize=7.5)
            cb = fig.colorbar(im, ax=ax, fraction=0.042, pad=0.02)
            cb.ax.tick_params(colors='#bbb', labelsize=7)

    fig_h = row_h * nrows + 1.2
    top_rect = max(0.84, min(0.96, 1.0 - 0.64 / fig_h))
    plt.tight_layout(rect=[0, 0, 1, top_rect])
    fig.savefig(out, dpi=115, facecolor=fig.get_facecolor())
    plt.close(fig)


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description='3D BSP exposure, overlook asymmetry & disengage-time analyzer.')
    ap.add_argument('maps', nargs='*', help='Compiled BSP29 map file(s)')
    ap.add_argument('--diff', nargs='+', metavar='BSP',
                    help='Compare two builds: --diff b1.bsp b2.bsp (or pass b1.bsp --diff b2.bsp)')
    ap.add_argument('--ref', choices=('duel', 'large', 'all'), default='duel',
                    help='Classic QW reference pool (default: duel)')
    ap.add_argument('--json', dest='json_out', help='Write structured JSON report to path')
    ap.add_argument('--png', dest='png_out', help='Write heatmap PNG to explicit file path (single map or diff)')
    ap.add_argument('--png-dir', dest='png_dir', help='Write heatmap PNG(s) into directory')
    ap.add_argument('--slices', type=int, default=DEFAULT_MAX_SLICES,
                    help=f'Maximum floor Z-slices for heatmaps (default: {DEFAULT_MAX_SLICES})')
    ap.add_argument('--overlook-range', type=float, default=DEFAULT_OVERLOOK_RANGE,
                    help=f'Horizontal range for overlook checks in units (default: {int(DEFAULT_OVERLOOK_RANGE)})')
    ap.add_argument('--overlook-dz', type=float, default=DEFAULT_OVERLOOK_DZ,
                    help=f'Minimum vertical elevation delta for overlook checks in units (default: {int(DEFAULT_OVERLOOK_DZ)})')
    ap.add_argument('--max-sightline', type=float, default=DEFAULT_MAX_SIGHTLINE,
                    help=f'Maximum 3D sightline distance in units (default: {int(DEFAULT_MAX_SIGHTLINE)})')
    ap.add_argument('--max-disengage', type=float, default=DEFAULT_MAX_DISENGAGE,
                    help=f'Disengage search cap in walk units (default: {int(DEFAULT_MAX_DISENGAGE)})')
    ap.add_argument('--shelter-area-k', type=float, default=DEFAULT_SHELTER_AREA_K,
                    help=f'Visible area (k sq u) below which un-overlooked floor counts as cover (default: {int(DEFAULT_SHELTER_AREA_K)})')
    ap.add_argument('--sample-cap', type=int, default=DEFAULT_SAMPLE_CAP,
                    help=f'Maximum 3D observer sample buckets (default: {DEFAULT_SAMPLE_CAP})')
    args = ap.parse_args(argv)

    if args.slices <= 0:
        ap.error('--slices must be positive')

    common = dict(
        overlook_range=args.overlook_range,
        overlook_dz=args.overlook_dz,
        max_sightline=args.max_sightline,
        max_disengage=args.max_disengage,
        shelter_area_k=args.shelter_area_k,
        sample_cap=args.sample_cap,
        max_slices=args.slices,
        ref=args.ref,
    )

    try:
        if args.diff is not None:
            if len(args.diff) == 2 and not args.maps:
                p1, p2 = args.diff
            elif len(args.diff) == 1 and len(args.maps) == 1:
                p1, p2 = args.maps[0], args.diff[0]
            else:
                ap.error('--diff requires exactly two BSP paths (e.g. --diff b1.bsp b2.bsp or b1.bsp --diff b2.bsp)')
            b1 = combat_profile(p1, **common)
            b2 = combat_profile(p2, **common)
            diff = compare_profiles(b1, b2, ref=args.ref)
            if args.png_out or args.png_dir:
                out_png = args.png_out or os.path.join(args.png_dir, f"{b1['map']}_vs_{b2['map']}.diff.png")
                os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
                draw_diff(b1, b2, diff, out_png)
            print(format_diff_report(diff))
            if args.json_out:
                with open(args.json_out, 'w', encoding='utf-8') as f:
                    json.dump(diff, f, indent=1)
                    f.write('\n')
            return 0

        if not args.maps:
            ap.error('provide at least one .bsp path or use --diff b1.bsp b2.bsp')
        if args.png_out and len(args.maps) > 1:
            ap.error('--png supports a single input map; use --png-dir for multiple maps')

        results = []
        for p in args.maps:
            res = combat_profile(p, **common)
            if args.png_out or args.png_dir:
                out_png = args.png_out or os.path.join(args.png_dir, res['map'] + '.combat.png')
                os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
                draw(res, out_png)
            res.pop('_draw')
            print(format_report(res))
            results.append(res)

        if args.json_out:
            with open(args.json_out, 'w', encoding='utf-8') as f:
                json.dump(results if len(results) > 1 else results[0], f, indent=1)
                f.write('\n')
        return 0
    except (OSError, ValueError, AssertionError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
