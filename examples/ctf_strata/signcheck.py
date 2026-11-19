"""b4: from every spawn (respawns and team starts), which direction signs can you see without moving?
Prints each spawn's nearest visible sign; spawns that see none get the walking distance to a spot that does."""
import json, math, sys, heapq
J = json.load(open(sys.argv[1]))
C, XMIN, YMIN, NX, NY = J['C'], J['XMIN'], J['YMIN'], J['NX'], J['NY']
cols = J['cols']
def solid(x, y, z):
    i, j = int((x - XMIN) // C), int((y - YMIN) // C)
    if not (0 <= i < NX and 0 <= j < NY):
        return True
    return any(a <= z < b for a, b, m in cols[i][j] if m not in ('lamp',))
signs = []
for d in J['decals']:
    x0, y0, z0, x1, y1, z1, tex = d[:7]
    if not tex.startswith(('sd_sign', 'sd_tag', 'sd_board')):
        continue
    cx, cy, cz = (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2
    for dx, dy in ((8, 0), (-8, 0), (0, 8), (0, -8)):
        if not solid(cx + dx, cy + dy, cz):
            signs.append((cx + dx, cy + dy, cz, tex))
            break
def los(a, b):
    n = int(math.dist(a, b) // 8) + 1
    return all(not solid(*(a[k] + (b[k] - a[k]) * t / n for k in range(3))) for t in range(1, n))
def seen(p, rng=1500):
    best = None
    for s in signs:
        d = math.dist(p, s[:3])
        if d < rng and los(p, s[:3]) and (best is None or d < best[0]):
            best = (d, s[3])
    return best
pts = [(x, y, z, lab) for x, y, z, a, lab in J['spawns']] + [(x, y, z, f'team{t}') for x, y, z, a, t in J['team_spawns']]
miss = 0
for x, y, z, lab in pts:
    b = seen((x, y, z + 46))
    if b:
        print(f'{lab:8s} {x:6d} {y:6d} {z:4d}  sees {b[1]:11s} at {b[0]:5.0f}')
    else:
        miss += 1
        # walk outward on the floor at the same height until a sign is in view
        start = (x // 16 * 16, y // 16 * 16)
        dist = {start: 0}
        h = [(0, start)]
        found = None
        while h and found is None:
            dd, (px, py) = heapq.heappop(h)
            if dd > 1200:
                break
            if dd % 32 == 0 and seen((px + 8, py + 8, z + 46)):
                found = dd
                break
            for ex, ey in ((16, 0), (-16, 0), (0, 16), (0, -16)):
                q = (px + ex, py + ey)
                if q not in dist and not solid(q[0] + 8, q[1] + 8, z + 8) and not solid(q[0] + 8, q[1] + 8, z + 60) and solid(q[0] + 8, q[1] + 8, z - 8):
                    dist[q] = dd + 16
                    heapq.heappush(h, (dd + 16, q))
        print(f'{lab:8s} {x:6d} {y:6d} {z:4d}  SEES NONE; walk {found} units to see one' if found is not None else f'{lab:8s} {x:6d} {y:6d} {z:4d}  SEES NONE within 1200 units')
print(len(signs), 'signs;', miss, 'of', len(pts), 'spawn points see none from where they stand')
