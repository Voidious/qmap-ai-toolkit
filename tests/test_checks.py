"""Regression tests for qmap/check.py and qmap/vprofile.py layout checks (CDEFG-21).

Run from the repository root:
    python3 -m unittest discover -s tests
"""
import importlib.util
import json
import math
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
QMAP_DIR = REPO_ROOT / 'qmap'
if str(QMAP_DIR) not in sys.path:
    sys.path.insert(0, str(QMAP_DIR))

import check  # noqa: E402

HAS_NUMBA = importlib.util.find_spec('numba') is not None
if HAS_NUMBA:
    import numpy as np  # noqa: E402
    import vprofile  # noqa: E402


# ------------------------------------------------------------------ synthetic map builder for check.py
class MiniGrid:
    """Minimal replica of template/_core.py's column grid for self-contained unit tests."""

    def __init__(self, xmin=-512, xmax=512, ymin=-512, ymax=512, bot=-128, top=384, c=16):
        self.C = c
        self.XMIN, self.XMAX = xmin, xmax
        self.YMIN, self.YMAX = ymin, ymax
        self.BOT, self.TOP = bot, top
        self.NX = (xmax - xmin) // c
        self.NY = (ymax - ymin) // c
        self.cols = [[[[bot, top, None]] for _ in range(self.NY)] for _ in range(self.NX)]
        self.spawns = []
        self.items = []
        self.prisms = []
        self.teleports = []
        self.pushes = []
        self.feet = []
        self.perches = []

    @staticmethod
    def _sub(col, z0, z1):
        out = []
        for a, b, m in col:
            if b <= z0 or a >= z1:
                out.append([a, b, m])
                continue
            if a < z0:
                out.append([a, z0, m])
            if b > z1:
                out.append([z1, b, m])
        return out

    def _cells(self, r):
        x0, y0, x1, y1 = r
        for i in range((x0 - self.XMIN) // self.C, (x1 - self.XMIN) // self.C):
            for j in range((y0 - self.YMIN) // self.C, (y1 - self.YMIN) // self.C):
                yield i, j

    def carve(self, r, z0, z1):
        for i, j in self._cells(r):
            self.cols[i][j] = self._sub(self.cols[i][j], z0, z1)

    def fill(self, r, z0, z1, mat=None):
        for i, j in self._cells(r):
            col = self._sub(self.cols[i][j], z0, z1)
            col.append([z0, z1, mat])
            col.sort()
            self.cols[i][j] = col

    def prism(self, pts, z0, z1, kind=None):
        pts = [tuple(p) for p in pts]
        self.prisms.append([pts, z0, z1, kind])
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        C, XMIN, YMIN = self.C, self.XMIN, self.YMIN
        for i in range(max(0, int((min(xs) - XMIN) // C)), min(self.NX, int((max(xs) - XMIN) // C) + 1)):
            for j in range(max(0, int((min(ys) - YMIN) // C)), min(self.NY, int((max(ys) - YMIN) // C) + 1)):
                x, y = XMIN + i * C, YMIN + j * C
                box = [(x, y), (x + C, y), (x + C, y + C), (x, y + C)]
                if kind not in (None, 'ledge') and all(check.poly_pt_dist(pts, u, v) == 0.0 for u, v in box):
                    m = kind
                elif check.poly_poly_dist(pts, box) == 0.0 and check.poly_clip_area(pts, box) > 0.5:
                    m = 'diag'
                else:
                    continue
                col, z = self.cols[i][j], z0
                for a, b, _m in sorted(col):
                    if b <= z or a >= z1:
                        continue
                    if a > z:
                        col.append([z, a, m])
                    z = max(z, b)
                if z < z1:
                    col.append([z, z1, m])
                col.sort()

    def octagon(self, cx, cy, r=64, z0=None, z1=None, kind='pillar'):
        z0 = self.BOT if z0 is None else z0
        z1 = self.TOP if z1 is None else z1
        pts = [
            (round(cx + r * math.cos(math.radians(22.5 + 45 * k))),
             round(cy + r * math.sin(math.radians(22.5 + 45 * k))))
            for k in range(8)
        ]
        self.prism(pts, z0, z1, kind=kind)

    def chamfer(self, r, corner, size, z0, z1):
        x = r[2] if 'e' in corner else r[0]
        y = r[3] if 'n' in corner else r[1]
        sx = -1 if 'e' in corner else 1
        sy = -1 if 'n' in corner else 1
        tri = [(x, y), (x + sx * size, y), (x, y + sy * size)]
        if sx * sy < 0:
            tri = tri[::-1]
        self.prism(tri, z0, z1, kind=None)

    def spawn(self, x, y, z, label='s'):
        self.spawns.append([x, y, z, 0, label])

    def item(self, cls, x, y, z, label='it'):
        self.items.append([cls, x, y, z, 0, label])

    def to_dict(self):
        return {
            'C': self.C, 'XMIN': self.XMIN, 'YMIN': self.YMIN,
            'NX': self.NX, 'NY': self.NY, 'BOT': self.BOT, 'TOP': self.TOP,
            'cols': self.cols, 'spawns': self.spawns, 'items': self.items,
            'prisms': self.prisms, 'teleports': self.teleports, 'pushes': self.pushes,
            'feet': self.feet, 'perches': self.perches, 'team_spawns': [],
        }


class TestCheckDocstring(unittest.TestCase):
    def test_docstring_describes_traps_and_pockets_accurately(self):
        doc = (check.__doc__ or '').lower()
        self.assertIn('trap', doc)
        self.assertIn('pocket', doc)
        self.assertIn('prism', doc)


class TestPrismSeparation(unittest.TestCase):
    def _arena(self):
        g = MiniGrid(-512, 512, -512, 512)
        g.carve((-384, -384, 384, 384), 0, 256)
        g.spawn(-256, -256, 0, 's1')
        g.spawn(256, 256, 0, 's2')
        return g

    def test_well_separated_pillars_and_chamfers_pass(self):
        g = self._arena()
        g.octagon(-96, 0, r=48)   # >= 144 from walls, >= 96 from other pillar
        g.octagon(96, 0, r=48)
        g.chamfer((-384, -384, 384, 384), 'nw', 96, 0, 256)
        g.chamfer((-384, -384, 384, 384), 'ne', 96, 0, 256)
        g.prism([(-384, -64), (384, -64), (384, 64), (-384, 64)], 96, 128, kind='bridge')
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertEqual(res['prism_separation'], [])

    def test_overlapping_and_close_pillars_fail(self):
        g = self._arena()
        g.octagon(0, 0, r=64)
        g.octagon(48, 112, r=64)   # overlaps (centre dist 121.8 < 2*64)
        g.octagon(48, 240, r=64)   # 10u from (48, 112)
        res = check.check_map(g.to_dict(), quiet=True)
        probs = res['prism_separation']
        self.assertTrue(any('prism #0' in p and 'prism #1' in p and 'dist 0.0' in p for p in probs), probs)
        self.assertTrue(any('prism #1' in p and 'prism #2' in p and 'dist 10.0' in p for p in probs), probs)

    def test_pillar_sealing_hall_mouth_fails(self):
        # Reproduce ca_mesas_b1 hall mouth: 128-wide hall opening into room, r64 pillar 5u off wall
        g = MiniGrid(-640, 512, -512, 512)
        g.carve((-384, -384, 384, 384), 0, 256)
        g.carve((-576, -64, -384, 64), 0, 256)  # 128-wide hall ending at x = -384
        g.octagon(-320, 0, r=64)                # spans x=-379..-261, 5u from x=-384
        g.spawn(256, 256, 0, 's1')
        g.spawn(256, -256, 0, 's2')
        res = check.check_map(g.to_dict(), quiet=True)
        probs = res['prism_separation']
        self.assertEqual(len(probs), 1, probs)
        self.assertIn('wall', probs[0])
        self.assertIn('31.8', probs[0])

    def test_pillar_overlapping_step_wall_fails(self):
        g = MiniGrid(-512, 512, -512, 512)
        g.carve((-384, -384, 384, 0), 0, 256)    # lower shelf z=0
        g.carve((-384, 0, 384, 384), 128, 384)   # upper mesa z=128 (cliff wall at y=0)
        g.octagon(0, 48, r=64)                   # reaches y=-11, overlapping y=0 cliff wall!
        g.spawn(-256, 256, 128, 's1')
        g.spawn(256, 256, 128, 's2')
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertTrue(any('dist 0.0' in p and 'z=0' in p for p in res['prism_separation']), res['prism_separation'])

    def test_pillar_too_close_to_fill_crate_fails(self):
        g = self._arena()
        g.fill((64, -64, 192, 64), 0, 128, 'crate')
        g.octagon(-32, 0, r=64)  # x=-91..27 -> 37u from crate at x=64
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertTrue(any('crate' in p and '37.0' in p for p in res['prism_separation']), res['prism_separation'])

    def test_chamfer_leaving_narrow_gap_to_unattached_wall_fails(self):
        g = self._arena()
        g.chamfer((-384, -384, 384, 384), 'nw', 128, 0, 256)  # ends at x=-256, y=384
        g.fill((-224, 256, -160, 384), 0, 128, 'crate')       # 32u east of chamfer vertex
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertTrue(any('crate' in p and '32.0' in p for p in res['prism_separation']), res['prism_separation'])

    def test_custom_min_prism_sep_threshold(self):
        g = self._arena()
        g.octagon(-256, 0, r=48)  # x=-300..-212 -> 84u from west wall x=-384
        res64 = check.check_map(g.to_dict(), min_prism_sep=64, quiet=True)
        res96 = check.check_map(g.to_dict(), min_prism_sep=96, quiet=True)
        self.assertEqual(res64['prism_separation'], [])
        self.assertEqual(len(res96['prism_separation']), 1)


class TestBlindPockets(unittest.TestCase):
    def _arena_with_corridor(self, length=320, width=128):
        g = MiniGrid(-512, 768, -512, 512)
        g.carve((-384, -384, 256, 384), 0, 256)
        half = width // 2
        g.carve((256, -half, 256 + length, half), 0, 256)
        g.spawn(-256, -256, 0, 's1')
        g.spawn(-256, 256, 0, 's2')
        return g

    def test_deep_empty_corridor_fails(self):
        g = self._arena_with_corridor(length=320, width=128)
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertEqual(len(res['pockets']), 1, res['pockets'])
        pk = res['pockets'][0]
        self.assertGreater(pk['depth'], pk['width'])
        self.assertEqual(pk['width'], 128)
        self.assertGreaterEqual(pk['depth'], 304)

    def test_shallow_empty_alcove_passes(self):
        g = self._arena_with_corridor(length=96, width=128)
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertEqual(res['pockets'], [])

    def test_deep_corridor_with_item_at_far_end_passes(self):
        g = self._arena_with_corridor(length=320, width=128)
        g.item('weapon_supernailgun', 512, 0, 0, 'SNG')
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertEqual(res['pockets'], [])

    def test_deep_corridor_with_spawn_at_mouth_flags_empty_tail(self):
        g = self._arena_with_corridor(length=320, width=128)
        g.spawn(304, 0, 0, 'mouth')  # 272u of empty corridor left past spawn!
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertEqual(len(res['pockets']), 1)
        self.assertGreater(res['pockets'][0]['depth'], 128)

    def test_corridor_connected_into_loop_passes(self):
        g = self._arena_with_corridor(length=320, width=128)
        # Add second arm back to the main room -> loop, not a pocket
        g.carve((448, 64, 576, 320), 0, 256)
        g.carve((256, 192, 448, 320), 0, 256)
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertEqual(res['pockets'], [])

    def test_corridor_with_teleporter_exit_passes(self):
        g = self._arena_with_corridor(length=320, width=128)
        g.teleports.append([(512, -32, 576, 32), 0, 0, 0, 0, 0])
        res = check.check_map(g.to_dict(), quiet=True)
        self.assertEqual(res['pockets'], [])

    def test_cli_reports_prism_and_pocket_problems(self):
        g = self._arena_with_corridor(length=320, width=128)
        g.octagon(0, 0, r=64)
        g.octagon(48, 112, r=64)
        with tempfile.TemporaryDirectory() as td:
            jp = pathlib.Path(td) / 'test.json'
            jp.write_text(json.dumps(g.to_dict()), encoding='utf-8')
            proc = subprocess.run(
                [sys.executable, str(QMAP_DIR / 'check.py'), str(jp), '--min-prism-sep', '64'],
                capture_output=True, text=True, check=True,
            )
        self.assertIn('prism separation (< 64): 1 PROBLEMS', proc.stdout)
        self.assertIn('BLIND POCKETS: 1', proc.stdout)

    def test_exec_compat_for_contact_sightlines_and_routes(self):
        # contact.py, sightlines.py, routes.py, and pick_spawns*.py load check.py via exec()
        # and rely on its module-level globals (spawns, snodes, nodes, C, XMIN, bfs, etc.).
        g = self._arena_with_corridor(length=96, width=128)
        with tempfile.TemporaryDirectory() as td:
            jp = pathlib.Path(td) / 'test.json'
            jp.write_text(json.dumps(g.to_dict()), encoding='utf-8')
            for script, extra in (
                ('contact.py', []),
                ('sightlines.py', []),
                ('routes.py', ['--from', '-256,-256,0', '--to', '-256,256,0']),
            ):
                proc = subprocess.run(
                    [sys.executable, str(QMAP_DIR / script), str(jp), *extra],
                    capture_output=True, text=True, check=True,
                )
                self.assertTrue(proc.stdout.strip(), f'{script} produced no output')


# ------------------------------------------------------------------ synthetic clipnode tests for vprofile.py
def _build_convex_room_clipnodes(planes):
    """Build a clipnode tree for a convex empty room bounded by inward-pointing half-spaces
    (nx, ny, nz, d) where n . p >= d is INSIDE (empty) and n . p < d is OUTSIDE (solid)."""
    pn = np.array([[nx, ny, nz] for nx, ny, nz, _ in planes], dtype=np.float64)
    pd = np.array([d for _, _, _, d in planes], dtype=np.float64)
    k = len(planes)
    cplane = np.arange(k, dtype=np.int64)
    cchild = np.zeros((k, 2), dtype=np.int64)
    for i in range(k):
        cchild[i, 0] = (i + 1) if i + 1 < k else -1   # front (>= 0): inside empty
        cchild[i, 1] = -2                            # back (< 0): solid
    return np.array([0], dtype=np.int64), cplane, cchild, pn, pd


@unittest.skipUnless(HAS_NUMBA, 'numba required for vprofile tests')
class TestVprofilePassageWidth(unittest.TestCase):
    def test_narrow_axial_corridor_detected_and_64_passes(self):
        # 48-wide physical axial corridor in X: real walls at x=0 and x=48 -> hull-1 planes at x=16, x=32
        # Inward normals: (+1, 0, 0) d=16 and (-1, 0, 0) d=-32; floor z >= 24, ceiling z <= 200
        roots, cp, cc, pn, pd = _build_convex_room_clipnodes([
            (1, 0, 0, 16), (-1, 0, 0, -32),
            (0, 1, 0, -200), (0, -1, 0, -200),
            (0, 0, 1, 24), (0, 0, -1, -200),
        ])
        xs = np.array([24.0])
        ys = np.array([0.0])
        fs = np.array([0.0])
        # Threshold 64 -> max_spare = 31.5 -> spare=16 MUST be caught
        idx, spare, phys, h1, h2, n1, n2 = vprofile._scan_passages(roots, cp, cc, pn, pd, xs, ys, fs, 31.5)
        self.assertEqual(len(idx), 1)
        self.assertAlmostEqual(spare[0], 16.0, delta=0.2)
        self.assertAlmostEqual(phys[0], 48.0, delta=0.2)

        # 64-wide physical corridor: hull-1 planes at x=16 and x=48 -> spare=32
        roots2, cp2, cc2, pn2, pd2 = _build_convex_room_clipnodes([
            (1, 0, 0, 16), (-1, 0, 0, -48),
            (0, 1, 0, -200), (0, -1, 0, -200),
            (0, 0, 1, 24), (0, 0, -1, -200),
        ])
        xs2 = np.array([32.0])
        idx64, _, _, _, _, _, _ = vprofile._scan_passages(roots2, cp2, cc2, pn2, pd2, xs2, ys, fs, 31.5)
        self.assertEqual(len(idx64), 0)
        # Same 64-wide corridor caught when threshold raised to 88 (max_spare = 55.5)
        idx88, sp88, _, _, _, _, _ = vprofile._scan_passages(roots2, cp2, cc2, pn2, pd2, xs2, ys, fs, 55.5)
        self.assertEqual(len(idx88), 1)
        self.assertAlmostEqual(sp88[0], 32.0, delta=0.2)

    def test_open_90_degree_room_corner_not_flagged(self):
        # Huge 1000x1000 room; player standing tight in the SW corner (x=24, y=24, 8u from both hull-1 walls)
        roots, cp, cc, pn, pd = _build_convex_room_clipnodes([
            (1, 0, 0, 16), (-1, 0, 0, -1000),
            (0, 1, 0, 16), (0, -1, 0, -1000),
            (0, 0, 1, 24), (0, 0, -1, -200),
        ])
        xs = np.array([24.0, 20.0, 32.0])
        ys = np.array([24.0, 20.0, 24.0])
        fs = np.array([0.0, 0.0, 0.0])
        idx, _, _, _, _, _, _ = vprofile._scan_passages(roots, cp, cc, pn, pd, xs, ys, fs, 64.0)
        self.assertEqual(len(idx), 0)

    def test_diagonal_45_corridor_penalizes_axis_aligned_player_box(self):
        # 64-wide physical corridor at 45 degrees: +/-16 box expands each 45-deg plane by 16*sqrt(2) = 22.63
        # So hull-1 free width is 64 - 45.25 = 18.75 (< 31.5!), caught at min_passage=64!
        s = math.sqrt(0.5)
        half_hull1 = (64.0 - 32.0 * math.sqrt(2.0)) / 2.0  # ~9.37u each side of origin
        roots, cp, cc, pn, pd = _build_convex_room_clipnodes([
            (s, s, 0, -half_hull1), (-s, -s, 0, -half_hull1),
            (s, -s, 0, -200), (-s, s, 0, -200),
            (0, 0, 1, 24), (0, 0, -1, -200),
        ])
        xs = np.array([0.0])
        ys = np.array([0.0])
        fs = np.array([0.0])
        idx, spare, phys, _, _, _, _ = vprofile._scan_passages(roots, cp, cc, pn, pd, xs, ys, fs, 31.5)
        self.assertEqual(len(idx), 1)
        self.assertAlmostEqual(spare[0], 64.0 - 32.0 * math.sqrt(2.0), delta=0.3)
        self.assertAlmostEqual(phys[0], 64.0, delta=0.5)

    def test_bsp_pockets_detects_sealed_corridor_and_ignores_loop(self):
        class DummyBSP:
            ents = [{'classname': 'info_player_deathmatch', 'origin': '64 64 24'}]

        # Main 256x256 room (i=0..15, j=0..15) + 320-long 96-wide (6 hull-1 cells = 96 + 32 = 128u) blind hall
        nodes = []
        nid = {}
        for i in range(16):
            for j in range(16):
                nid[(i, j)] = len(nodes)
                nodes.append((i, j, 0.0))
        for i in range(16, 36):
            for j in range(4, 10):
                nid[(i, j)] = len(nodes)
                nodes.append((i, j, 0.0))
        adj = {n: [] for n in range(len(nodes))}
        for (i, j), u in nid.items():
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                v = nid.get((i + di, j + dj))
                if v is not None:
                    adj[u].append((v, 16.0, 'walk'))
        R = np.ones(len(nodes), dtype=bool)
        pks = vprofile._bsp_pockets(DummyBSP(), nodes, R, adj, 0.0, 0.0)
        self.assertEqual(len(pks), 1, pks)
        self.assertGreater(pks[0]['depth'], pks[0]['width'])

        # Connect far end of hall back to main room via teleport -> no longer a pocket!
        adj[nid[(35, 6)]].append((nid[(2, 2)], 0.0, 'tele'))
        pks2 = vprofile._bsp_pockets(DummyBSP(), nodes, R, adj, 0.0, 0.0)
        self.assertEqual(pks2, [])


if __name__ == '__main__':
    unittest.main()
