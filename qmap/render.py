"""Tiny BSP29 preview renderer: textures + compiled lightmaps, z-buffered.
Usage: python3 render.py map.bsp out.png x y z yaw pitch [fov]
Companion QLIT RGB lighting is loaded automatically. See RENDERING.md for client settings."""
import argparse
import os
import math
from pathlib import Path
import re
import struct
import sys
import warnings

import numpy as np
from PIL import Image

PAL = np.frombuffer(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'quake_palette.lmp'), 'rb').read(), np.uint8).reshape(256, 3).astype(np.float32)


class BSP:
    def __init__(self, path, *, use_lit=True):
        self.path = Path(path)
        b = self.path.read_bytes()
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
        self.light_rgb = load_lit(self.path.with_suffix('.lit'), len(self.light)) if use_lit else None
        self.lighting = 'RGB .lit' if self.light_rgb is not None else 'BSP monochrome'
        self.nodes = [struct.unpack_from('<i2h', lump(5), offset)
                      for offset in range(0, len(lump(5)), 24)]
        self.leaves = [struct.unpack_from('<i', lump(10), offset)[0]
                       for offset in range(0, len(lump(10)), 28)]
        self.models = [struct.unpack_from('<9f7i', lump(14), offset)
                       for offset in range(0, len(lump(14)), 64)]
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
        # v3.3: trigger brushes (teleports, pushes) are invisible in game - don't draw them
        ents = lump(0).decode('latin1')
        md = lump(14)
        self.hidden = set()
        self.hidden_models = set()
        for blk in re.findall(r'\{([^}]*)\}', ents):
            kv = dict(re.findall(r'"([^"]*)"\s*"([^"]*)"', blk))
            m = kv.get('model', '')
            if kv.get('classname', '').startswith('trigger') and m.startswith('*'):
                ff, nf = struct.unpack_from('<ii', md, int(m[1:]) * 64 + 56)
                self.hidden.update(range(ff, ff + nf))
                self.hidden_models.add(int(m[1:]))

    def face_vertices(self, face):
        first, count = face[2:4]
        return self.verts[[self.edges[edge][0] if edge >= 0 else self.edges[-edge][1]
                           for edge in self.surfedges[first:first + count]]]

    def contents_at(self, point, model=0):
        node = self.models[model][9]
        for _ in range(len(self.nodes) + 1):
            if node < 0:
                return self.leaves[-node - 1]
            plane, front, back = self.nodes[node]
            normal = self.planes[plane][:3]
            node = front if np.dot(point, normal) >= self.planes[plane][3] else back
        raise ValueError(f'{self.path}: cyclic BSP node tree')


def load_lit(path, sample_count):
    """Read QLIT v1; reject mismatched companions instead of misaddressing samples."""
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        warnings.warn(f'{path}: cannot read .lit ({error}); using BSP monochrome', stacklevel=2)
        return None
    reason = None
    if len(data) < 8 or data[:4] != b'QLIT':
        reason = 'invalid QLIT header'
    elif struct.unpack_from('<I', data, 4)[0] != 1:
        reason = 'unsupported QLIT version (expected 1)'
    elif len(data) != 8 + 3 * sample_count:
        reason = f'incorrect size (expected {8 + 3 * sample_count} bytes, got {len(data)})'
    if reason:
        warnings.warn(f'{path}: {reason}; using BSP monochrome', stacklevel=2)
        return None
    return np.frombuffer(data, np.uint8, offset=8).reshape(-1, 3)


def light_samples(bsp, lightmode=1):
    """ezQuake gl_oldlitscaling=0 normalization, before filtering or style scaling."""
    mono = bsp.light.astype(np.float64)
    if bsp.light_rgb is None:
        return np.repeat(mono[:, None], 3, axis=1)
    samples = bsp.light_rgb.astype(np.float64)
    brightness = np.sqrt(samples ** 2 @ [0.241, 0.691, 0.068])
    samples *= (mono / np.where(brightness > 0, brightness, 1))[:, None]
    maximum = samples.max(axis=1)
    threshold = 170 if lightmode else 128
    samples *= np.minimum(1, threshold / np.maximum(maximum, 1))[:, None]
    samples = np.floor(samples + 0.5)
    samples[brightness == 0] = mono[brightness == 0, None]
    return samples


def build_lightmap(samples, offset, width, height, styles, lightmode=1, modulate=1):
    """Combine stored styles at normal 'm' intensity and clamp before interpolation."""
    count = next((index for index, style in enumerate(styles) if style == 255), len(styles))
    size = width * height
    end = offset + count * size
    if offset < 0 or end > len(samples):
        raise ValueError(f'lightmap samples {offset}:{end} exceed lighting lump ({len(samples)})')
    lightmap = samples[offset:end].reshape(count, height, width, 3).sum(axis=0)
    scale = int((384 if lightmode else 512) * modulate)
    fixed = lightmap.astype(np.int64) * 264 * scale
    maximum = fixed.max(axis=2, keepdims=True)
    limit = (255 << 16) + (1 << 15)
    rescale = (limit << 8) // np.maximum(maximum, 1)
    fixed = np.where(maximum > limit, (fixed >> 8) * rescale, fixed)
    return (fixed >> 16).astype(np.float64) / 255


def liquid_uv(points, texinfo, width=64, height=64):
    """Unwarped EmitWaterPolys projection: axes retained, shifts ignored, 64u repeat."""
    return points @ np.asarray(texinfo[:3]) * (width / 64), points @ np.asarray(texinfo[4:7]) * (height / 64)


def camera_basis(yaw, pitch):
    cosine_yaw, sine_yaw = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cosine_pitch, sine_pitch = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    forward = np.array([cosine_yaw * cosine_pitch, sine_yaw * cosine_pitch, -sine_pitch])
    right = np.array([sine_yaw, -cosine_yaw, 0.0])
    return forward, right, np.cross(right, forward)


def validate_camera(cam, yaw, pitch, fov, width, height, near):
    if np.shape(cam) != (3,) or not np.isfinite([*cam, yaw, pitch, fov, near]).all():
        raise ValueError('camera position and angles must be finite numbers')
    if not 0 < fov < 180 or near <= 0 or width <= 0 or height <= 0:
        raise ValueError('require 0 < fov < 180 and positive near clip, width, and height')


def clip_polygon(polygon, normal, distance):
    clipped = []
    for start, end in zip(polygon, np.roll(polygon, -1, axis=0)):
        start_dist = np.dot(start, normal) - distance
        end_dist = np.dot(end, normal) - distance
        if start_dist >= 0:
            clipped.append(start)
        if (start_dist >= 0) != (end_dist >= 0):
            clipped.append(start + (end - start) * start_dist / (start_dist - end_dist))
    return np.asarray(clipped)


def check_camera(bsp, cam, yaw, pitch, fov=95, W=960, H=540, near=2):
    """Check hull-0 contents and every visible face in the eye-to-near-plane frustum."""
    validate_camera(cam, yaw, pitch, fov, W, H, near)
    camera = np.asarray(cam, np.float64)
    issues = []
    if not bsp.models or not bsp.leaves:
        issues.append('camera contents unavailable (missing BSP models/leaves)')
    for model_index in range(len(bsp.models)):
        if model_index in bsp.hidden_models:
            continue
        contents = bsp.contents_at(camera, model_index)
        if contents in (-2, -6):
            contents_name = 'solid' if contents == -2 else 'sky'
            issues.append(f'camera inside {contents_name} (model *{model_index}, eye {tuple(cam)})')
    forward, right, up = camera_basis(yaw, pitch)
    horizontal = math.tan(math.radians(fov) / 2)
    vertical = horizontal * H / W
    bounds = [((0, 0, 1), 0), ((0, 0, -1), -near),
              ((1, 0, horizontal), 0), ((-1, 0, horizontal), 0),
              ((0, 1, vertical), 0), ((0, -1, vertical), 0)]
    for face_index, face in enumerate(bsp.faces):
        if face_index in bsp.hidden:
            continue
        relative = bsp.face_vertices(face) - camera
        polygon = np.column_stack((relative @ right, relative @ up, relative @ forward))
        if polygon[:, 2].min() > near or polygon[:, 2].max() < 0:
            continue
        for normal, distance in bounds:
            polygon = clip_polygon(polygon, normal, distance)
            if len(polygon) < 3:
                break
        if len(polygon) >= 3:
            area = np.linalg.norm(np.sum(np.cross(polygon, np.roll(polygon, -1, axis=0)), axis=0))
            if area > 1e-8:
                issues.append(f'near-clip obstruction (face {face_index}, within {near:g}u of eye)')
                break
    return issues


def report_camera(issues, label, strict=False):
    if issues:
        message = f'UNSAFE CAMERA {label}: ' + '; '.join(issues)
        if strict:
            raise ValueError(message)
        print(f'WARNING: {message}', file=sys.stderr)


def render(bsp, cam, yaw, pitch, fov=95, W=960, H=540, *, gamma=1, contrast=1,
           lightmode=1, modulate=1, near=2, camera_check='warn'):
    validate_camera(cam, yaw, pitch, fov, W, H, near)
    if not np.isfinite([gamma, contrast, modulate]).all() or gamma <= 0 or contrast <= 0 or not 0.5 <= modulate <= 3:
        raise ValueError('require positive finite gamma/contrast and 0.5 <= modulate <= 3')
    if camera_check not in ('warn', 'error', 'off'):
        raise ValueError('camera_check must be warn, error, or off')
    if camera_check != 'off':
        report_camera(check_camera(bsp, cam, yaw, pitch, fov, W, H, near), str(bsp.path), camera_check == 'error')
    samples = light_samples(bsp, lightmode)
    palette = np.floor(np.minimum(PAL * (4 / 3 if lightmode else 1), 255))
    fwd, right, up = camera_basis(yaw, pitch)
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
        if fi in getattr(bsp, 'hidden', ()):
            continue
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
        ok = inside & (t >= near) & (t < zb)
        if not ok.any():
            continue
        P = cam[None, None, :] + R * t[..., None]
        vs = bsp.texinfo[tinf]
        sv, tv = np.array(vs[0:3]), np.array(vs[4:7])
        S = P @ sv + vs[3]
        T = P @ tv + vs[7]
        name, tex = bsp.tex[vs[8]] or ('missing', None)
        liquid = name.startswith('*')
        if tex is None:
            col = np.full(S.shape + (3,), 128.0)
            idxs = np.zeros(S.shape, np.uint8)
        else:
            h, w = tex.shape
            texture_s, texture_t = liquid_uv(P, vs, w, h) if liquid else (S, T)
            idxs = tex[np.floor(texture_t).astype(int) % h, np.floor(texture_s).astype(int) % w]
            col = PAL[idxs] if liquid or name.startswith('sky') else palette[idxs]
        if name.startswith('sky'):
            shade = np.ones(S.shape + (3,))
        elif lofs >= 0 and s0 != 255:
            ps = poly @ sv + vs[3]
            pt = poly @ tv + vs[7]
            ms, mt_ = math.floor(ps.min() / 16), math.floor(pt.min() / 16)
            lw = math.ceil(ps.max() / 16) - ms + 1
            lh = math.ceil(pt.max() / 16) - mt_ + 1
            lm = build_lightmap(samples, lofs, lw, lh, (s0, s1, s2, s3), lightmode, modulate)
            u = np.clip(S / 16 - ms, 0, lw - 1)
            v = np.clip(T / 16 - mt_, 0, lh - 1)
            u0, v0 = np.floor(u).astype(int), np.floor(v).astype(int)
            u1, v1 = np.minimum(u0 + 1, lw - 1), np.minimum(v0 + 1, lh - 1)
            fu, fv = (u - u0)[..., None], (v - v0)[..., None]
            l = (lm[v0, u0] * (1 - fu) * (1 - fv) + lm[v0, u1] * fu * (1 - fv) +
                 lm[v1, u0] * (1 - fu) * fv + lm[v1, u1] * fu * fv)
            shade = l
        else:
            shade = np.full(S.shape + (3,), 1.0 if liquid or not len(bsp.light) else 0.0)
        out = col * shade
        if not liquid:
            out = np.where((idxs >= 224)[..., None], PAL[idxs], out)
        out = np.clip(out, 0, 255)
        sub = img[y0:y1, x0:x1]
        sub[ok] = out[ok]
        zb[ok] = t[ok]
    corrected = 255 * np.clip(img / 255 * contrast, 0, 1) ** gamma
    return Image.fromarray(corrected.astype(np.uint8))


def add_render_arguments(parser):
    parser.add_argument('--gamma', type=float, default=1, help='ezQuake gl_gamma exponent (default: 1)')
    parser.add_argument('--contrast', type=float, default=1, help='contrast before gamma (default: 1)')
    parser.add_argument('--lightmode', type=int, choices=(0, 1, 2), default=1, help='ezQuake gl_lightmode; 1 and 2 are equivalent')
    parser.add_argument('--modulate', type=float, default=1, help='ezQuake gl_modulate, 0.5 to 3')
    parser.add_argument('--near', type=float, default=2, help='near clipping distance in world units')
    parser.add_argument('--no-lit', action='store_true', help='ignore companion RGB lighting')
    parser.add_argument('--strict-cameras', action='store_true', help='fail instead of saving an unsafe camera')


def render_options(args):
    return {name: getattr(args, name) for name in ('gamma', 'contrast', 'lightmode', 'modulate', 'near')}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bsp')
    parser.add_argument('out')
    for name in ('x', 'y', 'z', 'yaw', 'pitch'):
        parser.add_argument(name, type=float)
    parser.add_argument('fov', type=float, nargs='?', default=95)
    parser.add_argument('--width', type=int, default=960)
    parser.add_argument('--height', type=int, default=540)
    add_render_arguments(parser)
    args = parser.parse_args(argv)
    try:
        bsp = BSP(args.bsp, use_lit=not args.no_lit)
        render(bsp, (args.x, args.y, args.z), args.yaw, args.pitch, args.fov, args.width, args.height,
               camera_check='error' if args.strict_cameras else 'warn', **render_options(args)).save(args.out)
    except (OSError, ValueError) as error:
        parser.exit(2, f'{error}\n')
    print(f'{args.out}: {bsp.lighting}; gamma={args.gamma:g}, contrast={args.contrast:g}, lightmode={args.lightmode}')


if __name__ == '__main__':
    main()
