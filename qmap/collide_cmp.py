"""Prove a visual-only build did not change collision: compare the SOLID space of two generated
.map files on an 8-unit voxel grid. Counts axis-aligned brushes in worldspawn and func_group
(func_detail_illusionary fixtures, triggers and lights are not solid). Bounds are read from the maps.
Usage: python3 collide_cmp.py old.map new.map"""
import re
import sys

import numpy as np


def entities(txt):
    out, depth, start = [], 0, 0
    for k, ch in enumerate(txt):
        if ch == '{':
            if depth == 0:
                start = k
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                out.append(txt[start:k + 1])
    return out


def boxes(path):
    out = []
    for e in entities(open(path).read()):
        m = re.search(r'"classname" "([^"]+)"', e)
        if not m or m.group(1) not in ('worldspawn', 'func_group'):
            continue
        for br in re.findall(r'\{\n(\(.*?)\n\}', e, re.S):
            faces = br.split('\n')
            a = [int(v) for v in re.findall(r'-?\d+', faces[0])[:3]]
            b = [int(v) for v in re.findall(r'-?\d+', faces[3])[:3]]
            out.append((*a, *b))
    return out


A, B = boxes(sys.argv[1]), boxes(sys.argv[2])
allb = np.array(A + B)
lo = allb[:, :3].min(0) // 8 * 8
hi = -(-allb[:, 3:].max(0) // 8) * 8
shape = tuple(((hi - lo) // 8).astype(int))


def vox(bs):
    g = np.zeros(shape, bool)
    for x1, y1, z1, x2, y2, z2 in bs:
        g[(x1 - lo[0]) // 8:(x2 - lo[0]) // 8, (y1 - lo[1]) // 8:(y2 - lo[1]) // 8, (z1 - lo[2]) // 8:(z2 - lo[2]) // 8] = True
    return g


diff = vox(A) ^ vox(B)
print(f'{sys.argv[1]}: {len(A)} solid brushes, {sys.argv[2]}: {len(B)} solid brushes')
if diff.any():
    idx = np.argwhere(diff)
    print(f'COLLISION DIFFERS: {len(idx)} voxels, e.g.', [tuple(int(v) for v in lo + k * 8) for k in idx[:5]])
    sys.exit(1)
print('collision identical (solid space matches voxel for voxel)')
