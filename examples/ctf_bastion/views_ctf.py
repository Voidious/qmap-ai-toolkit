"""Preview views with a tone curve fitted to the user's ezQuake screenshots (b6 vs my raw renders):
client ~= 255 * (raw/255) ** 0.55.  Prints DM2-comparable stats (DM2 shot: mean 35, 54% dark)."""
import sys, os
sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..', '..', 'qmap'] if 'examples' in os.path.abspath(__file__) else ['..', 'qmap'] if 'demos' in os.path.abspath(__file__) else [])))
import numpy as np
from render import BSP, render
from PIL import Image, ImageDraw
b = BSP(sys.argv[1])
views = [('Mid hall from the blue corridor mouth: Quad, pillars, both ledges', (440, 0, 60), 180, 6),
         ('Side route (north): from the high route down toward the red undercroft', (740, 704, 250), 180, -8),
         ('Main corridor: straight leg, then the dogleg into the base hall', (470, 60, 50), 0, 0),
         ('Base hall from the dogleg: south wing in the far corner', (1230, 220, 60), -40, 2),
         ('South wing toward the keep door', (1760, -560, 60), 0, 4),
         ('Keep: flag stand from the south door', (2112, -300, 60), 100, -6),
         ('Keep from the gallery (192)', (2200, 260, 250), 225, -24),
         ('North wing (192) toward the gallery door', (1740, 512, 250), 0, -2)]
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
sheet = Image.new('RGB', (1280, 360 * 4))
for k, t in enumerate(tiles):
    sheet.paste(t, ((k % 2) * 640, (k // 2) * 360))
sheet.save(sys.argv[2])
print(f'overall: mean {np.mean(means):.1f}  dark {np.mean(darks):.0f}%   (Relay ~48, Cistern ~55, Crucible ~51)')
