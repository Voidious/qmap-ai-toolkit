"""Contact sheet of a texture folder: each texture tiled 2x2 (so seams show), labelled."""
import os, sys
from PIL import Image, ImageDraw
d, out = sys.argv[1], sys.argv[2]
names = [l.split('=')[0] for l in open('wad_args.txt') if l.strip()]
cell = 200
cols = 7
rows = (len(names) + cols - 1) // cols
sheet = Image.new('RGB', (cols * cell, rows * (cell + 14)), (24, 24, 24))
dr = ImageDraw.Draw(sheet)
for k, nm in enumerate(names):
    im = Image.open(os.path.join(d, nm + '.png')).convert('RGB')
    w, h = im.size
    t = Image.new('RGB', (w * 2, h * 2))
    for a in (0, 1):
        for b in (0, 1):
            t.paste(im, (a * w, b * h))
    s = min(cell / (2 * w), cell / (2 * h), 2.0)
    t = t.resize((int(2 * w * s), int(2 * h * s)), Image.NEAREST)
    x, y = (k % cols) * cell, (k // cols) * (cell + 14)
    sheet.paste(t, (x, y + 14))
    dr.text((x + 2, y + 1), f'{nm} {w}x{h}', fill=(255, 230, 80))
sheet.save(out)
