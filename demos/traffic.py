"""Compare topology traffic with alive, in-play MVD occupancy on the same BSP.

python3 demos/traffic.py map.bsp match.mvd [more.mvd ...] --mode ca --json validation.json
No raw demos or player identities are written to reports. See qmap/TRAFFICPROFILE.md.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

import numpy as np
from scipy.spatial import cKDTree
from scipy.stats import spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'qmap'))
import trafficprofile
from mvd import parse


def play_windows(prints, duration, mode, start=None, end=None, whole_demo=False):
    if start is not None or end is not None:
        lower, upper = 0 if start is None else start, duration if end is None else end
        if not np.isfinite([lower, upper]).all() or lower < 0 or upper <= lower or upper > duration + 0.01:
            raise ValueError('invalid explicit demo interval')
        return [(lower, upper)], 'explicit interval'
    if whole_demo:
        return [(0, duration)], 'explicit whole-demo interval (may include warmup)'
    if mode == 'ca':
        starts = sorted(set(round(time + 5, 3) for time, message in prints
                            if re.search(r'round \[\d+\] starts in 5', message.lower())))
        ends = sorted(set(time for time, message in prints if re.search(r'sco\s+damg', message.lower())))
        windows = []
        for index, lower in enumerate(starts):
            limit = starts[index + 1] - 5 if index + 1 < len(starts) else duration
            upper = next((time for time in ends if lower < time <= limit), None)
            if upper is not None:
                windows.append((lower, upper))
    else:
        starts = sorted(set(time for time, message in prints if 'match has begun' in message.lower()))
        ends = sorted(set(time for time, message in prints if 'match is over' in message.lower()))
        windows = []
        for index, lower in enumerate(starts):
            limit = starts[index + 1] if index + 1 < len(starts) else duration
            upper = next((time for time in ends if lower < time <= limit), None)
            if upper is not None:
                windows.append((lower, upper))
    if not windows:
        raise ValueError('no complete match/round windows; specify --start/--end or explicitly --whole-demo')
    merged = []
    for lower, upper in sorted(windows):
        if merged and lower <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(upper, merged[-1][1]))
        else:
            merged.append((lower, upper))
    return merged, 'parsed CA rounds' if mode == 'ca' else 'parsed match windows'


def normalize_teams(mode, teams=None):
    if teams is None:
        return None if mode == 'ffa' else ('blue', 'red')
    values = teams.split(',') if isinstance(teams, str) else list(teams)
    if not values or any(not isinstance(team, str) or not team.strip() for team in values):
        raise ValueError('teams must be a nonempty list of nonempty names')
    return tuple(sorted({team.strip().casefold() for team in values}))


def occupancy(report, track, players, windows, max_gap=0.25, teams=None):
    selected_teams = normalize_teams(report['mode'], teams)
    points = np.array(report['cells']['points'], dtype=float).reshape(-1, 3)
    reach = np.flatnonzero(report['cells']['reachable'])
    seconds = np.zeros(len(points))
    tracks = defaultdict(list)
    named = set()
    for sample in track:
        player = players.get(sample[1], {})
        if player.get('name', '').strip():
            named.add(sample[1])
            if selected_teams is None or player.get('team', '').strip().casefold() in selected_teams:
                tracks[sample[1]].append(sample)
    excluded_teams = defaultdict(int)
    for player in named - tracks.keys():
        excluded_teams[players[player].get('team', '').strip().casefold() or '<empty>'] += 1
    warnings = []
    if excluded_teams:
        warnings.append(f'{len(named) - len(tracks)} named tracked players excluded by team filter; use --teams for custom teams')
    if not tracks:
        warnings.append('no named tracked players passed the team filter')
    coverage = dict(eligible_player_seconds=0, matched_player_seconds=0, matched_fraction=None,
                    team_filter=list(selected_teams) if selected_teams is not None else None,
                    named_tracked_players=len(named), included_players=len(tracks),
                    excluded_players=len(named) - len(tracks), excluded_teams=dict(sorted(excluded_teams.items())),
                    warnings=warnings)
    if not len(reach):
        warnings.append('no reachable floor for occupancy projection')
        return seconds, coverage
    tree = cKDTree(points[reach, :2])
    eligible, matched = 0.0, 0.0
    for samples in tracks.values():
        data = np.asarray(sorted(samples, key=lambda sample: sample[0]), dtype=float)
        if len(data) < 2:
            continue
        intervals = np.diff(data[:, 0])
        valid = (intervals > 0) & (intervals <= max_gap) & (data[:-1, 5] == 0) & (data[1:, 5] == 0)
        for lower, upper in windows:
            durations = np.maximum(0, np.minimum(data[1:, 0], upper) - np.maximum(data[:-1, 0], lower))
            selected = valid & (durations > 0)
            positions = data[:-1, 2:5][selected] - [0, 0, 24]
            weights = durations[selected]
            if not len(positions):
                continue
            eligible += float(weights.sum())
            _, candidates = tree.query(positions[:, :2], k=min(32, len(reach)))
            candidates = np.asarray(candidates).reshape(len(positions), -1)
            nodes = reach[candidates]
            horizontal = np.linalg.norm(points[nodes, :2] - positions[:, None, :2], axis=2)
            height = positions[:, None, 2] - points[nodes, 2]
            score = horizontal + np.abs(height)
            score[(horizontal > 32) | (height < -8) | (height > 96)] = np.inf
            best = np.argmin(score, axis=1)
            accepted = np.isfinite(score[np.arange(len(best)), best])
            chosen = nodes[np.arange(len(best)), best]
            np.add.at(seconds, chosen[accepted], weights[accepted])
            matched += float(weights[accepted].sum())
    coverage.update(eligible_player_seconds=round(eligible, 3), matched_player_seconds=round(matched, 3),
                    matched_fraction=round(matched / eligible, 4) if eligible else None)
    if tracks and not eligible:
        warnings.append('no eligible alive player intervals in the selected play windows')
    return seconds, coverage


def rank_comparison(report, seconds):
    patches = np.array(report['cells']['patch'], dtype=int)
    keep = patches >= 0
    if not keep.any():
        return dict(patches=0, spearman_all=None, spearman_visited=None, hot_cold_ratio=None)
    counts = np.bincount(patches[keep])
    prediction = np.bincount(patches[keep], weights=np.array(report['cells']['route_share'])[keep]) / counts
    observed = np.bincount(patches[keep], weights=seconds[keep]) / counts
    eligible = counts >= 4

    def correlation(selected):
        first, second = prediction[selected], observed[selected]
        if len(first) < 3 or np.ptp(first) == 0 or np.ptp(second) == 0:
            return None
        return round(float(spearmanr(first, second).statistic), 4)

    lower, upper = np.percentile(prediction[eligible], [25, 75]) if eligible.any() else (0, 0)
    distinct = upper > lower
    cold = float(observed[eligible & (prediction <= lower)].mean()) if distinct else 0
    hot = float(observed[eligible & (prediction >= upper)].mean()) if distinct else 0
    return dict(patches=int(eligible.sum()), visited_patches=int((eligible & (observed > 0)).sum()),
                spearman_all=correlation(eligible), spearman_visited=correlation(eligible & (observed > 0)),
                hot_cold_ratio=round(hot / cold, 4) if cold else None,
                cold_quartile_seconds_per_cell=round(cold, 6), hot_quartile_seconds_per_cell=round(hot, 6))


def draw_comparison(report, seconds, destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize

    points = np.array(report['cells']['points'], dtype=float).reshape(-1, 3)
    keep = np.array(report['cells']['reachable'], dtype=bool)
    bands = sorted(set(np.floor((points[keep, 2] + 1) / 128).astype(int))) if keep.any() else [0]
    if len(bands) > 32:
        raise ValueError('more than 32 floor slices')
    values = [np.array(report['cells']['route_share']), seconds]
    titles = ['Predicted route share', 'Observed alive player-seconds']
    figure, axes = plt.subplots(len(bands), 2, figsize=(12, 4 * len(bands)), squeeze=False)
    for row, band in enumerate(bands):
        selected = keep & (np.floor((points[:, 2] + 1) / 128) == band)
        for column, value in enumerate(values):
            axis = axes[row, column]
            maximum = max(float(np.percentile(value[keep], 99)) if keep.any() else 0, 1e-9)
            dots = axis.scatter(points[selected, 0], points[selected, 1], c=value[selected], s=7,
                                marker='s', cmap='inferno', norm=Normalize(0, maximum))
            axis.set_title(f'{titles[column]}, Z {band * 128}..{(band + 1) * 128}')
            axis.set_aspect('equal')
            if keep.any():
                axis.set_xlim(points[keep, 0].min() - 32, points[keep, 0].max() + 32)
                axis.set_ylim(points[keep, 1].min() - 32, points[keep, 1].max() + 32)
            figure.colorbar(dots, ax=axis, label='Independent column scale; saturated at 99th percentile')
    figure.suptitle(f"{report['map']} ({report['mode']}): topology versus occupancy")
    figure.tight_layout()
    figure.savefig(destination, dpi=130)
    plt.close(figure)


def validate(report, paths, *, start=None, end=None, whole_demo=False, skip_incomplete=False, png=None, teams=None):
    selected_teams = normalize_teams(report['mode'], teams)
    total = np.zeros(len(report['cells']['points']))
    records, seen = [], set()
    for path in paths:
        encoded = Path(path).read_bytes()
        digest = hashlib.sha256(encoded).hexdigest()
        if digest in seen:
            raise ValueError(f'{path}: duplicate demo content; compare independent recordings only once')
        seen.add(digest)
        labeled_map = re.search(r'\[([^\]]+)\]', Path(path).name)
        if labeled_map and labeled_map.group(1).lower() != report['map'].lower():
            raise ValueError(f'{path}: filename map does not match BSP name {report["map"]}')
        players, track, prints, _, unknown, duration = parse(str(path))
        if Path(path).read_bytes() != encoded:
            raise ValueError(f'{path}: demo changed while parsing')
        try:
            windows, source = play_windows(prints, duration, report['mode'], start, end, whole_demo)
        except ValueError as error:
            if not skip_incomplete:
                raise ValueError(f'{path}: {error}') from error
            records.append(dict(demo=Path(path).name, sha256=digest, status='not_checked', reason=str(error),
                                duration=duration, parser_unknown={str(key): value for key, value in unknown.items()}))
            continue
        seconds, coverage = occupancy(report, track, players, windows, teams=selected_teams)
        total += seconds
        records.append(dict(demo=Path(path).name, sha256=digest, duration=duration, status='checked',
                            windows=windows, window_source=source, parser_unknown={str(key): value for key, value in unknown.items()},
                            coverage=coverage, correlation=rank_comparison(report, seconds)))
    correlations = [record['correlation']['spearman_all'] for record in records
                    if record['status'] == 'checked' and record['correlation']['spearman_all'] is not None]
    if png:
        draw_comparison(report, total, png)
    return dict(map=report['map'], bsp_sha256=report['sha256'], mode=report['mode'], demos=records,
                team_filter=list(selected_teams) if selected_teams is not None else None,
                prediction_coverage=report['coverage'], settings=report['settings'],
                checked_demos=sum(record['status'] == 'checked' for record in records),
                omitted_demos=sum(record['status'] == 'not_checked' for record in records),
                pooled=rank_comparison(report, total),
                per_demo_spearman_median=float(np.median(correlations)) if correlations else None,
                per_demo_spearman_range=[min(correlations), max(correlations)] if correlations else None,
                limits=['Spatial patches and adjacent frames are not independent; no significance claim.',
                        'Occupancy is alive player-time, not traversal count or tactical intent.',
                        'Minimal MVD parser uses final roster and skips unknown message-block tails.',
                        'BSP build identity is not encoded by this parser; filename map matching is not a build proof.',
                        'Projection excludes unsupported positions, large jumps, swim/hook-only space.'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bsp')
    parser.add_argument('demos', nargs='+')
    parser.add_argument('--mode', choices=('ca', 'tdm', 'ffa', 'ctf'), required=True)
    parser.add_argument('--teams', help='comma-separated case-insensitive teams (default red,blue; FFA all named players)')
    parser.add_argument('--start', type=float)
    parser.add_argument('--end', type=float)
    parser.add_argument('--whole-demo', action='store_true')
    parser.add_argument('--skip-incomplete', action='store_true', help='report and omit demos without complete windows')
    parser.add_argument('--json', required=True)
    parser.add_argument('--png', help='floor-sliced predicted versus observed occupancy figure')
    args = parser.parse_args(argv)
    outputs = [Path(path).resolve() for path in (args.json, args.png) if path]
    if any(output in {Path(path).resolve() for path in [args.bsp] + args.demos} for output in outputs) or len(set(outputs)) != len(outputs):
        parser.error('outputs must be distinct and cannot overwrite inputs')
    try:
        report = trafficprofile.traffic_profile(args.bsp, mode=args.mode)
        result = validate(report, args.demos, start=args.start, end=args.end, whole_demo=args.whole_demo,
                          skip_incomplete=args.skip_incomplete, png=args.png, teams=args.teams)
        Path(args.json).write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
        for record in result['demos']:
            if record['status'] == 'not_checked':
                print(f"{record['demo']}: NOT CHECKED: {record['reason']}")
                continue
            print(f"{record['demo']}: rho={record['correlation']['spearman_all']}; matched={record['coverage']['matched_fraction']}; {record['window_source']}")
            for warning in record['coverage']['warnings']:
                print('NOT ESTABLISHED: ' + warning)
        print(f"Pooled rho={result['pooled']['spearman_all']}; per-demo median={result['per_demo_spearman_median']}")
    except (OSError, ValueError, AssertionError, IndexError, struct.error) as error:
        parser.error(str(error))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
