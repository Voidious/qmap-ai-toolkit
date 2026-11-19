"""Top-down plan image from the generator's JSON (qmap-toolkit v2, generic).
Two panels when the map has an upper level: LOWER (floors below SPLIT) and UPPER (floors at or above
SPLIT, with the lower level ghosted underneath). Floors are coloured by height (legend), spawns are
white dots with facing arrows (team starts: coloured squares), items are marked and named,
teleports / jump pads are arrows, perches are outlined.
Usage: python3 plan.py map.json out.png "title" [SPLIT]     (SPLIT default 120)"""
import json
import math
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import BoundaryNorm, ListedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

d = json.load(open(sys.argv[1]))
out, title = sys.argv[2], sys.argv[3]
SPLIT = int(sys.argv[4]) if len(sys.argv) > 4 else 120
C, XMIN, YMIN, NX, NY, BOT, TOP = (d[k] for k in ('C', 'XMIN', 'YMIN', 'NX', 'NY', 'BOT', 'TOP'))
cols = d['cols']


def air(i, j):
    res, z = [], BOT
    for a, b, m in sorted(cols[i][j]):
        if a > z:
            res.append((z, a))
        z = max(z, b)
    if z < TOP:
        res.append((z, TOP))
    return res


low = np.full((NY, NX), np.nan)
up = np.full((NY, NX), np.nan)
for i in range(NX):
    for j in range(NY):
        fl = [a for a, b in air(i, j) if a > BOT and b - a >= 56]
        lo = [f for f in fl if f < SPLIT]
        hi = [f for f in fl if f >= SPLIT]
        if lo:
            low[j, i] = max(lo)
        if hi:
            up[j, i] = min(hi)
heights = sorted({int(v) for v in np.concatenate([low[~np.isnan(low)], up[~np.isnan(up)]])})
pal = plt.get_cmap('viridis')(np.linspace(0.12, 0.95, max(2, len(heights))))
cmap = ListedColormap(pal[:len(heights)])
norm = BoundaryNorm([h - 0.5 for h in heights] + [heights[-1] + 0.5], cmap.N) if len(heights) > 1 else None
idx = {h: k for k, h in enumerate(heights)}
to_idx = np.vectorize(lambda v: np.nan if np.isnan(v) else idx[int(v)])
two = not np.all(np.isnan(up))
W, H = NX * C, NY * C
fig, axes = (plt.subplots(2, 1, figsize=(16, 16 * 2 * H / W + 2)) if (two and W > 1.3 * H) else
             plt.subplots(1, 2 if two else 1, figsize=(10 * (2 if two else 1) * min(1.6, W / H) + 2, 10)))
axes = np.atleast_1d(axes)
fig.patch.set_facecolor('#1d1f21')
ext = [XMIN, XMIN + W, YMIN, YMIN + H]
STY = {'w': ('#ff4d4d', 'D'), 'a': ('#ffe14d', 's'), 'h': ('#5ee36b', 'P'), 'q': ('#c77dff', '*'), 'm': ('#cfcfcf', '.')}
panels = [(axes[0], low, f'LOWER: floors below {SPLIT}' if two else 'PLAN')] + ([(axes[1], up, f'UPPER: floors at {SPLIT} and above')] if two else [])
for k, (ax, grid, name) in enumerate(panels):
    upper = k == 1
    ax.set_facecolor('#2a2c2e')
    if upper:
        ax.imshow(np.where(np.isnan(low), np.nan, 0), origin='lower', extent=ext, cmap=ListedColormap(['#3a3d40']),
                  interpolation='nearest')
    ax.imshow(to_idx(grid), origin='lower', extent=ext, cmap=cmap, vmin=-0.5, vmax=len(heights) - 0.5,
              interpolation='nearest')
    for (r, z0, z1, t) in d.get('liquids', []):
        if not upper:
            ax.add_patch(plt.Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], fc='#2f8fc0', ec='none', alpha=0.8))
    for kind_, t in [('t', t) for t in d.get('teleports', [])] + [('p', t) for t in d.get('pushes', [])]:
        r, z, dx, dy = t[0], t[1], t[2], t[3]
        if (z >= SPLIT) != upper:
            continue
        pc = '#39f' if kind_ == 't' else '#f0f'
        ax.add_patch(plt.Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], fc=pc, ec='white', lw=1, zorder=6))
        ax.annotate('', xy=(dx, dy), xytext=((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), zorder=7,
                    arrowprops=dict(arrowstyle='-|>', color=pc, lw=1.4, ls='--', connectionstyle='arc3,rad=0.25'))
    for r, z in d.get('perches', []):
        if (z >= SPLIT) == upper:
            ax.add_patch(plt.Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], fc='none', ec='#ff9ad5', lw=1.5, zorder=6))
    for x, y, z, ang, lab in d['spawns']:
        if (z >= SPLIT) != upper:
            continue
        a = math.radians(ang)
        ax.annotate('', xy=(x + 70 * math.cos(a), y + 70 * math.sin(a)), xytext=(x, y),
                    arrowprops=dict(arrowstyle='-|>', color='white', lw=1.5))
        ax.plot(x, y, 'o', ms=7, mfc='white', mec='black', mew=1.1)
    for x, y, z, ang, team in d.get('team_spawns', []):
        if (z >= SPLIT) == upper:
            ax.plot(x, y, 's', ms=7, mfc='#ff5050' if team == 1 else '#5090ff', mec='white', mew=1.0, zorder=5)
    for cls, x, y, z, flags, lab in d['items']:
        if (z >= SPLIT) != upper:
            continue
        kind = ('q' if 'artifact' in cls else 'w' if cls.startswith('weapon') else 'a' if ('armor' in cls or 'flag' in cls)
                else 'h' if (cls == 'item_health' and flags & 2) else 'm')
        c, mk = STY[kind]
        ax.plot(x, y, mk, ms=9 if kind != 'm' else 7, mfc=c, mec='black', mew=0.8, zorder=8)
        if kind != 'm' or lab != 'h':
            ax.text(x + 22, y + 14, lab, color=c, fontsize=8, weight='bold', zorder=9)
    for lb in d.get('labels', []):
        x, y, t = lb[:3]
        z = lb[3] if len(lb) > 3 else 0
        if (z >= SPLIT) == upper:
            ax.text(x, y, t, color='white', fontsize=9, ha='center', va='center', weight='bold', zorder=10,
                    bbox=dict(fc='#000a', ec='none', pad=1.5))
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_aspect('equal')
    ax.grid(color='#ffffff22', lw=0.5)
    ax.tick_params(colors='#999', labelsize=7)
    ax.set_title(name, color='white', fontsize=11)
cnt = {h: int(np.sum(low == h) + np.sum(up == h)) for h in heights}
main = sorted(h for h in heights if cnt[h] >= 0.03 * sum(cnt.values()))[:10]
legend = [Patch(color=cmap(idx[h]), label=f'floor {h}') for h in main]
legend += [Patch(color='white', label='spawn (arrow = facing)'), Patch(color='#5090ff', label='team start'),
           Patch(color='#ff4d4d', label='weapon'), Patch(color='#ffe14d', label='armour / flag'),
           Patch(color='#5ee36b', label='Mega'), Patch(color='#c77dff', label='powerup'),
           Patch(color='#cfcfcf', label='ammo / health'), Patch(color='#ff9ad5', label='perch (hook)')]
fig.legend(handles=legend, loc='lower center', ncol=min(8, len(legend)), fontsize=8, facecolor='#2a2c2e',
           labelcolor='white', edgecolor='#555')
fig.suptitle(title, color='white', fontsize=14)
plt.tight_layout(rect=(0, 0.06, 1, 0.96))
plt.savefig(out, facecolor=fig.get_facecolor(), dpi=90)
