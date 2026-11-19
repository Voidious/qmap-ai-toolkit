import re, math, collections, json, sys, glob
import numpy as np
from mvd import parse
from vert import movement_height      # v3: in-play height change (see vert.py)
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

WEAP = [('rocket', 'RL'), ('shaft', 'LG'), ('batteries', 'LG'), ('discharge', 'LG'), ('pineapple', 'GL'), ('grenade', 'GL'),
        ('buckshot', 'SSG'), ('boomstick', 'SG'), ('nailed', 'NG'), ('punctured', 'NG'), ('perforated', 'SNG'), ('pierced', 'SNG'),
        ('ventilated', 'SNG'), ('axe', 'axe'), ('telefrag', 'tele')]

def analyze(path):
    pl, tr, pr, st, unk, T = parse(path)
    mapname = re.search(r'_vs_(?:red|blue)(.+?)2026', path.split('/')[-1]).group(1)
    ids = [k for k, v in pl.items() if v['team'] in ('red', 'blue') and v['name'].strip()]
    team = {k: pl[k]['team'] for k in ids}; name = {k: pl[k]['name'] for k in ids}; byname = {v: k for k, v in name.items()}
    A = np.array([s for s in tr if s[1] in team], dtype=float)
    per = {n: A[A[:, 1] == n] for n in ids}
    ids = [n for n in ids if len(per[n]) > 100]; team = {n: team[n] for n in ids}; per = {n: per[n] for n in ids}
    def pos(n, t):
        a = per[n]; i = min(np.searchsorted(a[:, 0], t), len(a) - 1); return a[i, 2:5], a[i, 5]
    # rounds
    starts = [t + 5 for t, s in pr if re.search(r'round \[\d+\] starts in 5', s)]
    starts = sorted(set(round(s, 1) for s in starts))
    ends = sorted(set(round(t, 1) for t, s in pr if 'sco  damg' in s))
    rounds = []
    for s in starts:
        e = next((x for x in ends if x > s), None)
        if e: rounds.append((s, e))
    # kills from obituaries (dedupe by text+time)
    kills = []; seen = set()
    names = sorted(name.values(), key=len, reverse=True)
    for t, s in pr:
        s = s.strip()
        if (round(t, 1), s) in seen: continue
        seen.add((round(t, 1), s))
        if not any(s.startswith(nm + ' ') for nm in names): continue
        vic = next(nm for nm in names if s.startswith(nm + ' '))
        rest = s[len(vic):]
        kil = next((nm for nm in names if nm + "'s" in rest or rest.rstrip().endswith(' ' + nm) or (' by ' + nm) in rest), None)
        w = next((code for k, code in WEAP if k in rest), None)
        if kil and w and kil != vic:
            kills.append(dict(t=t, v=byname[vic], k=byname[kil], w=w))
    for K in kills:
        pk, _ = pos(K['k'], K['t'] - 0.05); pv, _ = pos(K['v'], K['t'] - 0.05)
        K['pk'] = pk; K['pv'] = pv; K['dist'] = float(np.linalg.norm(pk - pv)); K['dz'] = float(pk[2] - pv[2])
        K['friendly'] = team[K['k']] == team[K['v']]
    kills = [K for K in kills if not K['friendly']]
    # per-round timing
    R = []
    for s, e in rounds:
        ks = [K for K in kills if s <= K['t'] <= e]
        first = ks[0]['t'] - s if ks else None
        # alive counts through the round -> time spent in 1vX endgame
        ts = np.arange(s + 1, e, 0.25)
        endg = None; endpts = []
        for t in ts:
            al = {tm: [n for n in ids if team[n] == tm and pos(n, t)[1] == 0] for tm in ('red', 'blue')}
            if min(len(al['red']), len(al['blue'])) == 1 and max(len(al['red']), len(al['blue'])) >= 1:
                if endg is None: endg = t
                endpts += [pos(n, t)[0] for tm in al for n in al[tm]]
        R.append(dict(dur=e - s, first=first, kills=len(ks), endgame=(e - endg) if endg else 0, endpts=endpts))
    # spawn-to-contact: positions at round start
    spawn_pts = [pos(n, s + 0.3)[0] for s, e in rounds for n in ids]
    # time spent heat (alive, in rounds)
    inr = np.zeros(len(A), bool)
    for s, e in rounds: inr |= (A[:, 0] >= s) & (A[:, 0] <= e)
    live = A[inr & (A[:, 5] == 0)]
    zs = live[:, 4]
    dist = np.array([K['dist'] for K in kills]); dz = np.array([K['dz'] for K in kills])
    wc = collections.Counter(K['w'] for K in kills)
    out = dict(map=mapname, file=path.split('/')[-1], players=f"{sum(v=='red' for v in team.values())}v{sum(v=='blue' for v in team.values())}",
               rounds=len(R), round_len=[round(r['dur']) for r in R], median_round=round(np.median([r['dur'] for r in R])),
               first_kill=round(np.median([r['first'] for r in R if r['first'] is not None]), 1),
               kills=len(kills), weapons=dict(wc.most_common()),
               kill_dist=np.percentile(dist, [25, 50, 75]).round().tolist() if len(dist) else None,
               high_ground=f"{100*(dz>48).mean():.0f}% killer >48 higher, {100*(dz<-48).mean():.0f}% lower" if len(dz) else None,
               z_range=np.percentile(zs, [5, 50, 95]).round().tolist(),
               endgame=f"{sum(r['endgame']>0 for r in R)}/{len(R)} rounds reach 1vX; median {np.median([r['endgame'] for r in R if r['endgame']>0]):.0f}s of round",
               endgame_share=round(sum(r['endgame'] for r in R)/sum(r['dur'] for r in R), 2),
               **movement_height(per))
    # figure: time spent (bg), kills: line killer->victim coloured by weapon, spawn points
    lo, hi = live[:, 2:4].min(0) - 60, live[:, 2:4].max(0) + 60
    fig, ax = plt.subplots(figsize=(11, 11 * (hi[1] - lo[1]) / (hi[0] - lo[0]) + 0.8)); fig.patch.set_facecolor('#1d1f21'); ax.set_facecolor('#111')
    ax.hist2d(live[:, 2], live[:, 3], bins=[int((hi[0] - lo[0]) / 16), int((hi[1] - lo[1]) / 16)], range=[[lo[0], hi[0]], [lo[1], hi[1]]], norm=LogNorm(), cmap='gray')
    col = {'RL': '#ff5040', 'LG': '#60c8ff', 'GL': '#7cff6a', 'SSG': '#ffd040', 'SG': '#ffd040', 'NG': '#d080ff', 'SNG': '#d080ff', 'axe': 'w', 'tele': 'w'}
    for K in kills:
        ax.plot([K['pk'][0], K['pv'][0]], [K['pk'][1], K['pv'][1]], '-', color=col[K['w']], lw=0.8, alpha=0.55)
        ax.plot(K['pv'][0], K['pv'][1], 'o', ms=4, color=col[K['w']])
    ep = np.array([p for r in R for p in r['endpts']]) if any(r['endpts'] for r in R) else None
    if ep is not None: ax.plot(ep[::4, 0], ep[::4, 1], '.', ms=2, color='#ffe14d', alpha=0.35)
    sp = np.array(spawn_pts); ax.plot(sp[:, 0], sp[:, 1], 's', ms=5, mfc='none', mec='white', alpha=0.5)
    ax.set_aspect('equal'); ax.tick_params(colors='#888')
    ax.set_title(f"{mapname} {out['players']}: {len(R)} rounds, {len(kills)} kills. Lines = killer->victim (red RL, blue LG, green GL, yellow SSG); squares = round-start spawns; yellow = positions during 1vX endgames",
                 color='white', fontsize=9)
    tag = out['file'].replace('.mvd', '')
    plt.tight_layout(); plt.savefig(f'ca/{tag}.png', facecolor=fig.get_facecolor(), dpi=70); plt.close(fig)
    return out, kills, live, R

if __name__ == '__main__':
    for f in sorted(glob.glob('ca/*.mvd')):
        o, *_ = analyze(f); print(json.dumps(o, default=str))
