"""Preview renders of a compiled .bsp (qmap-toolkit v2, generic).
Edit CAMS for your map: (label, (x, y, z eye), yaw degrees (0 = +x, 90 = +y), pitch degrees (+ = DOWN, as in Quake; - looks up)).
The tone curve 255*(raw/255)^0.55 was fitted to ezQuake screenshots at default gamma/contrast, so the
'mean' brightness printed per view is comparable between maps (our maps sit around 45-60).
Usage: python3 views.py map.bsp out.png"""
import os
import sys

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from render import BSP, render  # noqa: E402

CAMS = [('Arena (0) from blue\'s arena arch: the arcade walls, side-lane doors, the loggias', (488, 300, 60), 196, -4),
        ('Atrium from high over blue\'s end (camera only): arena pit, side lanes', (520, 0, 600), 180, 30),
        ('Blue lower hall from the atrium arch: baffle, columns, the well', (600, 300, 60), -20, 2),
        ('Blue lower hall toward the base gate and the pier', (900, 0, 60), 0, 2),
        ('Blue north deck (256) from the bridge end', (540, 560, 302), 0, 0),
        ('Well room (256): Mega, the well down to the lower hall', (1120, 200, 302), -40, 16),
        ('Blue base from the gate: flag mezzanine, stairs up to both balconies', (1900, 0, 60), 0, 4),
        ('Blue base from the north balcony (256)', (1960, 560, 302), -20, 16),
        ('Blue south deck (256) toward the base', (560, -560, 302), 10, 0),
        ('Red base from its gate', (-1900, 0, 60), 180, 4)]


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
