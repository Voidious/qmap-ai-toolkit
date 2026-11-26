"""Unit and regression tests for qmap/ctfprofile.py and gallery/profiles/ctf_refs.json.

Run from the repository root:
    python3 -m unittest discover -s tests -v
"""
import importlib.util
import json
import pathlib
import sys
import unittest
from collections import defaultdict

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
QMAP_DIR = REPO_ROOT / 'qmap'
if str(QMAP_DIR) not in sys.path:
    sys.path.insert(0, str(QMAP_DIR))

HAS_NUMBA = importlib.util.find_spec('numba') is not None
if HAS_NUMBA:
    import numpy as np  # noqa: E402
    import ctfprofile  # noqa: E402


class TestCtfReferenceDataset(unittest.TestCase):
    def test_ctf_refs_json_schema_and_classic_only(self):
        p = REPO_ROOT / 'gallery' / 'profiles' / 'ctf_refs.json'
        self.assertTrue(p.is_file(), 'Missing gallery/profiles/ctf_refs.json')
        data = json.loads(p.read_text(encoding='utf-8'))
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 8)
        names = {row['map'] for row in data}
        # Must include core established classics
        for req in ('ctf1', 'ctf3', 'ctf5', 'ctf2m1'):
            self.assertIn(req, names)
        # Must NOT include toolkit-built eyeball maps
        for forbidden in ('ctf_bastion', 'ctf_bastion_b19', 'ctf_circuit', 'ctf_circuit_b5',
                          'ctf_strata', 'ctf_strata_b6', 'ctf_knot', 'ctf_knot_b5'):
            self.assertNotIn(forbidden, names)
        # Verify required fields
        for row in data:
            for k in ('map', 'travel_median', 'eff_levels', 'dominant_level',
                      'flag_gap_2d', 'flag_exits', 'flag_max_los', 'walk', 'hook'):
                self.assertIn(k, row, f"Missing {k} in {row.get('map')}")
            self.assertIn('connected', row['walk'])
            self.assertIn('connected', row['hook'])


@unittest.skipUnless(HAS_NUMBA, 'numba required for ctfprofile geometry/graph tests')
class TestCtfRouteIndependence(unittest.TestCase):
    def _build_three_lane_graph(self, include_north=True, include_south=True):
        """Synthetic CTF graph:
        Flag 1 at x=0, Flag 2 at x=2000 (step=100u).
        - Center lane (lane 0): y=0, x=0..2000 (length 2000)
        - North side tunnel (lane 1): y=+600, x=200..1800, connects at x=200 and x=1800 (length 3200)
        - South side tunnel (lane 2): y=-600, x=200..1800, connects at x=200 and x=1800 (length 3200)
        """
        pts = []
        lane_of = []
        adj = defaultdict(list)

        def add_node(x, y, lane):
            idx = len(pts)
            pts.append((float(x), float(y), 0.0))
            lane_of.append(lane)
            return idx

        def link(u, v):
            d = float(np.hypot(pts[u][0] - pts[v][0], pts[u][1] - pts[v][1]))
            adj[u].append((v, d, 'walk'))
            adj[v].append((u, d, 'walk'))

        # Center spine x=0, 100, ..., 2000
        center = [add_node(x, 0, 0) for x in range(0, 2100, 100)]
        for k in range(len(center) - 1):
            link(center[k], center[k + 1])

        if include_north:
            # West connector from center[2] (x=200,y=0) up to (200,600), across to (1800,600), down to center[18]
            n_nodes = [add_node(200, y, 1) for y in range(100, 700, 100)]
            n_nodes += [add_node(x, 600, 1) for x in range(300, 1900, 100)]
            n_nodes += [add_node(1800, y, 1) for y in range(500, 0, -100)]
            link(center[2], n_nodes[0])
            for k in range(len(n_nodes) - 1):
                link(n_nodes[k], n_nodes[k + 1])
            link(n_nodes[-1], center[18])

        if include_south:
            s_nodes = [add_node(200, y, 2) for y in range(-100, -700, -100)]
            s_nodes += [add_node(x, -600, 2) for x in range(300, 1900, 100)]
            s_nodes += [add_node(1800, y, 2) for y in range(-500, 0, 100)]
            link(center[2], s_nodes[0])
            for k in range(len(s_nodes) - 1):
                link(s_nodes[k], s_nodes[k + 1])
            link(s_nodes[-1], center[18])

        P = np.array(pts, dtype=np.float64)
        lanes = np.array(lane_of, dtype=np.int64)
        return center[0], center[-1], P, lanes, adj

    def test_single_open_center_is_cut_by_one_vantage(self):
        # Three physical lanes, but ALL mutually visible in one open center chamber -> 1 LOS route, cuts all!
        f1, f2, P, _lanes, adj = self._build_three_lane_graph(True, True)
        g = ctfprofile._geodesic_progress(adj, f1, f2, len(P))
        mid = np.nonzero((g >= 0.30) & (g <= 0.70))[0]
        # Open chamber LOS: every mid node sees every other mid node
        all_see_pts = lambda src_pts, b_arr: np.ones(len(b_arr), dtype=bool)
        all_see_one = lambda v_pt, b_arr: np.ones(len(b_arr), dtype=bool)
        res = ctfprofile.analyze_band_routes(adj, f1, f2, P, mid, all_see_pts, all_see_one)
        self.assertEqual(len(res['los_routes']), 1)
        self.assertTrue(res['vantage_cuts_all'])
        self.assertIsNone(res['worst_bypass'])
        # Spatially separated at 384u STILL finds all 3 physical corridors
        self.assertEqual(len(res['sp_routes']), 3)

    def test_walled_side_tunnels_give_three_los_routes_and_survive_single_vantage(self):
        f1, f2, P, lanes, adj = self._build_three_lane_graph(True, True)
        g = ctfprofile._geodesic_progress(adj, f1, f2, len(P))
        mid = np.nonzero((g >= 0.30) & (g <= 0.70))[0]

        # Walled lanes: nodes only see nodes in the SAME lane
        def lane_of_pt(pt):
            return 1 if pt[1] > 200 else (2 if pt[1] < -200 else 0)

        def walled_pts(src_pts, b_arr):
            src_lanes = {lane_of_pt(pt) for pt in src_pts}
            return np.array([lanes[m] in src_lanes for m in b_arr], dtype=bool)

        def walled_one(v_pt, b_arr):
            vl = lane_of_pt(v_pt)
            return np.array([lanes[m] == vl for m in b_arr], dtype=bool)

        res = ctfprofile.analyze_band_routes(adj, f1, f2, P, mid, walled_pts, walled_one)
        self.assertEqual(len(res['los_routes']), 3)
        self.assertAlmostEqual(res['los_routes'][0][0], 2000.0, delta=1.0)
        self.assertAlmostEqual(res['los_routes'][1][0], 3200.0, delta=1.0)
        self.assertAlmostEqual(res['los_routes'][2][0], 3200.0, delta=1.0)
        self.assertFalse(res['vantage_cuts_all'])
        # Blocking center lane forces detour onto side tunnel (3200u)
        self.assertAlmostEqual(res['worst_bypass'], 3200.0, delta=1.0)
        self.assertAlmostEqual(res['lat_sep'], 600.0, delta=1.0)

    def test_single_vantage_128u_grid_finds_off_route_choke(self):
        # Walled lanes EXCEPT one elevated sniper perch off route 1 in the band that sees all 3 lanes.
        f1, f2, P, lanes, adj = self._build_three_lane_graph(True, True)
        perch_id = len(P)
        # Attach perch off the center spine at (1000, 300, 128)
        P = np.vstack([P, [[1000.0, 300.0, 128.0]]])
        lanes = np.append(lanes, 99)
        # Connect perch to center node at x=1000 (index 10)
        adj[10].append((perch_id, 326.0, 'walk'))
        adj[perch_id].append((10, 326.0, 'walk'))
        g = ctfprofile._geodesic_progress(adj, f1, f2, len(P))
        mid = np.nonzero((g >= 0.30) & (g <= 0.70))[0]
        self.assertIn(perch_id, mid)

        def lane_of_pt(pt):
            if pt[2] > 64.0:
                return 99
            return 1 if pt[1] > 200 else (2 if pt[1] < -200 else 0)

        def walled_pts(src_pts, b_arr):
            src_lanes = {lane_of_pt(pt) for pt in src_pts}
            if 99 in src_lanes:
                return np.ones(len(b_arr), dtype=bool)
            return np.array([lanes[m] in src_lanes for m in b_arr], dtype=bool)

        def walled_one(v_pt, b_arr):
            vl = lane_of_pt(v_pt)
            if vl == 99:
                return np.ones(len(b_arr), dtype=bool)
            return np.array([lanes[m] == vl for m in b_arr], dtype=bool)

        res = ctfprofile.analyze_band_routes(adj, f1, f2, P, mid, walled_pts, walled_one)
        self.assertTrue(res['vantage_cuts_all'])
        self.assertEqual(res['worst_vantage_pos'], (1000, 300, 128))

    def test_geodesic_progress_handles_u_shaped_horseshoe(self):
        # Flags side-by-side at (0, 0) and (0, 400), connected only via an eastern loop out to x=1000
        pts = [(0.0, 0.0, 0.0), (500.0, 0.0, 0.0), (1000.0, 0.0, 0.0),
               (1000.0, 200.0, 0.0), (1000.0, 400.0, 0.0), (500.0, 400.0, 0.0), (0.0, 400.0, 0.0)]
        adj = defaultdict(list)
        for k in range(len(pts) - 1):
            d = float(np.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1]))
            adj[k].append((k + 1, d, 'walk'))
            adj[k + 1].append((k, d, 'walk'))
        g = ctfprofile._geodesic_progress(adj, 0, len(pts) - 1, len(pts))
        self.assertAlmostEqual(g[0], 0.0)
        self.assertAlmostEqual(g[-1], 1.0)
        # East mid node (1000, 200) is exact geodesic midpoint (0.5)
        self.assertAlmostEqual(g[3], 0.5, delta=1e-6)

    def test_count_flag_exits_distinguishes_one_vs_two_exits(self):
        # Small flag room at (0,0) with 1 corridor east vs 2 corridors (east + west)
        def make_corridor_graph(two_exits):
            adj = defaultdict(list)
            # 3-wide corridor strips so each exit shell component has >= 3 cells
            nid = {}
            idx = 0
            # Central 3x3 room around (0, 0)
            for ix in range(-1, 2):
                for iy in range(-1, 2):
                    nid[(ix, iy)] = idx
                    idx += 1
            # East corridor ix=2..10, iy=-1..1 (distance up to 160u with step=16)
            for ix in range(2, 12):
                for iy in range(-1, 2):
                    nid[(ix, iy)] = idx
                    idx += 1
            if two_exits:
                for ix in range(-11, -1):
                    for iy in range(-1, 2):
                        nid[(ix, iy)] = idx
                        idx += 1
            for (ix, iy), u in nid.items():
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    v = nid.get((ix + di, iy + dj))
                    if v is not None:
                        adj[u].append((v, 16.0))
            return nid[(0, 0)], adj

        f1, adj1 = make_corridor_graph(False)
        f2, adj2 = make_corridor_graph(True)
        self.assertEqual(ctfprofile._count_flag_exits(adj1, f1, radius=112.0), 1)
        self.assertEqual(ctfprofile._count_flag_exits(adj2, f2, radius=112.0), 2)

    def test_count_flag_exits_handles_large_open_room_and_prunes_corners(self):
        # 1024x1024 open flag room (ix,iy in [-32..32], 16u grid) with 3 corridors
        # (East, North, South) that connect into an outer midfield node, while the
        # four room corners are dead-end interiors.
        nid = {}
        idx = 0
        for ix in range(-32, 33):
            for iy in range(-32, 33):
                nid[(ix, iy)] = idx
                idx += 1
        # East corridor (width 9 cells = 128u, length 32 cells = 512u)
        for ix in range(33, 65):
            for iy in range(-4, 5):
                nid[(ix, iy)] = idx
                idx += 1
        # North corridor
        for iy in range(33, 65):
            for ix in range(-4, 5):
                nid[(ix, iy)] = idx
                idx += 1
        # South corridor
        for iy in range(-64, -32):
            for ix in range(-4, 5):
                nid[(ix, iy)] = idx
                idx += 1
        adj = defaultdict(list)
        for (ix, iy), u in nid.items():
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                v = nid.get((ix + di, iy + dj))
                if v is not None:
                    adj[u].append((v, 16.0))
        # Connect outer ends of all 3 corridors to a distant target flag node
        far_flag = idx
        for end_cell in ((64, 0), (0, 64), (0, -64)):
            u = nid[end_cell]
            adj[u].append((far_flag, 256.0))
            adj[far_flag].append((u, 256.0))

        # Adaptive shell advances past the 1024u interior and prunes the 4 room corners -> exactly 3
        self.assertEqual(ctfprofile._count_flag_exits(adj, nid[(0, 0)], target_node=far_flag), 3)

    def test_count_flag_exits_stops_at_narrow_single_doorway_before_downstream_fork(self):
        # Small flag room (192x192) with ONE narrow 96u exit east that forks N/S 512u away.
        nid = {}
        idx = 0
        for ix in range(-6, 7):
            for iy in range(-6, 7):
                nid[(ix, iy)] = idx
                idx += 1
        # Single narrow east corridor (6 cells wide = 80u) from ix=7..32
        for ix in range(7, 33):
            for iy in range(-2, 3):
                nid[(ix, iy)] = idx
                idx += 1
        # Fork north and south at ix=33..37
        for ix in range(33, 38):
            for iy in range(-20, 21):
                nid[(ix, iy)] = idx
                idx += 1
        adj = defaultdict(list)
        for (ix, iy), u in nid.items():
            for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                v = nid.get((ix + di, iy + dj))
                if v is not None:
                    adj[u].append((v, 16.0))
        far_flag = idx
        for end_cell in ((37, 20), (37, -20)):
            u = nid[end_cell]
            adj[u].append((far_flag, 256.0))
            adj[far_flag].append((u, 256.0))

        # Must report 1 (the single flag-room doorway), not 2 (the downstream fork)
        self.assertEqual(ctfprofile._count_flag_exits(adj, nid[(0, 0)], target_node=far_flag), 1)

    def test_hook_edge_kernel_respects_open_room_and_blocking_wall(self):
        # Convex box room: x in [0, 600], y in [-200, 200], z in [0, 256]
        # Hull 0 (world): inward planes for empty interior
        planes0 = [
            (1, 0, 0, 0), (-1, 0, 0, -600),
            (0, 1, 0, -200), (0, -1, 0, -200),
            (0, 0, 1, 0), (0, 0, -1, -256),
        ]
        # Hull 1 (player +/-16 xy, -24/+32 z): inset by 16 xy, +24 floor, -32 ceil
        planes1 = [
            (1, 0, 0, 16), (-1, 0, 0, -584),
            (0, 1, 0, -184), (0, -1, 0, -184),
            (0, 0, 1, 24), (0, 0, -1, -224),
        ]
        # Build combined plane table + node/clipnode trees
        pn = np.array([[a, b, c] for a, b, c, _ in planes0 + planes1], dtype=np.float64)
        pd = np.array([d for _, _, _, d in planes0 + planes1], dtype=np.float64)
        k = len(planes0)
        nplane = np.arange(k, dtype=np.int64)
        nchild = np.zeros((k, 2), dtype=np.int64)
        for i in range(k):
            nchild[i, 0] = (i + 1) if i + 1 < k else -1   # leaf 0 -> empty (-1)
            nchild[i, 1] = -2                             # leaf 1 -> solid (-2)
        lcont = np.array([-1, -2], dtype=np.int64)

        cplane = np.arange(k, 2 * k, dtype=np.int64)
        cchild = np.zeros((k, 2), dtype=np.int64)
        for i in range(k):
            cchild[i, 0] = (i + 1) if i + 1 < k else -1
            cchild[i, 1] = -2
        roots = np.array([0], dtype=np.int64)

        P = np.array([[64.0, 0.0, 0.0], [500.0, 0.0, 0.0]], dtype=np.float64)
        wp = np.array([0, 1], dtype=np.int64)
        roots0 = np.array([0], dtype=np.int64)
        hu, hv, hd = ctfprofile._build_hook_edges(
            roots, cplane, cchild, roots0, nplane, nchild, lcont, pn, pd, P, wp, 96.0, 1024.0
        )
        # Both directions (0->1 and 1->0) must have valid hook edges in the open room
        self.assertEqual(set(zip(hu, hv)), {(0, 1), (1, 0)})
        self.assertAlmostEqual(hd[0], 436.0, delta=0.5)

        # Now shrink x_max to 300 so point 1 (x=500) is behind a solid wall -> zero hook edges!
        pd_blocked = pd.copy()
        pd_blocked[1] = -300.0
        pd_blocked[k + 1] = -284.0
        hu2, hv2, _ = ctfprofile._build_hook_edges(
            roots, cplane, cchild, roots0, nplane, nchild, lcont, pn, pd_blocked, P, wp, 96.0, 1024.0
        )
        self.assertEqual(len(hu2), 0)

    def test_los_multi_blocks_through_func_wall_hull0(self):
        # World hull 0: open box x in [0, 600], y in [-200, 200], z in [0, 256] (empty inside -> leaf 0 = -1)
        # func_wall hull 0: solid slab x in [280, 320], y in [-200, 200], z in [0, 256] (solid inside -> leaf 1 = -2)
        world_planes = [
            (1, 0, 0, 0), (-1, 0, 0, -600),
            (0, 1, 0, -200), (0, -1, 0, -200),
            (0, 0, 1, 0), (0, 0, -1, -256),
        ]
        fwall_planes = [
            (1, 0, 0, 280), (-1, 0, 0, -320),
            (0, 1, 0, -200), (0, -1, 0, -200),
            (0, 0, 1, 0), (0, 0, -1, -256),
        ]
        pn = np.array([[a, b, c] for a, b, c, _ in world_planes + fwall_planes], dtype=np.float64)
        pd = np.array([d for _, _, _, d in world_planes + fwall_planes], dtype=np.float64)
        k = len(world_planes)
        nplane = np.arange(2 * k, dtype=np.int64)
        nchild = np.zeros((2 * k, 2), dtype=np.int64)
        # World tree (nodes 0..k-1): inside all planes -> leaf 0 (-1 empty), outside -> leaf 1 (-2 solid)
        for i in range(k):
            nchild[i, 0] = (i + 1) if i + 1 < k else -1
            nchild[i, 1] = -2
        # func_wall tree (nodes k..2k-1): inside all planes -> leaf 1 (-2 solid), outside -> leaf 0 (-1 empty)
        for i in range(k):
            nchild[k + i, 0] = (k + i + 1) if i + 1 < k else -2
            nchild[k + i, 1] = -1
        lcont = np.array([-1, -2], dtype=np.int64)

        # World-only LOS sees straight across the room
        self.assertTrue(ctfprofile._los_multi(
            np.array([0], dtype=np.int64), nplane, nchild, lcont, pn, pd,
            64.0, 0.0, 46.0, 500.0, 0.0, 32.0,
        ))
        # Adding the func_wall hull-0 root blocks LOS across x=280..320
        self.assertFalse(ctfprofile._los_multi(
            np.array([0, k], dtype=np.int64), nplane, nchild, lcont, pn, pd,
            64.0, 0.0, 46.0, 500.0, 0.0, 32.0,
        ))

    def test_hook_anchor_respects_max_range_cap(self):
        # Tall open box x in [0, 1400], y in [-300, 300], z in [0, 600]
        # A at x=64, B at x=1000 (936u apart): back wall at x=1400 is 1336u from A (> 1024),
        # ceiling at z=600 is > 1080u from A (> 1024) -> no anchor within 1024u!
        def make_box(x_max, z_max):
            planes0 = [
                (1, 0, 0, 0), (-1, 0, 0, -x_max),
                (0, 1, 0, -300), (0, -1, 0, -300),
                (0, 0, 1, 0), (0, 0, -1, -z_max),
            ]
            pn = np.array([[a, b, c] for a, b, c, _ in planes0], dtype=np.float64)
            pd = np.array([d for _, _, _, d in planes0], dtype=np.float64)
            k = len(planes0)
            nplane = np.arange(k, dtype=np.int64)
            nchild = np.zeros((k, 2), dtype=np.int64)
            for i in range(k):
                nchild[i, 0] = (i + 1) if i + 1 < k else -1
                nchild[i, 1] = -2
            lcont = np.array([-1, -2], dtype=np.int64)
            return np.array([0], dtype=np.int64), nplane, nchild, lcont, pn, pd

        roots0, nplane, nchild, lcont, pn, pd = make_box(1400.0, 600.0)
        self.assertFalse(ctfprofile._has_hook_anchor(
            roots0, nplane, nchild, lcont, pn, pd,
            64.0, 0.0, 0.0, 1000.0, 0.0, 0.0, 1024.0,
        ))
        # Bring the back wall inside 1024u (x_max = 1050 -> 986u from A) -> anchor valid!
        roots0, nplane, nchild, lcont, pn, pd = make_box(1050.0, 600.0)
        self.assertTrue(ctfprofile._has_hook_anchor(
            roots0, nplane, nchild, lcont, pn, pd,
            64.0, 0.0, 0.0, 1000.0, 0.0, 0.0, 1024.0,
        ))

    def test_format_report_handles_connected_and_disconnected_profiles(self):
        sample = json.loads((REPO_ROOT / 'gallery' / 'profiles' / 'ctf_refs.json').read_text(encoding='utf-8'))
        for row in sample:
            txt = ctfprofile.format_report(row)
            self.assertIn(row['map'], txt)
            self.assertIn('flags:', txt)
            self.assertNotIn('Nones', txt)

    def test_walk_time_graph_accounts_for_swim_and_teleport_costs(self):
        # 0 --(walk 320u)--> 1 --(swim 220u)--> 2 --(tele 0u)--> 3
        adj_walk = {
            0: [(1, 320.0, 'walk')],
            1: [(2, 220.0, 'swim')],
            2: [(3, 0.0, 'tele')],
            3: [],
        }
        adj_t = ctfprofile._build_walk_time_graph(adj_walk)
        wt, _, _ = ctfprofile._dijk_single(adj_t, 0, 3)
        # 320/320 + 220/220 + 0.15 = 2.15s (vs naive distance/320 = 540/320 = 1.6875s)
        self.assertAlmostEqual(wt, 1.0 + 1.0 + ctfprofile.TELE_COST_S, places=6)
        # Adding no-op/slower hook edge on top of adj_t never drops speedup below 1.0
        adj_hook = defaultdict(list, {u: list(es) for u, es in adj_t.items()})
        adj_hook[0].append((3, 5.0, 'hook'))
        ht, _, _ = ctfprofile._dijk_single(adj_hook, 0, 3)
        self.assertAlmostEqual(wt / ht, 1.0, places=6)


if __name__ == '__main__':
    unittest.main()
