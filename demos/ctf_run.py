import sys, math, collections, json
import numpy as np
from mvd import parse
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

def analyze(path, label):
    pl, tr, pr, st, unk, T = parse(path)
    t0 = next((t for t, s in pr if 'match has begun' in s), 0); t1 = next((t for t, s in pr if 'match is over' in s), T)
    ids = sorted(k for k, v in pl.items() if v['team'] in ('red', 'blue') and v['name'].strip())
    team = {k: pl[k]['team'] for k in ids}; name = {k: pl[k]['name'] for k in ids}
    A = np.array([s for s in tr if s[1] in team], dtype=float)
    A = A[(A[:, 0] >= t0) & (A[:, 0] <= t1)]
    per = {n: A[A[:, 1] == n] for n in ids}
    segs = []
    for n, a in per.items():
        c = (a[:, 6].astype(int) & 48) > 0; i = 0
        while i < len(a):
            if c[i]:
                j = i
                while j + 1 < len(a) and c[j + 1]: j += 1
                segs.append(dict(n=n, team=team[n], t0=a[i, 0], t1=a[j, 0], start=a[i, 2:5], end=a[j, 2:5],
                                 died=bool(a[min(j + 1, len(a) - 1), 5]), i0=i, i1=j))
                i = j + 1
            else: i += 1
    # flag stands = densest cluster of pickup starts, per carrying team
    stand = {}
    for tm in ('red', 'blue'):
        pts = np.array([s['start'] for s in segs if s['team'] == tm])
        best = max(pts, key=lambda p: (np.hypot(*(pts[:, :2] - p[:2]).T) < 150).sum())
        near = pts[np.hypot(*(pts[:, :2] - best[:2]).T) < 150]
        stand['blue' if tm == 'red' else 'red'] = near.mean(0)
    d2 = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])
    caps = [s for s in segs if not s['died'] and d2(s['end'], stand[s['team']]) < 200]
    grabs = [s for s in segs if d2(s['start'], stand['blue' if s['team'] == 'red' else 'red']) < 200]
    def frac(p, tm):
        a = stand['blue' if tm == 'red' else 'red']; b = stand[tm]; v = b[:2] - a[:2]
        return float(np.dot(np.array(p[:2]) - a[:2], v) / np.dot(v, v))
    killed = [s for s in segs if s['died']]
    early = sum(frac(s['end'], s['team']) < 0.25 for s in killed)
    caplen = []
    for s in caps:
        p = per[s['n']][s['i0']:s['i1'] + 1, 2:4]; L = np.hypot(*np.diff(p, axis=0).T); caplen.append((s['t1'] - s['t0'], L[L < 200].sum()))
    deaths = []; occ = {tm: collections.Counter() for tm in ('red', 'blue')}; fast = []
    for n, a in per.items():
        idx = np.where(np.diff(a[:, 5]) > 0)[0] + 1
        deaths += [(n, a[i, 2], a[i, 3]) for i in idx]
        for p in a[a[:, 5] == 0][::10]:
            f = frac(p[2:5], team[n]); occ[team[n]]['home' if f > 2 / 3 else 'enemy' if f < 1 / 3 else 'mid'] += 1
        t = a[:, 0]; i = np.clip(np.searchsorted(t, t + 0.25), 0, len(a) - 1)
        v = np.hypot(a[i, 2] - a[:, 2], a[i, 3] - a[:, 3]) / np.maximum(t[i] - t, 1e-3)
        ok = (a[:, 5] == 0) & (a[i, 5] == 0) & (v < 1500); fast.append((v[ok] > 500).mean())
    dz = collections.Counter()
    for n, x, y in deaths:
        f = frac((x, y), team[n]); dz['own base' if f > 2 / 3 else 'enemy base' if f < 1 / 3 else 'mid'] += 1
    capsby = collections.Counter(s['team'] for s in caps)
    mins = (t1 - t0) / 60
    R = dict(label=label, minutes=round(mins, 1), players=f"{sum(v=='red' for v in team.values())}v{sum(v=='blue' for v in team.values())}",
             pickups=len(segs), from_stand=len(grabs), caps=len(caps), caps_by=dict(capsby), conv=round(len(caps) / max(1, len(grabs)), 2),
             killed_early=f"{early}/{len(killed)}", cap_times=sorted(round(c[0], 1) for c in caplen),
             cap_pace=round(np.median([c[1] / c[0] for c in caplen]), 0) if caplen else None,
             cap_dist=sorted(round(c[1]) for c in caplen), stand_gap=round(d2(stand['red'], stand['blue'])),
             deaths_per_min=round(len(deaths) / mins, 1), deaths_zone=dict(dz),
             home_time={tm: round(100 * occ[tm]['home'] / sum(occ[tm].values())) for tm in occ},
             hook_time=f"{100*np.median(fast):.1f}% median, {100*max(fast):.1f}% max",
             score=[s for t, s in pr if 'captured' in s or 'Team scores' in s][-1:])
    # figure
    allp = np.concatenate([a[a[:, 5] == 0][:, 2:4] for a in per.values()])
    lo, hi = allp.min(0) - 60, allp.max(0) + 60
    fig, axes = plt.subplots(1, 2, figsize=(22, 10 * (hi[1] - lo[1]) / (hi[0] - lo[0]) + 1.2)); fig.patch.set_facecolor('#1d1f21')
    for k, ax in enumerate(axes):
        ax.set_facecolor('#111')
        ax.hist2d(allp[:, 0], allp[:, 1], bins=[int((hi[0] - lo[0]) / 20), int((hi[1] - lo[1]) / 20)], range=[[lo[0], hi[0]], [lo[1], hi[1]]], norm=LogNorm(), cmap='gray')
        for tm, c in (('blue', '#4f8cff'), ('red', '#ff4f4f')):
            ax.plot(*stand[tm][:2], '*', ms=22, mfc=c, mec='white')
        ax.set_aspect('equal'); ax.tick_params(colors='#888')
    for s in segs:
        a = per[s['n']][s['i0']:s['i1'] + 1]; cap = s in caps
        axes[0].plot(a[:, 2], a[:, 3], '-', color='#5bff7a' if cap else ('#ff9a3c' if s['team'] == 'red' else '#ff5bd8'), lw=2.4 if cap else 1.1, alpha=0.9 if cap else 0.7)
        if s['died']: axes[0].plot(a[-1, 2], a[-1, 3], 'x', color='white', ms=9, mew=2)
    for n, x, y in deaths:
        axes[1].plot(x, y, 'o', ms=5, mfc='#ff4f4f' if team[n] == 'red' else '#4f8cff', mec='none', alpha=0.8)
    axes[0].set_title('Flag carries: green = captured, orange/pink = carrier killed (x)', color='white')
    axes[1].set_title('Deaths (dot colour = dying player\'s team); background = time spent', color='white')
    fig.suptitle(f'{label}: {R["players"]}, {R["minutes"]} min', color='white', fontsize=14)
    plt.tight_layout(); plt.savefig(f'{label}.png', facecolor=fig.get_facecolor(), dpi=70); plt.close(fig)
    return R

if __name__ == "__main__":
  out = [analyze(p, l) for p, l in [('ctf1_0509.mvd', 'ctf1_2026-05-09'), ('ctf1_0328.mvd', 'ctf1_2026-03-28'),
                                  ('ctf1_0926.mvd', 'ctf1_2026-09-26'), ('ctf3_0328.mvd', 'ctf3_2026-03-28')]]
  for R in out:
      print(json.dumps({k: v for k, v in R.items()}, default=str))
