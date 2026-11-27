"""Shared-camera BSP preview and before/after sheets, used by template/views.py."""
import argparse
import json
from pathlib import Path
import re

import numpy as np
from PIL import Image, ImageDraw

from render import BSP, add_render_arguments, check_camera, render, render_options, report_camera


def previous_build(path):
    path = Path(path)
    match = re.fullmatch(r'(.*_b)(\d+)', path.stem)
    if not match or int(match[2]) < 2:
        raise ValueError('cannot infer previous build; provide --before path/to/older.bsp')
    previous = path.with_name(f'{match[1]}{int(match[2]) - 1}{path.suffix}')
    if not previous.is_file():
        raise ValueError(f'previous build not found: {previous}; provide --before explicitly')
    return previous


def camera_list(cameras):
    validated = []
    for index, camera in enumerate(cameras):
        try:
            label, position, yaw, pitch = camera
            if not isinstance(label, str) or len(position) != 3:
                raise ValueError()
            position = tuple(float(value) for value in position)
            yaw, pitch = float(yaw), float(pitch)
            if not np.isfinite([*position, yaw, pitch]).all():
                raise ValueError()
        except (TypeError, ValueError):
            raise ValueError(f'camera {index}: expected [label, [x, y, z], yaw, pitch] with finite coordinates') from None
        validated.append((label, position, yaw, pitch))
    if not validated:
        raise ValueError('camera list is empty')
    return validated


def make_sheet(bsp, out, cameras, *, before=None, fov=105, width=640, height=360,
               strict=False, use_lit=True, **options):
    options = {'gamma': 1, 'contrast': 1, 'lightmode': 1, 'modulate': 1, 'near': 2, **options}
    cameras = camera_list(cameras)
    paths = [Path(before), Path(bsp)] if before else [Path(bsp)]
    if Path(out).resolve() in {path.resolve() for path in paths}:
        raise ValueError('sheet output must not overwrite an input BSP')
    builds = [BSP(path, use_lit=use_lit) for path in paths]
    diagnostics = []
    unsafe_cameras = []
    for build in builds:
        build_issues = []
        for label, position, yaw, pitch in cameras:
            issues = check_camera(build, position, yaw, pitch, fov, width, height, options.get('near', 2))
            camera_label = f'{build.path.name} / {label}'
            if strict and issues:
                unsafe_cameras.append(f'UNSAFE CAMERA {camera_label}: ' + '; '.join(issues))
            else:
                report_camera(issues, camera_label)
            build_issues.append(issues)
        diagnostics.append(build_issues)
    if unsafe_cameras:
        raise ValueError('\n'.join(unsafe_cameras))
    header_height = 52
    label_height = 42
    tile_height = height + label_height
    rows = len(cameras) if before else (len(cameras) + 1) // 2
    sheet = Image.new('RGB', (2 * width, header_height + rows * tile_height), (16, 18, 22))
    draw = ImageDraw.Draw(sheet)
    settings = ', '.join(f'{name}={value:g}' for name, value in options.items())
    draw.text((8, 5), f'Horizontal FOV {fov:g}; {settings}', fill='white')
    for build_index, build in enumerate(builds):
        title_x = build_index * width if before else 0
        prefix = ('BEFORE' if build_index == 0 else 'AFTER') if before else 'PREVIEW'
        draw.text((title_x + 8, 25), f'{prefix}: {build.path.name} ({build.lighting})', fill=(255, 230, 80))
    means = [[] for _ in builds]
    for camera_index, (label, position, yaw, pitch) in enumerate(cameras):
        for build_index, build in enumerate(builds):
            issues = diagnostics[build_index][camera_index]
            tile = render(build, position, yaw, pitch, fov, width, height, camera_check='off', **options)
            mean = float((np.asarray(tile) @ [0.299, 0.587, 0.114]).mean()) if not issues else None
            means[build_index].append(mean)
            column = build_index if before else camera_index % 2
            row = camera_index if before else camera_index // 2
            left, top = column * width, header_height + row * tile_height
            sheet.paste(tile, (left, top + label_height))
            caption = Image.new('RGB', (width, label_height), (110, 0, 0) if issues else (16, 18, 22))
            caption_draw = ImageDraw.Draw(caption)
            caption_draw.text((6, 3), f'{camera_index}: {label}', fill='white')
            detail = 'UNSAFE CAMERA: ' + issues[0] if issues else f'mean {mean:.1f}; eye {position}; yaw {yaw:g}, pitch {pitch:g}'
            caption_draw.text((6, 22), detail, fill=(255, 220, 80))
            sheet.paste(caption, (left, top))
            if issues:
                draw.rectangle((left, top, left + width - 1, top + tile_height - 1), outline=(255, 40, 40), width=3)
    sheet.save(out)
    for build, values in zip(builds, means):
        valid = [value for value in values if value is not None]
        brightness = f'{np.mean(valid):.1f}' if valid else 'n/a'
        print(f'{build.path.name}: mean brightness {brightness} ({len(valid)}/{len(cameras)} safe cameras); {build.lighting}')
    return {'builds': [str(path) for path in paths], 'cameras': cameras, 'means': means, 'warnings': diagnostics,
            'settings': dict(fov=fov, width=width, height=height, use_lit=use_lit, **options)}


def main(cameras, argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bsp', help='current build')
    parser.add_argument('out', help='output sheet PNG')
    parser.add_argument('--before', nargs='?', const='previous', help='older BSP; omit value to infer _b(N-1).bsp')
    parser.add_argument('--cameras', help='JSON array of [label, [x,y,z], yaw, pitch]; overrides CAMS')
    parser.add_argument('--views', type=int, nargs='+', help='zero-based camera indices, in desired order')
    parser.add_argument('--fov', type=float, default=105, help='horizontal field of view')
    parser.add_argument('--width', type=int, default=640, help='width per camera')
    parser.add_argument('--height', type=int, default=360, help='height per camera')
    parser.add_argument('--report', help='optional JSON settings, brightness, and camera warnings')
    add_render_arguments(parser)
    args = parser.parse_args(argv)
    try:
        if args.cameras:
            cameras = json.loads(Path(args.cameras).read_text(encoding='utf-8'))
        cameras = camera_list(cameras)
        if args.views is not None:
            if any(index < 0 or index >= len(cameras) for index in args.views):
                raise ValueError(f'--views indices must be between 0 and {len(cameras) - 1}')
            cameras = [cameras[index] for index in args.views]
        before = previous_build(args.bsp) if args.before == 'previous' else args.before
        report = make_sheet(args.bsp, args.out, cameras, before=before, fov=args.fov,
                            width=args.width, height=args.height, strict=args.strict_cameras,
                            use_lit=not args.no_lit, **render_options(args))
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f'{error}\n')
