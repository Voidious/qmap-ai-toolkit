"""Self-contained texture lint, source mapping, WAD, and player-floor regressions."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qmap'))
import texcheck
from test_collide_cmp import box_faces, brush_block, entity_block
from test_render import write_bsp


def write_wad(path, textures):
    payload, entries, offset = [], [], 12
    for name, (width, height) in textures.items():
        blob = struct.pack('<16sII4I', name.encode(), width, height, 40, 0, 0, 0) + bytes(width * height)
        payload.append(blob)
        entries.append(struct.pack('<iii4B16s', offset, len(blob), len(blob), 0x44, 0, 0, 0, name.encode()))
        offset += len(blob)
    Path(path).write_bytes(b'WAD2' + struct.pack('<ii', len(entries), offset) + b''.join(payload + entries))


def wall(ident, start=0, end=64, bottom=0, top=128, shifts=(0, 32), period=(128, 128)):
    return texcheck.Face(ident, 'stone', np.array([[0, start, bottom], [0, end, bottom],
                                                 [0, end, top], [0, start, top]], dtype=float),
                         np.array([1., 0, 0]), np.array([[0., 1, 0], [0., 0, -1]]), np.array(shifts), period)


def horizontal(ident, texture, rect, height, normal=-1):
    lower_x, lower_y, upper_x, upper_y = rect
    return texcheck.Face(ident, texture, np.array([[lower_x, lower_y, height], [upper_x, lower_y, height],
                                                  [upper_x, upper_y, height], [lower_x, upper_y, height]], dtype=float),
                         np.array([0., 0, normal]), np.array([[1., 0, 0], [0., -1, 0]]), np.zeros(2), (128, 128))


def floor_bsp(path, *, lighting=bytes(9), ceiling=None, fullbright=False, model_class=None,
              light_offset=0, styles=(0, 255, 255, 255), texture_flags=0):
    write_bsp(path, lighting=lighting, indices=[224 if fullbright else 16] * 256,
              light_offset=light_offset, styles=styles)
    data = Path(path).read_bytes()
    lumps = [data[offset:offset + length] for offset, length in
             (struct.unpack_from('<ii', data, 4 + index * 8) for index in range(15))]
    lumps[1] = struct.pack('<4fi', 0, 0, 1, 0, 2) + struct.pack('<4fi', 0, 0, 1, 24, 2)
    vertices = [struct.unpack_from('<3f', lumps[3], offset) for offset in range(0, len(lumps[3]), 12)]
    lumps[3] = b''.join(struct.pack('<3f', point[1], point[2], point[0]) for point in vertices)
    lumps[6] = struct.pack('<8fii', 1, 0, 0, 0, 0, -1, 0, 0, 0, texture_flags)
    lumps[9] = struct.pack('<i2h', 1, -1, -2)
    if ceiling is not None:
        lumps[1] += struct.pack('<4fi', 0, 0, 1, ceiling - 32, 2)
        lumps[9] = struct.pack('<i2h', 1, 1, -2) + struct.pack('<i2h', 2, -2, -1)
    model = list(struct.unpack('<9f7i', lumps[14]))
    model[10] = 0
    lumps[14] = struct.pack('<9f7i', *model)
    if model_class:
        lumps[0] = (entity_block('worldspawn') + entity_block(model_class, extra_epairs='"model" "*1"\n')).encode() + b'\0'
        world = model.copy()
        world[10], world[15] = -1, 0
        lumps[14] = struct.pack('<9f7i', *world) + struct.pack('<9f7i', *model)
    offset, directory = 124, []
    for lump in lumps:
        directory.append(struct.pack('<ii', offset, len(lump)))
        offset += len(lump)
    Path(path).write_bytes(struct.pack('<i', 29) + b''.join(directory + lumps))


class TestAlignment(unittest.TestCase):
    def test_nonzero_anchors_modulo_actual_period_and_band_gap(self):
        lower = wall('lower', top=112)
        upper = wall('upper', bottom=128, top=256, shifts=(128, 160))
        self.assertEqual(texcheck.alignment_checks([lower, upper]), [])
        upper.shifts = np.array([0, 16])
        findings = texcheck.alignment_checks([lower, upper])
        self.assertEqual([finding['code'] for finding in findings], ['wall-course'])
        self.assertEqual(texcheck.alignment_checks([lower, upper], band_gap=8), [])
        lower.period = upper.period = (80, 80)
        upper.shifts = np.array([0, 112])
        self.assertEqual(texcheck.alignment_checks([lower, upper]), [])

    def test_corner_u_and_v_phases_and_unrelated_walls(self):
        first = wall('first')
        second = texcheck.Face('second', 'stone', np.array([[0., 64, 0], [64., 64, 0], [64., 64, 128], [0., 64, 128]]),
                               np.array([0., -1, 0]), np.array([[1., 0, 0], [0., 0, -1]]), np.array([64., 32]), (128, 128))
        self.assertEqual(texcheck.alignment_checks([first, second]), [])
        second.shifts = np.array([0., 16])
        self.assertEqual({finding['code'] for finding in texcheck.alignment_checks([first, second])},
                         {'wall-course'})
        self.assertEqual({finding['code'] for finding in texcheck.alignment_checks([first, second], corner_u=True)},
                         {'wall-course', 'corner-u-phase'})
        second.shifts[1] = 32
        self.assertEqual(texcheck.alignment_checks([first, second]), [])
        self.assertEqual(texcheck.alignment_checks([first, second], corner_u=True)[0]['code'], 'corner-u-phase')
        second.vertices[:, 0] += 256
        self.assertEqual(texcheck.alignment_checks([first, second]), [])

    def test_coplanar_u_mismatches_remain_enabled_by_default(self):
        first = wall('first')
        second = wall('second', start=64, end=128, shifts=(8, 32))
        findings = texcheck.alignment_checks([first, second])
        self.assertEqual([finding['code'] for finding in findings], ['wall-u-phase'])

    def test_scale_mismatch_cannot_alias_at_periodic_seam_endpoints(self):
        first, second = wall('first'), wall('second', start=64, end=128)
        second.axes[1, 2] = -3
        findings = texcheck.alignment_checks([first, second])
        self.assertTrue(any(finding['code'] == 'wall-course' for finding in findings))
        self.assertEqual(texcheck.alignment_checks([first, second], patterns=('other*',)), [])

    def test_portal_world_projection_ignores_shifts_and_merges_fragments(self):
        first = wall('portal', start=0, end=64)
        first.texture = '*tele'
        first.shifts = np.array([99., 0])
        self.assertEqual(texcheck.portal_checks([first]), [])
        first.vertices[:, 1] += 8
        first.shifts[0] = -8
        self.assertEqual(texcheck.portal_checks([first])[0]['code'], 'portal-alignment')
        second = wall('second', start=40, end=72)
        second.texture = '*tele'
        first.vertices[first.vertices[:, 1] == 72, 1] = 40
        self.assertEqual(len(texcheck.portal_checks([first, second])), 1)
        first.texture = second.texture = '*water'
        self.assertEqual(texcheck.portal_checks([first, second]), [])
        self.assertEqual(len(texcheck.portal_checks([first, second], patterns=('*water',))), 1)

    def test_sky_overlay_requires_positive_area_and_nearby_matching_plane(self):
        sky = horizontal('sky', 'SKY1', (0, 0, 128, 128), 256)
        decal = horizontal('decal', 'painting', (32, 32, 64, 64), 252)
        self.assertEqual(texcheck.sky_checks([sky, decal])[0]['code'], 'sky-overlap')
        decal.vertices[:, 0] += 96
        self.assertEqual(texcheck.sky_checks([sky, decal]), [])
        decal.vertices[:, 0] -= 96
        decal.vertices[:, 2] -= 32
        self.assertEqual(texcheck.sky_checks([sky, decal]), [])


class TestSourceAndWad(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / 'fixture.map'
        self.wad = self.directory / 'fixture.wad'
        write_wad(self.wad, {'stone': (128, 128), 'sky1': (256, 128), '*tele': (64, 64)})

    def write_map(self, body, extra=''):
        self.path.write_text(entity_block('worldspawn', body, extra_epairs='"wad" "fixture.wad"\n') + extra)

    def test_quaked_rotation_scale_and_valve_axes(self):
        axes, shifts = texcheck.texture_axes(np.array([1., 0, 0]), '8 -32 90 2 0.5')
        np.testing.assert_allclose(axes, [[0, 0, 0.5], [0, 2, 0]], atol=1e-9)
        np.testing.assert_array_equal(shifts, [8, -32])
        axes, shifts = texcheck.texture_axes(np.array([1., 0, 0]), '[ 0 1 0 -12 ] [ 0 0 -1 24 ] 0 -2 0.5')
        np.testing.assert_array_equal(axes, [[0, -0.5, 0], [0, 0, -2]])
        np.testing.assert_array_equal(shifts, [-12, 24])
        axes, _ = texcheck.texture_axes(np.array([0., 0, 1]), '0 0 0 0 0')
        np.testing.assert_array_equal(axes, [[1, 0, 0], [0, -1, 0]])

    def test_map_geometry_comments_quoted_metadata_and_valve_faces(self):
        body = brush_block(box_faces(0, 0, 0, 64, 64, 128, tex='stone', fmt='valve'))
        self.write_map(body, entity_block('light', extra_epairs='"message" "not } a brush // comment"\n'))
        text = self.path.read_text().replace('"classname" "worldspawn"', '"classname" "worldspawn" // ignored "wad" "wrong.wad"')
        self.path.write_text(text)
        faces, brushes, properties = texcheck.map_data(self.path)
        self.assertEqual(len(faces), 6)
        self.assertEqual(len(brushes), 1)
        self.assertEqual(properties[0]['wad'], 'fixture.wad')
        self.assertEqual(properties[1]['message'], 'not } a brush // comment')
        self.assertAlmostEqual(sum(texcheck.polygon_area(face.vertices) for face in faces), 40960, delta=2)
        report = texcheck.audit(self.path)
        self.assertNotIn('missing-texture', report['counts'])
        self.assertTrue(any('no companion BSP' in skipped for skipped in report['coverage']['skipped']))

    def test_missing_textures_and_detail_contents_with_portable_wad_fallback(self):
        self.write_map(brush_block(box_faces(0, 0, 0, 64, 64, 64, tex='absent')),
                       entity_block('FUNC_DETAIL_ILLUSIONARY', brush_block(box_faces(96, 0, 0, 160, 64, 64, tex='*tele'))))
        self.path.write_text(self.path.read_text().replace('fixture.wad', 'C:\\old\\fixture.wad'))
        report = texcheck.audit(self.path)
        self.assertEqual(report['counts']['missing-texture'], 1)
        self.assertEqual(report['counts']['illusionary-contents'], 1)
        self.assertNotIn('missing-wad', report['counts'])
        self.assertEqual(len(report['findings'][0]['faces']), 6)
        self.assertEqual(texcheck.wad_textures(self.wad)['stone'], (128, 128))

    def test_hidden_internal_faces_are_not_alignment_candidates(self):
        first = brush_block(box_faces(0, 0, 0, 64, 64, 64, tex='stone'))
        second = brush_block(box_faces(64, 0, 0, 128, 64, 64, tex='stone'))
        self.write_map(first + '\n' + second)
        faces, brushes, _ = texcheck.map_data(self.path)
        self.assertEqual(len(texcheck.source_visibility(faces, brushes)), 10)

    def test_long_touching_sky_borders_do_not_gain_overlap_area(self):
        sky = brush_block(box_faces(0, 0, 0, 1536, 64, 16, tex='sky1'))
        ceiling = brush_block(box_faces(0, 64, 0, 1536, 128, 16, tex='stone'))
        self.write_map(sky + '\n' + ceiling)
        report = texcheck.audit(self.path)
        self.assertNotIn('sky-overlap', report['counts'])
        _, brushes, _ = texcheck.map_data(self.path)
        for brush in brushes:
            for face in brush['faces']:
                self.assertTrue(np.all(face.vertices.min(0) >= brush['lower'] - 1e-8))
                self.assertTrue(np.all(face.vertices.max(0) <= brush['upper'] + 1e-8))

    def test_sky_checks_exclude_trigger_brushes_but_keep_real_decals(self):
        sky = brush_block(box_faces(0, 0, 0, 128, 128, 16, tex='sky1'))
        overlay = brush_block(box_faces(32, 32, -4, 64, 64, 0, tex='stone'))
        self.write_map(sky, entity_block('trigger_teleport', overlay))
        self.assertNotIn('sky-overlap', texcheck.audit(self.path)['counts'])
        self.write_map(sky, entity_block('func_detail_illusionary', overlay))
        self.assertIn('sky-overlap', texcheck.audit(self.path)['counts'])

    def test_missing_explicit_input_and_corrupt_wad_are_errors(self):
        self.write_map(brush_block(box_faces(0, 0, 0, 64, 64, 64, tex='stone')))
        with self.assertRaisesRegex(ValueError, 'explicit input not found'):
            texcheck.audit(self.path, bsp_path=self.directory / 'missing.bsp')
        self.wad.write_bytes(b'WAD2' + struct.pack('<ii', 1, 999))
        with self.assertRaisesRegex(ValueError, 'invalid WAD directory'):
            texcheck.audit(self.path)

    def test_cli_advisory_strict_json_ignore_and_input_protection(self):
        self.write_map(brush_block(box_faces(0, 0, 0, 64, 64, 64, tex='absent')))
        output = self.directory / 'report.json'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(texcheck.main([str(self.path), '--report', str(output), '--corner-u']), 0)
            self.assertEqual(texcheck.main([str(self.path), '--strict']), 1)
            self.assertEqual(texcheck.main([str(self.path), '--strict', '--ignore', 'missing-texture']), 0)
        self.assertIn('missing-texture', json.loads(output.read_text())['counts'])
        self.assertTrue(json.loads(output.read_text())['settings']['corner_u'])
        original = self.path.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            texcheck.main([str(self.path), '--report', str(self.path)])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.path.read_bytes(), original)


class TestDarkFloors(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'floor.bsp'

    def test_black_standable_cells_and_lit_control(self):
        floor_bsp(self.path)
        report = texcheck.audit(self.path)
        self.assertEqual(report['coverage']['standable_floor_cells'], 4)
        self.assertEqual(report['counts'], {'dark-floor': 1})
        self.assertEqual(len(report['findings'][0]['cells']), 4)
        floor_bsp(self.path, lighting=bytes([64] * 9))
        self.assertEqual(texcheck.audit(self.path)['counts'], {})

    def test_low_ceiling_fullbright_and_unlit_maps_do_not_report_dark_floor(self):
        floor_bsp(self.path, ceiling=40)
        self.assertEqual(texcheck.audit(self.path)['coverage']['standable_floor_cells'], 0)
        floor_bsp(self.path, fullbright=True)
        self.assertEqual(texcheck.audit(self.path)['counts'], {})
        floor_bsp(self.path, lighting=b'')
        report = texcheck.audit(self.path)
        self.assertEqual(report['counts'], {})
        self.assertTrue(any('fullbright map' in skipped for skipped in report['coverage']['skipped']))

    def test_omitted_lightmaps_are_black_except_special_or_fullbright_texels(self):
        for offset, styles in ((-1, (255, 255, 255, 255)), (-1, (0, 255, 255, 255)),
                               (0, (255, 255, 255, 255))):
            with self.subTest(offset=offset, styles=styles):
                floor_bsp(self.path, lighting=bytes([64] * 9), light_offset=offset, styles=styles)
                report = texcheck.audit(self.path)
                self.assertEqual(report['coverage']['standable_floor_cells'], 4)
                self.assertEqual(len(report['findings'][0]['cells']), 4)
                floor_bsp(self.path, light_offset=offset, styles=styles, fullbright=True)
                self.assertEqual(texcheck.audit(self.path)['counts'], {})
                floor_bsp(self.path, light_offset=offset, styles=styles, texture_flags=1)
                report = texcheck.audit(self.path)
                self.assertEqual(report['counts'], {})
                self.assertEqual(report['coverage']['standable_floor_cells'], 0)

    def test_floor_budget_and_invalid_settings_refuse_instead_of_claiming_clean(self):
        floor_bsp(self.path)
        with self.assertRaisesRegex(ValueError, 'sampling exceeds'):
            texcheck.audit(self.path, max_floor_cells=1)
        for options in ({'floor_step': 0}, {'dark_threshold': -1}, {'dark_threshold': 256}, {'band_gap': float('nan')}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                texcheck.audit(self.path, **options)

    def test_bsp_without_world_model_is_an_input_error(self):
        floor_bsp(self.path)
        data = bytearray(self.path.read_bytes())
        struct.pack_into('<i', data, 4 + 14 * 8 + 4, 0)
        self.path.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'missing BSP world model'):
            texcheck.audit(self.path)

    def test_illusionary_models_are_not_standable_but_static_walls_are(self):
        floor_bsp(self.path, model_class='func_illusionary')
        self.assertEqual(texcheck.audit(self.path)['coverage']['standable_floor_cells'], 0)
        floor_bsp(self.path, model_class='func_wall')
        self.assertEqual(texcheck.audit(self.path)['coverage']['standable_floor_cells'], 4)

    def test_json_report_cannot_overwrite_the_companion_lit(self):
        floor_bsp(self.path)
        companion = self.path.with_suffix('.lit')
        original = b'QLIT' + struct.pack('<i', 1) + bytes(27)
        companion.write_bytes(original)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            texcheck.main([str(self.path), '--report', str(companion)])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(companion.read_bytes(), original)


class TestTemplateAnchors(unittest.TestCase):
    def test_demo_strip_ramps_meet_the_room_strips(self):
        environment = {'__name__': 'template_test'}
        for name in ('_core.py', '_layout.py'):
            path = ROOT / 'template' / name
            exec(compile(path.read_text(), str(path), 'exec'), environment)
        column = (0 - environment['XMIN']) // environment['C']
        for height, position, room in ((-96, 688, 'low'), (0, 528, 'hall'), (0, 1024, 'hall')):
            with self.subTest(height=height, position=position):
                row = (position - environment['YMIN']) // environment['C']
                self.assertEqual(environment['strip_z']('low', height, column, row),
                                 environment['STRIPE_Z'][room])

    def test_default_and_custom_strip_use_one_wall_course_origin(self):
        environment = {'__name__': 'template_test'}
        for name in ('_core.py', '_out.py'):
            path = ROOT / 'template' / name
            exec(compile(path.read_text(), str(path), 'exec'), environment)
        environment['carve']((-64, -64, 64, 64), -64, 384, 'test', sym=False)
        self.assertEqual(environment['STRIPE_Z']['test'], 80)
        texture = environment['textures']('wall', 'test', 'wall')[2]
        for period, strip in ((128, 80), (128, 16), (80, 80)):
            with self.subTest(period=period, strip=strip):
                environment['WALL_PERIOD'][environment['zone']('test')] = period
                environment['STRIPE_Z']['test'] = strip
                info = dict(th='test', f=-64, c=384, sz=strip, nocap=False, foot=-32, tz=None)
                lower = environment['band_role'](info, -16)[1]
                upper = environment['band_role'](info, 256)[1]
                self.assertEqual(lower % period, upper % period)
                phases = {face[1] for piece in environment['detail_pieces']() for face in piece[7]
                          if face and face[0] == texture}
                self.assertEqual(phases, {-32 % period})

    def test_exposed_same_room_ramp_sides_share_the_wall_anchor(self):
        environment = {'__name__': 'template_test'}
        for name in ('_core.py', '_out.py'):
            path = ROOT / 'template' / name
            exec(compile(path.read_text(), str(path), 'exec'), environment)
        environment['carve']((-128, -128, 128, 128), -96, 224, 'test', sym=False)
        environment['ramp']((-64, -64, 0, 64), 'y', -96, 0, sym=False)
        list(environment['detail_pieces']())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'ramp.map'
            path.write_text(entity_block('worldspawn', *environment['EXTRA']['skin']))
            faces, _, _ = texcheck.map_data(path)
        texture = environment['textures']('ledge', 'test', None)[2]
        phases = {face.shifts[1] % 128 for face in faces if face.texture == texture}
        self.assertEqual(phases, {64})

    def test_prism_fallback_respects_the_configured_wall_period(self):
        environment = {'__name__': 'template_test'}
        for name in ('_core.py', '_out.py'):
            path = ROOT / 'template' / name
            exec(compile(path.read_text(), str(path), 'exec'), environment)
        environment['carve']((-128, -128, 128, 128), -64, 64, 'test', sym=False)
        environment['WALL_PERIOD'][environment['zone']('test')] = 80
        environment['prism']([(0, 0), (32, 0), (32, 32), (0, 32)], 96, 192, sym=False)
        list(environment['detail_pieces']())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'prism.map'
            path.write_text(entity_block('worldspawn', *environment['EXTRA']['world']))
            faces, _, _ = texcheck.map_data(path)
        texture = environment['textures']('wall', 'test', 'wall')[2]
        phases = {face.shifts[1] for face in faces if face.texture == texture}
        self.assertEqual(phases, {48})


if __name__ == '__main__':
    unittest.main()
