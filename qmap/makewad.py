"""Build a Quake WAD2 texture file from LibreQuake PNGs (BSD-licensed textures).

Usage: python3 makewad.py out.wad name=path.png [name=path.png ...]
Textures are converted to the Quake palette; '_fbr' sources keep fullbright colors.
"""
import os
import struct
import sys

from PIL import Image

PAL = list(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'quake_palette.lmp'), 'rb').read())
PAL_RGB = [tuple(PAL[i * 3:i * 3 + 3]) for i in range(256)]


def nearest(rgb, allow_fb):
    best, bi = 1 << 30, 0
    limit = 256 if allow_fb else 224
    for i in range(limit):
        p = PAL_RGB[i]
        d = (p[0] - rgb[0]) ** 2 + (p[1] - rgb[1]) ** 2 + (p[2] - rgb[2]) ** 2
        if d < best:
            best, bi = d, i
    return bi


def to_indices(path, allow_fb):
    im = Image.open(path)
    if im.mode == 'P':
        pal = im.getpalette()[:768]
        if pal == PAL[:len(pal)]:
            return im.size, list(im.getdata())
    im = im.convert('RGB')
    cache = {}
    out = []
    for px in im.getdata():
        if px not in cache:
            cache[px] = nearest(px, allow_fb)
        out.append(cache[px])
    return im.size, out


def mip(size, idx, level):
    w, h = size
    s = 1 << level
    return bytes(idx[(y * s) * w + (x * s)] for y in range(h // s) for x in range(w // s))


def miptex(name, path):
    allow_fb = '_fbr' in path or name.startswith('sky')
    (w, h), idx = to_indices(path, allow_fb)
    assert w % 16 == 0 and h % 16 == 0, (name, w, h)
    mips = [mip((w, h), idx, l) for l in range(4)]
    hdr = 16 + 4 + 4 + 16
    offs, o = [], hdr
    for m in mips:
        offs.append(o)
        o += len(m)
    return struct.pack('<16sII4I', name.encode()[:15], w, h, *offs) + b''.join(mips)


def main():
    out = sys.argv[1]
    lumps = []
    for arg in sys.argv[2:]:
        name, path = arg.split('=', 1)
        lumps.append((name, miptex(name, path)))
    data = b''
    entries = []
    pos = 12
    for name, blob in lumps:
        entries.append(struct.pack('<IIIbbbb16s', pos, len(blob), len(blob), 0x44, 0, 0, 0, name.encode()[:15]))
        data += blob
        pos += len(blob)
    with open(out, 'wb') as f:
        f.write(b'WAD2' + struct.pack('<II', len(lumps), pos))
        f.write(data)
        f.write(b''.join(entries))
    print(f'wrote {out}: {len(lumps)} textures')


if __name__ == '__main__':
    main()
