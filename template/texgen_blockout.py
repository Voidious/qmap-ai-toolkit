"""Blockout textures for layout builds (qmap-ai-toolkit): plain, readable, deliberately ugly-neutral,
so a layout is judged as a layout and no earlier map's look leaks into a new one.

  bk_z0..z7_{wall,flr,ceil,strp}  eight zone colours. Walls carry height marks (thin line every 32,
                                  strong every 128, joints every 64), floors a 64 checker with a 16
                                  grid - so heights and distances can be read off a screenshot.
  bk_base, bk_trim, bk_tread, bk_riser, bk_pillar, bk_pbase, bk_pcap, bk_perch, bk_crate,
  bk_cratetop, bk_stand, bk_pad, bk_lampbox, bk_light, bk_wlamp, bk_panel, sky_bk,
  *bk_water, *bk_lava
All generated here, quantized to the Quake palette (LibreQuake's, BSD-3).
Usage: python3 texgen_blockout.py outdir   (writes outdir/*.png and wad_args.txt for makewad.py)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'qmap'))
import texgen_runic as R  # noqa: E402
from texgen import fbm  # noqa: E402

ZONES = {'z0': (92, 104, 136), 'z1': (112, 112, 108), 'z2': (156, 96, 56), 'z3': (70, 118, 84),
         'z4': (120, 86, 124), 'z5': (176, 140, 56), 'z6': (104, 108, 52), 'z7': (146, 58, 50)}
# blue, grey, orange, green, mauve, gold, olive, red - chosen to stay distinct after palette quantizing


def noise(h, w, seed, amt=0.08):
    return (1 - amt + 2 * amt * fbm(h, w, seed, base=4, octaves=3))[..., None]


def wall(col, seed):
    h, w = 128, 128
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = np.array(col, float) * noise(h, w, seed)
    rgb[(yy % 32) == 0] *= 0.82
    rgb[(yy % 128) == 0] *= 0.6
    rgb[((xx % 64) == 0)] *= 0.8
    return rgb


def floor(col, seed):
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    c = np.array(col, float) * 1.12
    rgb = c * noise(n, n, seed, 0.05)
    rgb[((xx // 32) + (yy // 32)) % 2 == 1] *= 0.86
    rgb[(xx % 16 == 0) | (yy % 16 == 0)] *= 0.9
    rgb[(xx == 0) | (yy == 0)] *= 0.7
    return rgb


def ceil(col, seed):
    n = 64
    yy, xx = np.mgrid[0:n, 0:n]
    rgb = np.array(col, float) * 0.6 * noise(n, n, seed, 0.05)
    rgb[(xx == 0) | (yy == 0)] *= 0.6
    return rgb


def strip(seed):
    idx = np.full((16, 64), R.quantize(np.array([[[70, 64, 56]]], float))[0, 0], np.uint8)
    idx[4:12, :] = 236
    idx[4, :] = idx[11, :] = 234
    idx[4:12, 0:2] = idx[4:12, 32:34] = R.quantize(np.array([[[40, 36, 32]]], float))[0, 0]
    return idx


def plain(h, w, col, seed, lines=()):
    yy, xx = np.mgrid[0:h, 0:w]
    rgb = np.array(col, float) * noise(h, w, seed, 0.05)
    for axis, k, f in lines:
        rgb[((yy if axis == 'y' else xx) % k) == 0] *= f
    return rgb


def disc(n, col, ring, seed):
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(xx - (n - 1) / 2, yy - (n - 1) / 2)
    rgb = np.array(col, float) * noise(n, n, seed, 0.04)
    rgb[np.abs(r - n * 0.38) < n * 0.03] = ring
    rgb[r < n * 0.08] = ring
    return rgb


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    names = []

    def put(name, img):
        fname = name.replace('*', 'liquid_')            # '*' is not a portable file name character
        R.save(outdir, fname, img if img.ndim == 2 else R.quantize(np.clip(img, 0, 255)))
        names.append(f'{name}={outdir}/{fname}.png')

    for k, (z, col) in enumerate(ZONES.items()):
        put(f'bk_{z}_wall', wall(col, 10 + k))
        put(f'bk_{z}_flr', floor(col, 20 + k))
        put(f'bk_{z}_ceil', ceil(col, 30 + k))
        put(f'bk_{z}_strp', strip(40 + k))
    put('bk_base', plain(32, 64, (54, 52, 50), 1, (('y', 32, 0.6),)))
    put('bk_trim', plain(16, 64, (150, 146, 136), 2, (('y', 16, 0.6),)))
    put('bk_tread', plain(32, 32, (150, 146, 136), 3, (('y', 32, 0.75),)))
    put('bk_riser', plain(16, 32, (104, 100, 94), 4, (('y', 16, 0.7),)))
    put('bk_pillar', plain(128, 64, (138, 134, 126), 5, (('x', 16, 0.85), ('y', 64, 0.7))))
    put('bk_pbase', plain(32, 64, (110, 106, 98), 6, (('y', 8, 0.75),)))
    put('bk_pcap', plain(32, 64, (110, 106, 98), 7, (('y', 8, 0.75),)))
    put('bk_perch', plain(64, 64, (150, 104, 60), 8, (('y', 16, 0.7),)))
    put('bk_crate', plain(64, 64, (128, 110, 70), 9, (('x', 64, 0.6), ('y', 64, 0.6))))
    put('bk_cratetop', plain(64, 64, (140, 122, 80), 10, (('x', 64, 0.6), ('y', 64, 0.6))))
    put('bk_stand', disc(128, (120, 116, 110), (200, 180, 90), 11))
    put('bk_pad', disc(128, (90, 90, 120), (220, 220, 240), 12))
    put('bk_lampbox', plain(16, 32, (70, 66, 60), 13))
    li = np.full((32, 32), R.quantize(np.array([[[70, 66, 60]]], float))[0, 0], np.uint8)
    yy, xx = np.mgrid[0:32, 0:32]
    li[np.hypot(xx - 15.5, yy - 15.5) < 12] = 237
    li[np.hypot(xx - 15.5, yy - 15.5) < 6] = 239
    put('bk_light', li)
    wl = np.full((32, 32), R.quantize(np.array([[[80, 74, 64]]], float))[0, 0], np.uint8)
    wl[6:26, 8:24] = 236
    wl[10:22, 12:20] = 239
    put('bk_wlamp', wl)
    p = plain(256, 256, (70, 70, 90), 14)
    py_, px_ = np.mgrid[0:256, 0:256]
    d = np.abs(px_ - 127.5) + np.abs(py_ - 127.5)
    p[(d > 80) & (d < 96)] = (210, 200, 150)
    p[d < 30] = (210, 200, 150)
    p[:6] = p[-6:] = p[:, :6] = p[:, -6:] = (210, 200, 150)
    put('bk_panel', p)
    back = np.array([20, 24, 44]) + np.array([30, 34, 50]) * fbm(128, 128, 15, base=3, octaves=4)[..., None]
    bi = R.quantize(back)
    fi = np.zeros((128, 128), np.uint8)
    put('sky_bk', np.concatenate([fi, bi], 1))
    put('*bk_water', plain(64, 64, (40, 70, 100), 16, (('y', 16, 0.85),)))
    put('*bk_lava', plain(64, 64, (180, 70, 20), 17, (('x', 16, 0.8),)))
    open('wad_args.txt', 'w').write('\n'.join(names) + '\n')     # name=png pairs for makewad.py
    print(len(names), 'blockout textures')


if __name__ == '__main__':
    main(sys.argv[1])
