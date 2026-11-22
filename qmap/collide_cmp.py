"""Prove a visual-only build did not change collision: compare the SOLID space of two generated
.map files on a voxel grid (default 8-unit, supports sub-unit floats e.g. --step 0.5). Counts every
brush qbsp puts in the player collision hull -- both axis-aligned boxes and general convex brushes
(ramps, prisms, chamfers, veneers) via half-space planes -- and reports on stderr what it ignored,
so a brush flavour the rules below do not know about is named rather than silently dropped.
Water, slime and lava volumes are not solid, so they are excluded from the solid space and each
compared as its own class: a *water pool retextured *lava occupies the same volume but is a very
different room, and that shows up as a lava/water difference rather than vanishing.
Usage: python3 collide_cmp.py old.map new.map [--step 8]"""
from collections import Counter
import itertools
import math
import re
import sys

import numpy as np

PT_RE = re.compile(r'\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)')
MAX_SLICE = 50_000_000        # ~50 MB per 2D bool slice
MAX_TOTAL_VOXELS = 10_000_000_000  # ~10G voxel evaluations (~25-35s); refuse legibly instead of hanging

# Brush entities ericw-tools qbsp merges into the world model (IsWorldBrushEntity, qbsp/map.cc),
# less the two it then drops from the collision hulls. Measured by compiling a 128-unit cube in a
# sealed room per flavour and comparing clipnode counts against an empty control, not read off the
# source: func_detail / func_detail_wall / func_detail_fence all raise the count, so all three are
# solid to players. func_illusionary_visblocker is the trap -- it passes IsWorldBrushEntity(), so
# "count everything IsWorldBrushEntity accepts" would wrongly include it, but qbsp replaces its
# contents with ILLUSIONARY_VISBLOCKER (qbsp/map.cc, string_iequals branch) and it measures at the
# control's clipnode count. qbsp compares classnames with Q_strcasecmp, so match case-insensitively.
SOLID_CLASSNAMES = frozenset(('worldspawn', 'func_group', 'func_detail',
                              'func_detail_wall', 'func_detail_fence'))
# Merged into the world and then explicitly absent from every collision hull.
NO_COLLISION_CLASSNAMES = frozenset(('func_detail_illusionary', 'func_illusionary_visblocker'))

HINT_TEX = frozenset(('hint', 'hintskip'))
# Content classes, each compared independently: (class, label, DIFFERS banner, space noun).
# Independently, because a brush that changes class -- a wall retextured '*lava', a '*water' pool
# retextured '*lava' -- leaves one set and joins another, so both report a difference. Lumping the
# liquids together as one "non-solid" space would miss a water->lava swap, which fills exactly the
# same volume. 'solid' is always compared; a liquid class absent from both maps is skipped.
CLASSES = (('solid', 'collision', 'COLLISION DIFFERS', 'solid space'),
           ('water', 'water contents', 'WATER CONTENTS DIFFER', 'water volume'),
           ('slime', 'slime contents', 'SLIME CONTENTS DIFFER', 'slime volume'),
           ('lava', 'lava contents', 'LAVA CONTENTS DIFFER', 'lava volume'))
LIQUIDS = ('water', 'slime', 'lava')


def face_class(tex):
    """The content class one face texture asks for, by ericw-tools' Quake rules
    (face_get_contents, common/bspfile.cc). 'hint' and 'origin' mean no collision at all.

    Everything not listed is solid, which includes 'clip', 'skip', 'sky*' and 'trigger' -- all
    measured solid in the player hull, so none of them may be excluded on the strength of their
    name -- and includes '!'-prefixed names, which are liquid only in Half-Life, not here."""
    t = tex.lower()
    if t in HINT_TEX:
        return 'hint'
    if t == 'origin':
        return 'origin'
    if t.startswith('*'):
        return ('lava' if t[1:].startswith('lava') else
                'slime' if t[1:].startswith('slime') else 'water')
    return 'solid'


def brush_contents(texes):
    """(content class, mixed-contents?) for one brush, from its face textures in file order.

    Two independent qbsp rules, both measured by clipnode count rather than read off the source:
      - A single 'hint'/'hintskip' face anywhere drops the whole brush from the collision hulls,
        whatever the other five faces say (MapBrush_IsHint tests *any* face). Reading only
        face_get_contents() gets this backwards: hint returns *empty* contents there, which the
        first-face rule below skips over, predicting solid.
      - Otherwise the FIRST face in file order decides, and qbsp prints 'brush has multiple face
        contents (X vs Y), the former will be used'. So face order in the .map file decides whether
        a brush with one '*' face is a pool or a wall: '*lava' on face 1 of 6 measures non-solid,
        the same brush with '*lava' on face 6 measures solid."""
    fcs = [face_class(t) for t in texes]
    if not fcs or 'hint' in fcs:
        return 'hint', False
    return fcs[0], len(set(fcs)) > 1


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
    """Return (aabb_lo, aabb_hi, (N, D), is_aabb, geom_key, face_textures) for one brush, or None
    if degenerate. Quake .map face winding: (p3 - p1) x (p2 - p1) points OUTWARD, so inside is
    n.x <= d. Face textures come back in file order, including any face whose plane was degenerate,
    because qbsp reads the contents of every face regardless."""
    planes, texes = [], []
    for line in br.split('\n'):
        pts = list(PT_RE.finditer(line))
        if len(pts) < 3:
            continue
        # the texture name is the first token after the third ( x y z ) plane point, in both the
        # standard and the Valve 220 face format (whose [ s ] [ t ] axes follow the name)
        rest = line[pts[2].end():].split()
        texes.append(rest[0] if rest else '')
        p1, p2, p3 = (np.array([float(v) for v in pts[k].groups()]) for k in range(3))
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
                return (lo_a, hi_a, (N, D), True, gkey, texes)
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
    return (lo_a, hi_a, (N, D), False, gkey, texes)


def brushes(path):
    """Brushes per content class, with a stderr note accounting for every one ignored.

    The note is what keeps this blind spot from coming back: a classname or texture flavour these
    rules do not know about is reported by name instead of vanishing from the comparison."""
    out = {k: [] for k, _, _, _ in CLASSES}
    skipped, mixed = 0, 0
    no_collision, submodel, no_contents = Counter(), Counter(), Counter()
    for e in entities(open(path).read()):
        m = re.search(r'"classname" "([^"]+)"', e)
        cls = m.group(1) if m else '(no classname)'
        brs = re.findall(r'\{\n(\(.*?)\n\}', e, re.S)
        if cls.lower() not in SOLID_CLASSNAMES:
            if brs:                    # lights, spawns and items have no brushes: nothing ignored
                tally = no_collision if cls.lower() in NO_COLLISION_CLASSNAMES else submodel
                tally[cls] += len(brs)
            continue
        for br in brs:
            pb = parse_brush(br)
            if pb is None:
                skipped += 1
                continue
            *geom, texes = pb
            kind, is_mixed = brush_contents(texes)
            mixed += is_mixed
            if kind not in out:        # 'hint' or 'origin': in no collision hull at all
                # name the face that decided it, not texes[0]: a hint face in slot 3 drops the
                # brush, and reporting the slot-1 wall texture there would be actively misleading
                no_contents[next((t.lower() for t in texes if face_class(t) == kind), kind)] += 1
                continue
            out[kind].append(tuple(geom))
    if skipped:
        print(f'WARNING: {path}: skipped {skipped} degenerate/unbounded brush(es)', file=sys.stderr)
    if mixed:
        print(f'WARNING: {path}: {mixed} brush(es) mix face contents (e.g. one "*" face among five '
              f'solid ones); qbsp takes the first face in file order and warns -- check the texture '
              f'theme slots, this is usually a mistake', file=sys.stderr)
    for tally, why in ((no_collision, 'in entities with no player collision'),
                       (submodel, 'in submodel entities (own collision hull, solidity set at runtime)'),
                       (no_contents, 'whose face textures give them no collision contents')):
        if tally:
            named = ', '.join(f'{c} x{n}' for c, n in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])))
            print(f'note: {path}: ignored {sum(tally.values())} brush(es) {why}: {named}',
                  file=sys.stderr)
    return out


def merge_boxes(boxes, tol=1e-6):
    comps = []
    for blo, bhi in boxes:
        mlo, mhi = list(blo), list(bhi)
        while True:
            keep, grew = [], False
            for clo, chi in comps:
                if (chi[0] >= mlo[0] - tol and chi[1] >= mlo[1] - tol and chi[2] >= mlo[2] - tol and
                        clo[0] <= mhi[0] + tol and clo[1] <= mhi[1] + tol and clo[2] <= mhi[2] + tol):
                    mlo = [min(mlo[0], clo[0]), min(mlo[1], clo[1]), min(mlo[2], clo[2])]
                    mhi = [max(mhi[0], chi[0]), max(mhi[1], chi[1]), max(mhi[2], chi[2])]
                    grew = True
                else:
                    keep.append((clo, chi))
            comps = keep
            if not grew:
                break
        comps.append((mlo, mhi))
    return comps


def roi_grid(comps, s):
    snapped = []
    for roi_lo, roi_hi in comps:
        ilo = [math.floor(float(v) / s) for v in roi_lo]
        ihi = [max(lo_i + 1, math.ceil(float(v) / s)) for lo_i, v in zip(ilo, roi_hi)]
        snapped.append((ilo, ihi))
    specs, total, max_sl = [], 0, 0
    for ilo, ihi in merge_boxes(snapped, tol=-1):
        nx, ny, nz = ihi[0] - ilo[0], ihi[1] - ilo[1], ihi[2] - ilo[2]
        sl = nx * ny
        max_sl = max(max_sl, sl)
        total += sl * nz
        specs.append((np.array([ilo[0] * s, ilo[1] * s, ilo[2] * s]),
                      np.array([ihi[0] * s, ihi[1] * s, ihi[2] * s]),
                      nx, ny, nz))
    return specs, total, max_sl


def compare(A, B, step, kind, label, differs, space):
    """Voxel-compare one content class's space between the two maps. True if they differ.
    Exits 2 if --step cannot be resolved within the memory/time budget."""
    # Exact prefilter: any symmetric difference must lie inside the bbox of brushes whose geometry
    # is not present in both maps. Cluster differing brushes into overlapping AABB components so
    # distant changed corners don't inflate one giant ROI box across empty space between them.
    cA, cB = Counter(b[4] for b in A), Counter(b[4] for b in B)
    common = cA & cB
    remA, remB = cA - common, cB - common
    if not remA and not remB:
        print(f'{label} identical (all {len(A)} {kind} brush geometries identical)')
        return False

    diff_brushes = [b for b in A if b[4] in remA] + [b for b in B if b[4] in remB]
    comps = merge_boxes([(b[0], b[1]) for b in diff_brushes])

    # Finest parallel-plane gap among differing brushes: warns when --step is too coarse to resolve
    # thin cracks/slivers (e.g. a 1-unit gap between two shifted wedge planes).
    plane_groups = {}
    for _, _, (N, D), _, _ in diff_brushes:
        for n, d in zip(N, D):
            for c in n:
                if abs(c) > 1e-6:
                    sgn = 1.0 if c > 0 else -1.0
                    break
            else:
                continue
            cn = (round(float(n[0] * sgn) + 0.0, 5), round(float(n[1] * sgn) + 0.0, 5), round(float(n[2] * sgn) + 0.0, 5))
            plane_groups.setdefault(cn, []).append(float(d * sgn))
    min_gap = None
    for ds in plane_groups.values():
        ds = sorted(ds)
        for a_, b_ in zip(ds, ds[1:]):
            g_ = b_ - a_
            if g_ > 1e-4 and (min_gap is None or g_ < min_gap):
                min_gap = g_
    rec = min_gap / 2.0 if min_gap is not None else None
    gap_s = f'{min_gap:g}' if min_gap is not None else None
    unit = ('unit' if gap_s == '1' else 'units') if gap_s is not None else None
    under_resolved = min_gap is not None and step >= min_gap - 1e-6
    rec_fits, rec_over = True, None
    if rec is not None:
        _, rec_voxels, rec_max_slice = roi_grid(comps, rec)
        rec_fits = rec_max_slice <= MAX_SLICE and rec_voxels <= MAX_TOTAL_VOXELS
        if rec_max_slice > MAX_SLICE:
            rec_over = f'{rec_max_slice / (1024 ** 2):.1f} MiB/slice, over {MAX_SLICE / (1024 ** 2):.1f} MiB limit'
        elif rec_voxels > MAX_TOTAL_VOXELS:
            rec_over = f'{rec_voxels / 1e9:.2f}G voxels, over {MAX_TOTAL_VOXELS / 1e9:g}G limit'

    if rec is not None and rec_fits and rec > step + 1e-9:
        budget_tail = f'use a larger --step (finest differing plane gap is {gap_s} {unit}; --step {rec:g} suffices)'
    elif rec is not None and not rec_fits:
        budget_tail = (f'cannot resolve {gap_s}-unit features inside budget '
                       f'(--step {rec:g} needs {rec_over}); compare a narrower pair or use a coarser --step')
    else:
        budget_tail = 'use a larger --step'

    roi_specs, total_voxels, _ = roi_grid(comps, step)
    for lo, hi, nx, ny, nz in roi_specs:
        if nx * ny > MAX_SLICE:
            mb = (nx * ny) / (1024 ** 2)
            print(f'ERROR: {label}: ROI 2D slice {(nx, ny)} ({mb:.1f} MiB per slice at step={step:g}) '
                  f'exceeds limit; {budget_tail}', file=sys.stderr)
            sys.exit(2)
    if total_voxels > MAX_TOTAL_VOXELS:
        gv = total_voxels / 1e9
        print(f'ERROR: {label}: total ROI work {gv:.2f}G voxels across {len(roi_specs)} ROI(s) at '
              f'step={step:g} exceeds {MAX_TOTAL_VOXELS / 1e9:g}G limit; {budget_tail}', file=sys.stderr)
        sys.exit(2)
    if under_resolved:
        warn_tail = f'try --step {rec:g}' if rec_fits else f'resolving at --step {rec:g} needs {rec_over}; compare a narrower pair'
        print(f'WARNING: {label}: differing geometry has parallel planes as close as {gap_s} {unit}; '
              f'--step {step:g} may not resolve them ({warn_tail})', file=sys.stderr, flush=True)
    if total_voxels > 500_000_000:
        print(f'checking {label}: {total_voxels / 1e9:.2f}G voxels across {len(roi_specs)} ROI(s) at '
              f'step={step:g}...', file=sys.stderr, flush=True)

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
    for lo, hi, nx, ny, nz in roi_specs:
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
        caveat = f'; features down to {gap_s} {unit} not examined' if under_resolved else ''
        print(f'{differs}: {total_diff} voxels (step={step:g}, {len(roi_specs)} ROI(s){caveat}), e.g.', sample_pts)
        return True
    if under_resolved:
        out_tail = f'rerun with --step {rec:g}' if rec_fits else f'resolving at --step {rec:g} exceeds budget, compare a narrower pair'
        print(f'{label}: no difference found at step={step:g}, {len(roi_specs)} ROI(s) {shapes} '
              f'(features down to {gap_s} {unit} unresolved; {out_tail})')
        return False
    print(f'{label} identical ({space} matches voxel for voxel, step={step:g}, '
          f'{len(roi_specs)} ROI(s) {shapes})')
    return False


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
        if not math.isfinite(step) or step <= 0:
            print(f'--step must be positive, got {step}', file=sys.stderr)
            sys.exit(2)
        args = args[:idx] + args[idx + 2:]
    if len(args) != 2:
        print('usage: collide_cmp.py old.map new.map [--step N]', file=sys.stderr)
        sys.exit(2)

    pA, pB = args[0], args[1]
    A, B = brushes(pA), brushes(pB)
    na = sum(not b[3] for b in A['solid'])
    nb = sum(not b[3] for b in B['solid'])
    print(f'{pA}: {len(A["solid"])} solid brushes ({na} non-axis), '
          f'{pB}: {len(B["solid"])} solid brushes ({nb} non-axis)', flush=True)
    liq = [f'{k} {len(A[k])} -> {len(B[k])}' for k in LIQUIDS if A[k] or B[k]]
    if liq:
        print('liquid brushes (not solid, each class compared separately): ' + ', '.join(liq), flush=True)

    differed = False
    for kind, label, banner, space in CLASSES:
        if kind != 'solid' and not A[kind] and not B[kind]:
            continue
        differed |= compare(A[kind], B[kind], step, kind, label, banner, space)
    if differed:
        sys.exit(1)


if __name__ == '__main__':
    main()
