"""Flag-to-flag walking routes (grid Dijkstra, 8-way on the floor graph) for ctf_circuit.
Paces: 460 u/s = your Bastion measurement (5523 units in ~12 s, hook); 320 u/s = a real carrier."""
import io, contextlib, sys, math, heapq, os
J = sys.argv[1]
sys.argv = ['check.py', J]
with contextlib.redirect_stdout(io.StringIO()):
    exec(open(os.path.join(os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'), 'check.py')).read())
fl = {it[0]: it for it in d['items'] if it[0].startswith('item_flag')}
node = lambda x, y, z: (int((x - XMIN) // C), int((y - YMIN) // C), z)
X = lambda m: XMIN + m[0] * C + 8
Y = lambda m: YMIN + m[1] * C + 8
def dij(a, avoid=None, goal=None):
    dist = {a: 0.0}; prev = {}; pq = [(0.0, a)]
    while pq:
        dd, n = heapq.heappop(pq)
        if n == goal: break
        if dd > dist[n]: continue
        nb = list(neighbours(n)); S = set(nb)
        for di, dj in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            m = (n[0] + di, n[1] + dj, n[2])
            if m in nodes and (n[0] + di, n[1], n[2]) in S and (n[0], n[1] + dj, n[2]) in S: nb.append(m)
        for m in nb:
            if avoid and avoid(m): continue
            w = C * math.hypot(m[0] - n[0], m[1] - n[1]) + abs(m[2] - n[2]) * 0.5
            if dd + w < dist.get(m, 1e18):
                dist[m] = dd + w; prev[m] = n; heapq.heappush(pq, (dd + w, m))
    return dist, prev
def near(dist, x, y, z):
    return min(dist.get(node(x + dx, y + dy, z), 1e18) for dx in (-16, 0, 16) for dy in (-16, 0, 16))
B = fl['item_flag_team2'][1:4]; R = fl['item_flag_team1'][1:4]
CH = lambda m: abs(X(m)) < 1824 and abs(Y(m)) < 704         # chamber + spine (the whole core)
N_ = lambda m: Y(m) > 600 and abs(X(m)) < 1824
S_ = lambda m: Y(m) < -600 and abs(X(m)) < 1824
out = []
for name, avoid in [('shortest (any way)', None), ('high arc (north, no chamber)', lambda m: CH(m) or S_(m)),
                    ('low arc (south, no chamber)', lambda m: CH(m) or N_(m)),
                    ('spine (through the chamber, no arcs)', lambda m: N_(m) or S_(m)),
                    ('high arc, drop into the chamber, spine home', lambda m: S_(m) or (X(m) > 448 and CH(m)) or (X(m) < -448 and N_(m))),
                    ('high arc, drop, stairs down, low arc', lambda m: (X(m) > 448 and S_(m)) or (abs(X(m)) > 448 and CH(m)) or (X(m) < -448 and N_(m)))]:
    dist, _ = dij(node(*B), avoid)
    L = near(dist, *R)
    out.append((name, L))
    print(f'{name:42s} {L:6.0f} units  {L / 460:5.1f} s at 460 u/s  {L / 320:5.1f} s at 320 u/s')
