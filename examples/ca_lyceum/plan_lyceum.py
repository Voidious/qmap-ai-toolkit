"""Two-panel top-down plan for ca_lyceum: pit + main level, and the upper levels (160 / 288)."""
import json
import math
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch

d = json.load(open(sys.argv[1]))
out, title = sys.argv[2], sys.argv[3]
C, XMIN, YMIN, NX, NY, BOT, TOP = (d[k] for k in ('C', 'XMIN', 'YMIN', 'NX', 'NY', 'BOT', 'TOP'))
cols = d['cols']


def air(i, j):
    res, z = [], BOT
    for a, b, m in sorted(cols[i][j]):
        if a > z:
            res.append((z, a))
        z = max(z, b)
    return res


low = np.full((NY, NX), np.nan)
up = np.full((NY, NX), np.nan)
crypt = np.full((NY, NX), np.nan)
for i in range(NX):
    for j in range(NY):
        fl = [a for a, b in air(i, j) if a > BOT and b - a >= 56]
        if not fl:
            continue
        lo = [f for f in fl if f < 150]
        hi = [f for f in fl if f >= 150]
        if lo:
            low[j, i] = max(lo)            # the floor you walk on at ground level

        if hi:
            up[j, i] = min(hi)

bounds = [-120, -88, -8, 8, 40, 72, 150, 176, 272, 300]
colors = ['#2f5d4a', '#4f8a6e', '#3b6e8f', '#5b8fa8', '#8a8a8a', '#b9a34e', '#e8c878', '#d9a05b', '#d9674e']
cmap = ListedColormap(colors)
norm = BoundaryNorm(bounds, cmap.N)
STY = {'w': ('#ff4d4d', 'D'), 'a': ('#ffe14d', 's'), 'h': ('#5ee36b', 'P'), 'q': ('#c77dff', '*'), 'm': ('#cfcfcf', '.')}

fig, axes = plt.subplots(1, 2, figsize=(24, 9.5), dpi=100)
fig.patch.set_facecolor('#1d1f21')
ext = [XMIN, XMIN + NX * C, YMIN, YMIN + NY * C]
for k, (ax, grid, name) in enumerate(((axes[0], low, 'LOWER: pit / low passage -96, main floor 0'), (axes[1], up, 'UPPER: balcony, gallery, climb 160 - tower stand 288'))):
    ax.set_facecolor('#2a2c2e')
    if k == 1:   # ghost of the floor level under the upper level
        ax.imshow(np.where(np.isnan(low), np.nan, 0), origin='lower', extent=ext, cmap=ListedColormap(['#3a3d40']),
                  interpolation='nearest')
    ax.imshow(grid, origin='lower', extent=ext, cmap=cmap, norm=norm, interpolation='nearest')
    if k == 0:   # lava
        for (r, z0, z1, t) in d.get('liquids', []):
            ax.add_patch(plt.Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], fc='#2f8fc0', ec='none', alpha=0.85, zorder=3))
    for kind_, (r, z, dx, dy, dz, ang) in [('t', t) for t in d.get('teleports', [])] + [('p', t) for t in d.get('pushes', [])]:
        if k == 0:
            cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
            pc = '#39f' if kind_ == 't' else '#f0f'
            ax.add_patch(plt.Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], fc=pc, ec='white', lw=1, zorder=6))
            ax.annotate('', xy=(dx, dy), xytext=(cx, cy), zorder=7,
                        arrowprops=dict(arrowstyle='-|>', color=pc, lw=1.4, ls='--', connectionstyle='arc3,rad=0.25'))
    upper = k == 1
    for x, y, z, ang, lab in d['spawns']:
        if (z >= 150) != upper:
            continue
        a = math.radians(ang)
        ax.annotate('', xy=(x + 70 * math.cos(a), y + 70 * math.sin(a)), xytext=(x, y),
                    arrowprops=dict(arrowstyle='-|>', color='white', lw=1.6))
        ax.plot(x, y, 'o', ms=8, mfc='white', mec='black', mew=1.2)
    for cls, x, y, z, flags, lab in d['items']:
        if (z >= 150) != upper:
            continue
        kind = ('q' if 'artifact' in cls else 'w' if cls.startswith('weapon') else 'a' if 'armor' in cls
                else 'h' if cls == 'item_health' else 'm')
        col, mk = STY[kind]
        ax.plot(x, y, mk, ms=11 if kind in 'wqa' else 7 if kind == 'h' else 9, mfc=col, mec='black', mew=0.8, zorder=5)
        if kind == 'm':
            ax.text(x + 18, y + 10, lab, fontsize=7, color='#eee', zorder=6)
        elif lab not in ('h', 'h15'):
            txt = lab
            if z not in (0, -96, 160, 288):
                txt += f' @{z}'
            dy = -38 if lab == 'QUAD' else 30
            ax.text(x, y + dy, txt, ha='center', fontsize=8.5, weight='bold', color='black', zorder=6,
                    bbox=dict(boxstyle='round,pad=0.15', fc=col, ec='black', lw=0.5))
    for x, y, t in d['labels']:
        if (('160' in t) or ('288' in t) or ('climb' in t)) != upper:
            continue
        for sx, sy in [(x, y)]:
            tt = t
            ax.text(sx, sy, tt, ha='center', va='center', fontsize=8.5, color='black', weight='bold', zorder=4,
                    bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='none', alpha=0.75))
    ax.set_xlim(XMIN + 16, XMIN + NX * C - 16)
    ax.set_ylim(YMIN + 16, YMIN + NY * C - 16)
    ax.set_aspect('equal')
    ax.tick_params(colors='#aaa', labelsize=8)
    ax.set_xticks(range(-1024, 1025, 256))
    ax.set_yticks(range(-1024, 769, 256))
    ax.grid(color='#444', lw=0.4, alpha=0.5)
    ax.set_title(name, color='white', fontsize=12)
legend = [Patch(color=colors[0], label='pit / low passage -96'), Patch(color=colors[1], label='steps -80..-16'),
          Patch(color=colors[2], label='main floor 0'), Patch(color=colors[3], label='steps 16-32'),
          Patch(color=colors[4], label='plinth / platform 48-64'), Patch(color=colors[5], label='steps 80-144'),
          Patch(color=colors[6], label='balcony / gallery 160'), Patch(color=colors[7], label='climb / steps 176-272'),
          Patch(color=colors[8], label='tower stand 288'),
          Patch(color='white', label='spawn (arrow = facing)'), Patch(color='#ff4d4d', label='weapon'),
          Patch(color='#ffe14d', label='armour'), Patch(color='#5ee36b', label='health (MH = mega)'),
          Patch(color='#cfcfcf', label='ammo: s n r c')]
fig.legend(handles=legend, loc='lower center', ncol=7, fontsize=9, framealpha=0.9)
fig.suptitle(title, color='white', fontsize=13)
plt.tight_layout(rect=(0, 0.07, 1, 0.97))
plt.savefig(out, facecolor=fig.get_facecolor())
