"""Longest straight sightlines at eye height between two spots on the same floor level, along x
and along y - new in v2.
A sightline that runs the length of a route (end-to-end down an arc, base to base) is usually a
problem: rockets and LG own it, and the route stops being a route. Usage:
  python3 sightlines.py map.json [z1 z2 ...]        (floor heights; default: every main floor in the JSON)"""
import contextlib
import io
import os
import sys
from collections import Counter

J = sys.argv[1]
levels = [int(v) for v in sys.argv[2:]]
sys.argv = ['check.py', J]
with contextlib.redirect_stdout(io.StringIO()):
    exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check.py')).read())
if not levels:
    cnt = Counter(z for (i, j, z) in nodes)
    levels = sorted(z for z, n in cnt.items() if n >= 0.04 * len(nodes))     # the main floors
X1, Y1 = XMIN + NX * C, YMIN + NY * C
for f in levels:
    z = f + 46
    for axis in 'xy':
        best = (0, None)
        outer = range(YMIN + 8, Y1, 16) if axis == 'x' else range(XMIN + 8, X1, 16)
        inner = list(range(XMIN + 8, X1, 16)) if axis == 'x' else list(range(YMIN + 8, Y1, 16))
        for o in outer:
            first = None                     # first spot of this clear run that stands on this floor
            for k, v in enumerate(inner + [None]):
                p = (v, o) if axis == 'x' else (o, v)
                if v is None or solid_at(p[0], p[1], z):
                    first = None
                    continue
                if (int((p[0] - XMIN) // C), int((p[1] - YMIN) // C), f) in nodes:   # a player can stand here
                    if first is None:
                        first = v
                    elif v - first > best[0]:
                        best = (v - first, (first, v, o))
        if best[1] is None:
            continue
        L, (a, b, o) = best
        where = f'x {a}..{b} at y={o}' if axis == 'x' else f'y {a}..{b} at x={o}'
        print(f'floor {f:5d}: longest clear line along {axis}: {L:5d} units ({where})')
