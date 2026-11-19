"""Before/after sheet for the b2 side lanes, and a sheet of the new lanes.
  python3 views_lanes.py before.bsp after.bsp out_beforeafter.png out_lanes.png"""
import os
import sys

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
from render import BSP, render  # noqa: E402

PAIRS = [('Atrium from high over blue\'s end (camera only)', (520, 0, 600), 180, 30),
         ('Arena from blue\'s arena arch', (488, 300, 60), 196, -4),
         ('North bridge from the blue deck', (560, 560, 302), 180, 4)]
LANES = [('North bridge (256): the loggia on the left, the stair on the right', (300, 560, 302), 180, 8),
         ('Through the loggia: the Quad below', (0, 470, 302), 270, 40),
         ('South undercroft (0) from blue\'s south arch', (560, -560, 46), 180, 0),
         ('North undercroft (0): the alcove and the stair up to the bridge', (-460, 520, 46), 30, -14),
         ('Arena (0) door into the north undercroft, beside blue\'s arena arch', (300, 120, 46), 70, 0),
         ('Red end: north undercroft into red\'s hall', (-200, 560, 46), 180, 0)]


def shot(b, lab, c, yaw, p, tag=''):
    raw = np.asarray(render(b, c, yaw, p, 105, 640, 360)).astype(float)
    cl = 255 * (raw / 255) ** 0.55
    L = (cl @ [0.299, 0.587, 0.114]).mean()
    im = Image.fromarray(cl.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    t = f'{tag}{lab}  (mean {L:.0f})'
    d.rectangle((0, 0, len(t) * 6 + 12, 16), fill=(0, 0, 0))
    d.text((6, 2), t, fill=(255, 230, 80))
    return im


def sheet(tiles, out):
    s = Image.new('RGB', (1280, 360 * ((len(tiles) + 1) // 2)))
    for k, t in enumerate(tiles):
        s.paste(t, ((k % 2) * 640, (k // 2) * 360))
    s.save(out)


if __name__ == '__main__':
    b1, b2 = BSP(sys.argv[1]), BSP(sys.argv[2])
    tiles = []
    for lab, c, yaw, p in PAIRS:
        tiles += [shot(b1, lab, c, yaw, p, 'BEFORE b1: '), shot(b2, lab, c, yaw, p, 'AFTER b2: ')]
    sheet(tiles, sys.argv[3])
    sheet([shot(b2, *v) for v in LANES], sys.argv[4])
