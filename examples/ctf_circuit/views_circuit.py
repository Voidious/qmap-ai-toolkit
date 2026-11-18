"""Preview views for ctf_circuit (tone curve fitted to the user's ezQuake screenshots: 255*(raw/255)^0.55)."""
import os
import sys
sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
import numpy as np
from render import BSP, render
from PIL import Image, ImageDraw
b = BSP(sys.argv[1])
views = [('Mid chamber from the blue spine: Quad dais, columns, perch over the spine mouth', (430, 40, 60), 180, 4),
         ('Mid chamber: the gilded cupola over the Quad', (0, -430, 50), 90, -42),
         ('North court (192): Mega, gold-tile dado', (640, 1420, 250), 185, 8),
         ('Aqueduct hall: the bridge (192) and its water channel, perch on the north wall', (1780, 1100, 250), 180, 6),
         ('Aqueduct floor (0) under the bridge', (1500, 760, 60), 160, -4),
         ('Gatehouse (192) toward the forecourt stair', (3150, 960, 250), 180, 4),
         ('Blue forecourt from the spine mouth: banner between the flag-hall doors', (1850, -60, 60), 0, 4),
         ('Blue flag hall from the forecourt door', (2420, 300, 60), -15, 4),
         ('Red flag hall from the forecourt door', (-2420, 300, 60), 195, 4),
         ('Red forecourt: stairs up to the gatehouse, perch on the far wall', (-2300, -400, 60), 120, -6),
         ('Red spine junction room', (-1360, -200, 60), 20, 2),
         ('Undercroft (-128) toward the south court', (1780, -1100, -70), 180, 2)]
tiles, means, darks = [], [], []
for lab, c, yaw, p in views:
    raw = np.asarray(render(b, c, yaw, p, 105, 640, 360)).astype(float)
    cl = 255 * (raw / 255) ** 0.55
    L = cl @ [0.299, 0.587, 0.114]
    means.append(L.mean()); darks.append((L < 40).mean() * 100)
    im = Image.fromarray(cl.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im); t = f'{lab}  (mean {L.mean():.0f})'
    d.rectangle((0, 0, len(t) * 6 + 12, 16), fill=(0, 0, 0)); d.text((6, 2), t, fill=(255, 230, 80))
    tiles.append(im)
sheet = Image.new('RGB', (1280, 360 * ((len(tiles) + 1) // 2)))
for k, t in enumerate(tiles):
    sheet.paste(t, ((k % 2) * 640, (k // 2) * 360))
sheet.save(sys.argv[2])
print(f'overall: mean {np.mean(means):.1f}  dark {np.mean(darks):.0f}%')
