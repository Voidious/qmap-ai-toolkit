"""Spawn solver for SYMMETRIC maps: picks spots on the written half so that no spot - and no
spot's symmetric copy - can see any other at eye level; spread out, clear of items, stairs, pads.
Prints spawn() lines for the written half (the generator adds the copies).

  SYM=rotate (default, 180-degree rotation: (x, y) -> (-x, -y))  or  SYM=mirror ((x, y) -> (-x, y))
  MIND=224   minimum spacing      ITEMR=192   clearance round weapons / armour / Mega
  HALF_X0=64, HALF_X1=1e9   the written half is HALF_X0 < x < HALF_X1 (x > 0 side)
  FLAGR=448  keep this far from flags (read from the JSON)
  EXCLUDE="x0,y0,x1,y1;..."  extra no-spawn rectangles (e.g. a back tunnel)
Flag rooms (themes containing 'flag') are always excluded."""
import io, contextlib, json, math, sys, os
sys.argv = ['check.py', sys.argv[1]]; N = int(sys.argv[0] and 16)
with contextlib.redirect_stdout(io.StringIO()):
    exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check.py')).read())
reach = bfs(snodes[0], step=18)
items_ = d['items']; theme = d['theme']
def mat_under(i, j, z):
    return next((m for a, b, m in cols[i][j] if b == z), None)
SYM = os.environ.get('SYM', 'rotate')
COPY = (lambda p: (-p[0], -p[1], p[2])) if SYM == 'rotate' else (lambda p: (-p[0], p[1], p[2]))
HX0, HX1 = float(os.environ.get('HALF_X0', 64)), float(os.environ.get('HALF_X1', 1e9))
FLAGR = float(os.environ.get('FLAGR', 448))
FLAGS = [(it[1], it[2]) for it in items_ if it[0].startswith('item_flag')]
EXCL = [tuple(float(v) for v in r.split(',')) for r in os.environ.get('EXCLUDE', '').split(';') if r.strip()]
cand = []
for (i, j, z) in reach:
    if i % 2 or j % 2: continue
    ok = all((i + di, j + dj, z) in reach and mat_under(i + di, j + dj, z) in (None, 'ledge')
             for di in (-2, -1, 0, 1) for dj in (-2, -1, 0, 1))
    if not ok: continue
    x, y = XMIN + i * C, YMIN + j * C
    if any(math.dist((x, y), it[1:3]) < (int(os.environ.get('ITEMR', 192)) if it[0].startswith(('weapon', 'item_armor')) or it[4] & 2 else 96) and abs(it[3] - z) < 64 for it in items_): continue
    if any(math.dist((x, y), ((t[0][0] + t[0][2]) / 2, (t[0][1] + t[0][3]) / 2)) < 96 or math.dist((x, y), (t[2], t[3])) < 96 for t in d.get('teleports', []) + d.get('pushes', [])): continue
    th = theme[i][j] or 'passage'
    if 'flag' in th or not (HX0 < x < HX1): continue
    if any(r[0] <= x < r[2] and r[1] <= y < r[3] for r in EXCL): continue
    if any(math.dist((x, y), f) < FLAGR for f in FLAGS): continue
    cand.append((x, y, z, th))
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
cand = [c for c in cand if math.dist(c[:3], COPY(c)) >= MIND and not los(c, COPY(c))]
n = len(cand)
conf = [set() for _ in range(n)]
for a_, b_ in itertools.combinations(range(n), 2):
    A, B = cand[a_], cand[b_]
    RB = COPY(B)
    if math.dist(A[:3], B[:3]) < MIND or los(A, B) or math.dist(A[:3], RB) < MIND or los(A, RB):
        conf[a_].add(b_); conf[b_].add(a_)
best = None
for seed in range(int(os.environ.get('SEEDS', 600))):
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
