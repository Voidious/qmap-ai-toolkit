"""Close-up review shots (same tone curve as views_lyceum.py)."""
import os
import sys
sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
import numpy as np
from render import BSP, render
from PIL import Image, ImageDraw
b = BSP(sys.argv[1])
views = [('climb stairs: side walls', (-470, 300, 200), 80, 18),
         ('low passage stairs up to the duel hall', (200, -860, -50), 0, 10),
         ('RL plinth medallion from above', (0, -40, 170), 270, 58),
         ('duel south wall: panels, band, lamps', (800, -640, 70), 270, 8),
         ('balcony door into the gallery (sill)', (280, 300, 210), 0, 8),
         ('hub balcony front and grand stair', (-300, 60, 60), 75, 12),
         ('climb top: door onto the tower stand', (-448, 560, 330), 90, 4),
         ('gallery steps down into the duel hall', (760, -100, 60), 60, 14),
         ('column base', (-130, -170, 40), 220, -18),
         ('column capital', (-110, -130, 330), 220, -28),
         ('oculus from the tower floor', (-800, -60, 60), 90, -72),
         ('hub door to the duel hall', (250, -10, 60), 0, 5)]
tiles = []
for lab, c, yaw, p in views:
    raw = np.asarray(render(b, c, yaw, p, 100, 640, 360)).astype(float)
    cl = 255 * (raw / 255) ** 0.55
    im = Image.fromarray(cl.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, len(lab) * 6 + 12, 16), fill=(0, 0, 0)); d.text((6, 2), lab, fill=(255, 230, 80))
    tiles.append(im)
sheet = Image.new('RGB', (1280, 360 * ((len(tiles) + 1) // 2)))
for k, t in enumerate(tiles):
    sheet.paste(t, ((k % 2) * 640, (k // 2) * 360))
sheet.save(sys.argv[2])
