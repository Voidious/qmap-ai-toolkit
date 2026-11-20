"""Check generated pickup positions against a captured MVDSV `edicts` dump."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re


CORNER = {'item_health', 'item_shells', 'item_spikes', 'item_rockets', 'item_cells'}


def vector(value):
    coordinates = list(map(float, value.strip("'").split()))
    if len(coordinates) != 3 or not all(math.isfinite(coordinate) for coordinate in coordinates):
        raise ValueError('Invalid entity vector')
    return coordinates


def audit(grid_path, dump_path):
    grid = json.loads(grid_path.read_text())
    dump = dump_path.read_text(encoding='utf-8-sig')
    if not re.search(r'(?m)^EDICT \d+:', dump):
        raise ValueError('Expected a plain MVDSV edicts dump')
    if not isinstance(grid, dict) or not isinstance(grid.get('items'), list) or any(not isinstance(item, list) or len(item) != 6 for item in grid['items']):
        raise ValueError('Expected generator JSON with six-field items')
    entities = []
    for block in re.split(r'(?m)^EDICT \d+:\s*', dump)[1:]:
        fields = dict(re.findall(r'(?m)^(\w+)\s+([^\r\n]+)', block))
        if fields.get('classname', '').startswith(('item_', 'weapon_')):
            entities.append(fields)
    expected = Counter(item[0] for item in grid['items'])
    actual = Counter(entity['classname'] for entity in entities)
    if actual != expected:
        raise ValueError(f'Runtime pickup counts differ: expected {dict(expected)}, actual {dict(actual)}')
    checked = []
    remaining = list(entities)
    for classname, horizontal, vertical, floor, flags, label in grid['items']:
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (horizontal, vertical, floor)):
            raise ValueError(f'Invalid generated coordinates for {label}')
        def separation(entity):
            coordinates = vector(entity['origin'])
            offset = 16 if classname in CORNER else 0
            return math.dist((coordinates[0] + offset, coordinates[1] + offset), (horizontal, vertical))
        choices = [entity for entity in remaining if entity['classname'] == classname]
        entity = min(choices, key=separation)
        coordinates = vector(entity['origin'])
        minimum = vector(entity.get('mins', "'0 0 0'"))
        if separation(entity) > .2 or abs(coordinates[2] + minimum[2] - floor) > .2:
            raise ValueError(f'{label} did not settle at its intended position/floor: {coordinates}')
        if float(entity.get('solid', 0)) != 1 or not entity.get('touch', '').endswith('_touch()'):
            raise ValueError(f'{label} is not an active pickup touch trigger')
        checked.append(dict(kind=label, classname=classname, floor=floor, center_xy=[horizontal, vertical],
                            touch=entity['touch'], ammo_amount=float(entity.get('aflag', 0)),
                            heal_amount=float(entity.get('healamount', 0))))
        remaining.remove(entity)
    return dict(runtime_pickups=len(checked), expected_class_counts=dict(expected), actual_class_counts=dict(actual),
                all_intended_floors=True, all_active_touch_triggers=True, pickups=checked,
                generator_sha256=hashlib.sha256(grid_path.read_bytes()).hexdigest(),
                dump_sha256=hashlib.sha256(dump_path.read_bytes()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('grid', type=Path)
    parser.add_argument('dump', type=Path)
    parser.add_argument('--json', type=Path)
    arguments = parser.parse_args()
    try:
        result = audit(arguments.grid, arguments.dump)
        if arguments.json:
            arguments.json.write_text(json.dumps(result, indent=2) + '\n')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps({key: value for key, value in result.items() if key != 'pickups'}))


if __name__ == '__main__':
    main()
