"""Clan Arena pacing proxy - new in v2. Random team splits over the spawn set; for each split, the
closest opposing pair by walking distance. Use it to COMPARE a new map with a known-good one
(e.g. a map your group already likes), not as an absolute first-contact time.
Usage: python3 contact.py map.json"""
import contextlib
import io
import os
import random
import statistics
import sys

f = sys.argv[1]
sys.argv = ['check.py', f]
with contextlib.redirect_stdout(io.StringIO()):
    g = {}
    exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check.py')).read(), g)
sp, sn, C = g['spawns'], g['snodes'], g['C']
reach = [g['bfs'](s) for s in sn]
n = len(sp)
D = [[reach[a].get(sn[b], 10 ** 6) * C for b in range(n)] for a in range(n)]
for players in (8, 10, 12):
    ts = []
    for _ in range(4000):
        k = random.sample(range(n), min(players, n))
        A, B = k[:len(k) // 2], k[len(k) // 2:]
        ts.append(min(D[a][b] for a in A for b in B))
    print(f'{players:2d} players: closest opposing pair, walking distance: median {statistics.median(ts):.0f}, '
          f'mean {statistics.mean(ts):.0f} units')
