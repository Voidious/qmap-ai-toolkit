"""Error-diffusion quantizer onto a SUBSET of the Quake palette (new in v2).

The Quake palette has no true cream, ivory or warm beige: nearest-colour quantizing turns pale
marble pink or grey. Serpentine Floyd-Steinberg diffusion restricted to the neutral greys and the
warm ramps mixes them into colours the palette lacks. It diffuses over a 3x3 tiling and keeps the
centre, so the result still tiles seamlessly.

Use it for stone, plaster, marble, wood. Do NOT use it for saturated colour (reds, glazed tile,
paint): diffusion speckles them - quantize those to the nearest colour (texgen_runic.quantize),
or pass a mask so only the stone pixels are diffused (see examples/ctf_circuit/texgen_citadel.py).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import texgen as T  # noqa: E402

PAL = T.PAL
W8 = np.array([2.0, 4.0, 3.0])               # perceptual-ish channel weights
# greys 1-15, the warm grey-brown ramp 17-31, the rosy beige ramp 160-175, the tan ramp 112-127
STONE = list(range(1, 16)) + list(range(17, 32)) + list(range(160, 176)) + list(range(112, 128))


def fs_quantize(rgb, allowed=STONE, strength=0.85, seed=0):
    h, w, _ = rgb.shape
    big = np.tile(np.clip(rgb, 0, 255), (3, 3, 1)).astype(float)
    big += np.random.default_rng(seed).normal(0, 2.0, big.shape)
    pal = PAL[allowed]
    H, Wd = big.shape[:2]
    out = np.zeros((H, Wd), np.int32)
    for y in range(H):
        xs = range(Wd) if y % 2 == 0 else range(Wd - 1, -1, -1)
        s = 1 if y % 2 == 0 else -1
        row = big[y]
        for x in xs:
            px = row[x]
            k = int((((pal - px) ** 2) * W8).sum(1).argmin())
            out[y, x] = allowed[k]
            err = (px - pal[k]) * strength
            if 0 <= x + s < Wd:
                row[x + s] += err * 7 / 16
            if y + 1 < H:
                if 0 <= x - s < Wd:
                    big[y + 1, x - s] += err * 3 / 16
                big[y + 1, x] += err * 5 / 16
                if 0 <= x + s < Wd:
                    big[y + 1, x + s] += err * 1 / 16
    return out[h:2 * h, w:2 * w].astype(np.uint8)


def q1(rgb):
    """Nearest palette index for one colour (fullbright-safe)."""
    import texgen_runic as R
    return R.quantize(np.zeros((1, 1, 3)) + np.array(rgb, float))[0, 0]
