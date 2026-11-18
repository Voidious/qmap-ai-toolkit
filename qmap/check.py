"""Gameplay checks on the generator's column grid.

- every spawn stands on floor with player clearance
- walking graph (steps <= 18, drops allowed): every spawn reaches every other
- reachable floor area, dead-end check
- spawn-to-spawn sightlines (eye height) and spacing
"""
import itertools
import json
import math
import sys
from collections import deque

d = json.load(open(sys.argv[1]))
C, XMIN, YMIN, NX, NY, BOT, TOP = (d[k] for k in ('C', 'XMIN', 'YMIN', 'NX', 'NY', 'BOT', 'TOP'))
cols = d['cols']
STEP, HEAD = 18, 56


def air(i, j):
    segs = sorted((a, b) for a, b, _ in cols[i][j])
    out, z = [], BOT
    for a, b in segs:
        if a > z:
            out.append((z, a))
        z = max(z, b)
    if z < TOP:
        out.append((z, TOP))
    return out


AIR = [[air(i, j) for j in range(NY)] for i in range(NX)]


def solid_at(x, y, z):
    i, j = int((x - XMIN) // C), int((y - YMIN) // C)
    if not (0 <= i < NX and 0 <= j < NY):
        return True
    return not any(a < z < b for a, b in AIR[i][j])


# nodes: (i, j, floor_z)
nodes = set()
for i in range(NX):
    for j in range(NY):
        for a, b in AIR[i][j]:
            if a > BOT and b - a >= HEAD:
                nodes.add((i, j, a))


def neighbours(n, step=STEP):
    i, j, z = n
    top_here = next(b for a, b in AIR[i][j] if a == z)
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
            for d in range(2, 7):
                p, q = i + d * di, j + d * dj
                if not (0 <= p < NX and 0 <= q < NY):
                    break
                land = [a for a, b in AIR[p][q] if z - 128 <= a <= z + 8 and b - a >= HEAD and (p, q, a) in nodes]
                mid_ok = all(any(a <= z - 24 and b >= z + HEAD for a, b in AIR[i + k * di][j + k * dj])
                             for k in range(1, d))
                if not mid_ok:
                    break
                for a in land:
                    yield (p, q, a)


_neighbours_walk = neighbours
TELEPORTS = {}
for (r, z, dx, dy, dz, ang) in d.get('teleports', []) + d.get('pushes', []):
    dest = (int((dx - XMIN) // C), int((dy - YMIN) // C), dz)
    for i in range((r[0] - XMIN) // C, (r[2] - XMIN) // C):
        for j in range((r[1] - YMIN) // C, (r[3] - YMIN) // C):
            TELEPORTS[(i, j, z)] = dest


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
    snodes.append((i, j, z))

reach = [bfs(s) for s in snodes]
for (s, lab), r in zip(zip(snodes, [s[4] for s in spawns]), reach):
    missing = [spawns[k][4] for k, t in enumerate(snodes) if t not in r]
    if missing:
        problems.append(f'from {lab} cannot walk to: {missing}')

# floor reachable from spawn 0 vs all floor
r0 = reach[0]
area = len(r0) * C * C
unreached = [n for n in nodes if n not in r0 and n[2] >= 0]
print(f'walkable floor reachable on foot: {area / 1e6:.2f} M sq units ({len(r0)} cells); '
      f'unreached floor cells: {len(unreached)}')
if unreached:
    zs = {}
    for n in unreached:
        zs[n[2]] = zs.get(n[2], 0) + 1
    print('  unreached by height:', dict(sorted(zs.items())))

# sightlines between spawns (eye = origin+22 = floor+46)
vis_pairs = []
for (a, b) in itertools.combinations(range(len(spawns)), 2):
    xa, ya, za = spawns[a][:3]
    xb, yb, zb = spawns[b][:3]
    za += 46
    zb += 46
    dist = math.dist((xa, ya, za), (xb, yb, zb))
    steps = int(dist // 4)
    clear = all(not solid_at(xa + (xb - xa) * t / steps, ya + (yb - ya) * t / steps, za + (zb - za) * t / steps)
                for t in range(1, steps))
    if clear:
        vis_pairs.append((spawns[a][4], spawns[b][4], int(dist)))
min_d = min((math.dist(p[:2], q[:2]), p[4], q[4]) for p, q in itertools.combinations(spawns, 2))
print(f'spawns: {len(spawns)}; closest pair {min_d[1]} / {min_d[2]} at {min_d[0]:.0f} units')
print(f'spawn pairs with line of sight: {len(vis_pairs)}')
for p in vis_pairs:
    print('   ', p)
print('PROBLEMS:' if problems else 'no spawn/connectivity problems')
for p in problems:
    print('  -', p)

# ---------------------------------------------------------------- items
items = d.get('items', [])
if items:
    iprob = []
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
            print(f'  note: {lab} at {x},{y},{z} is on a hook-only perch (by design)')
        elif not any(c in jump for c in cells_):
            iprob.append(f'{lab} at {x},{y},{z}: unreachable even with jumps')
        elif not any(c in r0 for c in cells_):
            print(f'  note: {lab} at {x},{y},{z} needs a jump')
    for r, pz in d.get('perches', []):          # CTF: a perch must need the hook (or a rocket jump)
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
    from collections import Counter
    print('items:', dict(Counter(it[5] for it in items)))
    # walking distance (units) from each spawn to the nearest of each weapon class
    groups = {}
    for cls, x, y, z, flags, lab in items:
        if cls.startswith('weapon_') or lab in ('RA', 'YA', 'MH', 'QUAD'):
            i, j = int((x - XMIN) // C), int((y - YMIN) // C)
            groups.setdefault(lab, []).append((i, j, z))
    print('walk distance from each spawn to nearest (units, jumps allowed):')
    hdr = sorted(groups)
    print('   %-12s' % 'spawn' + ''.join('%6s' % h for h in hdr))
    for sn, sp in zip(snodes, spawns):
        dist = bfs(sn, step=40)
        row = []
        for h in hdr:
            ds = [dist[c] for g in groups[h] for c in [(g[0] + di, g[1] + dj, g[2]) for di in (-1, 0) for dj in (-1, 0)] if c in dist]
            row.append('%6d' % (min(ds) * C) if ds else '     -')
        print('   %-12s' % sp[4] + ''.join(row))
    print('ITEM PROBLEMS:' if iprob else 'no item problems')
    for p in iprob:
        print('  -', p)

# ---------------------------------------------------------------- traps
# Every spot a player can reach (walking, jumping, dropping) must have a way back
# to the spawns without a rocket jump. Reverse reachability from spawn 0.
reach = bfs(snodes[0], step=40)
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
    print('no traps: every reachable spot has a walk/jump route back')
else:
    seen, groups = set(), []
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
                if m in traps and m not in seen:
                    seen.add(m)
                    qq.append(m)
        groups.append(grp)
    trapset = set(traps)
    print(f'TRAPS: {len(groups)} area(s) you can get into but not out of without a rocket jump:')
    for g in sorted(groups, key=len, reverse=True):
        xs = [XMIN + i * C for i, j, z in g]
        ys = [YMIN + j * C for i, j, z in g]
        print(f'  - floor {g[0][2]}: x {min(xs)}..{max(xs) + C}, y {min(ys)}..{max(ys) + C} ({len(g)} cells)')
