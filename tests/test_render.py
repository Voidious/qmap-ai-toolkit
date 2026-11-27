"""Self-contained BSP29 renderer and shared-camera sheet regressions."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'qmap'))
import render
import view_sheet


def write_bsp(path, *, lighting=None, light_offset=0, styles=(0, 255, 255, 255),
              texture='stone', indices=None, shifts=(0, 0), hidden=False, back_contents=-2,
              tree_copies=1):
    """A textured wall at x=0, solid behind it, air in front; 3x3 luxels."""
    lumps = [b''] * 15
    lumps[0] = b'{"classname" "worldspawn"}\0'
    if hidden:
        lumps[0] = b'{"classname" "worldspawn"}{"classname" "trigger_teleport" "model" "*1"}\0'
    lumps[1] = struct.pack('<4fi', 1, 0, 0, 0, 0)
    pixels = bytes([16] * 256) if indices is None else bytes(indices)
    lumps[2] = struct.pack('<ii', 1, 8) + struct.pack('<16sII4I', texture.encode(), 16, 16, 40, 0, 0, 0) + pixels
    lumps[3] = b''.join(struct.pack('<3f', *point) for point in [(0, -16, -16), (0, 16, -16), (0, 16, 16), (0, -16, 16)])
    lumps[5] = struct.pack('<i2h6h2H', 0, -2, -1, -32, -32, -32, 32, 32, 32, 0, 1)
    lumps[6] = struct.pack('<8fii', 0, 1, 0, shifts[0], 0, 0, -1, shifts[1], 0, 0)
    lumps[7] = struct.pack('<hhihh4Bi', 0, 0, 0, 4, 0, *styles, light_offset)
    lumps[8] = bytes([64] * 9) if lighting is None else lighting
    lumps[10] = b''.join(struct.pack('<ii6h2H4B', contents, -1, -32, -32, -32, 32, 32, 32, 0, 0, 0, 0, 0, 0)
                         for contents in (back_contents, -1))
    lumps[12] = b''.join(struct.pack('<HH', index, (index + 1) % 4) for index in range(4))
    lumps[13] = struct.pack('<4i', 0, 1, 2, 3)
    model = struct.pack('<9f7i', -32, -32, -32, 32, 32, 32, 0, 0, 0, 0, -1, -1, -1, 1, 0, 1)
    lumps[14] = model
    if hidden:
        lumps[14] = struct.pack('<9f7i', -32, -32, -32, 32, 32, 32, 0, 0, 0, -2, -1, -1, -1, 1, 0, 0) + model
    for lump_index in (5, 10, 14):
        lumps[lump_index] *= tree_copies
    offset = 124
    header = struct.pack('<i', 29)
    for lump in lumps:
        header += struct.pack('<ii', offset, len(lump))
        offset += len(lump)
    Path(path).write_bytes(header + b''.join(lumps))
    return Path(path)


def write_lit(path, samples):
    Path(path).with_suffix('.lit').write_bytes(b'QLIT' + struct.pack('<I', 1) + bytes(samples))


class RendererFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test_b2.bsp'
        write_bsp(self.path)

    def image(self, bsp=None, **options):
        return np.asarray(render.render(bsp or render.BSP(self.path), (16, 0, 0), 180, 0, 90, 32, 32, **options))


class TestRenderer(RendererFixture):
    def test_large_tree_parsing_copies_at_most_one_file_of_lump_bytes(self):
        class CountedBytes(bytes):
            copied = 0

            def __getitem__(self, key):
                result = super().__getitem__(key)
                if isinstance(key, slice):
                    self.copied += len(result)
                return result

        write_bsp(self.path, tree_copies=256, hidden=True)
        data = CountedBytes(self.path.read_bytes())
        with patch.object(Path, 'read_bytes', return_value=data):
            bsp = render.BSP(self.path, use_lit=False)
        self.assertEqual(len(bsp.nodes), 256)
        self.assertEqual(len(bsp.leaves), 512)
        self.assertEqual(len(bsp.models), 512)
        self.assertEqual(bsp.hidden_models, {1})
        self.assertEqual(bsp.hidden, {0})
        self.assertLessEqual(data.copied, len(data))

    def test_missing_lit_uses_monochrome_and_client_palette(self):
        bsp = render.BSP(self.path)
        self.assertIsNone(bsp.light_rgb)
        expected = np.floor(render.PAL[16] * 4 / 3) * 99 / 255
        np.testing.assert_array_equal(self.image()[16, 16], expected.astype(np.uint8))

    def test_rgb_offsets_are_sample_offsets_and_normalized_before_rendering(self):
        write_bsp(self.path, lighting=bytes([1, 2] + [64] * 9), light_offset=2)
        write_lit(self.path, [0] * 6 + [100, 50, 25] * 9)
        bsp = render.BSP(self.path)
        self.assertEqual(bsp.light_rgb.shape, (11, 3))
        np.testing.assert_array_equal(render.light_samples(bsp)[2], [99, 49, 25])
        pixel = self.image(bsp)[16, 16]
        expected = np.floor(render.PAL[16] * 4 / 3) * np.array([153, 75, 38]) / 255
        np.testing.assert_array_equal(pixel, expected.astype(np.uint8))
        self.assertGreater(pixel[0], pixel[1])

    def test_bad_lit_warns_and_falls_back(self):
        for data in (b'', b'WRNG' + bytes(31), b'QLIT' + struct.pack('<I', 2) + bytes(27),
                     b'QLIT' + struct.pack('<I', 1) + bytes(26), b'QLIT' + struct.pack('<I', 1) + bytes(28)):
            with self.subTest(data=data[:8]):
                self.path.with_suffix('.lit').write_bytes(data)
                with self.assertWarnsRegex(UserWarning, 'using BSP monochrome'):
                    self.assertIsNone(render.BSP(self.path).light_rgb)

    def test_explicit_monochrome_does_not_read_bad_companion(self):
        self.path.with_suffix('.lit').write_bytes(b'bad')
        with warnings.catch_warnings(record=True) as caught:
            bsp = render.BSP(self.path, use_lit=False)
        self.assertEqual(caught, [])
        self.assertIsNone(bsp.light_rgb)

    def test_black_rgb_falls_back_and_saturation_preserves_hue(self):
        write_lit(self.path, [0, 0, 0, 255, 16, 8] + [255, 16, 8] * 7)
        samples = render.light_samples(render.BSP(self.path))
        np.testing.assert_array_equal(samples[0], [64, 64, 64])
        write_bsp(self.path, lighting=bytes([255] * 9))
        bright = render.light_samples(render.BSP(self.path))
        np.testing.assert_array_equal(bright[1], [170, 11, 5])
        shade = render.build_lightmap(bright, 0, 3, 3, (0, 255, 255, 255), modulate=3)
        self.assertEqual(shade[0, 1, 0], 252 / 255)
        self.assertLess(shade[0, 1, 1], 0.07)

    def test_multiple_styles_and_lump_bounds(self):
        samples = np.full((18, 3), 32)
        combined = render.build_lightmap(samples, 0, 3, 3, (0, 1, 255, 255))
        np.testing.assert_array_equal(combined, np.full((3, 3, 3), 99 / 255))
        with self.assertRaisesRegex(ValueError, 'exceed lighting lump'):
            render.build_lightmap(samples, 1, 3, 3, (0, 1, 255, 255))

    def test_gamma_contrast_are_applied_once_after_lighting(self):
        raw = self.image()
        corrected = self.image(gamma=0.5, contrast=1.2)
        expected = 255 * np.sqrt(np.clip(raw.astype(float) / 255 * 1.2, 0, 1))
        np.testing.assert_allclose(corrected, expected, atol=3)
        np.testing.assert_array_equal(self.image(lightmode=1), self.image(lightmode=2))

    def test_liquid_axes_and_64_unit_repeat_ignore_shifts(self):
        texinfo = (0, 2, 0, 123, 0, 0, -0.5, 456, 0, 1)
        points = np.array([[5, -20, 12], [5, 12, 12]])
        horizontal, vertical = render.liquid_uv(points, texinfo, 128, 32)
        np.testing.assert_array_equal(horizontal, [-80, 48])
        np.testing.assert_array_equal(vertical, [-3, -3])
        pattern = list(range(16)) * 16
        write_bsp(self.path, texture='*water', indices=pattern, light_offset=-1)
        baseline = self.image()
        self.assertGreater(baseline.max(), 0)
        write_bsp(self.path, texture='*water', indices=pattern, light_offset=-1, shifts=(23, -37))
        np.testing.assert_array_equal(baseline, self.image())
        write_bsp(self.path, indices=pattern, light_offset=-1, lighting=b'')
        normal = self.image()
        write_bsp(self.path, indices=pattern, light_offset=-1, lighting=b'', shifts=(3, 0))
        self.assertFalse(np.array_equal(normal, self.image()))

    def test_fullbright_and_no_lighting(self):
        write_bsp(self.path, indices=[224] * 256, lighting=bytes(9))
        np.testing.assert_array_equal(self.image()[16, 16], render.PAL[224])
        write_bsp(self.path, light_offset=-1)
        self.assertEqual(self.image().max(), 0)
        write_bsp(self.path, light_offset=-1, lighting=b'')
        self.assertGreater(self.image().max(), 0)

    def test_inside_solid_and_valid_camera(self):
        bsp = render.BSP(self.path)
        self.assertEqual(render.check_camera(bsp, (16, 0, 0), 180, 0), [])
        self.assertTrue(any('inside solid' in issue for issue in render.check_camera(bsp, (-1, 0, 0), 0, 0)))
        with self.assertRaisesRegex(ValueError, 'UNSAFE CAMERA'):
            render.render(bsp, (-1, 0, 0), 0, 0, W=16, H=16, camera_check='error')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            render.render(bsp, (-1, 0, 0), 0, 0, W=16, H=16)
        self.assertIn('WARNING: UNSAFE CAMERA', stderr.getvalue())

    def test_near_clip_plane_and_thin_off_center_obstruction(self):
        bsp = render.BSP(self.path)
        self.assertTrue(any('near-clip' in issue for issue in render.check_camera(bsp, (1, 0, 0), 180, 0)))
        self.assertEqual(render.check_camera(bsp, (1, 0, 0), 0, 0), [])
        bsp.verts = np.array([(0, 0.3, 0.1), (0, 0.4, 0.1), (0, 0.4, 0.2), (0, 0.3, 0.2)])
        self.assertTrue(any('near-clip' in issue for issue in render.check_camera(bsp, (1, 0, 0), 180, 0)))
        bsp.verts[:, 1] += 10
        self.assertEqual(render.check_camera(bsp, (1, 0, 0), 180, 0), [])

    def test_sky_contents_are_unsafe_but_air_and_liquids_are_allowed(self):
        write_bsp(self.path, back_contents=-6)
        bsp = render.BSP(self.path)
        self.assertEqual(bsp.contents_at((-8, 0, 0)), -6)
        self.assertTrue(any('inside sky' in issue for issue in render.check_camera(bsp, (-8, 0, 0), 0, 0)))
        with self.assertRaisesRegex(ValueError, 'UNSAFE CAMERA.*inside sky'):
            render.render(bsp, (-8, 0, 0), 0, 0, W=16, H=16, camera_check='error')
        for contents in (-1, -3, -4, -5):
            with self.subTest(contents=contents):
                write_bsp(self.path, back_contents=contents)
                self.assertEqual(render.check_camera(render.BSP(self.path), (-8, 0, 0), 0, 0), [])

    def test_missing_models_or_leaves_warns_without_traversing_contents(self):
        for missing in ('models', 'leaves'):
            with self.subTest(missing=missing):
                bsp = render.BSP(self.path)
                setattr(bsp, missing, [])
                with patch.object(bsp, 'contents_at', side_effect=AssertionError('contents unavailable')):
                    issues = render.check_camera(bsp, (16, 0, 0), 180, 0)
                self.assertEqual(issues, ['camera contents unavailable (missing BSP models/leaves)'])
                with self.assertRaisesRegex(ValueError, 'UNSAFE CAMERA.*contents unavailable'):
                    render.render(bsp, (16, 0, 0), 180, 0, W=16, H=16, camera_check='error')
                with contextlib.redirect_stderr(io.StringIO()) as stderr:
                    self.image(bsp)
                self.assertIn('WARNING: UNSAFE CAMERA', stderr.getvalue())
                self.assertTrue(any('near-clip' in issue for issue in render.check_camera(bsp, (1, 0, 0), 180, 0)))

    def test_trigger_models_are_neither_solid_cameras_nor_visible(self):
        write_bsp(self.path, hidden=True)
        bsp = render.BSP(self.path)
        self.assertEqual(render.check_camera(bsp, (-1, 0, 0), 0, 0), [])
        self.assertEqual(self.image(bsp).max(), 0)
        bsp.hidden_models.clear()
        self.assertTrue(any('model *1' in issue for issue in render.check_camera(bsp, (-1, 0, 0), 0, 0)))

    def test_invalid_camera_arguments_fail(self):
        for options in ({'fov': 180}, {'fov': 0}, {'near': 0}, {'W': 0}, {'yaw': float('nan')}):
            arguments = dict(cam=(16, 0, 0), yaw=180, pitch=0)
            arguments.update(options)
            with self.assertRaises(ValueError):
                render.check_camera(render.BSP(self.path), **arguments)


class TestViewSheet(RendererFixture):
    def test_same_camera_and_settings_on_both_builds(self):
        before = write_bsp(self.path.with_name('test_b1.bsp'), lighting=bytes([32] * 9))
        output = self.path.with_suffix('.png')
        cameras = [('wall', (16, 0, 0), 180, 0), ('closer wall', (8, 0, 0), 180, 10)]
        with patch.object(view_sheet, 'render', wraps=render.render) as recorded:
            report = view_sheet.make_sheet(self.path, output, cameras, before=before, width=32, height=32,
                                          fov=90, gamma=0.5, contrast=1.2)
        for first, second in zip(recorded.call_args_list[::2], recorded.call_args_list[1::2]):
            self.assertEqual(first.args[1:], second.args[1:])
            self.assertEqual(first.kwargs, second.kwargs)
        with Image.open(output) as image:
            self.assertEqual(image.size, (64, 200))
        self.assertLess(report['means'][0][0], report['means'][1][0])
        self.assertEqual(view_sheet.previous_build(self.path), before)

    def test_unsafe_view_is_marked_and_excluded_from_mean(self):
        output = self.path.with_suffix('.png')
        cameras = [('inside', (-1, 0, 0), 0, 0)]
        with contextlib.redirect_stderr(io.StringIO()):
            report = view_sheet.make_sheet(self.path, output, cameras, width=32, height=32)
        self.assertEqual(report['means'], [[None]])
        self.assertIn('inside solid', report['warnings'][0][0][0])
        with Image.open(output) as image:
            self.assertEqual(image.getpixel((0, 52)), (255, 40, 40))
        strict_output = output.with_name('strict.png')
        with self.assertRaisesRegex(ValueError, 'UNSAFE CAMERA'):
            view_sheet.make_sheet(self.path, strict_output, cameras, strict=True)
        self.assertFalse(strict_output.exists())

    def test_json_cli_selection_and_report(self):
        cameras = self.path.with_suffix('.json')
        cameras.write_text(json.dumps([['valid', [16, 0, 0], 180, 0], ['invalid', [-1, 0, 0], 0, 0]]))
        output = self.path.with_suffix('.png')
        report = self.path.with_name('report.json')
        write_bsp(self.path.with_name('test_b1.bsp'))
        view_sheet.main([], [str(self.path), str(output), '--before', '--cameras', str(cameras),
                             '--views', '0', '--width', '32', '--height', '32', '--report', str(report), '--strict-cameras'])
        data = json.loads(report.read_text())
        self.assertEqual(len(data['cameras']), 1)
        self.assertEqual(data['warnings'], [[[]], [[]]])
        with self.assertRaises(SystemExit) as caught, contextlib.redirect_stderr(io.StringIO()):
            view_sheet.main([], [str(self.path), str(output), '--cameras', str(cameras), '--views', '-1'])
        self.assertEqual(caught.exception.code, 2)

    def test_both_companions_and_before_camera_are_checked(self):
        before = write_bsp(self.path.with_name('test_b1.bsp'))
        write_lit(before, [100, 20, 10] * 9)
        write_lit(self.path, [10, 20, 100] * 9)
        output = self.path.with_suffix('.png')
        cameras = [('wall', (16, 0, 0), 180, 0)]
        view_sheet.make_sheet(self.path, output, cameras, before=before, width=32, height=32)
        with Image.open(output) as image:
            red = image.getpixel((16, 110))
            blue = image.getpixel((48, 110))
            self.assertGreater(red[0], red[2])
            self.assertGreater(blue[2], blue[0])
        write_bsp(self.path, hidden=True)
        strict_output = output.with_name('unsafe_before.png')
        with self.assertRaisesRegex(ValueError, 'test_b1.bsp.*inside solid'):
            view_sheet.make_sheet(self.path, strict_output, [('inside old only', (-1, 0, 0), 0, 0)],
                                  before=before, strict=True)
        self.assertFalse(strict_output.exists())

    def test_invalid_camera_lists(self):
        for cameras in ([], [['bad', [1, 2], 0, 0]], [['bad', [1, 2, float('nan')], 0, 0]]):
            with self.assertRaises(ValueError):
                view_sheet.camera_list(cameras)


if __name__ == '__main__':
    unittest.main()
