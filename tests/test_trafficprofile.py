"""Self-contained traffic, graph demand, build-diff and demo-occupancy regressions."""
from collections import defaultdict
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qmap'))
sys.path.insert(0, str(ROOT / 'demos'))
HAS_NUMBA = importlib.util.find_spec('numba') is not None
if HAS_NUMBA:
    import trafficprofile as traffic
    import traffic as demo_traffic
    from test_combatprofile import _write_synthetic_arena_bsp


class TestTrafficEvidence(unittest.TestCase):
    def test_reference_records_are_aggregate_and_preserve_coverage_limits(self):
        data = json.loads((ROOT / 'gallery/traffic/reference.json').read_text())
        rows = data['maps']
        self.assertEqual({(row['map'], row['mode']) for row in rows},
                         {('dm6', 'ca'), ('ztndm3', 'ca'), ('ca_agora', 'ca'),
                          ('ctf1', 'ctf'), ('ztndm3', 'tdm'), ('ztndm3', 'ffa')})
        checked, omitted = 0, 0
        for row in rows:
            self.assertNotIn('cells', row)
            self.assertEqual(len(row['sha256']), 64)
            self.assertTrue(-1 <= row['pooled']['spearman_all'] <= 1)
            validation = row['validation']
            self.assertEqual(validation['bsp_sha256'], row['sha256'])
            for record in validation['demos']:
                self.assertEqual(len(record['sha256']), 64)
                if record['status'] == 'not_checked':
                    omitted += 1
                    self.assertIn('reason', record)
                else:
                    checked += 1
                    self.assertTrue(0 <= record['coverage']['matched_fraction'] <= 1)
                    self.assertTrue(record['windows'])
                    self.assertIn('parser_unknown', record)
        self.assertEqual((checked, omitted), (38, 2))


@unittest.skipUnless(HAS_NUMBA, 'numba required for player-hull traffic analysis')
class TestTraffic(unittest.TestCase):
    def graph(self, links, count):
        adjacency = defaultdict(list)
        for source, target, weight in links:
            adjacency[source].append((target, weight, 'walk'))
        return traffic.canonical_graph(adjacency, count)

    def pair(self, source, target, weight=1):
        return dict(source=source, target=target, weight=weight)

    def test_equal_shortest_paths_split_and_endpoints_are_separate(self):
        graph = self.graph([(0, 1, 1), (0, 2, 1), (1, 3, 1), (2, 3, 1)], 4)
        share, between, routed, missed = traffic.route_load(graph, [self.pair(0, 3)])
        np.testing.assert_allclose(share, [1, 0.5, 0.5, 1])
        np.testing.assert_allclose(between, [0, 0.5, 0.5, 0])
        self.assertEqual((routed, missed), (1, 0))

    def test_fraction_uses_path_multiplicity_not_equal_predecessor_weights(self):
        graph = self.graph([(0, 1, 1), (0, 2, 1), (0, 3, 2), (1, 4, 1),
                            (2, 4, 1), (3, 5, 1), (4, 5, 1)], 6)
        share, _, _, _ = traffic.route_load(graph, [self.pair(0, 5)])
        np.testing.assert_allclose(share[[3, 4]], [1 / 3, 2 / 3])

    def test_dependency_kernel_matches_independent_bruteforce_on_weighted_cycles(self):
        random = np.random.default_rng(73)
        for trial in range(30):
            adjacency = defaultdict(list)
            for source in range(7):
                for target in range(7):
                    if source != target and random.random() < 0.3:
                        adjacency[source].append((target, int(random.integers(1, 4)), 'walk'))
            routes = []

            def enumerate_paths(path, cost):
                if path[-1] == 6:
                    routes.append((cost, path))
                    return
                for target, weight, _ in adjacency[path[-1]]:
                    if target not in path:
                        enumerate_paths(path + [target], cost + weight)

            enumerate_paths([0], 0)
            graph = traffic.canonical_graph(adjacency, 7)
            share, _, _, missed = traffic.route_load(graph, [self.pair(0, 6)])
            with self.subTest(trial=trial):
                if not routes:
                    self.assertEqual(missed, 1)
                    continue
                minimum = min(cost for cost, _ in routes)
                shortest = [path for cost, path in routes if cost == minimum]
                expected = np.zeros(7)
                for path in shortest:
                    expected[path] += 1 / len(shortest)
                np.testing.assert_allclose(share, expected)

    def test_directed_unreachable_pairs_report_missing_mass(self):
        graph = self.graph([(0, 1, 1), (1, 2, 1)], 3)
        pairs = [self.pair(0, 2, 0.25), self.pair(2, 0, 0.75)]
        share, _, routed, missed = traffic.route_load(graph, pairs)
        np.testing.assert_allclose(share, [1, 1, 1])
        self.assertEqual((routed, missed), (0.25, 0.75))
        self.assertIsNone(pairs[1]['cost'])

    def test_parallel_edges_are_not_extra_routes_and_teleports_are_positive(self):
        graph = traffic.canonical_graph({0: [(1, 0, 'tele'), (1, 64, 'walk'), (1, 48, 'pad')]}, 2)
        self.assertEqual(graph.nnz, 1)
        self.assertEqual(graph[0, 1], 48)
        for weight in (0, -1, float('nan')):
            with self.subTest(weight=weight), self.assertRaises(ValueError):
                traffic.canonical_graph({0: [(1, weight, 'walk')]}, 2)

    def test_log_counts_survive_more_than_float_path_count_capacity(self):
        layers = 1050
        links = [(0, 1, 1), (0, 2, 1)]
        for layer in range(layers - 1):
            for source in (1 + layer * 2, 2 + layer * 2):
                for target in (3 + layer * 2, 4 + layer * 2):
                    links.append((source, target, 1))
        target = 2 * layers + 1
        links.extend([(target - 2, target, 1), (target - 1, target, 1)])
        share, _, _, _ = traffic.route_load(self.graph(links, target + 1), [self.pair(0, target)])
        self.assertTrue(np.isfinite(share).all())
        np.testing.assert_allclose(share[1:target], 0.5, atol=1e-10)

    def test_sampling_preserves_family_mass_and_is_deterministic(self):
        endpoints = [dict(id=f'spawn:{index}', node=index) for index in range(10)]
        families = {'spawns': [(first, second) for first in endpoints for second in endpoints if first != second],
                    'items': [(endpoints[0], endpoints[9])]}
        first, possible = traffic.sample_demands(families, 8, 17)
        second, _ = traffic.sample_demands(families, 8, 17)
        self.assertEqual(first, second)
        self.assertEqual((len(first), possible), (8, 91))
        for family in families:
            self.assertAlmostEqual(sum(pair['weight'] for pair in first if pair['family'] == family), 0.5)
        with self.assertRaises(ValueError):
            traffic.sample_demands(families, 1)

    def test_sampling_does_not_change_when_entity_pair_enumeration_changes(self):
        endpoints = [dict(id=f'spawn:{index}', node=index, origin=[index * 16, 0, 24]) for index in range(10)]
        demands = [(first, second) for first in endpoints for second in endpoints if first != second]
        first, _ = traffic.sample_demands({'spawns': demands}, 16, 2)
        second, _ = traffic.sample_demands({'spawns': list(reversed(demands))}, 16, 2)
        self.assertEqual(first, second)

    def test_dead_region_uses_local_graph_not_nearby_disconnected_floor(self):
        points = np.array([[index * 16 + 8, 8, 0] for index in range(10)] +
                          [[index * 16 + 8, 24, 0] for index in range(10)], dtype=float)
        links = [(index, index + 1, 16) for index in range(9)] + [(index, index + 1, 16) for index in range(10, 19)]
        local = traffic.local_graph(self.graph(links, 20), points)
        share = np.r_[np.ones(10), np.zeros(10)]
        density, dead, _, patches = traffic.region_diagnostics(local, points, share, min_region_area=256)
        self.assertEqual(sum(region['cells'] for region in dead), 10)
        self.assertTrue(np.all(density[10:] == 0))
        self.assertNotEqual(patches[0], patches[10])

    def test_hot_bridge_and_low_demand_wing_are_reported(self):
        points = np.array([[index * 16 + 8, 8, 0] for index in range(100)], dtype=float)
        links = [(index, index + 1, 16) for index in range(99)]
        local = traffic.local_graph(self.graph(links, 100), points)
        share = np.zeros(100)
        share[48:56] = 1
        _, dead, hot, _ = traffic.region_diagnostics(local, points, share, min_region_area=4096)
        self.assertEqual(len(dead), 2)
        self.assertTrue(hot)
        self.assertEqual(hot[0]['peak_route_share'], 1)
        self.assertFalse(traffic.region_diagnostics(local, points, share, betweenness=share * 0)[2])
        self.assertFalse(traffic.region_diagnostics(local, points, share * 0)[1])

    def test_base_exit_shell_preserves_two_separated_routes(self):
        points = [[8, 8, 0], [808, 8, 0]]
        links = []
        for height in (8, 136):
            route = []
            for index in range(49):
                route.append(len(points))
                points.append([24 + index * 16, height, 0])
            chain = [0] + route + [1]
            for source, target in zip(chain, chain[1:]):
                links.extend([(source, target, 16), (target, source, 16)])
        graph = self.graph(links, len(points))
        local = traffic.local_graph(graph, np.array(points))
        self.assertEqual(len(traffic.base_exits(graph, local, 0, 1)), 2)

    def test_mode_families_select_spawns_items_and_flags(self):
        points = np.array([[8, 8, 0], [24, 8, 0], [40, 8, 0]], dtype=float)
        entities = [dict(classname='info_player_deathmatch', origin=f'{position} 8 24') for position in (8, 40)]
        entities += [dict(classname='weapon_rocketlauncher', origin='8 8 8'),
                     dict(classname='item_armor2', origin='40 8 8'),
                     dict(classname='item_flag_team1', origin='8 8 16'),
                     dict(classname='item_flag_team2', origin='40 8 16')]
        navigation = dict(bsp=SimpleNamespace(ents=entities), R=np.ones(3, dtype=bool),
                          node_near=lambda horizontal, vertical, height: 0 if horizontal == 8 else 2)
        graph = self.graph([(0, 1, 16), (1, 2, 16), (2, 1, 16), (1, 0, 16)], 3)
        prepared = dict(navigation=navigation, points=points, graph=graph, local=traffic.local_graph(graph, points))
        for mode, expected in (('ca', {'spawns'}), ('tdm', {'items'}), ('ffa', {'items', 'spawns'}), ('ctf', {'flags'})):
            with self.subTest(mode=mode):
                _, families, _ = traffic.demand_endpoints(prepared, mode)
                self.assertEqual(set(families), expected)

    def test_bsp_cli_diff_png_json_and_input_protection(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first, second = directory / 'test_b1.bsp', directory / 'test_b2.bsp'
            _write_synthetic_arena_bsp(first, with_balcony=True)
            _write_synthetic_arena_bsp(second, with_balcony=False)
            output, image = directory / 'traffic.json', directory / 'traffic.png'
            with redirect_stdout(io.StringIO()):
                self.assertEqual(traffic.main(['--diff', str(first), str(second), '--mode', 'ca', '--json', str(output), '--png', str(image)]), 0)
            report = json.loads(output.read_text())
            self.assertGreater(report['diff']['removed_cells'], 0)
            self.assertGreater(report['diff']['matched_cells'], 0)
            self.assertTrue(image.read_bytes().startswith(b'\x89PNG'))
            measured = traffic.traffic_profile(first, mode='ca')
            self.assertEqual(traffic.compare(measured, measured)['mean_absolute_shift'], 0)
            renamed = json.loads(json.dumps(measured))
            identifiers = {endpoint['id']: 'renamed:' + endpoint['id'] for endpoint in renamed['endpoints']}
            for endpoint in renamed['endpoints']:
                endpoint['id'] = identifiers[endpoint['id']]
            for pair in renamed['pairs']:
                pair['from_id'], pair['to_id'] = identifiers[pair['from_id']], identifiers[pair['to_id']]
            self.assertFalse(traffic.compare(measured, renamed)['demand_changed'])
            renamed['endpoints'][0]['status'] = 'unresolved'
            self.assertTrue(traffic.compare(measured, renamed)['demand_changed'])
            original = first.read_bytes()
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                traffic.main([str(first), '--json', str(first)])
            self.assertEqual(caught.exception.code, 2)
            self.assertEqual(first.read_bytes(), original)

    def test_insufficient_demand_never_calls_zero_traffic_a_dead_wing(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'single.bsp'
            _write_synthetic_arena_bsp(path, with_balcony=False)
            report = traffic.traffic_profile(path, mode='tdm')
            self.assertEqual(report['dead_wings'], [])
            self.assertEqual(report['overloaded_chokes'], [])
            self.assertEqual(report['coverage']['routed_weight'], 0)
            self.assertTrue(report['coverage']['warnings'])
            with self.assertRaises(ValueError):
                traffic.traffic_profile(path, seed=-1)

    def test_draw_computes_an_omitted_before_after_comparison(self):
        report = dict(map='floor', mode='ca', sha256='0' * 64, settings={}, endpoints=[], pairs=[],
                      cells=dict(points=[[8, 8, 0]], reachable=[True], route_share=[0.25]))
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'comparison.png'
            traffic.draw(report, destination, before=report)
            self.assertTrue(destination.read_bytes().startswith(b'\x89PNG'))
            incompatible = dict(report, mode='ctf')
            with self.assertRaisesRegex(ValueError, 'identical modes'):
                traffic.draw(report, destination, before=incompatible)

    def test_no_floor_bsp_reports_missing_coverage_without_nan_or_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'solid.bsp'
            _write_synthetic_arena_bsp(path, with_balcony=False, cover_box=(0, 0, 0, 512, 512, 320))
            report = traffic.traffic_profile(path, mode='ca')
            self.assertEqual(report['coverage']['reachable_cells'], 0)
            self.assertEqual(report['dead_wings'], [])
            json.dumps(report, allow_nan=False)


@unittest.skipUnless(HAS_NUMBA, 'numba required for demo/traffic integration')
class TestDemoTraffic(unittest.TestCase):
    def test_windows_exclude_warmup_and_refuse_silent_whole_demo_fallback(self):
        prints = [(5, 'round [1] starts in 5'), (20, 'sco  damg'), (23, 'round [2] starts in 5'), (40, 'sco damg')]
        windows, _ = demo_traffic.play_windows(prints, 60, 'ca')
        self.assertEqual(windows, [(10, 20), (28, 40)])
        self.assertEqual(demo_traffic.play_windows([(10, 'match has begun'), (30, 'match is over')], 40, 'ctf')[0], [(10, 30)])
        with self.assertRaises(ValueError):
            demo_traffic.play_windows([], 40, 'ca')
        self.assertEqual(demo_traffic.play_windows([], 40, 'ca', 5, 10)[0], [(5, 10)])

    def test_occupancy_weights_seconds_excludes_death_gaps_and_wrong_floor(self):
        report = dict(mode='ca', cells=dict(points=[[8, 8, 0], [8, 8, 128]], reachable=[True, True]))
        players = {0: dict(name='player', team='red')}
        track = [(0, 0, 8, 8, 24, 0), (0.1, 0, 8, 8, 24, 0),
                 (0.2, 0, 8, 8, 152, 1), (1, 0, 8, 8, 152, 0), (1.1, 0, 8, 8, 152, 0)]
        seconds, coverage = demo_traffic.occupancy(report, track, players, [(0.05, 1.05)])
        np.testing.assert_allclose(seconds, [0.05, 0.05])
        self.assertEqual(coverage['matched_fraction'], 1)

    def test_restarted_matches_do_not_pair_an_aborted_start_with_a_later_end(self):
        prints = [(10, 'Match has begun'), (50, 'Match has begun'), (100, 'Match is over')]
        for mode in ('tdm', 'ffa', 'ctf'):
            with self.subTest(mode=mode):
                self.assertEqual(demo_traffic.play_windows(prints, 120, mode)[0], [(50, 100)])
        prints = [(5, 'match has begun'), (20, 'match is over'), (30, 'match has begun'),
                  (60, 'match has begun'), (90, 'match is over'), (95, 'match has begun')]
        self.assertEqual(demo_traffic.play_windows(prints, 120, 'tdm')[0], [(5, 20), (60, 90)])
        with self.assertRaisesRegex(ValueError, 'no complete'):
            demo_traffic.play_windows([(5, 'match has begun'), (30, 'match has begun')], 120, 'ctf')

    def test_rank_correlation_handles_ties_and_constant_predictions(self):
        report = dict(cells=dict(patch=np.repeat(np.arange(4), 4).tolist(), route_share=np.repeat([0, 0.1, 0.2, 0.3], 4).tolist()))
        result = demo_traffic.rank_comparison(report, np.repeat([0, 1, 2, 3], 4))
        self.assertEqual(result['spearman_all'], 1)
        report['cells']['route_share'] = [0] * 16
        self.assertIsNone(demo_traffic.rank_comparison(report, np.ones(16))['spearman_all'])

    def test_real_mvd_parser_validation_cli_and_incomplete_recording(self):
        def block(payload, milliseconds=100):
            return struct.pack('<BBi', milliseconds, 6, len(payload)) + payload

        def message(text):
            return bytes([8, 2]) + text.encode() + b'\0'

        def position(horizontal):
            return struct.pack('<BBHBhhh', 42, 0, 7, 0, horizontal * 8, 256 * 8, 24 * 8)

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bsp, demo = directory / 'arena.bsp', directory / 'ctf_[arena].mvd'
            _write_synthetic_arena_bsp(bsp, with_balcony=False)
            user = bytes([40, 0]) + struct.pack('<i', 1) + b'\\name\\player\\team\\red\0'
            encoded = block(user + message('match has begun'), 0)
            encoded += b''.join(block(position(64 + index * 16)) for index in range(10))
            encoded += block(message('match is over'))
            demo.write_bytes(encoded)
            report = traffic.traffic_profile(bsp, mode='ctf')
            result = demo_traffic.validate(report, [demo], png=directory / 'observed.png')
            self.assertEqual(result['demos'][0]['status'], 'checked')
            self.assertGreater(result['demos'][0]['coverage']['matched_player_seconds'], 0)
            self.assertTrue((directory / 'observed.png').read_bytes().startswith(b'\x89PNG'))
            with self.assertRaisesRegex(ValueError, 'duplicate demo'):
                demo_traffic.validate(report, [demo, demo])
            incomplete = directory / 'incomplete.mvd'
            incomplete.write_bytes(block(user + position(128)))
            skipped = demo_traffic.validate(report, [incomplete], skip_incomplete=True)
            self.assertEqual(skipped['demos'][0]['status'], 'not_checked')
            output = directory / 'validation.json'
            with redirect_stdout(io.StringIO()):
                self.assertEqual(demo_traffic.main([str(bsp), str(demo), '--mode', 'ctf', '--json', str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())['demos'][0]['status'], 'checked')
            incomplete.write_bytes(bytes([0, 6, 0]))
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                demo_traffic.main([str(bsp), str(incomplete), '--mode', 'ctf', '--json', str(output)])
            self.assertEqual(caught.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
