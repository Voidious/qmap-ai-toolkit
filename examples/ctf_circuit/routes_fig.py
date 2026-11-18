"""Draw the three runs (shortest walking lines) over the map footprint."""
import io, contextlib, sys, math, heapq, os, json
J, OUT = sys.argv[1], sys.argv[2]
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
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
runs = [('spine (through the mid chamber)', lambda m: N_(m) or S_(m), '#ff7ad9'),
        ('north arc - high (192)', lambda m: CH(m) or S_(m), '#ffd84d'),
        ('south arc - low (-128)', lambda m: CH(m) or N_(m), '#6dffb0')]
fig, ax = plt.subplots(figsize=(20, 10.5), dpi=80); fig.patch.set_facecolor('#1d1f21'); ax.set_facecolor('#151617')
img = np.full((NY, NX), np.nan)
for (i, j, z) in nodes:
    v = {-128: 0, 0: 1, 192: 2}.get(z, 1)
    img[j, i] = max(v, img[j, i]) if not np.isnan(img[j, i]) else v
from matplotlib.colors import ListedColormap
ax.imshow(img, origin='lower', extent=[XMIN, XMIN + NX * C, YMIN, YMIN + NY * C], cmap=ListedColormap(['#24463a', '#2f4f66', '#6b5d34']),
          vmin=0, vmax=2, interpolation='nearest')
a = node(*B); b = node(*R)
for name, avoid, col in runs:
    dist, prev = dij(a, avoid)
    tgt = min((n for n in dist if abs(X(n) - R[0]) < 24 and abs(Y(n) - R[1]) < 24), key=lambda n: dist[n])
    path = [tgt]
    while path[-1] in prev: path.append(prev[path[-1]])
    xs = [X(n) for n in path]; ys = [Y(n) for n in path]
    ax.plot(xs, ys, '-', color=col, lw=3, alpha=0.95, label=f'{name}: {dist[tgt]:.0f} units = {dist[tgt]/460:.1f} s at 460 u/s, {dist[tgt]/320:.1f} s at 320 u/s')
for x, y, c in ((B[0], B[1], '#4da6ff'), (R[0], R[1], '#ff4d4d')):
    ax.plot(x, y, '^', ms=18, color=c, mec='white', mew=1.5)
ax.plot(0, -160, '*', ms=20, color='#c77dff', mec='white')
ax.set_xlim(XMIN, XMIN + NX * C); ax.set_ylim(YMIN, YMIN + NY * C); ax.set_aspect('equal')
ax.set_xticks([]); ax.set_yticks([])
ax.legend(loc='lower center', fontsize=11, framealpha=0.9)
ax.set_title('ctf_circuit: the three runs, flag to flag (floor colour: green = low -128, blue = main 0, gold = high 192; star = Quad)', color='white', fontsize=12)
plt.tight_layout(); plt.savefig(OUT, facecolor=fig.get_facecolor())
