"""Audit QuakeEd/Valve 220 .map and BSP29 texture alignment and visual hazards.

Usage: python3 qmap/texcheck.py map.map [--bsp map.bsp] [--report lint.json]
Diagnostics exit 0 by default; --strict exits 1 on findings. Input errors exit 2.
See TEXCHECK.md for coverage, texture selection, and intentional seams.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
import fnmatch
import itertools
import json
import math
from pathlib import Path
import re
import struct

import numpy as np

import collide_cmp
import render


EPSILON = 1e-4
TOOLS = frozenset(('clip', 'skip', 'hint', 'hintskip', 'origin', 'trigger'))
NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
POINT = re.compile(r'\(\s*(' + NUMBER + r')\s+(' + NUMBER + r')\s+(' + NUMBER + r')\s*\)')


@dataclass
class Face:
    ident: str
    texture: str
    vertices: np.ndarray
    normal: np.ndarray
    axes: np.ndarray
    shifts: np.ndarray
    period: tuple = None
    owner: int = 0
    index: int = -1

    def uv(self, points):
        return np.asarray(points) @ self.axes.T + self.shifts

    def location(self):
        return {'face': self.ident, 'texture': self.texture,
                'position': self.vertices.mean(axis=0).round(4).tolist()}


class SpatialIndex:
    def __init__(self):
        self.buckets = defaultdict(list)
        self.large = []
        self.bounds = {}

    def cells(self, lower, upper):
        lower = np.floor(np.asarray(lower) / 256).astype(int)
        upper = np.floor(np.asarray(upper) / 256).astype(int)
        if math.prod(upper - lower + 1) > 4096:
            return None
        return itertools.product(*(range(start, end + 1) for start, end in zip(lower, upper)))

    def add(self, ident, lower, upper):
        self.bounds[ident] = (np.asarray(lower), np.asarray(upper))
        cells = self.cells(lower, upper)
        if cells is None:
            self.large.append(ident)
        else:
            for cell in cells:
                self.buckets[cell].append(ident)

    def query(self, lower, upper):
        cells = self.cells(lower, upper)
        candidates = set(self.bounds) if cells is None else set(self.large)
        if cells is not None:
            for cell in cells:
                candidates.update(self.buckets.get(cell, ()))
        return [ident for ident in candidates if np.all(self.bounds[ident][0] <= upper + EPSILON)
                and np.all(self.bounds[ident][1] >= lower - EPSILON)]


def polygon_area(vertices):
    if len(vertices) < 3:
        return 0.0
    relative = vertices - vertices[0]
    return float(np.linalg.norm(np.cross(relative, np.roll(relative, -1, axis=0)).sum(axis=0)) / 2)


def face_polygon(normal, distance, normals, distances, lower, upper):
    tangent = np.cross(normal, (0, 0, 1) if abs(normal[2]) < 0.9 else (0, 1, 0))
    tangent /= np.linalg.norm(tangent)
    vertical = np.cross(normal, tangent)
    center = normal * distance
    extent = np.linalg.norm(upper - lower) + np.linalg.norm(center - lower) + 1
    polygon = np.array([center + extent * (horizontal * tangent + height * vertical)
                        for horizontal, height in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for clip_normal, clip_distance in zip(normals, distances):
        if np.dot(clip_normal, normal) > 1 - EPSILON and abs(clip_distance - distance) < EPSILON:
            continue
        polygon = render.clip_polygon(polygon, -clip_normal, -clip_distance)
        if len(polygon) < 3:
            return np.empty((0, 3))
    return polygon


def texture_axes(normal, tail):
    values = [float(value) for value in re.findall(NUMBER, tail)]
    if not np.isfinite(values).all():
        raise ValueError('texture coordinates must be finite')
    if tail.lstrip().startswith('['):
        if len(values) < 11:
            raise ValueError('incomplete Valve 220 texture definition')
        axes = np.array([values[:3], values[4:7]])
        shifts = np.array([values[3], values[7]])
        scales = np.array(values[9:11])
    else:
        if len(values) < 5:
            raise ValueError('incomplete QuakeEd texture definition')
        directions = np.array([(0, 0, 1), (0, 0, -1), (1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)])
        selected = int(np.argmax(directions @ normal))
        axes = np.array([((1, 0, 0), (0, -1, 0)) if selected < 2 else
                         ((0, 1, 0), (0, 0, -1)) if selected < 4 else
                         ((1, 0, 0), (0, 0, -1))], dtype=float)[0]
        horizontal = int(np.flatnonzero(axes[0])[0])
        vertical = int(np.flatnonzero(axes[1])[0])
        angle = math.radians(values[2])
        cosine, sine = math.cos(angle), math.sin(angle)
        old_horizontal, old_vertical = axes[:, horizontal].copy(), axes[:, vertical].copy()
        axes[:, horizontal] = cosine * old_horizontal - sine * old_vertical
        axes[:, vertical] = sine * old_horizontal + cosine * old_vertical
        shifts, scales = np.array(values[:2]), np.array(values[3:5])
    axes /= np.where(scales == 0, 1, scales)[:, None]
    return axes, shifts


def map_data(path):
    text = Path(path).read_text(encoding='utf-8')
    entities = list(collide_cmp.entities(text))
    if not entities:
        raise ValueError(f'{path}: no map entities')
    stripped, cursor, brushes, faces = [], 0, [], []
    for entity_index, (blocks, classname) in enumerate(entities):
        classname = (classname or '').lower()
        for brush_index, block in enumerate(blocks):
            start = text.find(block, cursor)
            stripped.append(text[cursor:start])
            cursor = start + len(block)
            cleaned = collide_cmp._strip_brush_comments(block)
            if 'brushDef' in cleaned or collide_cmp.BP_MAT_RE.search(cleaned):
                raise ValueError(f'{path}: brush primitives are unsupported; compile to BSP29 or use Valve 220')
            parsed = collide_cmp.parse_brush(block)
            if parsed is None:
                raise ValueError(f'{path}: degenerate brush {entity_index}/{brush_index}')
            lower, upper, (normals, distances), *_ = parsed
            brush_faces = []
            for line in cleaned.splitlines():
                points = list(POINT.finditer(line))
                if len(points) < 3:
                    continue
                vertices = np.array([[float(value) for value in point.groups()] for point in points[:3]])
                normal = np.cross(vertices[2] - vertices[0], vertices[1] - vertices[0])
                length = np.linalg.norm(normal)
                if length < EPSILON:
                    continue
                normal /= length
                tail = line[points[2].end():]
                token = next((match for match in collide_cmp.TOKEN_RE.finditer(tail) if match.lastindex), None)
                if token is None:
                    raise ValueError(f'{path}: missing face texture')
                texture = token.group(token.lastindex)
                axes, shifts = texture_axes(normal, tail[token.end():])
                polygon = face_polygon(normal, np.dot(normal, vertices[0]), normals, distances, lower, upper)
                if polygon_area(polygon) < EPSILON:
                    continue
                face = Face(f'entity {entity_index} brush {brush_index} face {len(brush_faces)}', texture,
                            polygon, normal, axes, shifts, owner=len(brushes))
                brush_faces.append(face)
                faces.append(face)
            contents, _ = collide_cmp.brush_contents([face.texture for face in brush_faces])
            occludes = contents in ('solid', 'sky') and (classname in collide_cmp.WORLD_ENTITY_TYPES
                        and contents in collide_cmp.WORLD_ENTITY_TYPES[classname][1] or classname == 'func_wall')
            brushes.append({'classname': classname, 'faces': brush_faces, 'lower': lower, 'upper': upper,
                            'normals': normals, 'distances': distances, 'occludes': occludes})
    stripped.append(text[cursor:])
    properties, current, key = [], None, None
    for token in collide_cmp.TOKEN_RE.finditer('\n'.join(stripped)):
        if token.lastindex is None:
            continue
        value = token.group(token.lastindex)
        if key is not None:
            current[key] = value
            key = None
        elif value == '{':
            current = {}
        elif value == '}':
            properties.append(current)
            current = None
        elif current is not None:
            key = value.strip(collide_cmp.KEY_WS)
    if len(properties) != len(entities):
        raise ValueError(f'{path}: malformed entity properties')
    return faces, brushes, properties


def wad_textures(path):
    data = Path(path).read_bytes()
    if len(data) < 12 or data[:4] not in (b'WAD2', b'WAD3'):
        raise ValueError(f'{path}: invalid WAD header')
    count, offset = struct.unpack_from('<ii', data, 4)
    if count < 0 or offset < 12 or offset + count * 32 > len(data):
        raise ValueError(f'{path}: invalid WAD directory')
    textures = {}
    for entry in range(count):
        start, size, _, kind, compressed, _, _, name = struct.unpack_from('<iii4B16s', data, offset + entry * 32)
        if kind not in (0x43, 0x44):
            continue
        if compressed or start < 12 or size < 40 or start + size > len(data):
            raise ValueError(f'{path}: invalid or compressed miptex {entry}')
        width, height = struct.unpack_from('<II', data, start + 16)
        if not width or not height:
            raise ValueError(f'{path}: zero-sized texture {entry}')
        textures[name.split(b'\0')[0].decode('latin1').lower()] = (width, height)
    return textures


def source_visibility(faces, brushes):
    index = SpatialIndex()
    for brush_index, brush in enumerate(brushes):
        if brush['occludes']:
            index.add(brush_index, brush['lower'], brush['upper'])
    visible = []
    for face in faces:
        classname = brushes[face.owner]['classname']
        if classname.startswith('trigger') or face.texture.lower() in TOOLS:
            continue
        center = face.vertices.mean(axis=0)
        probes = np.vstack((center, (face.vertices + center) / 2)) + face.normal * 0.05
        candidates = [candidate for candidate in index.query(probes.min(0), probes.max(0)) if candidate != face.owner]
        covered = np.zeros(len(probes), bool)
        for candidate in candidates:
            brush = brushes[candidate]
            covered |= np.all(probes @ brush['normals'].T <= brush['distances'] + EPSILON, axis=1)
        if not covered.all():
            visible.append(face)
    return visible


def bsp_data(path):
    data = Path(path).read_bytes()
    if len(data) < 124 or struct.unpack_from('<i', data)[0] != 29:
        raise ValueError(f'{path}: expected BSP29')
    for lump_index in range(15):
        offset, length = struct.unpack_from('<ii', data, 4 + lump_index * 8)
        if offset < 0 or length < 0 or offset + length > len(data):
            raise ValueError(f'{path}: invalid BSP lump {lump_index}')
    bsp = render.BSP(path)
    if not bsp.models:
        raise ValueError(f'{path}: missing BSP world model')
    offset, length = struct.unpack_from('<ii', data, 4)
    entity_text = data[offset:offset + length].decode('latin1').rstrip('\0')
    bsp.solid_models = {0} if bsp.models else set()
    for block in re.findall(r'\{([^}]*)\}', entity_text):
        properties = dict(re.findall(r'"([^"]*)"\s*"([^"]*)"', block))
        model = properties.get('model', '')
        if properties.get('classname', '').lower() == 'func_wall' and re.fullmatch(r'\*\d+', model):
            model_index = int(model[1:])
            if model_index >= len(bsp.models):
                raise ValueError(f'{path}: invalid func_wall model {model}')
            bsp.solid_models.add(model_index)
    offset, length = struct.unpack_from('<ii', data, 4 + 9 * 8)
    if length % 8:
        raise ValueError(f'{path}: invalid clipnode lump')
    clipnodes = [struct.unpack_from('<i2h', data, cursor) for cursor in range(offset, offset + length, 8)]
    faces = []
    for model_index, model in enumerate(bsp.models):
        if model_index in bsp.hidden_models:
            continue
        for face_index in range(model[14], model[14] + model[15]):
            face = bsp.faces[face_index]
            vertices = bsp.face_vertices(face)
            if polygon_area(vertices) < EPSILON:
                continue
            texinfo = bsp.texinfo[face[4]]
            texture = bsp.tex[texinfo[8]]
            name, pixels = texture or (f'missing_miptex_{texinfo[8]}', None)
            period = (pixels.shape[1], pixels.shape[0]) if pixels is not None else None
            normal = np.array(bsp.planes[face[0]][:3]) * (-1 if face[1] else 1)
            faces.append(Face(f'model *{model_index} face {face_index}', name, vertices, normal,
                              np.array([texinfo[:3], texinfo[4:7]]), np.array([texinfo[3], texinfo[7]]),
                              period, model_index, face_index))
    return bsp, clipnodes, faces


def finding(code, message, faces=(), **details):
    return {'code': code, 'message': message, 'faces': [face.location() for face in faces], **details}


def phase_error(values, period):
    return np.abs((np.asarray(values) + period / 2) % period - period / 2)


def alignment_checks(faces, band_gap=32, patterns=(), *, corner_u=False):
    walls = [face for face in faces if abs(face.normal[2]) < EPSILON and face.period
             and face.texture.lower() not in TOOLS and not face.texture.startswith('*')
             and not face.texture.lower().startswith('sky')
             and (not patterns or any(fnmatch.fnmatchcase(face.texture.lower(), pattern.lower()) for pattern in patterns))]
    findings, seen = [], set()

    def compare(first, second, points, components, corner=False):
        if first is second:
            return
        for component in components:
            delta = first.uv(points)[:, component] - second.uv(points)[:, component]
            period = first.period[component]
            code = 'wall-course' if component == 1 else 'corner-u-phase' if corner else 'wall-u-phase'
            key = (code, *sorted((first.ident, second.ident)))
            if key not in seen and (np.max(phase_error(delta, period)) > 0.05 or np.ptp(delta) > 0.05):
                seen.add(key)
                findings.append(finding(code, f'{"V course" if component else "U seam"} disagrees modulo {period:g}px',
                                        (first, second), phase_delta=round(float(delta[0]), 4), period=period))

    edges = defaultdict(list)
    for face in walls:
        for start, end in zip(face.vertices, np.roll(face.vertices, -1, axis=0)):
            direction = end - start
            length = np.linalg.norm(direction)
            if length < EPSILON:
                continue
            direction /= length
            if direction[np.flatnonzero(np.abs(direction) > EPSILON)[0]] < 0:
                direction = -direction
            moment = np.cross(start, direction)
            key = (face.texture.lower(), face.period, *np.round(direction, 3), *np.round(moment, 2))
            lower, upper = sorted((float(start @ direction), float(end @ direction)))
            edges[key].append((lower, upper, face, direction, start))
    for group in edges.values():
        active = []
        for lower, upper, face, direction, start in sorted(group, key=lambda edge: edge[0]):
            active = [edge for edge in active if edge[1] > lower + EPSILON]
            for old_lower, old_upper, other, *_ in active:
                common_lower, common_upper = max(lower, old_lower), min(upper, old_upper)
                if common_upper - common_lower <= EPSILON:
                    continue
                origin = start - direction * (start @ direction)
                points = origin + np.linspace(common_lower, common_upper, 3)[:, None] * direction
                corner = np.dot(face.normal, other.normal) < 1 - EPSILON
                compare(face, other, points, (0, 1) if corner_u or not corner else (1,), corner)
            active.append((lower, upper, face, direction, start))
    planes = defaultdict(list)
    for face in walls:
        key = (face.texture.lower(), face.period, *np.round(face.normal, 3), round(float(face.normal @ face.vertices[0]), 2))
        planes[key].append(face)
    for group in planes.values():
        active = []
        for face in sorted(group, key=lambda face: face.vertices[:, 2].min()):
            lower, upper = face.vertices[:, 2].min(), face.vertices[:, 2].max()
            active = [other for other in active if other.vertices[:, 2].max() >= lower - band_gap - EPSILON]
            tangent = np.cross(face.normal, (0, 0, 1))
            span = face.vertices @ tangent
            for other in active:
                other_span = other.vertices @ tangent
                overlap = (max(span.min(), other_span.min()), min(span.max(), other_span.max()))
                gap = lower - other.vertices[:, 2].max()
                if overlap[1] - overlap[0] > EPSILON and -EPSILON <= gap <= band_gap + EPSILON:
                    origin = face.normal * (face.normal @ face.vertices[0]) + np.array([0, 0, lower])
                    points = origin + np.linspace(*overlap, 3)[:, None] * tangent
                    compare(face, other, points, (0, 1))
            active.append(face)
    return findings


def portal_checks(faces, patterns=()):
    groups = defaultdict(list)
    for face in faces:
        name = face.texture.lower()
        selected = any(fnmatch.fnmatchcase(name, pattern.lower()) for pattern in patterns) if patterns else 'tele' in name or 'portal' in name
        if name.startswith('*') and selected and abs(face.normal[2]) < EPSILON:
            key = (name, *np.round(face.normal, 3), round(float(face.normal @ face.vertices[0]), 2), *np.round(face.axes[0], 4))
            groups[key].append(face)
    findings = []
    for group in groups.values():
        remaining = set(range(len(group)))
        index = SpatialIndex()
        for face_index, face in enumerate(group):
            index.add(face_index, face.vertices.min(0) - EPSILON, face.vertices.max(0) + EPSILON)
        while remaining:
            seed = remaining.pop()
            component, pending = [group[seed]], [seed]
            while pending:
                face = group[pending.pop()]
                for neighbour in index.query(face.vertices.min(0) - EPSILON, face.vertices.max(0) + EPSILON):
                    if neighbour in remaining:
                        remaining.remove(neighbour)
                        component.append(group[neighbour])
                        pending.append(neighbour)
            coordinates = np.vstack([face.vertices for face in component]) @ component[0].axes[0]
            if abs(np.ptp(coordinates) - 64) > 0.05:
                continue
            center = (coordinates.min() + coordinates.max()) / 2
            if phase_error(center - 32, 64) > 0.05:
                findings.append(finding('portal-alignment', '64u portal center is not 32 modulo 64 in world U (texture shifts are ignored)',
                                        component, world_u_center=round(float(center), 4)))
    return findings


def sky_checks(faces, gap=8):
    skies = [face for face in faces if face.texture.lower().startswith('sky')]
    index = SpatialIndex()
    for sky_index, sky in enumerate(skies):
        index.add(sky_index, sky.vertices.min(0) - gap, sky.vertices.max(0) + gap)
    findings = []
    for face in faces:
        if face.texture.lower() in TOOLS or face.texture.lower().startswith('sky') or face.texture.startswith('*'):
            continue
        for sky_index in index.query(face.vertices.min(0), face.vertices.max(0)):
            sky = skies[sky_index]
            if np.dot(face.normal, sky.normal) < 1 - EPSILON:
                continue
            distances = (face.vertices - sky.vertices[0]) @ sky.normal
            if np.max(np.abs(distances)) > gap + EPSILON:
                continue
            polygon = face.vertices - distances[:, None] * sky.normal
            center = sky.vertices.mean(0)
            for start, end in zip(sky.vertices, np.roll(sky.vertices, -1, axis=0)):
                inward = np.cross(sky.normal, end - start)
                if np.dot(center - start, inward) < 0:
                    inward = -inward
                polygon = render.clip_polygon(polygon, inward, np.dot(start, inward))
                if len(polygon) < 3:
                    break
            if polygon_area(polygon) > 0.1:
                findings.append(finding('sky-overlap', 'ordinary surface overlaps sky within the decal clearance', (face, sky)))
    return findings


def hull_contents(bsp, clipnodes, point, model):
    node = bsp.models[model][10]
    for _ in range(len(clipnodes) + 1):
        if node < 0:
            return node
        plane, front, back = clipnodes[node]
        normal = bsp.planes[plane][:3]
        node = front if np.dot(point, normal) >= bsp.planes[plane][3] else back
    raise ValueError('cyclic player-hull clipnode tree')


def inside_face(point, face):
    center = face.vertices.mean(0)
    for start, end in zip(face.vertices, np.roll(face.vertices, -1, axis=0)):
        inward = np.cross(face.normal, end - start)
        if np.dot(center - start, inward) < 0:
            inward = -inward
        if np.dot(point - start, inward) < -EPSILON:
            return False
    return True


def dark_floor_checks(bsp, clipnodes, faces, step=16, threshold=0, budget=1000000):
    findings, checked, visited, attempted = [], 0, set(), 0
    if not clipnodes or not len(bsp.light):
        return findings, checked
    samples = render.light_samples(bsp)
    models = sorted(bsp.solid_models)
    for face in faces:
        if face.owner not in bsp.solid_models or face.normal[2] < 0.7 or face.texture.startswith('*') or face.texture.lower().startswith('sky'):
            continue
        stored = bsp.faces[face.index]
        if bsp.texinfo[stored[4]][9] & 1:
            continue
        lightmap = None
        if stored[9] >= 0 and stored[5] != 255:
            uv = face.uv(face.vertices)
            minimum = np.floor(uv.min(0) / 16)
            size = (np.ceil(uv.max(0) / 16) - minimum + 1).astype(int)
            lightmap = render.build_lightmap(samples, stored[9], int(size[0]), int(size[1]), stored[5:9]) * 255
        lower, upper = face.vertices.min(0), face.vertices.max(0)
        xstart, xend = math.ceil(lower[0] / step - 0.5), math.ceil(upper[0] / step - 0.5)
        ystart, yend = math.ceil(lower[1] / step - 0.5), math.ceil(upper[1] / step - 0.5)
        attempted += max(0, xend - xstart) * max(0, yend - ystart)
        if attempted > budget:
            raise ValueError(f'floor sampling exceeds {budget} candidate cells; increase --floor-step or --max-floor-cells')
        dark = []
        for column, row in itertools.product(range(xstart, xend), range(ystart, yend)):
            horizontal = np.array([(column + 0.5) * step, (row + 0.5) * step, 0.0])
            height = (face.normal @ face.vertices[0] - face.normal @ horizontal) / face.normal[2]
            point = horizontal + (0, 0, height)
            key = (column, row, round(float(height), 3))
            if key in visited or not inside_face(point, face):
                continue
            lift = 24 + 16 * np.abs(face.normal[:2]).sum() / face.normal[2]
            origin = point + (0, 0, lift + 0.1)
            below = origin - (0, 0, 0.2)
            if any(hull_contents(bsp, clipnodes, origin, model) in (-2, -6) for model in models):
                continue
            if not any(hull_contents(bsp, clipnodes, below, model) == -2 for model in models):
                continue
            visited.add(key)
            checked += 1
            texture = bsp.tex[bsp.texinfo[stored[4]][8]]
            texture_uv = face.uv(point)
            if texture and texture[1] is not None:
                pixels = texture[1]
                if pixels[int(math.floor(texture_uv[1])) % pixels.shape[0], int(math.floor(texture_uv[0])) % pixels.shape[1]] >= 224:
                    continue
            luminance = 0.0
            if lightmap is not None:
                coordinate = np.clip(texture_uv / 16 - minimum, 0, size - 1)
                start = np.floor(coordinate).astype(int)
                end = np.minimum(start + 1, size - 1)
                horizontal_weight, vertical_weight = coordinate - start
                brightness = (lightmap[start[1], start[0]] * (1 - horizontal_weight) * (1 - vertical_weight)
                              + lightmap[start[1], end[0]] * horizontal_weight * (1 - vertical_weight)
                              + lightmap[end[1], start[0]] * (1 - horizontal_weight) * vertical_weight
                              + lightmap[end[1], end[0]] * horizontal_weight * vertical_weight)
                luminance = float(brightness @ [0.299, 0.587, 0.114])
            if luminance <= threshold:
                dark.append(point.round(4).tolist())
        if dark:
            findings.append(finding('dark-floor', f'{len(dark)} pitch-black standable floor cells', (face,), cells=dark))
    return findings, checked


def audit(path, *, map_path=None, bsp_path=None, wad_paths=None, wall_textures=(), portal_textures=(),
          band_gap=32, sky_gap=8, floor_step=16, dark_threshold=0, max_floor_cells=1000000, corner_u=False):
    if not np.isfinite([band_gap, sky_gap, floor_step, dark_threshold]).all() or min(band_gap, sky_gap, dark_threshold) < 0 or dark_threshold > 255 or floor_step <= 0 or max_floor_cells <= 0:
        raise ValueError('require finite nonnegative gaps, 0 <= dark threshold <= 255, and positive floor step/budget')
    path = Path(path)
    if path.suffix.lower() not in ('.map', '.bsp'):
        raise ValueError('input must be a .map or BSP29 .bsp')
    for supplied in (map_path, bsp_path):
        if supplied is not None and not Path(supplied).is_file():
            raise ValueError(f'explicit input not found: {supplied}')
    map_path = Path(map_path) if map_path else path if path.suffix.lower() == '.map' else path.with_suffix('.map')
    bsp_path = Path(bsp_path) if bsp_path else path if path.suffix.lower() == '.bsp' else path.with_suffix('.bsp')
    if not path.is_file():
        raise ValueError(f'input not found: {path}')
    source_faces, brushes, properties, compiled_faces = [], [], [], []
    findings, skipped, textures, wads = [], [], {}, []
    if map_path.is_file():
        source_faces, brushes, properties = map_data(map_path)
        world = next((entity for entity in properties if entity.get('classname', '').lower() == 'worldspawn'), {})
        references = list(wad_paths) if wad_paths is not None else [value for value in world.get('wad', '').split(';') if value]
        if not references and map_path.with_suffix('.wad').is_file():
            references = [str(map_path.with_suffix('.wad').resolve())]
        for reference in references:
            requested = Path(reference)
            candidates = [map_path.parent / requested, requested, map_path.parent / re.split(r'[/\\]', str(reference))[-1]]
            resolved = next((candidate for candidate in candidates if candidate.is_file()), None)
            if resolved is None:
                findings.append(finding('missing-wad', f'WAD not found: {reference}'))
            else:
                wads.append(str(resolved))
                for name, period in wad_textures(resolved).items():
                    textures.setdefault(name, period)
        if not references:
            skipped.append('source texture availability/periods: no WAD specified or found')
        for face in source_faces:
            face.period = textures.get(face.texture.lower())
        if references:
            missing = defaultdict(list)
            for face in source_faces:
                if face.texture.lower() not in textures and face.texture.lower() not in TOOLS:
                    missing[face.texture.lower()].append(face)
            findings.extend(finding('missing-texture', f'texture absent from supplied WADs: {name}', faces)
                            for name, faces in sorted(missing.items()))
        for brush in brushes:
            hazards = [face for face in brush['faces'] if face.texture.startswith('*') or face.texture.lower().startswith('sky')]
            if brush['classname'] == 'func_detail_illusionary' and hazards:
                findings.append(finding('illusionary-contents', 'func_detail_illusionary has liquid/sky faces that can retain hull-0 contents', hazards))
    else:
        skipped.append('source-only checks: WAD references and func_detail_illusionary brush classification')
    if bsp_path.is_file():
        bsp, clipnodes, compiled_faces = bsp_data(bsp_path)
        findings.extend(finding('missing-texture', 'compiled texture pixels are missing', (face,))
                        for face in compiled_faces if face.period is None and face.texture.lower() not in TOOLS)
        dark, checked = dark_floor_checks(bsp, clipnodes, compiled_faces, floor_step, dark_threshold, max_floor_cells)
        findings.extend(dark)
        if not clipnodes:
            skipped.append('dark floors: compiled player hull is unavailable')
        elif not len(bsp.light):
            skipped.append('dark floors: no compiled lighting (fullbright map)')
    else:
        checked = 0
        skipped.append('dark floors: no companion BSP')
    geometry = compiled_faces if bsp_path.is_file() else source_visibility(source_faces, brushes)
    if any(face.period is None and face.texture.lower() not in TOOLS for face in geometry):
        skipped.append('wall alignment: faces with unknown texture periods')
    findings.extend(alignment_checks(geometry, band_gap, wall_textures, corner_u=corner_u))
    findings.extend(portal_checks(geometry, portal_textures))
    sky_faces = [face for face in source_faces if not brushes[face.owner]['classname'].startswith('trigger')]
    findings.extend(sky_checks(sky_faces if source_faces else compiled_faces, sky_gap))
    return {'input': str(path), 'map': str(map_path) if map_path.is_file() else None,
            'bsp': str(bsp_path) if bsp_path.is_file() else None, 'wads': wads,
            'findings': findings, 'counts': dict(sorted(Counter(item['code'] for item in findings).items())),
            'coverage': {'geometry': 'compiled BSP faces' if bsp_path.is_file() else 'source faces with sampled exposure',
                         'faces': len(geometry), 'standable_floor_cells': checked, 'skipped': skipped},
            'settings': dict(band_gap=band_gap, sky_gap=sky_gap, floor_step=floor_step, dark_threshold=dark_threshold,
                             max_floor_cells=max_floor_cells, wall_textures=list(wall_textures), portal_textures=list(portal_textures),
                             corner_u=corner_u)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input')
    parser.add_argument('--map', dest='map_path', help='corresponding source map (otherwise auto-discovered)')
    parser.add_argument('--bsp', dest='bsp_path', help='corresponding BSP29 (otherwise auto-discovered)')
    parser.add_argument('--wad', action='append', dest='wad_paths', help='WAD path; repeat to override worldspawn WAD list')
    parser.add_argument('--wall-texture', action='append', default=[], help='audit only matching wall texture globs')
    parser.add_argument('--corner-u', action='store_true', help='also check U phase across independent corner projections')
    parser.add_argument('--portal-texture', action='append', default=[], help='portal texture globs (default: * names containing tele/portal)')
    parser.add_argument('--band-gap', type=float, default=32, help='maximum intervening wall-band height')
    parser.add_argument('--sky-gap', type=float, default=8, help='maximum decal clearance from sky')
    parser.add_argument('--floor-step', type=float, default=16, help='floor sample grid spacing in world units')
    parser.add_argument('--dark-threshold', type=float, default=0, help='maximum lightmap luminance, 0..255 (default: exact black)')
    parser.add_argument('--max-floor-cells', type=int, default=1000000)
    parser.add_argument('--ignore', action='append', default=[], help='ignore a finding code (repeatable)')
    parser.add_argument('--limit', type=int, default=40, help='maximum findings printed; JSON retains all')
    parser.add_argument('--report', help='write complete JSON report')
    parser.add_argument('--strict', action='store_true', help='exit 1 if any non-ignored findings remain')
    args = parser.parse_args(argv)
    try:
        report = audit(args.input, map_path=args.map_path, bsp_path=args.bsp_path, wad_paths=args.wad_paths,
                       wall_textures=args.wall_texture, portal_textures=args.portal_texture,
                       band_gap=args.band_gap, sky_gap=args.sky_gap, floor_step=args.floor_step,
                       dark_threshold=args.dark_threshold, max_floor_cells=args.max_floor_cells, corner_u=args.corner_u)
        report['ignored_codes'] = args.ignore
        active = [item for item in report['findings'] if item['code'] not in args.ignore]
        if args.report:
            report_path = Path(args.report).resolve()
            inputs = [report['map'], report['bsp'], *report['wads']]
            if report['bsp']:
                inputs.append(str(Path(report['bsp']).with_suffix('.lit')))
            if report_path in {Path(value).resolve() for value in inputs if value}:
                raise ValueError('report must not overwrite an input map, BSP, WAD, or .lit')
            report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(f'{args.input}: {len(active)} findings; {report["coverage"]["faces"]} faces; '
              f'{report["coverage"]["standable_floor_cells"]} standable floor cells')
        for item in active[:max(0, args.limit)]:
            locations = '; '.join(f'{face["face"]} [{face["texture"]}] at {face["position"]}' for face in item['faces'][:2])
            print(f'  {item["code"]}: {item["message"]}' + (f' — {locations}' if locations else ''))
        if len(active) > max(0, args.limit):
            print(f'  {len(active) - max(0, args.limit)} more findings; use --report for all locations')
        for skipped in report['coverage']['skipped']:
            print(f'  NOT CHECKED: {skipped}')
        return 1 if args.strict and active else 0
    except (OSError, ValueError, IndexError, struct.error, AssertionError) as error:
        parser.exit(2, f'{error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
