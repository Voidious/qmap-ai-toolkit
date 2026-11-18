"""Walking routes on the floor graph (8-way Dijkstra over check.py's nodes) - new in v2.

  python3 routes.py map.json                       shortest flag-to-flag route (CTF)
  python3 routes.py map.json --from x,y,z --to x,y,z
  python3 routes.py map.json --run "north arc=-1824,-1800,1824,704" --run "spine=..."

Each --run NAME=RECTS forbids the listed rectangles (x0,y0,x1,y1;...), so you can measure each
distinct run between the flags: e.g. forbid the south arc and the core to get the north-arc time.
Prints units and seconds at 320 u/s (a real carrier in our demos) and 460 u/s (a solo hook run).
Never estimate route times in prose - measure them here, every layout build."""
import contextlib
import heapq
import io
import math
import os
import sys

args = sys.argv[1:]
J = args[0]
sys.argv = ['check.py', J]
with contextlib.redirect_stdout(io.StringIO()):
    exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check.py')).read())


def opt(name):
    return [args[k + 1] for k in range(len(args) - 1) if args[k] == name]


node = lambda x, y, z: (int((x - XMIN) // C), int((y - YMIN) // C), z)
X = lambda m: XMIN + m[0] * C + 8
Y = lambda m: YMIN + m[1] * C + 8


def dij(a, avoid=None):
    dist = {a: 0.0}
    prev = {}
    pq = [(0.0, a)]
    while pq:
        dd, n = heapq.heappop(pq)
        if dd > dist[n]:
            continue
        nb = list(neighbours(n))
        S = set(nb)
        for di, dj in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            m = (n[0] + di, n[1] + dj, n[2])
            if m in nodes and (n[0] + di, n[1], n[2]) in S and (n[0], n[1] + dj, n[2]) in S:
                nb.append(m)
        for m in nb:
            if avoid and avoid(m):
                continue
            w = C * math.hypot(m[0] - n[0], m[1] - n[1]) + abs(m[2] - n[2]) * 0.5
            if dd + w < dist.get(m, 1e18):
                dist[m] = dd + w
                prev[m] = n
                heapq.heappush(pq, (dd + w, m))
    return dist, prev


def near(dist, x, y, z):
    return min(dist.get(node(x + dx, y + dy, z), 1e18) for dx in (-16, 0, 16) for dy in (-16, 0, 16))


def pt(s):
    return tuple(float(v) for v in s.split(','))


if opt('--from'):
    A, B = pt(opt('--from')[0]), pt(opt('--to')[0])
else:
    fl = {it[0]: it for it in d['items'] if it[0].startswith('item_flag')}
    A, B = fl['item_flag_team2'][1:4], fl['item_flag_team1'][1:4]
    A = (A[0], A[1], A[2] - (A[2] % 16))
    B = (B[0], B[1], B[2] - (B[2] % 16))
start = min((n for n in nodes if abs(X(n) - A[0]) < 24 and abs(Y(n) - A[1]) < 24), key=lambda n: abs(n[2] - A[2]))
runs = [('shortest (any way)', None)]
for r in opt('--run'):
    name, rects = r.split('=', 1)
    R = [pt(q) for q in rects.split(';') if q.strip()]
    runs.append((name, (lambda R: lambda m: any(a <= X(m) < c and b <= Y(m) < e for a, b, c, e in R))(R)))
for name, avoid in runs:
    dist, _ = dij(start, avoid)
    L = min(dist.get(n, 1e18) for n in dist if abs(X(n) - B[0]) < 24 and abs(Y(n) - B[1]) < 24) if dist else 1e18
    if L >= 1e17:
        print(f'{name:40s} unreachable with these rectangles forbidden')
    else:
        print(f'{name:40s} {L:6.0f} units  {L / 320:5.1f} s at 320 u/s  {L / 460:5.1f} s at 460 u/s')
