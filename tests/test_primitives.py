"""Unit and regression tests for non-box architectural primitives (template/_core.py, _out.py, check.py).

Self-contained: no ericw-tools/qbsp binaries or external BSPs required.
Run from the repository root:
    python3 -m unittest discover -s tests
"""
import contextlib
import io
import json
import math
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
QMAP_DIR = REPO_ROOT / 'qmap'
TEMPLATE_DIR = REPO_ROOT / 'template'
if str(QMAP_DIR) not in sys.path:
    sys.path.insert(0, str(QMAP_DIR))

import check  # noqa: E402
import collide_cmp  # noqa: E402
import texcheck  # noqa: E402


def _load_template(sym='none', layout_src=None, items_src=None):
    """Execute concatenated template (_core + layout + _itemh + items + _out) in an isolated dict."""
    core_src = (TEMPLATE_DIR / '_core.py').read_text(encoding='utf-8')
    core_src = core_src.replace("SYM = 'none'", f"SYM = '{sym}'", 1)
    if layout_src is None:
        layout_src = (TEMPLATE_DIR / '_layout.py').read_text(encoding='utf-8')
    itemh_src = (TEMPLATE_DIR / '_itemh.py').read_text(encoding='utf-8')
    if items_src is None:
        items_src = (TEMPLATE_DIR / '_items.py').read_text(encoding='utf-8')
    out_src = (TEMPLATE_DIR / '_out.py').read_text(encoding='utf-8')
    ns = {'__name__': 'template_test_mod'}
    combined = '\n'.join((core_src, layout_src, itemh_src, items_src, out_src))
    exec(compile(combined, '<template>', 'exec'), ns)
    return ns


def _build_and_dump(ns, td, name='testmap'):
    map_path = pathlib.Path(td) / f'{name}.map'
    json_path = pathlib.Path(td) / f'{name}.json'
    ns['write_map'](str(map_path))
    ns['dump'](str(json_path))
    return map_path, json_path, json.loads(json_path.read_text(encoding='utf-8'))


def _parse_map_clean(map_path):
    """Run collide_cmp.brushes() and assert zero degenerate/no-normal/mixed-contents warnings."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        res = collide_cmp.brushes(str(map_path))
    stderr = err.getvalue()
    warnings = [ln for ln in stderr.splitlines() if ln.startswith('WARNING:')]
    return res, warnings, stderr


class TestSlopedAndVaultedCeilings(unittest.TestCase):
    def test_sloped_gable_barrel_and_pendant_lamps(self):
        layout = """
carve((-256, -256, 256, 256), 0, 384, 'hall', sym=False)
gable_ceil((-256, -256, 256, 256), 'x', 256, 384, sym=False)
room_lamps((-256, -256, 256, 256), 384, step=256, value=400, sym=False)

carve((256, -64, 384, 64), 0, 160, 'hall', door=True, sym=False)
carve((384, -192, 768, 192), 0, 288, 'vault', sym=False)
barrel_vault((384, -192, 768, 192), 'y', 192, 288, segs=6, sym=False)
room_lamps((384, -192, 768, 192), 288, step=256, value=380, sym=False)

carve((-384, -128, -256, 128), 0, 256, 'overhang', sym=False)
sloped_ceil((-384, -128, -256, 128), 'x', 160, 224, top_z=256, sym=False)
room_lamps((-384, -128, -256, 128), 256, step=128, value=320, sym=False)

spawn(-128, 0, 0, 0, 's1', sym=False)
spawn(576, 0, 0, 180, 's2', sym=False)
"""
        ns = _load_template('none', layout_src=layout, items_src='')
        # Every ceiling lamp under sloped/vaulted ceilings must hang below the roof, never clip into it
        self.assertGreater(len(ns['PENDANT_LAMPS']), 0)
        for px, py, z_mount, z_stem_top in ns['PENDANT_LAMPS']:
            # Verify pendant mount does not exceed actual ceiling height over its 32x32 footprint
            ceil_ref = 384 if -256 <= px <= 256 else (288 if px >= 384 else 256)
            roof_min = ns['ceil_height_at'](px, py, ceil_ref, half=16)
            self.assertLessEqual(z_mount, roof_min + 1e-6)
            self.assertGreaterEqual(z_stem_top, z_mount)
        # Every light point must sit strictly below the sloped roof at its (x, y)
        for lx, ly, lz, *_ in ns['lights']:
            ceil_ref = 384 if -256 <= lx <= 256 else (288 if lx >= 384 else 256)
            roof_pt = ns['ceil_height_at'](lx, ly, ceil_ref, half=0)
            self.assertLess(lz, roof_pt - 16)
        with tempfile.TemporaryDirectory() as td:
            mp, _, data = _build_and_dump(ns, td)
            _, warnings, _ = _parse_map_clean(mp)
            self.assertEqual(warnings, [])
            chk = check.check_map(data, quiet=True)
            self.assertEqual(chk['problems'], [])
            self.assertEqual(chk['traps'], [])
            # Verify continuous V UV across barrel vault facets
            faces, _, _ = texcheck.map_data(mp)
            vault_undersides = [
                f for f in faces
                if -0.999 < f.normal[2] < -0.05 and f.vertices[:, 0].min() >= 383.5 and f.vertices[:, 0].max() <= 768.5
            ]
            self.assertEqual(len(vault_undersides), 6)
            vault_undersides.sort(key=lambda f: f.vertices[:, 1].mean())
            for a, b in zip(vault_undersides, vault_undersides[1:]):
                # Find shared edge y between consecutive facets
                shared_y = a.vertices[:, 1].max()
                pt_z = a.vertices[a.vertices[:, 1].argmax(), 2]
                pt = [[576.0, float(shared_y), float(pt_z)]]
                va = float(a.uv(pt)[0, 1])
                vb = float(b.uv(pt)[0, 1])
                self.assertAlmostEqual(va, vb, places=2)

    def test_sloped_ceil_symmetry_modes(self):
        layout = """
carve((-256, -256, 256, 256), 0, 320, 'mid', sym=False)
carve((256, -64, 384, 64), 0, 160, 'mid', door=True)
carve((384, -256, 768, 256), 0, 320, 'wing')
sloped_ceil((384, -256, 768, 256), 'x', 224, 320)
room_lamps((384, -256, 768, 256), 320, step=256, value=380)
spawn(576, 0, 0, 180, 'w')
"""
        for sym in ('rotate', 'mirror'):
            ns = _load_template(sym, layout_src=layout, items_src='')
            self.assertEqual(len(ns['SLOPED_CEILS']), 2)
            orig, copy = ns['SLOPED_CEILS']
            # In both rotate and mirror, x-axis slope flips sign (-1) on the x < 0 copy
            self.assertEqual(orig[2], 1)
            self.assertEqual(copy[2], -1)
            # Height at inner edge (+384 and -384) must match z_lo (224); outer edge (+/-768) = 320
            self.assertAlmostEqual(ns['ceil_height_at'](384 + 16, 0, 320, half=0),
                                   ns['ceil_height_at'](-384 - 16, 0, 320, half=0), places=2)
            with tempfile.TemporaryDirectory() as td:
                mp, _, data = _build_and_dump(ns, td)
                _, warnings, _ = _parse_map_clean(mp)
                self.assertEqual(warnings, [])
                chk = check.check_map(data, quiet=True)
                self.assertEqual(chk['problems'], [])


class TestArchesTrussesAndButtresses(unittest.TestCase):
    def test_arch_door_headroom_guard_and_illusionary_trim(self):
        # Reject spring height below z0 + 56
        bad_layout = """
carve((-256, -256, 256, 256), 0, 256, 'a', sym=False)
arch_door((256, -64, 384, 64), 'y', 0, 96, 'a', arch_h=48, sym=False)
"""
        with self.assertRaises(AssertionError):
            _load_template('none', layout_src=bad_layout, items_src='')

        # trim=True vs trim=False must have IDENTICAL collision (trim is func_detail_illusionary)
        base = """
carve((-256, -256, 256, 256), 0, 256, 'a', sym=False)
carve((384, -256, 768, 256), 0, 256, 'b', sym=False)
arch_door((256, -64, 384, 64), 'y', 0, 160, 'a', arch_h=48, trim={trim}, sym=False)
spawn(0, 0, 0, 0, 's1', sym=False)
spawn(576, 0, 0, 180, 's2', sym=False)
"""
        ns_plain = _load_template('none', layout_src=base.format(trim=False), items_src='')
        ns_trim = _load_template('none', layout_src=base.format(trim=True), items_src='')
        with tempfile.TemporaryDirectory() as td:
            m1, _, _ = _build_and_dump(ns_plain, td, 'plain')
            m2, _, _ = _build_and_dump(ns_trim, td, 'trim')
            b1, w1, _ = _parse_map_clean(m1)
            b2, w2, _ = _parse_map_clean(m2)
            self.assertEqual(w1, [])
            self.assertEqual(w2, [])
            for cls, label, differs, space in collide_cmp.CLASSES[:2]:
                diff, _, msg, _ = collide_cmp.compare(b1[cls], b2[cls], 8, cls, label, differs, space)
                self.assertFalse(diff, msg)

    def test_truss_and_buttress_v41_collision_policy(self):
        # Overhead truss >= floor + 96 defaults to solid; low truss (< floor + 96) defaults to non-solid
        layout = """
carve((-384, -384, 384, 384), 0, 384, 'hall', sym=False)
truss((-384, -12, 384, 12), 'x', 256, 384, beam_h=16, knee=32, sym=False)
truss((-384, 116, 384, 140), 'x', 80, 96, beam_h=16, knee=0, sym=False)
buttress((-384, -256, -352, -192), '-x', 0, 224, top_depth=8, solid=True, sym=False)
buttress((-384, 192, -352, 256), '-x', 0, 224, top_depth=8, solid=False, sym=False)
buttress((352, -256, 384, -192), '+x', 192, 320, top_depth=0, taper='bottom', solid=True, sym=False)
room_lamps((-384, -384, 384, 384), 384, step=256, value=450, sym=False)
spawn(-192, -192, 0, 45, 's1', sym=False)
spawn(192, 192, 0, 225, 's2', sym=False)
"""
        ns = _load_template('none', layout_src=layout, items_src='')
        self.assertTrue(ns['TRUSSES'][0][-1])    # high truss (256 - 32 = 224 >= 96) -> solid
        self.assertFalse(ns['TRUSSES'][1][-1])   # low beam (80 < 96) -> non-solid func_detail_illusionary
        # No ceiling lamp may overlap the overhead trusses
        for lx, ly, lz, *_ in ns['lights']:
            self.assertFalse(ns['_truss_hits'](lx, ly, lz - 8, lz + 40, half=16))
        with tempfile.TemporaryDirectory() as td:
            mp, _, data = _build_and_dump(ns, td)
            _, warnings, _ = _parse_map_clean(mp)
            self.assertEqual(warnings, [])
            chk = check.check_map(data, quiet=True)
            self.assertEqual(chk['problems'], [])
            self.assertEqual(chk['traps'], [])


class TestCurvedWallsRotundasAndCylinders(unittest.TestCase):
    def test_cylinder_and_rotunda_continuous_uv_wrap(self):
        layout = """
_rb = rotunda(0, 0, 288, 0, 288, 'rot', sides=12, openings=[('+x', 128, 160)], sym=False)
carve((288, -64, 448, 64), 0, 160, 'rot', door=True, sym=False)
carve((448, -256, 832, 256), 0, 288, 'east', sym=False)
cylinder(0, 0, 40, 0, 288, sides=12, kind='pillar', sym=False)
curved_wall(608, 0, 64, 96, 120, 240, 0, 96, segs=4, sym=False)
room_lamps(_rb, 288, step=256, value=460, sym=False)
spawn(-160, 0, 0, 0, 's1', sym=False)
spawn(736, 0, 0, 180, 's2', sym=False)
"""
        ns = _load_template('none', layout_src=layout, items_src='')
        with tempfile.TemporaryDirectory() as td:
            mp, _, data = _build_and_dump(ns, td)
            _, warnings, _ = _parse_map_clean(mp)
            self.assertEqual(warnings, [])
            chk = check.check_map(data, quiet=True)
            self.assertEqual(chk['problems'], [])
            self.assertEqual(chk['prism_separation'], [])
            self.assertEqual(chk['traps'], [])
            # Verify continuous UVs around cylinder (all 12 visible facets + closing seam)
            faces, brushes_, _ = texcheck.map_data(mp)
            vis_faces = texcheck.source_visibility(faces, brushes_)
            # Assign synthetic texture periods to verify exact UV continuity with texcheck.alignment_checks
            for f in vis_faces:
                f.period = (64, 128) if f.texture in ('bk_pillar', 'bk_pbase', 'bk_pcap') else (128, 128)
            pillar_faces = [f for f in vis_faces if f.texture == 'bk_pillar' and abs(f.normal[2]) < 1e-4]
            self.assertEqual(len(pillar_faces), 12)
            pillar_findings = texcheck.alignment_checks(pillar_faces, corner_u=True)
            self.assertEqual(pillar_findings, [], pillar_findings)
            # Verify curved_wall inner & outer arcs have zero U seam between consecutive segments
            cw_faces = [
                f for f in vis_faces
                if abs(f.normal[2]) < 1e-4 and f.vertices[:, 0].min() >= 500 and f.vertices[:, 0].max() <= 620
                and f.vertices[:, 2].min() >= 31 and f.vertices[:, 2].max() <= 97
                and abs(f.normal[0]) < 0.999 and abs(f.normal[1]) < 0.999
            ]
            # Filter strictly curved arc faces (exclude 2 radial end-caps by checking radius from (608, 0))
            arc_faces = []
            for f in cw_faces:
                c = f.vertices.mean(axis=0)
                dx, dy = c[0] - 608.0, c[1]
                r_c = math.hypot(dx, dy)
                radial = abs((dx * f.normal[0] + dy * f.normal[1]) / max(1e-6, r_c))
                if radial > 0.85:
                    arc_faces.append(f)
            self.assertGreaterEqual(len(arc_faces), 8)
            self.assertEqual(texcheck.alignment_checks(arc_faces, corner_u=True), [])

    def test_rotunda_still_flags_close_interior_pillar(self):
        # Grouping rotunda wedges must NOT hide an interior pillar placed < 64u from the rotunda wall
        layout = """
rotunda(0, 0, 224, 0, 256, 'rot', sides=12, sym=False)
cylinder(160, 0, 40, 0, 256, sides=8, kind='pillar', sym=False)
spawn(-128, 0, 0, 0, 's1', sym=False)
spawn(0, 128, 0, 270, 's2', sym=False)
"""
        ns = _load_template('none', layout_src=layout, items_src='')
        with tempfile.TemporaryDirectory() as td:
            _, _, data = _build_and_dump(ns, td)
            chk = check.check_map(data, quiet=True)
            self.assertTrue(chk['prism_separation'], 'expected close pillar inside rotunda to be flagged')

    def test_curved_wall_and_rotunda_symmetry(self):
        layout = """
carve((-256, -256, 256, 256), 0, 256, 'mid', sym=False)
carve((256, -64, 384, 64), 0, 160, 'mid', door=True)
rotunda(608, 0, 224, 0, 256, 'wing', sides=12, openings=[('-x', 128, 160)])
curved_wall(608, 0, 64, 96, -45, 45, 0, 96, segs=4)
spawn(512, 0, 0, 180, 's')
"""
        for sym in ('rotate', 'mirror'):
            ns = _load_template(sym, layout_src=layout, items_src='')
            with tempfile.TemporaryDirectory() as td:
                mp, _, data = _build_and_dump(ns, td)
                _, warnings, _ = _parse_map_clean(mp)
                self.assertEqual(warnings, [])
                chk = check.check_map(data, quiet=True)
                self.assertEqual(chk['problems'], [])
                self.assertEqual(chk['prism_separation'], [])


class TestDiagonalRamps(unittest.TestCase):
    def test_diag_ramp_walkable_and_elevated_slab(self):
        layout = """
carve((-384, -384, 384, 384), 0, 320, 'hall', sym=False)
fill((128, -384, 384, -128), BOT, 128, None, sym=False)
diag_ramp(-96, 96, 160, -160, 96, 0, 128, sym=False)
# Second diagonal ramp as an elevated sloped slab (thick=24) in the NW quadrant, well clear of ramp 1
fill((-384, 192, -192, 384), BOT, 96, None, sym=False)
diag_ramp(-64, 192, -224, 320, 80, 0, 96, thick=24, sym=False)
spawn(-256, -256, 0, 45, 'lo', sym=False)
spawn(256, -256, 128, 135, 'hi1', sym=False)
spawn(-288, 288, 96, 315, 'hi2', sym=False)
"""
        ns = _load_template('none', layout_src=layout, items_src='')
        with tempfile.TemporaryDirectory() as td:
            mp, _, data = _build_and_dump(ns, td)
            _, warnings, _ = _parse_map_clean(mp)
            self.assertEqual(warnings, [])
            chk = check.check_map(data, quiet=True)
            self.assertEqual(chk['problems'], [])
            self.assertEqual(chk['traps'], [])
            self.assertEqual(chk['stair_feet'], [])

    def test_diag_ramp_blocked_foot_flagged_by_check(self):
        layout = """
carve((-384, -384, 384, 384), 0, 256, 'hall', sym=False)
fill((128, -384, 384, -128), BOT, 96, None, sym=False)
diag_ramp(-32, 32, 160, -160, 96, 0, 96, sym=False)
fill((-64, 32, 0, 96), 0, 128, 'crate', sym=False)
spawn(-256, -256, 0, 45, 'lo', sym=False)
spawn(256, -256, 96, 135, 'hi', sym=False)
"""
        ns = _load_template('none', layout_src=layout, items_src='')
        with tempfile.TemporaryDirectory() as td:
            _, _, data = _build_and_dump(ns, td)
            chk = check.check_map(data, quiet=True)
            self.assertTrue(any('diag_ramp foot' in s for s in chk['stair_feet']), chk['stair_feet'])

    def test_diag_ramp_rejects_steeper_than_45_deg(self):
        bad = """
carve((-256, -256, 256, 256), 0, 256, 'h', sym=False)
diag_ramp(0, 0, 64, 64, 64, 0, 128, sym=False)
"""
        with self.assertRaises(AssertionError):
            _load_template('none', layout_src=bad, items_src='')


class TestTemplateDemoAllSymmetryModes(unittest.TestCase):
    def test_template_demo_builds_cleanly_in_all_three_sym_modes(self):
        counts = {}
        for sym in ('none', 'rotate', 'mirror'):
            with self.subTest(sym=sym):
                ns = _load_template(sym)
                counts[sym] = {
                    'sloped_ceils': len(ns['SLOPED_CEILS']),
                    'trusses': len(ns['TRUSSES']),
                    'buttresses': len(ns['BUTTRESSES']),
                    'diag_ramps': len(ns['DIAG_RAMPS']),
                    'arch_trims': len(ns['ARCH_TRIMS']),
                    'prism_groups': len({m.get('group') for m in ns['PRISM_META'] if m.get('group') is not None}),
                    'cyl_prisms': sum(1 for _p, _z0, _z1, k in ns['PRISMS'] if k == 'pillar'),
                }
                with tempfile.TemporaryDirectory() as td:
                    mp, _, data = _build_and_dump(ns, td, f'demo_{sym}')
                    b, warnings, _ = _parse_map_clean(mp)
                    self.assertEqual(warnings, [], f'SYM={sym} collide_cmp warnings: {warnings}')
                    self.assertGreater(len(b['solid']), 100)
                    chk = check.check_map(data, quiet=True)
                    self.assertEqual(chk['problems'], [], f'SYM={sym} problems: {chk["problems"]}')
                    self.assertEqual(chk['item_problems'], [], f'SYM={sym} item_problems: {chk["item_problems"]}')
                    self.assertEqual(chk['traps'], [], f'SYM={sym} traps')
                    self.assertEqual(chk['stair_feet'], [], f'SYM={sym} stair_feet: {chk["stair_feet"]}')
                    self.assertEqual(chk['slots'], [], f'SYM={sym} slots: {chk["slots"]}')
                    self.assertEqual(chk['prism_separation'], [], f'SYM={sym} prism_sep: {chk["prism_separation"]}')
                    self.assertEqual(chk['pockets'], [], f'SYM={sym} pockets: {chk["pockets"]}')
                    # Source-level texcheck: zero illusionary content hazards and zero sky overlaps
                    report = texcheck.audit(mp, wad_paths=[])
                    bad_codes = [f for f in report['findings'] if f['code'] in ('illusionary-contents', 'sky-overlap')]
                    self.assertEqual(bad_codes, [], f'SYM={sym} hazards: {bad_codes}')
        # Symmetric modes must actually emit copied geometry for every new primitive family
        for sym in ('rotate', 'mirror'):
            for key, base_n in counts['none'].items():
                self.assertGreater(counts[sym][key], base_n,
                                   f'SYM={sym} did not emit symmetric copies for {key}: {counts[sym][key]} <= {base_n}')


if __name__ == '__main__':
    unittest.main()
