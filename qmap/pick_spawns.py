"""Greedy spawn picker: floor spots with no mutual eye-level line of sight, spread out,
at least one per zone, clear of items, stairs, pads. Prints spawn() lines."""
import io, contextlib, json, math, sys, os
sys.argv = ['check.py', sys.argv[1]]; N = int(sys.argv[0] and 16)
with contextlib.redirect_stdout(io.StringIO()):
    exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check.py')).read())
reach = bfs(snodes[0], step=18)
items_ = d['items']; theme = d['theme']
def mat_under(i, j, z):
    return next((m for a, b, m in cols[i][j] if b == z), None)
cand = []
for (i, j, z) in reach:
    if i % 2 or j % 2: continue
    ok = all((i + di, j + dj, z) in reach and mat_under(i + di, j + dj, z) in (None, 'ledge')
             for di in (-2, -1, 0, 1) for dj in (-2, -1, 0, 1))
    if not ok: continue
    x, y = XMIN + i * C, YMIN + j * C
    if any(math.dist((x, y), it[1:3]) < (int(os.environ.get('ITEMR', 192)) if it[0].startswith(('weapon', 'item_armor')) or it[4] & 2 else 96) and abs(it[3] - z) < 64 for it in items_): continue
    if any(math.dist((x, y), ((t[0][0] + t[0][2]) / 2, (t[0][1] + t[0][3]) / 2)) < 96 or math.dist((x, y), (t[2], t[3])) < 96 for t in d.get('teleports', []) + d.get('pushes', [])): continue
    cand.append((x, y, z, theme[i][j] or 'passage'))
def los(a, b):
    xa, ya, za = a[0], a[1], a[2] + 46; xb, yb, zb = b[0], b[1], b[2] + 46
    n = int(math.dist((xa, ya, za), (xb, yb, zb)) // 4)
    return all(not solid_at(xa + (xb - xa) * t / n, ya + (yb - ya) * t / n, za + (zb - za) * t / n) for t in range(1, n))
def openness(p):
    best, ang = -1, 0
    for a in range(0, 360, 45):
        r = 0
        while r < 800 and not solid_at(p[0] + math.cos(math.radians(a)) * r, p[1] + math.sin(math.radians(a)) * r, p[2] + 46): r += 16
        if r > best: best, ang = r, a
    return ang
import random, itertools, os
MIND = int(os.environ.get("MIND", 224))
n = len(cand)
conf = [set() for _ in range(n)]
for a_, b_ in itertools.combinations(range(n), 2):
    if math.dist(cand[a_][:3], cand[b_][:3]) < MIND or los(cand[a_], cand[b_]):
        conf[a_].add(b_); conf[b_].add(a_)
best = None
for seed in range(600):
    rnd = random.Random(seed)
    alive = set(range(n)); sel = []
    while alive:
        m = min(len(conf[v] & alive) for v in alive)
        pool = [v for v in alive if len(conf[v] & alive) <= m + 1]
        v = rnd.choice(pool); sel.append(v); alive -= conf[v] | {v}
    zones_hit = len({cand[v][3] for v in sel})
    dmin = min(math.dist(cand[a_][:3], cand[b_][:3]) for a_, b_ in itertools.combinations(sel, 2))
    key = (len(sel), zones_hit, dmin)
    if best is None or key > best[0]: best = (key, sel)
print('best (count, zones, min spacing):', best[0], 'from', n, 'candidates')
for v in best[1]:
    c = cand[v]
    print(f"    ({int(c[0])}, {int(c[1])}, {c[2]}, {openness(c)}, '{c[3]}'),")
