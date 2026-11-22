"""Prove a visual-only build did not change collision: compare the SOLID space of two generated
.map files on a voxel grid (default 8-unit). Counts all solid brushes in worldspawn and func_group
— both axis-aligned boxes and general convex brushes (ramps, prisms, chamfers, veneers) via half-space
planes (func_detail_illusionary fixtures, triggers and lights are not solid). Bounds are read from the maps.
Usage: python3 collide_cmp.py old.map new.map [--step 8]"""
import itertools
import re
import sys

import numpy as np

PT_RE = re.compile(r'\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)')


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
    """Return (aabb_lo, aabb_hi, planes, is_aabb) for one brush, or None if degenerate.
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
                return (lo_a, hi_a, (N, D), True)
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
    return (lo_a, hi_a, (N, D), False)


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
    step = 8
    if '--step' in args:
        idx = args.index('--step')
        step = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]
    pA, pB = args[0], args[1]
    A, B = brushes(pA), brushes(pB)
    all_lo = np.array([b[0] for b in A + B])
    all_hi = np.array([b[1] for b in A + B])
    lo = np.floor(all_lo.min(0) / step).astype(int) * step
    hi = np.ceil(all_hi.max(0) / step).astype(int) * step
    shape = tuple(((hi - lo) // step).astype(int))

    def vox(bs):
        g = np.zeros(shape, bool)
        for blo, bhi, (N, D), is_aabb in bs:
            # Slice covering all voxel centers lo + (i + 0.5)*step that could fall inside [blo, bhi]
            i0 = np.maximum(0, np.ceil((blo - lo) / step - 0.5 - 1e-9).astype(int))
            i1 = np.minimum(shape, np.floor((bhi - lo) / step - 0.5 + 1e-9).astype(int) + 1)
            if np.any(i1 <= i0):
                continue
            if is_aabb:
                g[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] = True
            else:
                xs = lo[0] + (np.arange(i0[0], i1[0]) + 0.5) * step
                ys = lo[1] + (np.arange(i0[1], i1[1]) + 0.5) * step
                zs = lo[2] + (np.arange(i0[2], i1[2]) + 0.5) * step
                # Evaluate N @ p <= D + 1e-4 via separable outer sums (fast, low memory)
                inside = np.ones((len(xs), len(ys), len(zs)), bool)
                for n, d in zip(N, D):
                    val = (n[0] * xs)[:, None, None] + (n[1] * ys)[None, :, None] + (n[2] * zs)[None, None, :]
                    inside &= (val <= d + 1e-4)
                    if not inside.any():
                        break
                g[i0[0]:i1[0], i0[1]:i1[1], i0[2]:i1[2]] |= inside
        return g

    diff = vox(A) ^ vox(B)
    na = sum(not b[3] for b in A)
    nb = sum(not b[3] for b in B)
    print(f'{pA}: {len(A)} solid brushes ({na} non-axis), {pB}: {len(B)} solid brushes ({nb} non-axis)')
    if diff.any():
        idx = np.argwhere(diff)
        pts = [tuple(float(v) for v in lo + (k + 0.5) * step) for k in idx[:5]]
        print(f'COLLISION DIFFERS: {len(idx)} voxels (step={step}), e.g.', pts)
        sys.exit(1)
    print(f'collision identical (solid space matches voxel for voxel, step={step})')


if __name__ == '__main__':
    main()
