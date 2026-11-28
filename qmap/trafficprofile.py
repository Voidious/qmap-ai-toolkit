"""Demand-weighted traffic on vprofile's directed BSP29 player-hull floor graph.

Usage: python3 qmap/trafficprofile.py map.bsp --mode ca --json traffic.json --png traffic.png
       python3 qmap/trafficprofile.py --diff map_b1.bsp map_b2.bsp --mode ffa --png shift.png
Topology diagnostics are advisory, not observed player behavior. See TRAFFICPROFILE.md.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import struct

import numpy as np
from numba import njit
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

import itemprofile
import vprofile


MODES = ('auto', 'ca', 'tdm', 'ffa', 'ctf')
TELE_COST = 48.0


def canonical_graph(adjacency, count):
    destinations, weights, offsets = [], [], [0]
    for source in range(count):
        minimum = {}
        for target, cost, kind in adjacency.get(source, ()):
            weight = TELE_COST if kind == 'tele' else float(cost)
            if not 0 <= target < count or not math.isfinite(weight) or weight <= 0:
                raise ValueError('navigation edges require valid destinations and positive finite costs')
            if target != source:
                minimum[target] = min(minimum.get(target, math.inf), weight)
        for target, weight in sorted(minimum.items()):
            destinations.append(target)
            weights.append(weight)
        offsets.append(len(destinations))
    return csr_matrix((np.array(weights, dtype=float), np.array(destinations, dtype=np.int32),
                       np.array(offsets, dtype=np.int32)), shape=(count, count))


@njit(cache=True)
def _dependencies(offsets, destinations, weights, distances, source, target_mass):
    """Target-weighted Brandes accumulation using logarithmic shortest-path counts."""
    order = np.argsort(distances)
    log_counts = np.full(len(distances), -np.inf)
    log_counts[source] = 0.0
    for node in order:
        if not np.isfinite(distances[node]):
            break
        for edge in range(offsets[node], offsets[node + 1]):
            target = destinations[edge]
            if distances[target] > distances[node] and abs(distances[node] + weights[edge] - distances[target]) <= 1e-7:
                log_counts[target] = np.logaddexp(log_counts[target], log_counts[node])
    load = target_mass.copy()
    for index in range(len(order) - 1, -1, -1):
        node = order[index]
        if not np.isfinite(distances[node]):
            continue
        for edge in range(offsets[node], offsets[node + 1]):
            target = destinations[edge]
            if distances[target] > distances[node] and abs(distances[node] + weights[edge] - distances[target]) <= 1e-7:
                load[node] += math.exp(log_counts[node] - log_counts[target]) * load[target]
    between = load - target_mass
    between[source] = 0.0
    return load, between


def route_load(graph, pairs):
    count = graph.shape[0]
    share, between = np.zeros(count), np.zeros(count)
    grouped = defaultdict(list)
    for pair in pairs:
        grouped[pair['source']].append(pair)
    routed, missed = 0.0, 0.0
    for source, demands in sorted(grouped.items()):
        distances = dijkstra(graph, directed=True, indices=source)
        mass = np.zeros(count)
        for pair in demands:
            target, weight = pair['target'], pair['weight']
            if np.isfinite(distances[target]):
                mass[target] += weight
                routed += weight
                pair['cost'] = round(float(distances[target]), 4)
            else:
                missed += weight
                pair['cost'] = None
        if mass.any():
            load, centrality = _dependencies(graph.indptr, graph.indices, graph.data, distances, source, mass)
            share += load
            between += centrality
    if routed:
        share /= routed
        between /= routed
    return share, between, routed, missed


def local_graph(graph, points):
    source, target = graph.nonzero()
    delta = np.abs(points[source] - points[target])
    keep = (delta[:, :2].max(axis=1) <= 16.01) & (delta[:, 2] <= 44.01)
    local = csr_matrix((np.ones(int(keep.sum())), (source[keep], target[keep])), shape=graph.shape)
    return local.maximum(local.T)


def components(graph, selected):
    indices = np.flatnonzero(selected)
    if not len(indices):
        return []
    count, labels = connected_components(graph[indices][:, indices], directed=False)
    groups = [[] for _ in range(count)]
    for node, label in zip(indices, labels):
        groups[label].append(int(node))
    return groups


def floor_patches(local, points, grid=128):
    buckets = np.column_stack((np.floor(points[:, :2] / grid), np.floor((points[:, 2] + 1) / 64))).astype(int)
    source, target = local.nonzero()
    keep = np.all(buckets[source] == buckets[target], axis=1)
    restricted = csr_matrix((np.ones(int(keep.sum())), (source[keep], target[keep])), shape=local.shape)
    _, labels = connected_components(restricted, directed=False)
    return labels


def region_diagnostics(local, points, share, *, patch_grid=128, dead_fraction=0.05,
                       choke_multiple=4, choke_share=0.25, min_region_area=16384, betweenness=None):
    if not len(points):
        return np.zeros(0), [], [], np.zeros(0, dtype=int)
    labels = floor_patches(local, points, patch_grid)
    mean = np.bincount(labels, weights=share) / np.bincount(labels)
    average = float(share.mean())
    density = mean[labels] / average if average else np.zeros(len(points))
    internal = share if betweenness is None else betweenness

    def summarize(selected, minimum):
        regions = []
        for members in components(local, selected):
            if len(members) * 256 < minimum:
                continue
            sub = points[members]
            regions.append(dict(cells=len(members), area=len(members) * 256,
                                center=sub.mean(axis=0).round(2).tolist(),
                                bounds=[sub.min(axis=0).tolist(), sub.max(axis=0).tolist()],
                                mean_relative_density=round(float(density[members].mean()), 6),
                                peak_route_share=round(float(share[members].max()), 6),
                                peak_betweenness=round(float(internal[members].max()), 6),
                                node_indices=members))
        return sorted(regions, key=lambda region: (-region['area'], region['center']))

    dead = summarize(density <= dead_fraction, min_region_area) if average else []
    peak = np.zeros(len(mean))
    np.maximum.at(peak, labels, internal)
    hot = (density >= choke_multiple) & (peak[labels] >= choke_share)
    chokes = summarize(hot, 256) if average else []
    return density, dead, chokes, labels


def base_exits(graph, local, flag, enemy, radius=384):
    distances = dijkstra(graph, directed=True, indices=flag)
    outer = np.isfinite(distances) & (distances >= radius - 16)
    candidates = np.flatnonzero(outer)
    if enemy not in candidates:
        return []
    sub = graph[candidates][:, candidates]
    enemy_index = int(np.flatnonzero(candidates == enemy)[0])
    can_continue = np.isfinite(dijkstra(sub.T.tocsr(), directed=True, indices=enemy_index))
    shell = np.zeros(graph.shape[0], dtype=bool)
    shell[candidates] = can_continue & (distances[candidates] <= radius + 32)
    exits = []
    for group in components(local, shell):
        if len(group) >= 3:
            exits.append(min(group, key=lambda node: (abs(distances[node] - radius), node)))
    return sorted(exits)


def demand_endpoints(prepared, mode):
    navigation, points, graph, local = (prepared[key] for key in ('navigation', 'points', 'graph', 'local'))
    bsp = navigation['bsp']
    endpoints, warnings = [], []
    groups = defaultdict(list)

    def add(label, family, coordinates, node):
        valid = node is not None and bool(navigation['R'][node])
        record = dict(id=label, family=family, origin=np.asarray(coordinates).tolist(),
                      node=int(node) if valid else None, status='mapped' if valid else 'unresolved')
        endpoints.append(record)
        if valid:
            groups[family].append(record)

    if mode in ('ca', 'ffa'):
        for index, entity in enumerate(bsp.ents):
            if entity.get('classname') == 'info_player_deathmatch' and not int(entity.get('spawnflags', 0)) & 2048:
                position = vprofile.origin(entity)
                add(f'spawn:{index}', 'spawns', position, navigation['node_near'](*position))
    if mode in ('tdm', 'ffa'):
        inventory, _ = itemprofile.inventory(bsp.ents)
        for item in inventory:
            if item['kind'] in itemprofile.KEYS:
                _, node = itemprofile.project(item, dict(points=points, reachable=navigation['R'], bsp=bsp))
                add(item['id'], 'items', item['origin'], node)
    if mode == 'ctf':
        for team in (1, 2):
            entity = next((entity for entity in bsp.ents if entity.get('classname') == f'item_flag_team{team}'), None)
            if entity is None:
                warnings.append(f'missing item_flag_team{team}')
                continue
            position = vprofile.origin(entity)
            candidates = np.flatnonzero(navigation['R'] & (np.abs(points[:, :2] - position[:2]).max(axis=1) <= 64)
                                        & (np.abs(points[:, 2] - (position[2] - 16)) <= 96))
            node = min(candidates, key=lambda node: np.linalg.norm(points[node] - position + [0, 0, 16])) if len(candidates) else None
            add(f'flag:{team}', 'flags', position, node)
        if len(groups['flags']) == 2:
            first, second = groups['flags']
            for own, enemy in ((first, second), (second, first)):
                for index, node in enumerate(base_exits(graph, local, own['node'], enemy['node'])):
                    add(f"{own['id']}:exit:{index}", own['id'] + ':exits', points[node], node)
            if not groups['flag:1:exits'] or not groups['flag:2:exits']:
                warnings.append('base-exit shell unavailable for one or both bases; flag routes still measured')
    families = {}
    if len(endpoints) > 512:
        raise ValueError('more than 512 demand endpoints; reduce endpoint count')

    def pairs(first, second, same=False):
        return [(source, target) for source in first for target in second
                if source['node'] != target['node'] and (not same or source['id'] != target['id'])]

    for family in ('spawns', 'items', 'flags'):
        if family in groups:
            families[family] = pairs(groups[family], groups[family], True)
    if len(groups['flags']) == 2:
        first, second = groups['flags']
        exits_first, exits_second = groups['flag:1:exits'], groups['flag:2:exits']
        families['base-exits'] = pairs([first], exits_first) + pairs(exits_first, [first]) + pairs([second], exits_second) + pairs(exits_second, [second])
        families['cross-base'] = pairs(exits_first, exits_second) + pairs(exits_second, exits_first)
    families = {family: demands for family, demands in families.items() if demands}
    expected = {'ca': ('spawns',), 'tdm': ('items',), 'ffa': ('spawns', 'items'),
                'ctf': ('flags', 'base-exits', 'cross-base')}
    warnings.extend(f'no usable {family} demand pairs' for family in expected[mode] if family not in families)
    return endpoints, families, warnings


def sample_demands(families, maximum=256, seed=0):
    if maximum < len(families):
        raise ValueError('max-pairs must permit at least one pair per demand family')
    total = sum(len(pairs) for pairs in families.values())
    if total > 1000000:
        raise ValueError('more than one million demand pairs; reduce endpoint count')
    allocation = {family: 1 for family in families}
    remaining = min(maximum, total) - len(families)
    while remaining > 0:
        candidates = [family for family in families if allocation[family] < len(families[family])]
        selected = min(candidates, key=lambda family: (allocation[family] / len(families[family]), family))
        allocation[selected] += 1
        remaining -= 1
    random = np.random.default_rng(seed)
    selected_pairs = []
    for family, demands in sorted(families.items()):
        demands = sorted(demands, key=lambda pair: (tuple(pair[0].get('origin', (pair[0]['node'],))),
                                                   tuple(pair[1].get('origin', (pair[1]['node'],))),
                                                   pair[0]['id'], pair[1]['id']))
        count = allocation[family]
        for index in sorted(random.choice(len(demands), count, replace=False)):
            source, target = demands[index]
            selected_pairs.append(dict(source=source['node'], target=target['node'], from_id=source['id'],
                                       to_id=target['id'], family=family, weight=1 / (len(families) * count)))
    return selected_pairs, total


def prepare(path, max_nodes=150000):
    path = Path(path)
    encoded = path.read_bytes()
    if len(encoded) < 124 or struct.unpack_from('<i', encoded)[0] != 29:
        raise ValueError(f'{path}: only BSP29 is supported')
    navigation = vprofile.build_floor_graph(str(path))
    if len(navigation['nodes']) > max_nodes:
        raise ValueError(f'{path}: floor graph exceeds {max_nodes} node budget')
    if path.read_bytes() != encoded:
        raise ValueError(f'{path}: BSP changed while reading; rerun on a stable build')
    points = np.array([(navigation['x0'] + column * 16 + 8, navigation['y0'] + row * 16 + 8, floor)
                       for column, row, floor in navigation['nodes']], dtype=float).reshape(-1, 3)
    graph = canonical_graph(navigation['adj'], len(points))
    walking = canonical_graph({node: [edge for edge in edges if edge[2] in ('walk', 'jump', 'drop')]
                               for node, edges in navigation['adj'].items()}, len(points))
    return dict(path=str(path), sha256=hashlib.sha256(encoded).hexdigest(), navigation=navigation,
                points=points, graph=graph, local=local_graph(walking, points))


def analyze(prepared, *, mode='auto', max_pairs=256, seed=0, patch_grid=128,
            dead_fraction=0.05, choke_multiple=4, choke_share=0.25, min_region_area=16384):
    if mode not in MODES or not 1 <= max_pairs <= 4096 or seed < 0:
        raise ValueError('invalid mode, seed, or max-pairs (1..4096)')
    if not np.isfinite([patch_grid, dead_fraction, choke_multiple, choke_share, min_region_area]).all() or patch_grid < 16 or not 0 <= dead_fraction < 1 or choke_multiple <= 1 or not 0 < choke_share <= 1 or min_region_area < 256:
        raise ValueError('invalid patch grid or diagnostic thresholds')
    navigation, points = prepared['navigation'], prepared['points']
    if mode == 'auto':
        mode = 'ctf' if any(entity.get('classname') == 'item_flag_team1' for entity in navigation['bsp'].ents) else 'ffa'
    endpoints, families, warnings = demand_endpoints(prepared, mode)
    pairs, possible = sample_demands(families, max_pairs, seed)
    share, between, routed, missed = route_load(prepared['graph'], pairs)
    reachable = np.asarray(navigation['R'], dtype=bool)
    active = np.flatnonzero(reachable)
    local = prepared['local'][active][:, active]
    density, dead, chokes, labels = region_diagnostics(local, points[active], share[active], patch_grid=patch_grid,
        dead_fraction=dead_fraction, choke_multiple=choke_multiple, choke_share=choke_share,
        min_region_area=min_region_area, betweenness=between[active])
    for region in dead + chokes:
        region['node_indices'] = active[region['node_indices']].tolist()
    full_density, full_labels = np.zeros(len(points)), np.full(len(points), -1, dtype=int)
    full_density[active], full_labels[active] = density, labels
    if not routed:
        warnings.append('no routed demand; dead-wing/choke diagnostics unavailable, not a clean bill of health')
    if missed:
        warnings.append('some directed demand pairs are unreachable; scores condition on routed demand')
    unresolved = [endpoint['id'] for endpoint in endpoints if endpoint['node'] is None]
    if unresolved:
        warnings.append(f'{len(unresolved)} endpoints have no reachable supported stance')
    return dict(map=Path(prepared['path']).stem, input=prepared['path'], sha256=prepared['sha256'], mode=mode,
                settings=dict(max_pairs=max_pairs, seed=seed, patch_grid=patch_grid, dead_fraction=dead_fraction,
                              choke_multiple=choke_multiple, choke_share=choke_share, min_region_area=min_region_area),
                coverage=dict(floor_cells=len(points), reachable_cells=int(reachable.sum()), possible_pairs=possible,
                              sampled_pairs=len(pairs), routed_weight=round(routed, 9), unreachable_weight=round(missed, 9),
                              unresolved_endpoints=unresolved, warnings=warnings),
                endpoints=endpoints, pairs=pairs, dead_wings=dead, overloaded_chokes=chokes,
                cells=dict(points=points.tolist(), reachable=reachable.tolist(), route_share=share.tolist(),
                           betweenness=between.tolist(), relative_density=full_density.tolist(), patch=full_labels.tolist()))


def traffic_profile(path, **settings):
    return analyze(prepare(path), **settings)


def compare(before, after):
    if before['mode'] != after['mode'] or before['settings'] != after['settings']:
        raise ValueError('traffic diffs require identical modes and settings')

    def keys(report):
        return {(round(point[0], 4), round(point[1], 4), round(point[2] / 4)): index
                for index, point in enumerate(report['cells']['points']) if report['cells']['reachable'][index]}

    first, second = keys(before), keys(after)
    common = sorted(first.keys() & second.keys())
    changes = [after['cells']['route_share'][second[key]] - before['cells']['route_share'][first[key]] for key in common]
    def demand_signature(report):
        endpoints = {endpoint['id']: endpoint for endpoint in report['endpoints']}
        identity = sorted((endpoint['family'], tuple(endpoint['origin']), endpoint['status']) for endpoint in endpoints.values())
        demands = sorted((pair['family'], tuple(endpoints[pair['from_id']]['origin']),
                          tuple(endpoints[pair['to_id']]['origin']), pair['weight']) for pair in report['pairs'])
        return identity, demands

    return dict(before=before['map'], after=after['map'], before_sha256=before['sha256'], after_sha256=after['sha256'], mode=after['mode'],
                matched_cells=len(common), added_cells=len(second.keys() - first.keys()),
                removed_cells=len(first.keys() - second.keys()), demand_changed=demand_signature(before) != demand_signature(after),
                mean_absolute_shift=float(np.mean(np.abs(changes))) if changes else None,
                changes=[dict(point=after['cells']['points'][second[key]], delta=delta) for key, delta in zip(common, changes)],
                added_points=[after['cells']['points'][second[key]] for key in sorted(second.keys() - first.keys())],
                removed_points=[before['cells']['points'][first[key]] for key in sorted(first.keys() - second.keys())])


def draw(report, destination, before=None, difference=None, heatmap_gamma=0.5):
    if not math.isfinite(heatmap_gamma) or heatmap_gamma <= 0:
        raise ValueError('heatmap gamma must be positive and finite')
    if before is not None and difference is None:
        difference = compare(before, report)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize, PowerNorm

    points = np.asarray(report['cells']['points'], dtype=float).reshape(-1, 3)
    reachable = np.asarray(report['cells']['reachable'], dtype=bool)
    selected = points[reachable]
    if before:
        old_points = np.asarray(before['cells']['points'], dtype=float).reshape(-1, 3)
        selected = np.vstack((selected, old_points[np.asarray(before['cells']['reachable'], dtype=bool)]))
    bands = sorted(set(np.floor((selected[:, 2] + 1) / 128).astype(int))) if len(selected) else [0]
    if len(bands) > 32:
        raise ValueError('more than 32 floor slices; render a smaller vertical extent')
    columns = 3 if before else 1
    figure, axes = plt.subplots(len(bands), columns, figsize=(6 * columns, 4 * len(bands)), squeeze=False)
    maximum = max(max(report['cells']['route_share'], default=0), max(before['cells']['route_share'], default=0) if before else 0, 1e-9)
    limit = max((abs(item['delta']) for item in difference['changes']), default=0) if difference else 0
    limit = max(limit, 1e-9)
    for row, band in enumerate(bands):
        for column, current in enumerate((before, report) if before else (report,)):
            axis = axes[row, column]
            coords = np.asarray(current['cells']['points'], dtype=float).reshape(-1, 3)
            keep = np.asarray(current['cells']['reachable'], dtype=bool) & (np.floor((coords[:, 2] + 1) / 128) == band)
            values = np.asarray(current['cells']['route_share'])[keep]
            dots = axis.scatter(coords[keep, 0], coords[keep, 1], c=values, s=7, marker='s', cmap='inferno', norm=PowerNorm(heatmap_gamma, vmin=0, vmax=maximum))
            axis.set_title(f"{current['map']} ({current['mode']}), Z {band * 128}..{(band + 1) * 128}")
            figure.colorbar(dots, ax=axis, label=f'route share (color gamma {heatmap_gamma:g})')
        if before:
            axis = axes[row, 2]
            changed = [item for item in difference['changes'] if math.floor((item['point'][2] + 1) / 128) == band]
            dots = axis.scatter([item['point'][0] for item in changed], [item['point'][1] for item in changed],
                                c=[item['delta'] for item in changed], cmap='coolwarm', norm=Normalize(-limit, limit), s=7, marker='s')
            for name in ('added_points', 'removed_points'):
                coords = np.array([point for point in difference[name] if math.floor((point[2] + 1) / 128) == band]).reshape(-1, 3)
                style = dict(marker='o', facecolors='none', edgecolors='green', s=28, linewidths=1, zorder=4) if name == 'added_points' else dict(marker='x', color='gray', s=8, zorder=5)
                axis.scatter(coords[:, 0], coords[:, 1], **style, label=name.replace('_points', ' floor'))
            axis.set_title('After minus before; matched floor only')
            axis.legend(fontsize=7)
            figure.colorbar(dots, ax=axis, label='route-share shift')
        for axis in axes[row]:
            axis.set_aspect('equal')
            axis.set_xlabel('world X')
            axis.set_ylabel('world Y')
            if len(selected):
                axis.set_xlim(selected[:, 0].min() - 32, selected[:, 0].max() + 32)
                axis.set_ylim(selected[:, 1].min() - 32, selected[:, 1].max() + 32)
    figure.tight_layout()
    figure.savefig(destination, dpi=130)
    plt.close(figure)


def format_report(report):
    coverage = report['coverage']
    lines = [f"{report['map']} ({report['mode']}): {coverage['reachable_cells']}/{coverage['floor_cells']} reachable cells; "
             f"{coverage['sampled_pairs']}/{coverage['possible_pairs']} demand pairs; routed mass {coverage['routed_weight']:.3f}"]
    for title, key in (('PREDICTED DEAD WINGS', 'dead_wings'), ('OVERLOADED CHOKE CANDIDATES', 'overloaded_chokes')):
        lines.append(f'{title}: {len(report[key])}')
        for region in report[key][:5]:
            lines.append(f"  {region['area']} sq u at {region['center']}; density {region['mean_relative_density']:.3f}x, peak route share {region['peak_route_share']:.3f}, internal {region['peak_betweenness']:.3f}")
    lines.extend('NOT ESTABLISHED: ' + warning for warning in coverage['warnings'])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bsps', nargs='*')
    parser.add_argument('--diff', nargs=2, metavar=('BEFORE', 'AFTER'))
    parser.add_argument('--mode', choices=MODES, default='auto')
    parser.add_argument('--max-pairs', type=int, default=256)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--patch-grid', type=float, default=128)
    parser.add_argument('--dead-fraction', type=float, default=0.05)
    parser.add_argument('--choke-multiple', type=float, default=4)
    parser.add_argument('--choke-share', type=float, default=0.25)
    parser.add_argument('--min-region-area', type=float, default=16384)
    parser.add_argument('--heatmap-gamma', type=float, default=0.5, help='positive PNG color gamma (default sqrt; 1 restores linear)')
    parser.add_argument('--json')
    parser.add_argument('--png')
    parser.add_argument('--png-dir')
    args = parser.parse_args(argv)
    if not math.isfinite(args.heatmap_gamma) or args.heatmap_gamma <= 0:
        parser.error('--heatmap-gamma must be positive and finite')
    paths = args.diff or args.bsps
    if not paths or args.diff and args.bsps or args.png and args.png_dir or args.png and not args.diff and len(paths) != 1:
        parser.error('provide BSPs or --diff; --png requires one analysis; choose --png or --png-dir')
    destinations = [Path(value) for value in (args.json, args.png) if value]
    if args.png_dir:
        names = [f'{Path(path).stem}.traffic.png' for path in paths] if not args.diff else [f'{Path(paths[0]).stem}_vs_{Path(paths[1]).stem}.traffic.png']
        destinations.extend(Path(args.png_dir) / name for name in names)
    inputs = {Path(path).resolve() for path in paths}
    if any(destination.resolve() in inputs for destination in destinations) or len({destination.resolve() for destination in destinations}) != len(destinations):
        parser.error('outputs must be distinct and cannot overwrite BSP inputs')
    settings = {key: getattr(args, key) for key in ('mode', 'max_pairs', 'seed', 'patch_grid', 'dead_fraction', 'choke_multiple', 'choke_share', 'min_region_area')}
    try:
        reports = [traffic_profile(path, **settings) for path in paths]
        difference = compare(*reports) if args.diff else None
        for report in reports:
            print(format_report(report))
        if difference:
            mean_shift = difference['mean_absolute_shift']
            shift_label = f'{mean_shift:.6g}' if mean_shift is not None else 'n/a (no matched floor)'
            print(f"TRAFFIC SHIFT: {difference['matched_cells']} matched, +{difference['added_cells']}/-{difference['removed_cells']} floor cells; mean absolute shift {shift_label}")
            if difference['demand_changed']:
                print('DEMAND CHANGED: endpoints differ; this is not a geometry-only comparison')
        for destination in destinations:
            destination.parent.mkdir(parents=True, exist_ok=True)
        if args.json:
            payload = dict(before=reports[0], after=reports[1], diff=difference) if args.diff else reports[0] if len(reports) == 1 else reports
            Path(args.json).write_text(json.dumps(payload, indent=2, allow_nan=False) + '\n')
        pngs = destinations[1 if args.json else 0:]
        for index, destination in enumerate(pngs):
            draw(reports[-1] if args.diff else reports[index], destination,
                 before=reports[0] if args.diff else None, difference=difference, heatmap_gamma=args.heatmap_gamma)
    except (OSError, ValueError, AssertionError, IndexError, struct.error) as error:
        parser.error(str(error))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
