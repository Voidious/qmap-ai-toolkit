"""Inventory and relative pickup placement on BSP29 maps; diagnostics, not balance scores."""
import argparse
from collections import Counter
import hashlib
import itertools
import json
import math
from pathlib import Path
import struct

import numpy as np

from vprofile import BSP, _los, origin, profile


KINDS = {
    'item_armorInv': 'RA', 'item_armor2': 'YA', 'item_armor1': 'GA',
    'weapon_rocketlauncher': 'RL', 'weapon_lightning': 'LG',
    'weapon_grenadelauncher': 'GL', 'weapon_supershotgun': 'SSG',
    'weapon_supernailgun': 'SNG', 'weapon_nailgun': 'NG',
    'item_artifact_super_damage': 'QUAD', 'item_artifact_invulnerability': 'PENT',
    'item_artifact_invisibility': 'RING', 'item_rockets': 'rockets',
    'item_cells': 'cells', 'item_spikes': 'nails', 'item_shells': 'shells',
}
CORNER = {'item_health', 'item_rockets', 'item_cells', 'item_spikes', 'item_shells'}
AMMO = {'rockets': (5, 10), 'cells': (6, 12), 'nails': (25, 50), 'shells': (20, 40)}
MATCHING = {'rockets': {'RL', 'GL'}, 'cells': {'LG'}, 'nails': {'SNG', 'NG'}, 'shells': {'SSG'}}
KEYS = {'RL', 'LG', 'RA', 'YA', 'GA', 'MH', 'QUAD', 'PENT', 'RING'}
ARMOR_HEALTH = {'RA', 'YA', 'GA', 'MH'}


def inventory(entities):
    counts = Counter()
    items, excluded = [], []
    for entity_index, entity in enumerate(entities):
        classname = entity.get('classname', '')
        if not classname.startswith(('item_', 'weapon_')):
            continue
        flags = int(entity.get('spawnflags', 0))
        kind = KINDS.get(classname, classname)
        if classname == 'item_health':
            kind = 'H15' if flags & 1 else 'MH' if flags & 2 else 'H25'
        coordinates = origin(entity)
        if coordinates.shape != (3,) or not np.isfinite(coordinates).all():
            raise ValueError(f'Invalid item origin at entity {entity_index}')
        center = coordinates[:2] + (16 if classname in CORNER else 0)
        record = dict(entity_index=entity_index, classname=classname, kind=kind, spawnflags=flags,
                      origin=coordinates.tolist(), center_xy=center.tolist(),
                      override_fields={key: entity[key] for key in ('count', 'aflag', 'healamount', 'armorvalue') if key in entity})
        if flags & 2048:
            excluded.append(record)
            continue
        counts[kind] += 1
        record['id'] = f'{kind}{counts[kind]}'
        items.append(record)
    return items, excluded


def prepare(path, inventory_only=False):
    path = Path(path)
    encoded = path.read_bytes()
    if len(encoded) < 124 or struct.unpack_from('<i', encoded)[0] != 29:
        raise ValueError(f'{path}: only Quake BSP29 is supported')
    if inventory_only:
        result = dict(path=path, sha256=hashlib.sha256(encoded).hexdigest(), bsp=BSP(str(path)))
        if path.read_bytes() != encoded:
            raise ValueError(f'{path}: BSP changed while reading; rerun on a stable build')
        return result
    measured = profile(str(path), with_navigation=True)
    if path.read_bytes() != encoded:
        raise ValueError(f'{path}: BSP changed while profiling; rerun on a stable build')
    navigation = measured.pop('_navigation')
    drawing = measured.pop('_draw')
    measured.pop('_check')
    points = np.array([[drawing['x0'] + column * 16 + 8, drawing['y0'] + row * 16 + 8, floor]
                       for column, row, floor in drawing['nodes']], dtype=float)
    return dict(path=path, sha256=hashlib.sha256(encoded).hexdigest(), bsp=navigation['bsp'],
                navigation=navigation, profile=measured, points=points,
                reachable=np.asarray(drawing['R'], dtype=bool))


def world_visible(bsp, first, second):
    return bool(_los(int(bsp.models[0]['h'][0]), bsp.nplane, bsp.nchild, bsp.lcont,
                     bsp.pn, bsp.pd, *map(float, first), *map(float, second)))


def project(item, prepared):
    points, reachable = prepared['points'], prepared['reachable']
    center = np.array(item['center_xy'])
    bottom = item['origin'][2] - (24 if item['classname'].startswith('item_artifact') else 0)
    horizontal = np.abs(points[:, :2] - center)
    candidates = np.nonzero((horizontal.max(axis=1) <= 24) & (points[:, 2] <= bottom + 6)
                            & (points[:, 2] >= bottom - 256))[0]
    if not len(candidates):
        return dict(status='unresolved', reason='no nearby supported floor below the spawn origin'), None
    support = min(candidates, key=lambda index: (np.linalg.norm(points[index, :2] - center), -points[index, 2]))
    floor = points[support, 2]
    result = dict(floor=round(float(floor), 2), support_point=points[support].tolist())
    if reachable[support]:
        result.update(status='center_stance', stance=points[support].tolist())
        return result, int(support)
    candidates = np.nonzero(reachable & (horizontal.max(axis=1) < 47) & (np.abs(points[:, 2] - floor) < 56))[0]
    candidates = sorted(candidates, key=lambda index: (abs(points[index, 2] - floor), np.linalg.norm(points[index, :2] - center)))
    for candidate in candidates:
        if world_visible(prepared['bsp'], points[candidate] + [0, 0, 28], np.r_[center, floor + 28]):
            result.update(status='nearby_touch_stance', stance=points[candidate].tolist())
            return result, int(candidate)
    result.update(status='unresolved', reason='support has no modeled reachable center or nearby clear touch stance')
    return result, None


def apply_moves(items, moves):
    identifiers = {item['id']: item for item in items}
    applied = []
    for identifier, coordinates in moves.items():
        if identifier not in identifiers:
            raise ValueError(f'Unknown pickup ID for --move: {identifier}')
        if len(coordinates) != 3 or not np.isfinite(coordinates).all():
            raise ValueError(f'Invalid candidate coordinates for {identifier}')
        item = identifiers[identifier]
        horizontal, vertical, floor = coordinates
        offset = 16 if item['classname'] in CORNER else 0
        height = 32 if item['classname'].startswith('item_artifact') else 8
        applied.append(dict(id=identifier, old_origin=item['origin'], proposed_center_floor=list(coordinates)))
        item['origin'] = [horizontal - offset, vertical - offset, floor + height]
        item['center_xy'] = [horizontal, vertical]
        item['requested_floor'] = floor
    return applied


def supply(items):
    return dict(counts=dict(Counter(item['kind'] for item in items)),
                regular_health=sum(15 if item['kind'] == 'H15' else 25 if item['kind'] == 'H25' else 0 for item in items),
                loose_ammo={kind: sum(quantities[bool(item['spawnflags'] & 1)] for item in items if item['kind'] == kind)
                            for kind, quantities in AMMO.items()},
                unknown_kinds=sorted({item['kind'] for item in items if item['kind'] not in set(KINDS.values()) | {'MH', 'H15', 'H25'}}),
                overrides_present=[item['id'] for item in items if item['override_fields']])


def pair_route(first, second, nodes, routes, prepared, include_paths):
    result = dict(from_id=first['id'], to_id=second['id'], model_cost=None, world_eye_los=None)
    source, target = nodes.get(first['id']), nodes.get(second['id'])
    if source is None or target is None:
        result['reason'] = 'unresolved pickup stance'
        return result
    endpoints = prepared['points'][[source, target]]
    result.update(direct_3d=round(float(np.linalg.norm(endpoints[1] - endpoints[0])), 2),
                  world_eye_los=world_visible(prepared['bsp'], endpoints[0] + [0, 0, 46], endpoints[1] + [0, 0, 46]))
    distances, previous = routes[first['id']]
    if target not in distances:
        result['reason'] = 'no directed route in the movement model'
        return result
    route = [target]
    while route[-1] != source:
        route.append(previous[route[-1]])
    route.reverse()
    points = prepared['points'][route]
    changes = np.diff(points[:, 2])
    kinds = Counter()
    for start, end in zip(route, route[1:]):
        options = [(cost, kind) for neighbor, cost, kind in prepared['navigation']['adjacency'][start] if neighbor == end]
        kinds[min(options)[1]] += 1
    cost = float(distances[target])
    median = prepared['profile']['travel_median']
    result.update(model_cost=round(cost, 2), relative_to_map_median=round(cost / median, 3) if median else None,
                  ascent=round(float(changes[changes > 0].sum()), 2),
                  descent=round(float(-changes[changes < 0].sum()), 2), edge_kinds=dict(kinds))
    if include_paths:
        result['path'] = points.tolist()
    return result


def clusters(items, pairs, visible, vantage_points, median):
    result = []
    lookup = {(pair['from_id'], pair['to_id']): pair for pair in pairs}
    rockets = [item for item in items if item['kind'] == 'RL']
    lightning = [item for item in items if item['kind'] == 'LG']
    resources = [item for item in items if item['kind'] in ARMOR_HEALTH]
    for rocket, gun, resource in itertools.product(rockets, lightning, resources):
        identifiers = [rocket['id'], gun['id'], resource['id']]
        options = []
        for order in itertools.permutations(identifiers):
            legs = [lookup[(order[index], order[index + 1])]['model_cost'] for index in range(2)]
            if all(cost is not None for cost in legs):
                options.append((sum(legs), order))
        cycles = []
        for order in itertools.permutations(identifiers):
            legs = [lookup[(order[index], order[(index + 1) % 3])]['model_cost'] for index in range(3)]
            if all(cost is not None for cost in legs):
                cycles.append(sum(legs))
        minimum, order = min(options) if options else (None, None)
        common = None
        if all(visible[identifier] is not None for identifier in identifiers):
            common = np.ones(len(vantage_points), dtype=bool)
            for identifier in identifiers:
                common &= visible[identifier]
        record = dict(ids=identifiers, minimum_visit_cost=round(minimum, 2) if minimum is not None else None,
                      visit_order=order, cycle_cost=round(min(cycles), 2) if cycles else None,
                      visit_relative_to_map_median=round(minimum / median, 3) if minimum is not None and median else None,
                      common_world_eye_samples=int(common.sum()) if common is not None else None,
                      tested_samples=len(vantage_points),
                      example_common_vantages=vantage_points[common][:3].tolist() if common is not None else [])
        result.append(record)
    return result


def analyze(prepared, moves=None, include_paths=False, vantage_samples=256):
    items, excluded = inventory(prepared['bsp'].ents)
    applied = apply_moves(items, moves or {})
    report = dict(map=prepared['path'].stem, bsp_sha256=prepared['sha256'], hypothetical=bool(applied),
                  proposed_moves=applied, supply=supply(items), items=items,
                  excluded_not_deathmatch=excluded, pairs=[], rl_lg_resource_groups=[])
    if 'navigation' not in prepared:
        return report
    report['geometry_profile'] = {key: value for key, value in prepared['profile'].items()
                                  if key not in ('route_vert_per_1000', 'route_level_pairs', 'item_height_spread', 'key_items')}
    nodes = {}
    for item in items:
        item['projection'], node = project(item, prepared)
        if 'requested_floor' in item and abs(item['projection'].get('floor', float('inf')) - item['requested_floor']) > 1:
            item['projection'].update(status='unresolved', reason='candidate does not settle on the requested floor')
            node = None
        if node is not None:
            nodes[item['id']] = node
    key_items = [item for item in items if item['kind'] in KEYS]
    sources = [item for item in items if item['kind'] in KEYS or item['classname'].startswith('weapon_')]
    routes = {item['id']: prepared['navigation']['shortest_paths'](nodes[item['id']])
              for item in sources if item['id'] in nodes}
    for first, second in itertools.permutations(key_items, 2):
        report['pairs'].append(pair_route(first, second, nodes, routes, prepared, include_paths))
    for item in items:
        if item['kind'] not in MATCHING or item['id'] not in nodes:
            continue
        options = [(routes[weapon['id']][0].get(nodes[item['id']], float('inf')), weapon['id'])
                   for weapon in sources if weapon['kind'] in MATCHING[item['kind']] and weapon['id'] in routes]
        if options:
            distance, weapon = min(options)
            item['nearest_matching_weapon'] = dict(id=weapon, weapon_to_ammo_cost=round(distance, 2) if math.isfinite(distance) else None)
    reachable = np.nonzero(prepared['reachable'])[0]
    randomizer = np.random.default_rng(7)
    sample = randomizer.choice(reachable, min(vantage_samples, len(reachable)), replace=False)
    vantage_points = prepared['points'][sample]
    visible = {}
    for item in key_items:
        flags = None
        if item['id'] in nodes:
            flags = np.zeros(len(sample), dtype=bool)
            target = prepared['points'][nodes[item['id']]] + [0, 0, 46]
            for index, point in enumerate(vantage_points):
                if np.linalg.norm(point - prepared['points'][nodes[item['id']]]) <= 1200:
                    flags[index] = world_visible(prepared['bsp'], point + [0, 0, 46], target)
        visible[item['id']] = flags
    report['vantage_sampling'] = dict(seed=7, count=len(sample), radius=1200, world_only=True)
    report['rl_lg_resource_groups'] = clusters(key_items, report['pairs'], visible, vantage_points,
                                               prepared['profile']['travel_median'])
    report['unresolved_stances'] = [item['id'] for item in items if item['id'] not in nodes]
    return report


def draw(report, prepared, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(15, 7), facecolor='#181c22')
    for axis in axes:
        axis.set_facecolor('#252c36')
        axis.tick_params(colors='#c8d0dc', labelsize=8)
    points = prepared['points'][prepared['reachable']]
    axes[0].scatter(points[:, 0], points[:, 1], c=points[:, 2], cmap='viridis', marker='s', s=3, alpha=.65)
    keys = [item for item in report['items'] if item['kind'] in KEYS]
    for item in keys:
        color = '#ffe27a' if item['kind'] in {'RA', 'YA', 'GA'} else '#bc9cff' if item['kind'] in {'MH', 'QUAD', 'PENT', 'RING'} else '#ff7c8b'
        horizontal, vertical = item['center_xy']
        supported = item['projection']['status'] != 'unresolved'
        axes[0].scatter([horizontal], [vertical], marker='D' if supported else 'x', c=color, s=40, zorder=3)
        axes[0].annotate(item['id'], (horizontal, vertical), xytext=(4, 4), textcoords='offset points', color=color, fontsize=8,
                         bbox=dict(fc='#10141acc', ec='none', pad=1), zorder=4)
    axes[0].set_aspect('equal')
    axes[0].set_title('Pickup locations; color = floor; x = unresolved stance', color='white', fontsize=10)
    identifiers = [item['id'] for item in keys]
    values = np.full((len(keys), len(keys)), np.nan)
    for index in range(len(keys)):
        values[index, index] = 0
    for pair in report['pairs']:
        if pair['model_cost'] is not None:
            values[identifiers.index(pair['from_id']), identifiers.index(pair['to_id'])] = pair['model_cost']
    if len(keys):
        palette = plt.get_cmap('magma').copy()
        palette.set_bad('#747b83')
        plotted = axes[1].imshow(values, cmap=palette, interpolation='nearest')
        axes[1].set_xticks(range(len(keys)), identifiers, rotation=90)
        axes[1].set_yticks(range(len(keys)), identifiers)
        bar = figure.colorbar(plotted, ax=axes[1], shrink=.7)
        bar.ax.tick_params(colors='white')
    axes[1].set_xlabel('To pickup', color='white')
    axes[1].set_ylabel('From pickup', color='white')
    axes[1].set_title('Directed model cost, not seconds; gray = unknown', color='white', fontsize=10)
    label = 'HYPOTHETICAL MOVES' if report['hypothetical'] else 'embedded placement'
    figure.suptitle(f"{report['map']} / {label}", color='white')
    figure.tight_layout()
    figure.savefig(destination, dpi=110)
    plt.close(figure)


def print_report(report):
    print(f"{report['map']}{' (hypothetical)' if report['hypothetical'] else ''}: {report['supply']['counts']}")
    print(f"  regular health {report['supply']['regular_health']}; standard loose ammo {report['supply']['loose_ammo']}")
    if 'geometry_profile' not in report:
        return
    pairs = report['pairs']
    for item in report['items']:
        if item['kind'] not in ARMOR_HEALTH:
            continue
        costs = {}
        for weapon in ('RL', 'LG'):
            options = [pair['model_cost'] for pair in pairs if pair['from_id'] == item['id']
                       and next(other['kind'] for other in report['items'] if other['id'] == pair['to_id']) == weapon
                       and pair['model_cost'] is not None]
            costs[weapon] = round(min(options)) if options else None
        print(f"  {item['id']} -> nearest RL/LG: {costs}; {item['projection']['status']}")
    print(f"  unresolved pickup stances: {report['unresolved_stances']} (model limits, not proof of unavailable items)")
    print('  RL + LG + armor/MH location sweeps (cost, not pickup timing or a balance grade):')
    for group in sorted(report['rl_lg_resource_groups'], key=lambda record: record['minimum_visit_cost'] if record['minimum_visit_cost'] is not None else float('inf'))[:6]:
        print(f"    {group['ids']}: visit {group['minimum_visit_cost']}, cycle {group['cycle_cost']}, common eyes {group['common_world_eye_samples']}/{group['tested_samples']}")


def parse_move(value):
    try:
        identifier, coordinates = value.split('=', 1)
        position = tuple(map(float, coordinates.split(',')))
        if len(position) != 3 or not np.isfinite(position).all() or not identifier:
            raise ValueError()
        return identifier, position
    except ValueError as error:
        raise argparse.ArgumentTypeError('use ID=x,y,floor, for example LG1=512,768,192') from error


def main():
    source_hashes = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                     for name in ('itemprofile.py', 'vprofile.py')}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('maps', type=Path, nargs='+')
    parser.add_argument('--inventory-only', action='store_true', help='skip movement and visibility modeling')
    parser.add_argument('--json', type=Path, help='write a schema-versioned report')
    parser.add_argument('--png-dir', type=Path, help='write per-map location/matrix figures')
    parser.add_argument('--paths', action='store_true', help='include route coordinates in JSON')
    parser.add_argument('--move', type=parse_move, action='append', default=[], help='hypothetical pickup move; never edits a BSP')
    arguments = parser.parse_args()
    if arguments.move and (len(arguments.maps) != 1 or arguments.inventory_only):
        parser.error('--move requires one map and movement modeling')
    if arguments.png_dir and arguments.inventory_only:
        parser.error('--png-dir requires movement modeling')
    moves = dict(arguments.move)
    if len(moves) != len(arguments.move):
        parser.error('each --move ID may appear only once')
    reports = []
    for path in arguments.maps:
        try:
            prepared = prepare(path, arguments.inventory_only)
            report = analyze(prepared, moves=moves, include_paths=arguments.paths)
        except (OSError, ValueError, AssertionError) as error:
            parser.error(str(error))
        print_report(report)
        if arguments.png_dir:
            arguments.png_dir.mkdir(parents=True, exist_ok=True)
            draw(report, prepared, arguments.png_dir / (path.stem + '.items.png'))
        reports.append(report)
    if arguments.json:
        if any(hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() != digest
               for name, digest in source_hashes.items()):
            parser.error('tool source changed during analysis; rerun with a stable checkout')
        output = dict(schema_version=1, quantity_basis='standard QW items.qc; no mod overrides or respawn-rate simulation',
                      tool_sha256=source_hashes, maps=reports)
        arguments.json.write_text(json.dumps(output, indent=2) + '\n')


if __name__ == '__main__':
    main()
