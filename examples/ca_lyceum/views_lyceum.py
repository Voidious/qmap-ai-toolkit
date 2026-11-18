"""Preview views with a tone curve fitted to the user's ezQuake screenshots (b6 vs my raw renders):
client ~= 255 * (raw/255) ** 0.55.  Prints DM2-comparable stats (DM2 shot: mean 35, 54% dark)."""
import os
import sys
sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
import numpy as np
from render import BSP, render
from PIL import Image, ImageDraw
b = BSP(sys.argv[1])
views = [('Hub from the SE: plinth RL, balcony and grand stair', (330, -340, 60), 130, 4),
         ('Hub from the balcony (160): plinth, doors to pit and duel', (0, 352, 220), 270, -14),
         ('Tower floor: broad stair up to the stand (288)', (-800, -160, 60), 90, 8),
         ('Tower stand (288): MH and LG, looking down the stair', (-640, 740, 350), 250, -16),
         ('Climb: balcony up to the stand', (-448, 280, 220), 90, 10),
         ('Pit from the rim: pier, RA beyond, low passage at left', (-790, -560, 60), -40, -14),
         ('Low passage (-96) toward the duel hall', (24, -832, -40), 0, 2),
         ('Duel hall from the low passage stairs', (540, -860, 60), 55, 2),
         ('Duel hall: platform YA, wall stub, gallery steps', (1040, -860, 60), 115, 4),
         ('Gallery (160) over the duel hall', (540, 480, 220), -40, -10)]
tiles, means, darks = [], [], []
for lab, c, yaw, p in views:
    raw = np.asarray(render(b, c, yaw, p, 105, 640, 360)).astype(float)
    cl = 255 * (raw / 255) ** 0.55
    L = cl @ [0.299, 0.587, 0.114]
    means.append(L.mean()); darks.append((L < 40).mean() * 100)
    im = Image.fromarray(cl.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im); t = f'{lab}  (mean {L.mean():.0f}, dark {darks[-1]:.0f}%)'
    d.rectangle((0, 0, len(t) * 6 + 12, 16), fill=(0, 0, 0)); d.text((6, 2), t, fill=(255, 230, 80))
    tiles.append(im)
sheet = Image.new('RGB', (1280, 360 * 5))
for k, t in enumerate(tiles):
    sheet.paste(t, ((k % 2) * 640, (k // 2) * 360))
sheet.save(sys.argv[2])
print(f'overall: mean {np.mean(means):.1f}  dark {np.mean(darks):.0f}%   (Crucible ~51, Vigil ~43, Agora ~110, DM2 35)')
