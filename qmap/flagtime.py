"""Shortest walking route between the two flags (grid Dijkstra, 8-way moves on the floor graph),
scaled to seconds with the b1 calibration (b1 measured in-game at ~9 s with the hook)."""
import os
import io, contextlib, sys, math, heapq, json
J = sys.argv[1]
sys.argv = ['check.py', J]
with contextlib.redirect_stdout(io.StringIO()):
    exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check.py')).read())
fl = {it[0]: it for it in d['items'] if it[0].startswith('item_flag')}
def node(x, y, z): return (int((x - XMIN) // C), int((y - YMIN) // C), z)
def dij(a, b, avoid=None):
    dist = {a: 0.0}; pq = [(0.0, a)]
    while pq:
        dd, n = heapq.heappop(pq)
        if n == b: return dd
        if dd > dist[n]: continue
        nb = list(neighbours(n))
        # diagonal moves when both orthogonal neighbours are on the same level
        S = set(nb)
        for di, dj in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            m = (n[0] + di, n[1] + dj, n[2])
            if m in nodes and (n[0] + di, n[1], n[2]) in S and (n[0], n[1] + dj, n[2]) in S:
                nb.append(m)
        for m in nb:
            if avoid and avoid(m): continue
            w = C * math.hypot(m[0] - n[0], m[1] - n[1]) + abs(m[2] - n[2]) * 0.5
            if dd + w < dist.get(m, 1e18):
                dist[m] = dd + w; heapq.heappush(pq, (dd + w, m))
    return None
a = node(*fl['item_flag_team2'][1:4]); b = node(*fl['item_flag_team1'][1:4])
L = dij(a, b)
print(f'shortest flag-to-flag walk: {L:.0f} units')
X = lambda m: XMIN + m[0] * C
Y = lambda m: YMIN + m[1] * C
in_corr = lambda m: abs(Y(m)) < 160 and 448 <= abs(X(m)) <= 1216
routes = [('main corridor (no undercroft, no high route)', lambda m: m[2] < 0 or (m[2] >= 160 and 448 <= abs(X(m)) <= 1216)),
          ('undercroft + back tunnel (no corridor, no high route)', lambda m: (in_corr(m) and m[2] == 0) or (m[2] >= 160 and 448 <= abs(X(m)) <= 1216)),
          ('side route (never enters the mid hall)', lambda m: abs(X(m)) < 448 and abs(Y(m)) < 576),
          ('high route (no corridor, no undercroft, no side route)', lambda m: m[2] < 0 or (in_corr(m) and m[2] == 0) or abs(Y(m)) >= 640)]
for name, test in routes:
    l2 = dij(a, b, test)
    print(f'  {name}: {l2:.0f} units = {l2 * 9 / 4018:.1f} s at your b1 pace' if l2 else f'  {name}: none')
