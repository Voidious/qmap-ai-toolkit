"""Unit and regression tests for qmap/combatprofile.py and gallery/profiles/combat_refs.json.

Run from the repository root:
    python3 -m unittest discover -s tests -v
"""
import importlib.util
import io
import json
import math
import pathlib
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
QMAP_DIR = REPO_ROOT / 'qmap'
if str(QMAP_DIR) not in sys.path:
    sys.path.insert(0, str(QMAP_DIR))

HAS_NUMBA = importlib.util.find_spec('numba') is not None
if HAS_NUMBA:
    import numpy as np  # noqa: E402
    import combatprofile as cp  # noqa: E402


class TestCombatReferenceDataset(unittest.TestCase):
    def test_combat_refs_json_schema_and_classic_only(self):
        p = REPO_ROOT / 'gallery' / 'profiles' / 'combat_refs.json'
        self.assertTrue(p.is_file(), 'Missing gallery/profiles/combat_refs.json')
        data = json.loads(p.read_text(encoding='utf-8'))
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 15)

        duel_names = {row['map'] for row in data if row.get('pool') == 'duel'}
        large_names = {row['map'] for row in data if row.get('pool') == 'large'}
        self.assertEqual(duel_names, {'aerowalk', 'dapak12', 'naked3', 'naked4', 'ztndm3'})
        self.assertEqual(
            large_names,
            {'skull', 'bravado', 'spinev2', 'ultrav', 'schloss', 'cmt4', 'dm3', 'e2m2tdm', 'cmt3', 'e1m2'},
        )

        # Must NOT include toolkit-built maps
        all_names = duel_names | large_names
        for forbidden in ('agora', 'bastion', 'circuit', 'cistern', 'crucible', 'helix', 'lyceum', 'relay', 'strata', 'vigil'):
            self.assertNotIn(forbidden, all_names)

        req_metrics = (
            'sightline_3d_p50', 'sightline_3d_p90', 'sightline_3d_max',
            'exposure_median', 'exposure_p90', 'exposure_area_k_p90',
            'overlooked_by_p90', 'overlooked_by_area_k_p90',
            'overlook_net_p05', 'overlook_net_p95',
            'killbox_share', 'perch_share',
            'disengage_p50_s', 'disengage_p90_s', 'disengage_overlooked_p90_s',
        )
        for row in data:
            for k in ('map', 'pool', 'floor_area_k', 'eff_levels', 'reachable_cells',
                      'observer_samples', 'sample_grid', 'metrics'):
                self.assertIn(k, row, f"Missing {k} in {row.get('map')}")
            m = row['metrics']
            for k in req_metrics:
                self.assertIn(k, m, f"Missing metric {k} in {row.get('map')}")
            self.assertGreater(m['sightline_3d_max'], m['sightline_3d_p90'])
            self.assertGreaterEqual(m['sightline_3d_p90'], m['sightline_3d_p50'])
            self.assertLessEqual(m['overlook_net_p05'], 0.0)
            self.assertGreaterEqual(m['overlook_net_p95'], 0.0)
            self.assertGreater(m['disengage_p90_s'], 0.0)

    @unittest.skipUnless(HAS_NUMBA, 'numba required to import combatprofile reference tables')
    def test_reference_tables_match_combat_refs_json_min_max(self):
        p = REPO_ROOT / 'gallery' / 'profiles' / 'combat_refs.json'
        rows = json.loads(p.read_text(encoding='utf-8'))
        for pool, table in (('duel', cp.REFERENCE_DUEL), ('large', cp.REFERENCE_LARGE)):
            pool_rows = [r for r in rows if r['pool'] == pool]
            for metric, spec in table.items():
                lo, hi = spec[0], spec[1]
                vals = [r['metrics'][metric] for r in pool_rows]
                self.assertEqual(lo, min(vals), f'{pool} {metric} healthy_lo mismatch vs combat_refs.json')
                self.assertEqual(hi, max(vals), f'{pool} {metric} healthy_hi mismatch vs combat_refs.json')
            # Every classic in the pool must classify 'ok' against its own pool (zero HIGH/EXTREME)
            for row in pool_rows:
                for metric, spec in table.items():
                    self.assertEqual(
                        cp.classify_metric(row['metrics'][metric], spec),
                        'ok',
                        f"{row['map']} failed {pool} ref on {metric}={row['metrics'][metric]} vs {spec[:2]}",
                    )

        for metric, spec in cp.REFERENCE_ALL.items():
            d_spec = cp.REFERENCE_DUEL[metric]
            l_spec = cp.REFERENCE_LARGE[metric]
            self.assertEqual(spec[0], min(d_spec[0], l_spec[0]), f'all {metric} lo')
            self.assertEqual(spec[1], max(d_spec[1], l_spec[1]), f'all {metric} hi')


def _write_synthetic_arena_bsp(path, *, with_balcony=True, cover_box=None, cover_as_func_wall=False,
                               balcony_spawn=True, teleporter=None, push_pad=None):
    """Build a self-contained compiled BSP29 arena with exact hull-0 nodes and hull-1 clipnodes.

    World interior: x in [0, 512], y in [0, 512], z in [0, 320].
    Optional balcony (z=128): solid step/block at x in [0, 128], y in [0, 512], z in [0, 128].
    Optional cover_box: (x0, y0, z0, x1, y1, z1) solid wall/baffle inside the arena, placed
    either in worldspawn or as a func_wall submodel (*1).
    Optional teleporter: (trigger_box, dest_xyz) adding a trigger_teleport + info_teleport_destination.
    Optional push_pad: (trigger_box, angles_str, speed) adding a trigger_push launch pad.
    """
    planes = []

    def add_plane(nx, ny, nz, d):
        idx = len(planes)
        ptype = 0 if abs(nx) == 1 else (1 if abs(ny) == 1 else (2 if abs(nz) == 1 else 3))
        planes.append((float(nx), float(ny), float(nz), float(d), ptype))
        return idx

    # Build a BSP tree representing a union of solid AABBs inside an outer empty box (or outside = solid)
    # Leaf convention: for hull-0 nodes, child < 0 indexes leaves[-1 - child] where leaf 0 = empty (-1), leaf 1 = solid (-2).
    # For hull-1 clipnodes, child = -1 (empty) or -2 (solid).
    nodes = []      # (plane_idx, front_child, back_child)
    clipnodes = []  # (plane_idx, front_child, back_child)

    def _box_bsp(boxes, is_hull0, expand_xy=0.0, expand_z_lo=0.0, expand_z_hi=0.0, outer_empty=True):
        """Return root node/clipnode where union(boxes) is SOLID and complement is EMPTY (if outer_empty)
        or intersection of outer box with complement of inner boxes is EMPTY."""
        # Expand boxes for hull-1 (player box is [-16,+16] x [-16,+16] x [-24,+32]:
        # a solid box [x0..x1, y0..y1, z0..z1] blocks player origin in [x0-16..x1+16, y0-16..y1+16, z0-32..z1+24]).
        adj_boxes = [
            (b[0] - expand_xy, b[1] - expand_xy, b[2] - expand_z_lo,
             b[3] + expand_xy, b[4] + expand_xy, b[5] + expand_z_hi)
            for b in boxes
        ]

        empty_leaf = -1  # leaf 0 (contents -1) for hull 0; CONTENTS_EMPTY (-1) for hull 1
        solid_leaf = -2  # leaf 1 (contents -2) for hull 0; CONTENTS_SOLID (-2) for hull 1

        def add_node(p_idx, front, back):
            arr = nodes if is_hull0 else clipnodes
            idx = len(arr)
            arr.append((p_idx, front, back))
            return idx

        def solid_chain(box, fallback_leaf):
            # Inside box -> solid_leaf; outside box -> fallback_leaf
            x0, y0, z0, x1, y1, z1 = box
            cur = solid_leaf
            for (nx, ny, nz, d), inside_is_back in (
                ((1, 0, 0, x1), True),
                ((1, 0, 0, x0), False),
                ((0, 1, 0, y1), True),
                ((0, 1, 0, y0), False),
                ((0, 0, 1, z1), True),
                ((0, 0, 1, z0), False),
            ):
                p = add_plane(nx, ny, nz, d)
                if inside_is_back:
                    cur = add_node(p, fallback_leaf, cur)
                else:
                    cur = add_node(p, cur, fallback_leaf)
            return cur

        def build_union(blist):
            cur = empty_leaf
            for box in reversed(blist):
                cur = solid_chain(box, cur)
            return cur

        if outer_empty:
            return build_union(adj_boxes)

        # Outer room [0..512, 0..512, 0..320] shrunk inward for hull-1:
        # player origin is empty in [0+16..512-16, 0+16..512-16, 0+24..320-32]
        rx0, ry0, rz0 = 0.0 + expand_xy, 0.0 + expand_xy, 0.0 + expand_z_hi
        rx1, ry1, rz1 = 512.0 - expand_xy, 512.0 - expand_xy, 320.0 - expand_z_lo
        inner = build_union(adj_boxes)
        cur = inner
        for (nx, ny, nz, d), inside_is_back in (
            ((1, 0, 0, rx1), True),
            ((1, 0, 0, rx0), False),
            ((0, 1, 0, ry1), True),
            ((0, 1, 0, ry0), False),
            ((0, 0, 1, rz1), True),
            ((0, 0, 1, rz0), False),
        ):
            p = add_plane(nx, ny, nz, d)
            if inside_is_back:
                cur = add_node(p, solid_leaf, cur)
            else:
                cur = add_node(p, cur, solid_leaf)
        return cur

    world_boxes = []
    if with_balcony:
        world_boxes.append((0.0, 0.0, 0.0, 128.0, 512.0, 128.0))
    if cover_box is not None and not cover_as_func_wall:
        world_boxes.append(cover_box)

    w_h0 = _box_bsp(world_boxes, is_hull0=True, outer_empty=False)
    w_h1 = _box_bsp(world_boxes, is_hull0=False, expand_xy=16.0, expand_z_lo=32.0, expand_z_hi=24.0, outer_empty=False)

    models = [
        # (mins3, maxs3, origin3, headnodes4, visleafs, firstface, numfaces)
        ((0.0, 0.0, 0.0), (512.0, 512.0, 320.0), (0.0, 0.0, 0.0), (w_h0, w_h1, w_h1, 0), 2, 0, 0),
    ]

    ents = [
        '{\n"classname" "worldspawn"\n}\n',
        '{\n"classname" "info_player_deathmatch"\n"origin" "384 256 24"\n}\n',
    ]
    if with_balcony and balcony_spawn:
        # Spawn on the balcony as well so both tiers are reachable
        ents.append('{\n"classname" "info_player_deathmatch"\n"origin" "64 256 152"\n}\n')

    if cover_box is not None and cover_as_func_wall:
        fw_h0 = _box_bsp([cover_box], is_hull0=True, outer_empty=True)
        fw_h1 = _box_bsp([cover_box], is_hull0=False, expand_xy=16.0, expand_z_lo=32.0, expand_z_hi=24.0, outer_empty=True)
        mi = len(models)
        models.append((
            (cover_box[0], cover_box[1], cover_box[2]),
            (cover_box[3], cover_box[4], cover_box[5]),
            (0.0, 0.0, 0.0),
            (fw_h0, fw_h1, fw_h1, 0),
            2, 0, 0,
        ))
        ents.append(f'{{\n"classname" "func_wall"\n"model" "*{mi}"\n}}\n')

    if teleporter is not None:
        tbox, dest_xyz = teleporter
        mi = len(models)
        models.append((
            (tbox[0], tbox[1], tbox[2]),
            (tbox[3], tbox[4], tbox[5]),
            (0.0, 0.0, 0.0),
            (-1, -1, -1, 0),
            1, 0, 0,
        ))
        ents.append(f'{{\n"classname" "trigger_teleport"\n"model" "*{mi}"\n"target" "tele_dest"\n}}\n')
        ents.append(
            f'{{\n"classname" "info_teleport_destination"\n"targetname" "tele_dest"\n'
            f'"origin" "{dest_xyz[0]} {dest_xyz[1]} {dest_xyz[2]}"\n}}\n'
        )

    if push_pad is not None:
        pbox, angles_str, speed = push_pad
        mi = len(models)
        models.append((
            (pbox[0], pbox[1], pbox[2]),
            (pbox[3], pbox[4], pbox[5]),
            (0.0, 0.0, 0.0),
            (-1, -1, -1, 0),
            1, 0, 0,
        ))
        ents.append(
            f'{{\n"classname" "trigger_push"\n"model" "*{mi}"\n'
            f'"angles" "{angles_str}"\n"speed" "{speed}"\n}}\n'
        )

    # Pack BSP29 lumps
    lump_ents = ''.join(ents).encode('latin1') + b'\0'
    lump_planes = b''.join(struct.pack('<4fi', *p) for p in planes)
    lump_miptex = struct.pack('<i', 0)
    lump_verts = b''
    lump_vis = b''
    lump_nodes = b''.join(struct.pack('<i2h6h2H', p, f, b, 0, 0, 0, 512, 512, 320, 0, 0) for p, f, b in nodes)
    lump_texinfo = b''
    lump_faces = b''
    lump_light = b''
    lump_clipnodes = b''.join(struct.pack('<i2h', p, f, b) for p, f, b in clipnodes)
    # Leaf 0 = empty (-1), Leaf 1 = solid (-2)
    lump_leaves = (
        struct.pack('<2i6h2H4B', -1, -1, 0, 0, 0, 512, 512, 320, 0, 0, 0, 0, 0, 0)
        + struct.pack('<2i6h2H4B', -2, -1, 0, 0, 0, 512, 512, 320, 0, 0, 0, 0, 0, 0)
    )
    lump_marksurf = b''
    lump_edges = b''
    lump_surfedges = b''
    lump_models = b''.join(
        struct.pack('<9f7i', *mn, *mx, *org, *hd, vl, ff, nf)
        for mn, mx, org, hd, vl, ff, nf in models
    )

    lumps = [
        lump_ents, lump_planes, lump_miptex, lump_verts, lump_vis,
        lump_nodes, lump_texinfo, lump_faces, lump_light, lump_clipnodes,
        lump_leaves, lump_marksurf, lump_edges, lump_surfedges, lump_models,
    ]
    offset = 4 + 15 * 8
    directory = []
    for data in lumps:
        directory.append(struct.pack('<ii', offset, len(data)))
        offset += len(data)
    pathlib.Path(path).write_bytes(struct.pack('<i', 29) + b''.join(directory + lumps))


@unittest.skipUnless(HAS_NUMBA, 'numba required for combatprofile geometry/graph tests')
class TestCombatProfile(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)

    def test_3d_diagonal_and_elevation_sightlines_and_overlook_asymmetry(self):
        bsp_path = self.dir / 'balcony_open.bsp'
        _write_synthetic_arena_bsp(bsp_path, with_balcony=True, cover_box=None)
        res = cp.combat_profile(str(bsp_path), ref='duel')
        D = res['_draw']
        m = res['metrics']

        # True 3D sightline crosses diagonally AND vertically (> 512u axial room width)
        self.assertGreater(m['sightline_3d_max'], 620)
        self.assertTrue(any(abs(sl['dz']) >= 64 for sl in res['top_sightlines']))

        # Overlook asymmetry cleanly separates balcony (+perch) vs pit (-killbox)
        F = D['pts'][:, 2]
        balcony = F >= 120.0
        pit = F <= 8.0
        self.assertTrue(np.any(balcony))
        self.assertTrue(np.any(pit))

        # Balcony shoots down onto pit and is never shot down on;
        # edge cells see more of the pit than back-wall cells occluded by the balcony lip.
        self.assertGreater(float(D['overlooks_share'][balcony].mean()), 0.50)
        self.assertEqual(float(D['overlooked_by_share'][balcony].max()), 0.0)
        self.assertGreater(float(D['overlook_net'][balcony].min()), 0.25)
        self.assertGreater(float(D['overlook_net'][balcony].max()), 0.65)
        bal_x = D['pts'][balcony, 0]
        self.assertGreater(
            float(D['overlooks_share'][balcony][bal_x > 80].mean()),
            float(D['overlooks_share'][balcony][bal_x < 48].mean()),
        )

        # Pit is shot down on from balcony and cannot overlook anything;
        # cells tucked under the balcony lip are less exposed than the open pit.
        self.assertGreater(float(D['overlooked_by_share'][pit].mean()), 0.15)
        self.assertEqual(float(D['overlooks_share'][pit].max()), 0.0)
        self.assertLess(float(D['overlook_net'][pit].mean()), -0.15)
        self.assertLess(float(D['overlook_net'][pit].max()), -0.05)
        pit_x = D['pts'][pit, 0]
        self.assertGreater(
            float(D['overlooked_by_share'][pit][pit_x > 256].mean()),
            float(D['overlooked_by_share'][pit][pit_x < 176].mean()),
        )

        # Floor slicing splits pit (z=0) and balcony (z=128) into 2 distinct slices
        self.assertEqual(len(D['slices']), 2)
        self.assertLess(D['slices'][0][1], 128)

    def test_cover_baffle_improves_disengage_and_diff_mode_detects_improvement(self):
        open_bsp = self.dir / 'arena_b1.bsp'
        cover_bsp = self.dir / 'arena_b2.bsp'
        _write_synthetic_arena_bsp(open_bsp, with_balcony=True, cover_box=None)
        # Tall baffle in mid-pit creates a shadowed cover pocket breaking balcony LOS
        _write_synthetic_arena_bsp(cover_bsp, with_balcony=True, cover_box=(256.0, 128.0, 0.0, 288.0, 384.0, 208.0))

        b1 = cp.combat_profile(str(open_bsp), ref='duel')
        b2 = cp.combat_profile(str(cover_bsp), ref='duel')

        # Adding cover drops exposure, median/overlooked disengage time, and uncovered floor share
        self.assertLess(b2['metrics']['exposure_p90'], b1['metrics']['exposure_p90'])
        self.assertLess(b2['metrics']['disengage_p50_s'], b1['metrics']['disengage_p50_s'])
        self.assertLess(b2['metrics']['disengage_overlooked_p90_s'], b1['metrics']['disengage_overlooked_p90_s'])
        self.assertLess(b2['metrics']['disengage_uncovered_share'], b1['metrics']['disengage_uncovered_share'])

        diff = cp.compare_profiles(b1, b2, ref='duel')
        self.assertLess(diff['deltas']['disengage_overlooked_p90_s']['delta'], 0.0)
        self.assertEqual(diff['deltas']['disengage_overlooked_p90_s']['trend'], 'improved')
        self.assertLess(diff['deltas']['exposure_p90']['delta'], 0.0)
        self.assertIn('combat diff: arena_b1 -> arena_b2', cp.format_diff_report(diff))

        # Verify both single-map and diff PNG heatmaps render cleanly
        single_png = self.dir / 'arena_b2.combat.png'
        diff_png = self.dir / 'arena_diff.png'
        cp.draw(b2, str(single_png))
        cp.draw_diff(b1, b2, diff, str(diff_png))
        self.assertGreater(single_png.stat().st_size, 5000)
        self.assertGreater(diff_png.stat().st_size, 5000)

    def test_corridor_corner_credits_active_watcher_los_break(self):
        # Symmetric 128u-wide L-corridor (two equal wings separated by a solid 384x384 block):
        # turning the 90-degree corner keeps total visible area identical, so disengage must
        # credit breaking LOS from >= 50% of active watchers rather than capping out across wings.
        bsp_path = self.dir / 'l_corridor.bsp'
        _write_synthetic_arena_bsp(bsp_path, with_balcony=False, cover_box=(0.0, 0.0, 0.0, 384.0, 384.0, 320.0))
        res = cp.combat_profile(str(bsp_path), ref='duel')
        self.assertLess(res['metrics']['disengage_p50_s'], 1.2)
        self.assertLess(res['metrics']['disengage_uncovered_share'], 0.25)

        # Single-slice flat map still renders cleanly
        png_path = self.dir / 'l_corridor.png'
        cp.draw(res, str(png_path))
        self.assertGreater(png_path.stat().st_size, 5000)

    def test_disengage_requires_regional_overlook_cover_and_unoverlooked_shelter(self):
        # 1. Single-point overlooker LOS break behind a narrow obstacle must NOT count as cover
        #    when most of the overlooking ledge (region) still sees you.
        # 3-node chain: 0 --(16u)--> 1 --(16u)--> 2.
        # 4 overlooker samples (0..3) all on one ledge (within 192u), all watching node 0.
        # Node 1 hides ONLY dominant sample 0 (3 of 4 still see it -> 75% remain).
        # Node 2 hides samples 0, 1, 2 (1 of 4 remains -> 25% <= 50%).
        indptr = np.array([0, 1, 3, 4], np.int64)
        indices = np.array([1, 0, 2, 1], np.int64)
        weights = np.array([16.0, 16.0, 16.0, 16.0], np.float64)
        rep_pts = np.array([
            [0.0, 0.0, 128.0],
            [48.0, 0.0, 128.0],
            [96.0, 0.0, 128.0],
            [144.0, 0.0, 128.0],
        ], np.float64)
        rep_w = np.full(4, 250.0, np.float64)
        cell_area = float(cp.C * cp.C)
        pts_z = np.array([0.0, 0.0, 0.0], np.float64)
        reg_indptr, reg_indices = cp._build_overlook_regions(rep_pts)

        # Exposure matches active watchers (rep_w * cell_area = 64k each):
        # node 0 sees 4 (256k), node 1 sees 3 (192k, > 50% of 256k), node 2 sees 1 (64k, <= 50%).
        # Give node 2 an extra ground watcher or use exposure_area = [256k, 192k, 192k] so ONLY
        # regional overlook-break (not total-exposure cut) triggers at node 2.
        exposure_area = np.array([4 * 250.0 * cell_area, 3 * 250.0 * cell_area, 3 * 250.0 * cell_area], np.float64)
        overlooked_by_area = np.array([4 * 250.0 * cell_area, 3 * 250.0 * cell_area, 1 * 250.0 * cell_area], np.float64)
        dom_obs = np.array([0, 1, 3], np.int64)
        cell_sees = np.array([
            [1, 1, 1, 1],
            [0, 1, 1, 1],
            [0, 0, 0, 1],
        ], np.uint8)
        d_dist, d_reason = cp._compute_disengage(
            indptr, indices, weights, exposure_area, overlooked_by_area, dom_obs,
            cell_sees, rep_w, np.ascontiguousarray(rep_pts[:, 2]), pts_z,
            reg_indptr, reg_indices, 64.0, 64000.0, 1536.0,
        )
        # Must walk 32u to node 2 (not stop at 16u node 1 where only 1 point lost LOS)
        self.assertAlmostEqual(float(d_dist[0]), 32.0)
        self.assertEqual(int(d_reason[0]), 2)

        # 2. Shelter check must inspect destination dom_obs[u] < 0 (not start cell dom < 0)
        #    and report distinct reason code 5 when reaching genuine shelter.
        # Node 0: un-overlooked, exposure 70k (> 64k shelter).
        # Node 1 (16u away): exposure 50k (<= 64k) BUT overlooked (dom_obs[1] = 0) -> NOT shelter!
        # Node 2 (32u away): exposure 50k (<= 64k) and NOT overlooked (dom_obs[2] = -1) -> shelter (reason 5)!
        rep_w_sh = np.full(4, 68.0, np.float64)  # 4 * 68 * 256 = 69632 (consistent with 70k)
        exposure_sh = np.array([70000.0, 50000.0, 50000.0], np.float64)
        overlooked_sh = np.array([0.0, 4 * 68.0 * cell_area, 0.0], np.float64)
        dom_sh = np.array([-1, 0, -1], np.int64)
        sees_sh = np.array([
            [1, 1, 1, 1],
            [1, 1, 1, 1],
            [1, 1, 1, 1],
        ], np.uint8)
        d_dist2, d_reason2 = cp._compute_disengage(
            indptr, indices, weights, exposure_sh, overlooked_sh, dom_sh,
            sees_sh, rep_w_sh, np.ascontiguousarray(rep_pts[:, 2]), pts_z,
            reg_indptr, reg_indices, 64.0, 64000.0, 1536.0,
        )
        self.assertAlmostEqual(float(d_dist2[0]), 32.0)
        self.assertEqual(int(d_reason2[0]), 5)

    def test_func_wall_submodel_blocks_hull0_sightlines(self):
        world_cover = self.dir / 'world_cover.bsp'
        fw_cover = self.dir / 'func_wall_cover.bsp'
        box = (256.0, 128.0, 0.0, 288.0, 384.0, 208.0)
        _write_synthetic_arena_bsp(world_cover, with_balcony=True, cover_box=box, cover_as_func_wall=False)
        _write_synthetic_arena_bsp(fw_cover, with_balcony=True, cover_box=box, cover_as_func_wall=True)

        r_world = cp.combat_profile(str(world_cover), ref='duel')
        r_fw = cp.combat_profile(str(fw_cover), ref='duel')
        self.assertAlmostEqual(r_fw['metrics']['exposure_p90'], r_world['metrics']['exposure_p90'], delta=0.02)
        self.assertAlmostEqual(r_fw['metrics']['disengage_overlooked_p90_s'],
                               r_world['metrics']['disengage_overlooked_p90_s'], delta=0.10)

    def test_reference_classification_and_floor_slices(self):
        spec_down = (900, 1200, 1500, 'down', 'sightline')
        self.assertEqual(cp.classify_metric(800, spec_down), 'LOW')
        self.assertEqual(cp.classify_metric(1050, spec_down), 'ok')
        self.assertEqual(cp.classify_metric(1350, spec_down), 'HIGH')
        self.assertEqual(cp.classify_metric(1600, spec_down), 'EXTREME')

        spec_up = (-0.13, -0.07, -0.18, 'up', 'killbox tail')
        self.assertEqual(cp.classify_metric(-0.02, spec_up), 'LOW')
        self.assertEqual(cp.classify_metric(-0.10, spec_up), 'ok')
        self.assertEqual(cp.classify_metric(-0.15, spec_up), 'HIGH')
        self.assertEqual(cp.classify_metric(-0.22, spec_up), 'EXTREME')

        # Flat floor stays 1 slice; 3-tier floor splits cleanly between tiers
        self.assertEqual(len(cp.compute_floor_slices(np.zeros(100), max_slices=4)), 1)
        three_tiers = np.concatenate([np.zeros(200), np.full(200, 128.0), np.full(200, 256.0)])
        slices = cp.compute_floor_slices(three_tiers, max_slices=4)
        self.assertEqual(len(slices), 3)
        self.assertTrue(slices[0][0] <= 0 < slices[0][1] <= 128 < slices[1][1] <= 256 <= slices[2][1])

    def test_floor_graph_matches_vprofile_and_handles_teleporter_and_push_pad(self):
        import vprofile

        # 1. Parity with vprofile.profile() on reachable floor nodes
        arena = self.dir / 'parity.bsp'
        _write_synthetic_arena_bsp(arena, with_balcony=True, cover_box=(256.0, 128.0, 0.0, 288.0, 384.0, 208.0))
        vp = vprofile.profile(str(arena))
        vp_reach = {
            vp['_draw']['nodes'][idx]
            for idx, ok in enumerate(vp['_draw']['R'])
            if ok
        }
        cp_loaded = cp.load_walkable_floor(str(arena))
        self.assertEqual(set(cp_loaded['nodes_reach']), vp_reach)

        # 2. Teleporter connects pit (only spawn) up to balcony with TELE_COST edge
        tele_bsp = self.dir / 'tele.bsp'
        _write_synthetic_arena_bsp(
            tele_bsp,
            with_balcony=True,
            balcony_spawn=False,
            teleporter=((224.0, 224.0, 0.0, 288.0, 288.0, 64.0), (64, 256, 152)),
        )
        loaded_tele = cp.load_walkable_floor(str(tele_bsp))
        self.assertTrue(np.any(loaded_tele['pts'][:, 2] >= 120.0), 'teleporter should reach balcony')
        # Verify at least one edge uses TELE_COST (48.0) jumping from z=0 to z=128
        found_tele_edge = False
        for u in range(len(loaded_tele['pts'])):
            if loaded_tele['pts'][u, 2] <= 8.0:
                for e in range(loaded_tele['indptr'][u], loaded_tele['indptr'][u + 1]):
                    v = loaded_tele['indices'][e]
                    if loaded_tele['pts'][v, 2] >= 120.0 and loaded_tele['weights'][e] == cp.TELE_COST:
                        found_tele_edge = True
                        break
        self.assertTrue(found_tele_edge, 'expected TELE_COST edge from pit trigger to balcony')

        # 3. Push pad launches pit player onto balcony (only pit spawn, no balcony spawn)
        pad_bsp = self.dir / 'pad.bsp'
        _write_synthetic_arena_bsp(
            pad_bsp,
            with_balcony=True,
            balcony_spawn=False,
            push_pad=((208.0, 224.0, 0.0, 272.0, 288.0, 64.0), '-75 180 0', 75),
        )
        loaded_pad = cp.load_walkable_floor(str(pad_bsp))
        self.assertTrue(np.any(loaded_pad['pts'][:, 2] >= 120.0), 'push pad should launch onto balcony')
        vp_pad = vprofile.profile(str(pad_bsp))
        vp_pad_reach = {
            vp_pad['_draw']['nodes'][idx]
            for idx, ok in enumerate(vp_pad['_draw']['R'])
            if ok
        }
        self.assertEqual(set(loaded_pad['nodes_reach']), vp_pad_reach)

    def test_cli_single_diff_json_and_errors(self):
        b1 = self.dir / 'cli_b1.bsp'
        b2 = self.dir / 'cli_b2.bsp'
        _write_synthetic_arena_bsp(b1, with_balcony=True, cover_box=None)
        _write_synthetic_arena_bsp(b2, with_balcony=True, cover_box=(256.0, 128.0, 0.0, 288.0, 384.0, 208.0))

        out_json = self.dir / 'single.json'
        out_png = self.dir / 'single.png'
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cp.main([str(b1), '--ref', 'duel', '--json', str(out_json), '--png', str(out_png)])
        self.assertEqual(rc, 0)
        self.assertIn('combat profile of cli_b1', buf.getvalue())
        payload = json.loads(out_json.read_text(encoding='utf-8'))
        self.assertEqual(payload['map'], 'cli_b1')
        self.assertIn('metrics', payload)
        self.assertGreater(out_png.stat().st_size, 5000)

        diff_json = self.dir / 'diff.json'
        diff_png = self.dir / 'diff.png'
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = cp.main(['--diff', str(b1), str(b2), '--ref', 'all', '--json', str(diff_json), '--png', str(diff_png)])
        self.assertEqual(rc, 0)
        self.assertIn('combat diff: cli_b1 -> cli_b2', buf.getvalue())
        diff_payload = json.loads(diff_json.read_text(encoding='utf-8'))
        self.assertEqual(diff_payload['before_map'], 'cli_b1')
        self.assertEqual(diff_payload['after_map'], 'cli_b2')
        self.assertGreater(diff_png.stat().st_size, 5000)

        # Missing input exits 2 cleanly
        err = io.StringIO()
        with redirect_stderr(err):
            rc = cp.main([str(self.dir / 'nonexistent.bsp')])
        self.assertEqual(rc, 2)


if __name__ == '__main__':
    unittest.main()
