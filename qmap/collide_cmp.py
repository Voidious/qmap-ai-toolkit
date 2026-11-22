"""Prove a visual-only build did not change collision: compare the SOLID space of two generated
.map files on a voxel grid (default 8-unit, supports sub-unit floats e.g. --step 0.5). Counts all
solid brushes in worldspawn and func_group — both axis-aligned boxes and general convex brushes
(ramps, prisms, chamfers, veneers) via half-space planes (func_detail_illusionary fixtures, triggers
and lights are not solid). Prefilters to differing brush geometry clustered into overlapping ROI
components and streams one Z-slice at a time, so sub-unit resolution uses only a few MB of RAM.
Usage: python3 collide_cmp.py old.map new.map [--step 8]"""
from collections import Counter
import itertools
import re
import sys

import numpy as np

PT_RE = re.compile(r'\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)')
MAX_SLICE = 50_000_000   # ~50 MB per 2D bool slice (plenty for any realistic ROI even at step=0.25)


def entities(txt):
    out, depth, start = [], 0, 0
    for k, ch in enumerate(txt):
        if ch == '{':
            if depth == 0:
                start = k
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                out.append(txt[start:k + 1])
    return out


def parse_brush(br):
    """Return (aabb_lo, aabb_hi, (N, D), is_aabb, geom_key) for one brush, or None if degenerate.
    Quake .map face winding: (p3 - p1) x (p2 - p1) points OUTWARD, so inside is n.x <= d."""
    planes = []
    for line in br.split('\n'):
        pts = PT_RE.findall(line)
        if len(pts) < 3:
            continue
        p1, p2, p3 = (np.array([float(v) for v in pts[k]]) for k in range(3))
        n = np.cross(p3 - p1, p2 - p1)
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            continue
        n /= ln
        planes.append((n, float(np.dot(n, p1))))
    if len(planes) < 4:
        return None
    N = np.array([p[0] for p in planes])
    D = np.array([p[1] for p in planes])
    # Canonical geometry key (independent of textures/ordering) for exact common-brush prefiltering
    gkey = tuple(sorted(
        (round(float(n[0]) + 0.0, 6), round(float(n[1]) + 0.0, 6), round(float(n[2]) + 0.0, 6), round(float(d) + 0.0, 4))
        for n, d in planes
    ))
    # Fast path: pure axis-aligned 6-face box
    if len(planes) == 6 and np.all(np.max(np.abs(N), axis=1) > 1.0 - 1e-6):
        lo, hi = [None, None, None], [None, None, None]
        for n, d in planes:
            ax = int(np.argmax(np.abs(n)))
            if n[ax] < 0:
                lo[ax] = -d
            else:
                hi[ax] = d
        if all(v is not None for v in lo + hi):
            lo_a, hi_a = np.array(lo), np.array(hi)
            if np.all(hi_a > lo_a + 1e-6):
                return (lo_a, hi_a, (N, D), True, gkey)
            return None
    # General convex brush: exact bounding box from feasible plane-triple intersections
    verts = []
    m = len(planes)
    for i, j, k in itertools.combinations(range(m), 3):
        M = N[[i, j, k]]
        if abs(np.linalg.det(M)) < 1e-6:
            continue
        v = np.linalg.solve(M, D[[i, j, k]])
        if np.all(N @ v <= D + 1e-3):
            verts.append(v)
    if len(verts) < 4:
        return None
    V = np.array(verts)
    lo_a, hi_a = V.min(0), V.max(0)
    if np.any(hi_a <= lo_a + 1e-6):
        return None
    return (lo_a, hi_a, (N, D), False, gkey)


def brushes(path):
    out, skipped = [], 0
    for e in entities(open(path).read()):
        m = re.search(r'"classname" "([^"]+)"', e)
        if not m or m.group(1) not in ('worldspawn', 'func_group'):
            continue
        for br in re.findall(r'\{\n(\(.*?)\n\}', e, re.S):
            pb = parse_brush(br)
            if pb is None:
                skipped += 1
            else:
                out.append(pb)
    if skipped:
        print(f'WARNING: {path}: skipped {skipped} degenerate/unbounded brush(es)', file=sys.stderr)
    return out


def main():
    args = sys.argv[1:]
    step = 8.0
    if '--step' in args:
        idx = args.index('--step')
        if idx + 1 >= len(args):
            print('usage: collide_cmp.py old.map new.map [--step N]', file=sys.stderr)
            sys.exit(2)
        try:
            step = float(args[idx + 1])
        except ValueError:
            print(f'invalid --step value: {args[idx + 1]}', file=sys.stderr)
            sys.exit(2)
        if step <= 0:
            print(f'--step must be positive, got {step}', file=sys.stderr)
            sys.exit(2)
        args = args[:idx] + args[idx + 2:]
    if len(args) != 2:
        print('usage: collide_cmp.py old.map new.map [--step N]', file=sys.stderr)
        sys.exit(2)

    pA, pB = args[0], args[1]
    A, B = brushes(pA), brushes(pB)
    na = sum(not b[3] for b in A)
    nb = sum(not b[3] for b in B)
    print(f'{pA}: {len(A)} solid brushes ({na} non-axis), {pB}: {len(B)} solid brushes ({nb} non-axis)')

    # Exact prefilter: any symmetric difference must lie inside the bbox of brushes whose geometry
    # is not present in both maps. Cluster differing brushes into overlapping AABB components so
    # distant changed corners don't inflate one giant ROI box across empty space between them.
    cA, cB = Counter(b[4] for b in A), Counter(b[4] for b in B)
    common = cA & cB
    remA, remB = cA - common, cB - common
    if not remA and not remB:
        print(f'collision identical (all {len(A)} solid brush geometries identical)')
        return

    diff_brushes = [b for b in A if b[4] in remA] + [b for b in B if b[4] in remB]
    comps = []
    for b in diff_brushes:
        blo, bhi = b[0].copy(), b[1].copy()
        merged, keep = (blo, bhi), []
        for clo, chi in comps:
            if np.all(chi >= merged[0] - 1e-6) and np.all(clo <= merged[1] + 1e-6):
                merged = (np.minimum(merged[0], clo), np.maximum(merged[1], chi))
            else:
                keep.append((clo, chi))
        keep.append(merged)
        comps = keep

    def vox_slice(bs, lo, nx, ny, zc):
        g = np.zeros((nx, ny), bool)
        for blo, bhi, (N, D), is_aabb, _ in bs:
            if zc < blo[2] - 1e-4 or zc > bhi[2] + 1e-4:
                continue
            ix0 = max(0, int(np.ceil((blo[0] - lo[0]) / step - 0.5 - 1e-9)))
            ix1 = min(nx, int(np.floor((bhi[0] - lo[0]) / step - 0.5 + 1e-9)) + 1)
            iy0 = max(0, int(np.ceil((blo[1] - lo[1]) / step - 0.5 - 1e-9)))
            iy1 = min(ny, int(np.floor((bhi[1] - lo[1]) / step - 0.5 + 1e-9)) + 1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            if is_aabb:
                g[ix0:ix1, iy0:iy1] = True
            else:
                xs = lo[0] + (np.arange(ix0, ix1) + 0.5) * step
                ys = lo[1] + (np.arange(iy0, iy1) + 0.5) * step
                inside = np.ones((ix1 - ix0, iy1 - iy0), bool)
                for n, d in zip(N, D):
                    rhs = d - n[2] * zc + 1e-4
                    if abs(n[0]) < 1e-9 and abs(n[1]) < 1e-9:
                        if rhs < 0:
                            inside[:] = False
                            break
                    else:
                        inside &= ((n[0] * xs)[:, None] + (n[1] * ys)[None, :] <= rhs)
                        if not inside.any():
                            break
                g[ix0:ix1, iy0:iy1] |= inside
        return g

    total_diff, sample_pts, shapes = 0, [], []
    for roi_lo, roi_hi in comps:
        lo = np.floor(roi_lo / step) * step
        hi = np.ceil(roi_hi / step) * step
        nx, ny, nz = (int(v) for v in np.maximum(1, np.round((hi - lo) / step).astype(int)))
        if nx * ny > MAX_SLICE:
            mb = (nx * ny) / (1024 ** 2)
            print(f'ERROR: ROI 2D slice {(nx, ny)} ({mb:.1f} MiB per slice at step={step:g}) exceeds limit; use a larger --step',
                  file=sys.stderr)
            sys.exit(2)
        shapes.append((nx, ny, nz))
        subA = [b for b in A if bool(np.all(b[1] > lo - 1e-6) and np.all(b[0] < hi + 1e-6))]
        subB = [b for b in B if bool(np.all(b[1] > lo - 1e-6) and np.all(b[0] < hi + 1e-6))]
        for iz in range(nz):
            zc = lo[2] + (iz + 0.5) * step
            diff = vox_slice(subA, lo, nx, ny, zc) ^ vox_slice(subB, lo, nx, ny, zc)
            if diff.any():
                idx = np.argwhere(diff)
                total_diff += len(idx)
                for ix, iy in idx[:max(0, 5 - len(sample_pts))]:
                    sample_pts.append((float(lo[0] + (ix + 0.5) * step), float(lo[1] + (iy + 0.5) * step), float(zc)))

    if total_diff:
        print(f'COLLISION DIFFERS: {total_diff} voxels (step={step:g}, {len(comps)} ROI(s)), e.g.', sample_pts)
        sys.exit(1)
    print(f'collision identical (solid space matches voxel for voxel, step={step:g}, {len(comps)} ROI(s) {shapes})')


if __name__ == '__main__':
    main()
