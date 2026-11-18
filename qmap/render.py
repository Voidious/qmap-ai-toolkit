"""Tiny BSP29 preview renderer: textures + compiled lightmaps, z-buffered.
Usage: python3 render.py map.bsp out.png x y z yaw pitch [fov]
Approximates how a software/GL Quake client shows the lit map (no overbright tricks)."""
import os
import math
import struct
import sys

import numpy as np
from PIL import Image

PAL = np.frombuffer(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'quake_palette.lmp'), 'rb').read(), np.uint8).reshape(256, 3).astype(np.float32)


class BSP:
    def __init__(self, path):
        b = open(path, 'rb').read()
        ver, = struct.unpack_from('<i', b, 0)
        assert ver == 29
        L = [struct.unpack_from('<ii', b, 4 + 8 * i) for i in range(15)]
        lump = lambda i: b[L[i][0]:L[i][0] + L[i][1]]
        pl = lump(1)
        self.planes = [struct.unpack_from('<4fi', pl, i) for i in range(0, len(pl), 20)]
        vx = lump(3)
        self.verts = np.array([struct.unpack_from('<3f', vx, i) for i in range(0, len(vx), 12)], np.float64)
        ti = lump(6)
        self.texinfo = [struct.unpack_from('<8fii', ti, i) for i in range(0, len(ti), 40)]
        ed = lump(12)
        self.edges = [struct.unpack_from('<HH', ed, i) for i in range(0, len(ed), 4)]
        se = lump(13)
        self.surfedges = struct.unpack('<%di' % (len(se) // 4), se)
        fc = lump(7)
        self.faces = [struct.unpack_from('<hhihh4Bi', fc, i) for i in range(0, len(fc), 20)]
        self.light = np.frombuffer(lump(8), np.uint8)
        mt = lump(2)
        n, = struct.unpack_from('<i', mt, 0)
        offs = struct.unpack_from('<%di' % n, mt, 4)
        self.tex = []
        for o in offs:
            if o < 0:
                self.tex.append(None)
                continue
            name, w, h, o0, *_ = struct.unpack_from('<16sII4I', mt, o)
            name = name.split(b'\0')[0].decode()
            if w == 0 or o0 == 0:
                self.tex.append((name, None))
                continue
            data = np.frombuffer(mt[o + o0:o + o0 + w * h], np.uint8).reshape(h, w)
            self.tex.append((name, data))


def render(bsp, cam, yaw, pitch, fov=95, W=960, H=540):
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    fwd = np.array([cy * cp, sy * cp, -sp])
    right = np.array([sy, -cy, 0.0])
    up = np.cross(right, fwd)
    f = (W / 2) / math.tan(math.radians(fov) / 2)
    cam = np.array(cam, np.float64)
    zbuf = np.full((H, W), np.inf)
    img = np.zeros((H, W, 3), np.float32)
    px, py = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    # ray direction per pixel (world)
    dx = (px - W / 2) / f
    dy = -(py - H / 2) / f
    rays = fwd[None, None, :] + dx[..., None] * right[None, None, :] + dy[..., None] * up[None, None, :]

    for fi, (pn, side, fe, ne, tinf, s0, s1, s2, s3, lofs) in enumerate(bsp.faces):
        idx = []
        for k in range(ne):
            e = bsp.surfedges[fe + k]
            idx.append(bsp.edges[e][0] if e >= 0 else bsp.edges[-e][1])
        poly = bsp.verts[idx]
        nx, ny, nz, dist, _ = bsp.planes[pn]
        n = np.array([nx, ny, nz])
        if side:
            n, dist = -n, -dist
        if np.dot(n, cam) - dist <= 0.01:
            continue  # back face
        rel = poly - cam
        cz = rel @ fwd
        cx = rel @ right
        cyv = rel @ up
        # clip to near plane
        pts = list(zip(cx, cyv, cz))
        clipped = []
        near = 1.0
        for a, bpt in zip(pts, pts[1:] + pts[:1]):
            ain, bin_ = a[2] > near, bpt[2] > near
            if ain:
                clipped.append(a)
            if ain != bin_:
                t = (near - a[2]) / (bpt[2] - a[2])
                clipped.append(tuple(a[i] + (bpt[i] - a[i]) * t for i in range(3)))
        if len(clipped) < 3:
            continue
        sx = np.array([W / 2 + f * p[0] / p[2] for p in clipped])
        syy = np.array([H / 2 - f * p[1] / p[2] for p in clipped])
        x0, x1 = max(0, int(sx.min())), min(W, int(math.ceil(sx.max())) + 1)
        y0, y1 = max(0, int(syy.min())), min(H, int(math.ceil(syy.max())) + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        # inside test for convex polygon (either winding)
        X = px[y0:y1, x0:x1]
        Y = py[y0:y1, x0:x1]
        sgn = None
        inside = np.ones(X.shape, bool)
        m = len(sx)
        area = sum(sx[i] * syy[(i + 1) % m] - sx[(i + 1) % m] * syy[i] for i in range(m))
        s_ = 1 if area > 0 else -1
        for i in range(m):
            ax_, ay_, bx_, by_ = sx[i], syy[i], sx[(i + 1) % m], syy[(i + 1) % m]
            inside &= s_ * ((bx_ - ax_) * (Y - ay_) - (by_ - ay_) * (X - ax_)) >= -0.5
        if not inside.any():
            continue
        R = rays[y0:y1, x0:x1]
        denom = R @ n
        t = (dist - np.dot(n, cam)) / np.where(np.abs(denom) < 1e-9, 1e-9, denom)
        zb = zbuf[y0:y1, x0:x1]
        ok = inside & (t > 0) & (t < zb)
        if not ok.any():
            continue
        P = cam[None, None, :] + R * t[..., None]
        vs = bsp.texinfo[tinf]
        sv, tv = np.array(vs[0:3]), np.array(vs[4:7])
        S = P @ sv + vs[3]
        T = P @ tv + vs[7]
        name, tex = bsp.tex[vs[8]]
        if tex is None:
            col = np.full(S.shape + (3,), 128.0)
            idxs = np.zeros(S.shape, np.uint8)
        else:
            h, w = tex.shape
            idxs = tex[np.floor(T).astype(int) % h, np.floor(S).astype(int) % w]
            col = PAL[idxs]
        if name.startswith('sky'):
            shade = np.full(S.shape, 1.0)
        elif lofs >= 0 and s0 != 255:
            ps = poly @ sv + vs[3]
            pt = poly @ tv + vs[7]
            ms, mt_ = math.floor(ps.min() / 16), math.floor(pt.min() / 16)
            lw = math.ceil(ps.max() / 16) - ms + 1
            lh = math.ceil(pt.max() / 16) - mt_ + 1
            lm = bsp.light[lofs:lofs + lw * lh].reshape(lh, lw).astype(np.float32)
            u = np.clip(S / 16 - ms, 0, lw - 1)
            v = np.clip(T / 16 - mt_, 0, lh - 1)
            u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
            u1, v1 = np.minimum(u0 + 1, lw - 1), np.minimum(v0 + 1, lh - 1)
            fu, fv = u - u0, v - v0
            l = (lm[v0, u0] * (1 - fu) * (1 - fv) + lm[v0, u1] * fu * (1 - fv) +
                 lm[v1, u0] * (1 - fu) * fv + lm[v1, u1] * fu * fv)
            shade = l / 128.0
        else:
            shade = np.full(S.shape, 0.0)      # no lightmap = unlit (engine draws it black)
        shade = np.where(idxs >= 224, 1.0, shade)
        out = np.clip(col * shade[..., None], 0, 255)
        sub = img[y0:y1, x0:x1]
        sub[ok] = out[ok]
        zb[ok] = t[ok]
    return Image.fromarray(img.astype(np.uint8))


if __name__ == '__main__':
    bsp = BSP(sys.argv[1])
    x, y, z, yaw, pitch = map(float, sys.argv[3:8])
    fov = float(sys.argv[8]) if len(sys.argv) > 8 else 95
    render(bsp, (x, y, z), yaw, pitch, fov).save(sys.argv[2])
