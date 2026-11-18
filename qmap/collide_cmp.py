"""Compare the solid space of two generated .map files (axis-aligned brushes) on an 8-unit voxel grid."""
import re, sys
import numpy as np
XMIN, YMIN, BOT = -2432, -960, -256
def vox(path):
    txt = open(path).read()
    world = txt                                    # all brushes (world + func_group)
    g = np.zeros((4864 // 8, 1920 // 8, 1024 // 8), bool)
    n = 0
    for br in re.findall(r'\{\n(\(.*?)\n\}', world, re.S):
        faces = br.split('\n')
        p1 = [int(v) for v in re.findall(r'-?\d+', faces[0])[:3]]
        p4 = [int(v) for v in re.findall(r'-?\d+', faces[3])[:3]]
        (x1, y1, z1), (x2, y2, z2) = p1, p4
        g[(x1 - XMIN) // 8:(x2 - XMIN) // 8, (y1 - YMIN) // 8:(y2 - YMIN) // 8, (z1 - BOT) // 8:(z2 - BOT) // 8] = True
        n += 1
    return g, n
a, na = vox(sys.argv[1]); b, nb = vox(sys.argv[2])
diff = a ^ b
print(f'{sys.argv[1]}: {na} brushes, {sys.argv[2]}: {nb} brushes')
print('solid voxels:', a.sum(), b.sum(), '| differing voxels:', diff.sum())
