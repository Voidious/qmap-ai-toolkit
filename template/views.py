"""Preview renders of a compiled .bsp (qmap-toolkit v3, generic).
Edit CAMS for your map: (label, (x, y, z eye), yaw degrees (0 = +x, 90 = +y), pitch degrees (+ = DOWN, as in Quake; - looks up)).
The tone curve 255*(raw/255)^0.55 was fitted to ezQuake screenshots at default gamma/contrast, so the
'mean' brightness printed per view is comparable between maps (our maps sit around 45-60).
Usage: python3 views.py map.bsp out.png"""
import os
import sys

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'qmap'))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from render import BSP, render  # noqa: E402

CAMS = [('hall from the south-west corner', (-340, -340, 60), 45, 0),
        ('hall: plinth and the doorway north', (0, -330, 60), 90, -4),
        ('east wing: gallery steps and the perch', (560, -280, 60), 40, 6),
        ('low room: ramp to the ledge, octagonal pillar', (330, 920, -36), 184, 4)]


def main(bsp, out):
    b = BSP(bsp)
    tiles, means = [], []
    for lab, c, yaw, p in CAMS:
        raw = np.asarray(render(b, c, yaw, p, 105, 640, 360)).astype(float)
        cl = 255 * (raw / 255) ** 0.55
        L = cl @ [0.299, 0.587, 0.114]
        means.append(L.mean())
        im = Image.fromarray(cl.clip(0, 255).astype(np.uint8))
        d = ImageDraw.Draw(im)
        t = f'{lab}  (mean {L.mean():.0f})'
        d.rectangle((0, 0, len(t) * 6 + 12, 16), fill=(0, 0, 0))
        d.text((6, 2), t, fill=(255, 230, 80))
        tiles.append(im)
    sheet = Image.new('RGB', (1280, 360 * ((len(tiles) + 1) // 2)))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % 2) * 640, (k // 2) * 360))
    sheet.save(out)
    print(f'mean brightness {np.mean(means):.1f}')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
