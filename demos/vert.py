"""v3: how players actually move up and down, from a demo - the in-play twin of vprofile's
'height changed per 1000 units' (map geometry). Used by ca_run.py and ctf_run.py.

floor height is the rolling minimum of a player's z over 0.6 s (so bunny-hop arcs don't count);
floor_change_per_1000 = how much that floor height changes per 1000 units travelled while alive."""
from collections import deque

import numpy as np


def floor_z(t, z, win=0.6):
    out = np.empty_like(z)
    dq = deque()
    j = 0
    n = len(t)
    for i in range(n):                       # window [t_i - win/2, t_i + win/2]
        while j < n and t[j] <= t[i] + win / 2:
            while dq and z[dq[-1]] >= z[j]:
                dq.pop()
            dq.append(j)
            j += 1
        while dq[0] < i and t[dq[0]] < t[i] - win / 2:
            dq.popleft()
        out[i] = z[dq[0]]
    return out


def movement_height(per):
    """per: player id -> array of samples [t, id, x, y, z, dead, ...] (mvd.parse tracks)."""
    vert = horiz = 0.0
    zs, air = [], []
    for a in per.values():
        if len(a) < 10:
            continue
        t, x, y, z, dead = a[:, 0], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
        fz = floor_z(t, z)
        live = dead == 0
        dxy = np.hypot(np.diff(x), np.diff(y))
        dzf = np.abs(np.diff(fz))
        dt = np.diff(t)
        ok = live[1:] & live[:-1] & (dxy < 200) & (dzf < 200) & (dt < 0.25)
        vert += dzf[ok].sum()
        horiz += dxy[ok].sum()
        zs.append(z[live])
        air.append((z - fz)[live] > 16)
    zs = np.concatenate(zs) if zs else np.zeros(1)
    air = np.concatenate(air) if air else np.zeros(1)
    return dict(floor_change_per_1000=round(1000 * vert / max(1, horiz)),
                z_range=np.percentile(zs, [5, 50, 95]).round().tolist(),
                airborne=round(float(air.mean()), 2))
