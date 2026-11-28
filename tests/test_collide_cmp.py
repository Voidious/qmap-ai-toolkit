"""Regression tests for qmap/collide_cmp.py (hull-0 rules, ROI merging/masking, parser hardening).

Run from the repository root:
    python3 -m unittest discover -s tests
or directly:
    python3 tests/test_collide_cmp.py
"""
import contextlib
import io
import math
import pathlib
import random
import subprocess
import sys
import tempfile
import unittest

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
QMAP_DIR = REPO_ROOT / 'qmap'
COLLIDE_CMP = QMAP_DIR / 'collide_cmp.py'
sys.path.insert(0, str(QMAP_DIR))

import collide_cmp as cc  # noqa: E402


def box_faces(x0, y0, z0, x1, y1, z1, tex='wall1', fmt='quaked', q2=''):
    if fmt == 'quaked':
        return [
            f'( {x0} {y0} {z0} ) ( {x0} {y1} {z0} ) ( {x0} {y1} {z1} ) {tex} 0 0 0 1 1{q2}',
            f'( {x1} {y0} {z0} ) ( {x1} {y0} {z1} ) ( {x1} {y1} {z1} ) {tex} 0 0 0 1 1{q2}',
            f'( {x0} {y0} {z0} ) ( {x0} {y0} {z1} ) ( {x1} {y0} {z1} ) {tex} 0 0 0 1 1{q2}',
            f'( {x0} {y1} {z0} ) ( {x1} {y1} {z0} ) ( {x1} {y1} {z1} ) {tex} 0 0 0 1 1{q2}',
            f'( {x0} {y0} {z0} ) ( {x1} {y0} {z0} ) ( {x1} {y1} {z0} ) {tex} 0 0 0 1 1{q2}',
            f'( {x0} {y0} {z1} ) ( {x0} {y1} {z1} ) ( {x1} {y1} {z1} ) {tex} 0 0 0 1 1{q2}',
        ]
    if fmt == 'valve':
        return [
            f'( {x0} {y0} {z0} ) ( {x0} {y1} {z0} ) ( {x0} {y1} {z1} ) {tex} [ 0 1 0 0 ] [ 0 0 -1 0 ] 0 1 1{q2}',
            f'( {x1} {y0} {z0} ) ( {x1} {y0} {z1} ) ( {x1} {y1} {z1} ) {tex} [ 0 1 0 0 ] [ 0 0 -1 0 ] 0 1 1{q2}',
            f'( {x0} {y0} {z0} ) ( {x0} {y0} {z1} ) ( {x1} {y0} {z1} ) {tex} [ 1 0 0 0 ] [ 0 0 -1 0 ] 0 1 1{q2}',
            f'( {x0} {y1} {z0} ) ( {x1} {y1} {z0} ) ( {x1} {y1} {z1} ) {tex} [ 1 0 0 0 ] [ 0 0 -1 0 ] 0 1 1{q2}',
            f'( {x0} {y0} {z0} ) ( {x1} {y0} {z0} ) ( {x1} {y1} {z0} ) {tex} [ 1 0 0 0 ] [ 0 -1 0 0 ] 0 1 1{q2}',
            f'( {x0} {y0} {z1} ) ( {x0} {y1} {z1} ) ( {x1} {y1} {z1} ) {tex} [ 1 0 0 0 ] [ 0 -1 0 0 ] 0 1 1{q2}',
        ]
    m = '( ( 0.015625 0 0 ) ( 0 0.015625 0 ) )'
    return [
        f'( {x0} {y0} {z0} ) ( {x0} {y1} {z0} ) ( {x0} {y1} {z1} ) {m} {tex} 0 0 0',
        f'( {x1} {y0} {z0} ) ( {x1} {y0} {z1} ) ( {x1} {y1} {z1} ) {m} {tex} 0 0 0',
        f'( {x0} {y0} {z0} ) ( {x0} {y0} {z1} ) ( {x1} {y0} {z1} ) {m} {tex} 0 0 0',
        f'( {x0} {y1} {z0} ) ( {x1} {y1} {z0} ) ( {x1} {y1} {z1} ) {m} {tex} 0 0 0',
        f'( {x0} {y0} {z0} ) ( {x1} {y0} {z0} ) ( {x1} {y1} {z0} ) {m} {tex} 0 0 0',
        f'( {x0} {y0} {z1} ) ( {x0} {y1} {z1} ) ( {x1} {y1} {z1} ) {m} {tex} 0 0 0',
    ]


def brush_block(faces, open_tok='{', close_tok='}'):
    return f'{open_tok}\n' + '\n'.join(faces) + f'\n{close_tok}'


def bp_brush(faces, header='brushDef', o1='{', o2='{', c2='}', c1='}'):
    hdr = f'{header}\n' if header else ''
    return f'{o1}\n{hdr}{o2}\n' + '\n'.join(faces) + f'\n{c2}\n{c1}'


def sealed_room():
    walls = [
        brush_block(box_faces(-272, -272, -272, -256, 272, 272)),
        brush_block(box_faces(256, -272, -272, 272, 272, 272)),
        brush_block(box_faces(-256, -272, -272, 256, -256, 272)),
        brush_block(box_faces(-256, 256, -272, 256, 272, 272)),
        brush_block(box_faces(-256, -256, -272, 256, 256, -256)),
        brush_block(box_faces(-256, -256, 256, 256, 256, 272)),
    ]
    return (
        '{\n"classname" "worldspawn"\n' + '\n'.join(walls) + '\n}\n'
        '{\n"classname" "info_player_start"\n"origin" "128 128 0"\n}\n'
    )


def entity_block(classname, *brushes, extra_epairs=''):
    body = f'"classname" "{classname}"\n' if classname is not None else ''
    return '{\n' + body + extra_epairs + '\n'.join(brushes) + '\n}\n'


def parse_map_text(txt):
    with tempfile.TemporaryDirectory() as td:
        mp = pathlib.Path(td) / 't.map'
        mp.write_text(txt, encoding='utf-8', newline='\n')
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = cc.brushes(str(mp))
        return {k: len(v) for k, v in out.items() if v}, err.getvalue().strip()


def run_cli(txt_a, txt_b, extra_args=()):
    with tempfile.TemporaryDirectory() as td:
        pa, pb = pathlib.Path(td) / 'a.map', pathlib.Path(td) / 'b.map'
        pa.write_text(txt_a, encoding='utf-8', newline='\n')
        pb.write_text(txt_b, encoding='utf-8', newline='\n')
        r = subprocess.run(
            [sys.executable, str(COLLIDE_CMP), str(pa), str(pb), *extra_args],
            capture_output=True, text=True,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()


def brute_diff_aabb(A, B, step):
    """Independent whole-grid occupancy symmetric difference for axis-aligned boxes."""
    all_b = A + B
    if not all_b:
        return 0
    lo = np.min([b[0] for b in all_b], axis=0)
    hi = np.max([b[1] for b in all_b], axis=0)
    ilo = [math.floor(float(v) / step) for v in lo]
    ihi = [max(l + 1, math.ceil(float(v) / step)) for l, v in zip(ilo, hi)]
    nx, ny, nz = ihi[0] - ilo[0], ihi[1] - ilo[1], ihi[2] - ilo[2]
    xs = (ilo[0] + np.arange(nx) + 0.5) * step
    ys = (ilo[1] + np.arange(ny) + 0.5) * step
    zs = (ilo[2] + np.arange(nz) + 0.5) * step

    def occ(bs):
        g = np.zeros((nx, ny, nz), bool)
        for blo, bhi, _, _, _ in bs:
            mx = (xs >= blo[0] - 1e-4) & (xs <= bhi[0] + 1e-4)
            my = (ys >= blo[1] - 1e-4) & (ys <= bhi[1] + 1e-4)
            mz = (zs >= blo[2] - 1e-4) & (zs <= bhi[2] + 1e-4)
            g |= mx[:, None, None] & my[None, :, None] & mz[None, None, :]
        return g

    return int((occ(A) ^ occ(B)).sum())


class TestHull0AndEntityRules(unittest.TestCase):
    def test_entity_texture_matrix(self):
        """Full 7x11 (entity x texture) matrix matching live-qbsp player + hull-0 rules."""
        solid_ents = ('worldspawn', 'func_group', 'func_detail', 'func_detail_wall', 'func_detail_fence')
        # Expected added brush counts per class for a single cube of each texture.
        expected_by_ent = {}
        for ent in solid_ents:
            expected_by_ent[ent] = {
                'wall1':    {'solid': 1, 'proj': 1},
                'skip':     {'solid': 1, 'proj': 1},
                'trigger':  {'solid': 1, 'proj': 1},
                'clip':     {'solid': 1},
                'sky1':     {'solid': 1, 'sky': 1},
                '*water':   {'water': 1},
                '*slime':   {'slime': 1},
                '*lava':    {'lava': 1},
                'hint':     {},
                'hintskip': {},
                'origin':   {},
            }
        expected_by_ent['func_detail_illusionary'] = {
            'wall1':    {},
            'skip':     {},
            'trigger':  {},
            'clip':     {},
            'sky1':     {'sky': 1},
            '*water':   {'water': 1},
            '*slime':   {'slime': 1},
            '*lava':    {'lava': 1},
            'hint':     {},
            'hintskip': {},
            'origin':   {},
        }
        expected_by_ent['func_illusionary_visblocker'] = {
            'wall1':    {},
            'skip':     {},
            'trigger':  {},
            'clip':     {'solid': 1},
            'sky1':     {},
            '*water':   {},
            '*slime':   {},
            '*lava':    {},
            'hint':     {},
            'hintskip': {},
            'origin':   {},
        }
        for ent, tex_map in expected_by_ent.items():
            for tex, exp in tex_map.items():
                with self.subTest(entity=ent, texture=tex):
                    txt = entity_block(ent, brush_block(box_faces(-64, -64, -64, 64, 64, 64, tex)))
                    got, _ = parse_map_text(txt)
                    self.assertEqual(got, exp)

    def test_hull0_cli_scenarios(self):
        base = entity_block('worldspawn', brush_block(box_faces(-256, -256, -256, 256, 256, -240, 'wall1')))
        cube = lambda tex: brush_block(box_faces(0, 0, 0, 64, 64, 64, tex))

        scenarios = [
            ('wall -> clip',
             base + entity_block('worldspawn', cube('wall1')),
             base + entity_block('worldspawn', cube('clip')),
             1, ('collision identical', 'PROJECTILE COLLISION DIFFERS')),
            ('wall -> sky1',
             base + entity_block('worldspawn', cube('wall1')),
             base + entity_block('worldspawn', cube('sky1')),
             1, ('collision identical', 'PROJECTILE COLLISION DIFFERS', 'SKY CONTENTS DIFFER')),
            ('wall -> skip',
             base + entity_block('worldspawn', cube('wall1')),
             base + entity_block('worldspawn', cube('skip')),
             0, ('collision identical', 'hull-0/contents identical: projectile collision')),
            ('wall -> trigger',
             base + entity_block('worldspawn', cube('wall1')),
             base + entity_block('worldspawn', cube('trigger')),
             0, ('collision identical',)),
            ('clip -> sky1',
             base + entity_block('worldspawn', cube('clip')),
             base + entity_block('worldspawn', cube('sky1')),
             1, ('collision identical', 'SKY CONTENTS DIFFER')),
            ('func_detail wall -> clip',
             base + entity_block('func_detail', cube('wall1')),
             base + entity_block('func_detail', cube('clip')),
             1, ('PROJECTILE COLLISION DIFFERS',)),
            ('func_detail_illusionary sky1',
             base,
             base + entity_block('func_detail_illusionary', cube('sky1')),
             1, ('collision identical', 'SKY CONTENTS DIFFER')),
            ('func_detail_illusionary sky1+hint',
             base,
             base + entity_block('func_detail_illusionary', cube('sky1').replace('sky1', 'hint', 1)),
             0, ('collision identical',)),
            ('func_detail_illusionary wall1',
             base,
             base + entity_block('func_detail_illusionary', cube('wall1')),
             0, ('collision identical',)),
            ('func_detail_illusionary clip',
             base,
             base + entity_block('func_detail_illusionary', cube('clip')),
             0, ('collision identical',)),
            ('visblocker clip added',
             base,
             base + entity_block('func_illusionary_visblocker', cube('clip')),
             1, ('COLLISION DIFFERS',)),
            ('visblocker sky1 added',
             base,
             base + entity_block('func_illusionary_visblocker', cube('sky1')),
             0, ('collision identical',)),
            ('visblocker clip == world clip',
             base + entity_block('func_illusionary_visblocker', cube('clip')),
             base + entity_block('worldspawn', cube('clip')),
             0, ('collision identical',)),
            ('visblocker clip != world wall',
             base + entity_block('func_illusionary_visblocker', cube('clip')),
             base + entity_block('worldspawn', cube('wall1')),
             1, ('collision identical', 'PROJECTILE COLLISION DIFFERS')),
            ('wall removed inside unchanged clip',
             base + entity_block('worldspawn',
                                 brush_block(box_faces(0, 0, 0, 128, 128, 128, 'clip')),
                                 brush_block(box_faces(32, 32, 32, 96, 96, 96, 'wall1'))),
             base + entity_block('worldspawn',
                                 brush_block(box_faces(0, 0, 0, 128, 128, 128, 'clip'))),
             1, ('collision identical', 'PROJECTILE COLLISION DIFFERS')),
        ]
        for name, map_a, map_b, exp_rc, substrings in scenarios:
            with self.subTest(name=name):
                rc, out, _ = run_cli(map_a, map_b)
                self.assertEqual(rc, exp_rc, f'{name}: stdout={out}')
                for sub in substrings:
                    self.assertIn(sub, out)

    def test_proj_reuse_matches_independent_compare(self):
        """Main-loop proj reuse optimization must match running solid and proj separately."""
        rng = random.Random(1337)
        with tempfile.TemporaryDirectory() as td:
            pa, pb = pathlib.Path(td) / 'a.map', pathlib.Path(td) / 'b.map'
            for seed in range(40):
                def gen_brushes():
                    out = []
                    for _ in range(rng.randint(2, 6)):
                        x0 = rng.randint(-2, 4) * 16
                        y0 = rng.randint(-2, 4) * 16
                        z0 = rng.randint(0, 2) * 16
                        dx = rng.choice([16, 32, 48])
                        dy = rng.choice([16, 32, 48])
                        dz = rng.choice([16, 32])
                        tex = rng.choice(['wall1', 'wall1', 'clip', 'sky1'])
                        out.append(brush_block(box_faces(x0, y0, z0, x0 + dx, y0 + dy, z0 + dz, tex)))
                    return out

                shared = gen_brushes()[:2]
                mA = entity_block('worldspawn', *(shared + gen_brushes()))
                mB = entity_block('worldspawn', *(shared + gen_brushes()))
                pa.write_text(mA, encoding='utf-8')
                pb.write_text(mB, encoding='utf-8')
                A, B = cc.brushes(str(pa)), cc.brushes(str(pb))
                indep_diff = False
                for kind, label, banner, space in cc.CLASSES:
                    if kind not in ('solid', 'proj') and not A[kind] and not B[kind]:
                        continue
                    d, _, _, _ = cc.compare(A[kind], B[kind], 8.0, kind, label, banner, space)
                    indep_diff |= d
                old_argv = sys.argv
                buf = io.StringIO()
                try:
                    sys.argv = ['collide_cmp.py', str(pa), str(pb), '--step', '8']
                    with contextlib.redirect_stdout(buf):
                        try:
                            cc.main()
                            main_diff = False
                        except SystemExit as e:
                            main_diff = (e.code != 0)
                finally:
                    sys.argv = old_argv
                self.assertEqual(main_diff, indep_diff, f'seed={seed}: out={buf.getvalue()}')


class TestRoiMergeAndMasking(unittest.TestCase):
    def test_l_shape_does_not_inflate(self):
        l_boxes = [
            ([0.0, 0.0, 0.0], [2000.0, 32.0, 256.0]),
            ([0.0, 0.0, 0.0], [32.0, 2000.0, 256.0]),
            ([1968.0, 0.0, 0.0], [2000.0, 2000.0, 256.0]),
        ]
        comps = cc.merge_boxes(l_boxes)
        self.assertEqual(len(comps), 3)
        _, vox, max_sl = cc.roi_grid(comps, 0.25)
        self.assertLessEqual(vox, cc.MAX_TOTAL_VOXELS)
        self.assertLessEqual(max_sl, cc.MAX_SLICE)
        self.assertLess(vox, 3.5e9)

    def test_bounded_bloat_random_configs(self):
        rng = random.Random(42)
        for _ in range(500):
            n = rng.randint(2, 10)
            boxes = []
            for _ in range(n):
                x0, y0, z0 = rng.randint(0, 60), rng.randint(0, 60), rng.randint(0, 40)
                dx = rng.choice([2, 4, 8, 32, 64])
                dy = rng.choice([2, 4, 8, 32, 64])
                dz = rng.choice([2, 4, 16, 32])
                boxes.append(([float(x0), float(y0), float(z0)],
                              [float(x0 + dx), float(y0 + dy), float(z0 + dz)]))
            raw_sum = sum((b[1][0] - b[0][0]) * (b[1][1] - b[0][1]) * (b[1][2] - b[0][2]) for b in boxes)
            _, vox, _ = cc.roi_grid(cc.merge_boxes(boxes), 1.0)
            self.assertLessEqual(vox, raw_sum * 1.5 + 1e-6)

    def test_overlap_masking_exact_vs_brute_force(self):
        for seed in range(60):
            r = random.Random(seed)
            step = (0.25, 0.5, 1.0, 2.0, 4.0)[seed % 5]
            scale = max(1, int(step)) if step >= 1 else 1

            def mk_set():
                bs = []
                for _ in range(r.randint(2, 7)):
                    x0 = r.randint(-8, 8) * scale
                    y0 = r.randint(-8, 8) * scale
                    z0 = r.randint(-4, 4) * scale
                    dx = r.choice([1, 2, 4, 8]) * scale
                    dy = r.choice([1, 2, 4, 8]) * scale
                    dz = r.choice([1, 2, 4]) * scale
                    pb = cc.parse_brush(brush_block(box_faces(x0, y0, z0, x0 + dx, y0 + dy, z0 + dz)))
                    bs.append(tuple(pb[:5]))
                return bs

            A, B = mk_set(), mk_set()
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                diff, _, msg, _ = cc.compare(A, B, step, 'solid', 'collision', 'COLLISION DIFFERS', 'solid space')
            got = int(msg.split('COLLISION DIFFERS: ')[1].split(' voxels')[0]) if diff else 0
            exp = brute_diff_aabb(A, B, step)
            self.assertEqual(got, exp, f'seed={seed} step={step}: msg={msg}')


class TestParserHardening(unittest.TestCase):
    def test_optional_brush_spans_preserve_the_default_token_walk(self):
        brush = brush_block(box_faces(0, 0, 0, 64, 64, 64))
        primitive = bp_brush(box_faces(0, 0, 0, 64, 64, 64, fmt='bp'))
        text = entity_block('worldspawn', '{ }', brush, primitive,
                            extra_epairs=f'"message" "{brush}"\n')
        original = list(cc.entities(text))
        positioned = list(cc.entities(text, spans=True))
        self.assertEqual(len(positioned), len(original))
        for (blocks, classname), (spans, positioned_classname) in zip(original, positioned):
            self.assertEqual(classname, positioned_classname)
            self.assertEqual(blocks, [text[start:end] for start, end in spans])
            self.assertEqual(blocks, ['{ }', brush, primitive])
            self.assertGreater(spans[1][0], text.index('"message"') + len(brush))

    def setUp(self):
        self.room = sealed_room()
        self.cube = box_faces(-64, -64, -64, 64, 64, 64, 'wall1')
        self.valve_cube = box_faces(-64, -64, -64, 64, 64, 64, 'wall1', fmt='valve')

    def test_brace_texture_names_do_not_hide_collision(self):
        """Quoted and unquoted '{'/' }' texture names are face data, never structural braces."""
        cases = [
            ('quaked quoted {',  brush_block([self.cube[0].replace('wall1', '"{"')] + self.cube[1:])),
            ('quaked quoted }',  brush_block([self.cube[0].replace('wall1', '"}"')] + self.cube[1:])),
            ('quaked bare {',    brush_block([self.cube[0].replace('wall1', '{')] + self.cube[1:])),
            ('quaked bare }',    brush_block([self.cube[0].replace('wall1', '}')] + self.cube[1:])),
            ('valve quoted {',   brush_block([self.valve_cube[0].replace('wall1', '"{"')] + self.valve_cube[1:])),
            ('valve quoted }',   brush_block([self.valve_cube[0].replace('wall1', '"}"')] + self.valve_cube[1:])),
            ('valve bare {',     brush_block([self.valve_cube[0].replace('wall1', '{')] + self.valve_cube[1:])),
            ('valve bare }',     brush_block([self.valve_cube[0].replace('wall1', '}')] + self.valve_cube[1:])),
            ('bp quoted {',      bp_brush(box_faces(-64, -64, -64, 64, 64, 64, '"{"', fmt='bp'))),
            ('bp quoted }',      bp_brush(box_faces(-64, -64, -64, 64, 64, 64, '"}"', fmt='bp'))),
            ('bp bare {',        bp_brush(box_faces(-64, -64, -64, 64, 64, 64, '{', fmt='bp'))),
            ('bp bare }',        bp_brush(box_faces(-64, -64, -64, 64, 64, 64, '}', fmt='bp'))),
        ]
        for name, br in cases:
            with self.subTest(name=name):
                added = self.room + entity_block('func_detail', br)
                counts, err = parse_map_text(added)
                self.assertEqual(counts, {'solid': 7, 'proj': 7})
                self.assertEqual(err, '')
                rc, out, cli_err = run_cli(self.room, added)
                self.assertEqual(rc, 1, f'{name}: stdout={out} stderr={cli_err}')
                self.assertIn('COLLISION DIFFERS', out)
                self.assertIn('PROJECTILE COLLISION DIFFERS', out)

    def test_brace_texture_does_not_swallow_following_entity(self):
        first = entity_block('func_detail',
                             brush_block([self.cube[0].replace('wall1', '"{"')] + self.cube[1:]))
        second = entity_block('func_detail',
                              brush_block(box_faces(80, 0, 0, 144, 64, 64, 'wall1')))
        counts, err = parse_map_text(self.room + first + second)
        self.assertEqual(counts, {'solid': 8, 'proj': 8})
        self.assertEqual(err, '')

    def test_quoted_brush_delimiters_and_layouts(self):
        cases = [
            ('quoted quaked braces',
             brush_block(self.cube, '"{"', '"}"')),
            ('quoted brushDef braces',
             bp_brush(box_faces(-64, -64, -64, 64, 64, 64, 'wall1', fmt='bp'),
                      header='"brushDef"', o1='"{"', o2='"{"', c2='"}"', c1='"}"')),
            ('quoted brushDef no header',
             bp_brush(box_faces(-64, -64, -64, 64, 64, 64, 'wall1', fmt='bp'),
                      header='', o1='"{"', o2='"{"', c2='"}"', c1='"}"')),
            ('same-line face after open brace',
             '{ ' + '\n'.join(self.cube) + '\n}'),
            ('same-line brushDef close',
             '{\nbrushDef\n{\n' + '\n'.join(box_faces(-64, -64, -64, 64, 64, 64, 'wall1', fmt='bp')) + '\n} }'),
            ('q2 extended ints same-line close',
             '{\n' + '\n'.join(box_faces(-64, -64, -64, 64, 64, 64, 'wall1', q2=' 0 0 0')) + ' }'),
        ]
        for name, br in cases:
            with self.subTest(name=name):
                counts, err = parse_map_text(self.room + entity_block('func_detail', br))
                self.assertEqual(counts, {'solid': 7, 'proj': 7})
                self.assertEqual(err, '')

    def test_quoted_special_textures(self):
        cases = [
            ('quoted *lava',       brush_block(box_faces(-64, -64, -64, 64, 64, 64, '"*lava"')),      {'solid': 6, 'proj': 6, 'lava': 1}, ''),
            ('quoted hint',        brush_block([self.cube[0].replace('wall1', '"hint"')] + self.cube[1:]), {'solid': 6, 'proj': 6}, 'hint x1'),
            ('quoted clip',        brush_block(box_faces(-64, -64, -64, 64, 64, 64, '"clip"')),       {'solid': 7, 'proj': 6}, ''),
            ('quoted sky1',        brush_block(box_faces(-64, -64, -64, 64, 64, 64, '"sky1"')),       {'solid': 7, 'proj': 6, 'sky': 1}, ''),
            ('quoted *lava //x',   brush_block(box_faces(-64, -64, -64, 64, 64, 64, '"*lava //x"')),  {'solid': 6, 'proj': 6, 'lava': 1}, ''),
            ('bp quoted *lava',    bp_brush(box_faces(-64, -64, -64, 64, 64, 64, '"*lava"', fmt='bp')), {'solid': 6, 'proj': 6, 'lava': 1}, ''),
        ]
        for name, br, exp_counts, exp_err_sub in cases:
            with self.subTest(name=name):
                counts, err = parse_map_text(self.room + entity_block('func_detail', br))
                self.assertEqual(counts, exp_counts)
                if exp_err_sub:
                    self.assertIn(exp_err_sub, err)
                else:
                    self.assertEqual(err, '')

    def test_brush_comments_and_brushdef_textures(self):
        lava_face = box_faces(-64, -64, -64, 64, 64, 64, '*lava')[0]
        hint_face = self.cube[0].replace('wall1', 'hint')
        cases = [
            ('commented // *lava face',  '{\n// ' + lava_face + '\n' + '\n'.join(self.cube) + '\n}', {'solid': 7, 'proj': 7}, ''),
            ('commented // hint face',   '{\n// ' + hint_face + '\n' + '\n'.join(self.cube) + '\n}', {'solid': 7, 'proj': 7}, ''),
            ('commented ; hint face',    '{\n; ' + hint_face + '\n' + '\n'.join(self.cube) + '\n}',  {'solid': 7, 'proj': 7}, ''),
            ('commented empty brush',    '{\n// ' + self.cube[0] + '\n}',                            {'solid': 6, 'proj': 6}, ''),
            ('trailing face comment',    '{\n' + '\n'.join(f + ' // hi' for f in self.cube) + '\n}', {'solid': 7, 'proj': 7}, ''),
            ('mid-token // in texture',  brush_block(box_faces(-64, -64, -64, 64, 64, 64, '*lava//x')), {'solid': 6, 'proj': 6, 'lava': 1}, ''),
            ('bp wall1',                 bp_brush(box_faces(-64, -64, -64, 64, 64, 64, 'wall1', fmt='bp')), {'solid': 7, 'proj': 7}, ''),
            ('bp *lava',                 bp_brush(box_faces(-64, -64, -64, 64, 64, 64, '*lava', fmt='bp')), {'solid': 6, 'proj': 6, 'lava': 1}, ''),
            ('bp hint',                  bp_brush(box_faces(-64, -64, -64, 64, 64, 64, 'hint', fmt='bp')),  {'solid': 6, 'proj': 6}, 'hint x1'),
            ('bp clip',                  bp_brush(box_faces(-64, -64, -64, 64, 64, 64, 'clip', fmt='bp')),  {'solid': 7, 'proj': 6}, ''),
            ('bp sky1',                  bp_brush(box_faces(-64, -64, -64, 64, 64, 64, 'sky1', fmt='bp')),  {'solid': 7, 'proj': 6, 'sky': 1}, ''),
        ]
        for name, br, exp_counts, exp_err_sub in cases:
            with self.subTest(name=name):
                counts, err = parse_map_text(self.room + entity_block('func_detail', br))
                self.assertEqual(counts, exp_counts)
                if exp_err_sub:
                    self.assertIn(exp_err_sub, err)
                else:
                    self.assertEqual(err, '')

    def test_bare_token_embedded_quote_before_commented_face(self):
        """A quote inside a bare texture token (e.g. wall"mark) must not swallow a following comment."""
        hint_face = self.cube[0].replace('wall1', 'hint')
        lava_face = self.cube[0].replace('wall1', '*lava')
        quote_wall_face = self.cube[0].replace('wall1', 'wall"mark')
        quote_lava_cube = box_faces(-64, -64, -64, 64, 64, 64, '*lava"mark')
        cases = [
            ('wall"mark before // hint "removed"',
             '{\n' + quote_wall_face + '\n// ' + hint_face + ' "removed"\n' + '\n'.join(self.cube[1:]) + '\n}',
             {'solid': 7, 'proj': 7}, True),
            ('wall"mark before ; hint "removed"',
             '{\n' + quote_wall_face + '\n; ' + hint_face + ' "removed"\n' + '\n'.join(self.cube[1:]) + '\n}',
             {'solid': 7, 'proj': 7}, True),
            ('wall"mark before // *lava "removed"',
             '{\n' + quote_wall_face + '\n// ' + lava_face + ' "removed"\n' + '\n'.join(self.cube[1:]) + '\n}',
             {'solid': 7, 'proj': 7}, True),
            ('*lava"mark before // hint "removed"',
             '{\n' + quote_lava_cube[0] + '\n// ' + hint_face + ' "removed"\n' + '\n'.join(quote_lava_cube[1:]) + '\n}',
             {'solid': 6, 'proj': 6, 'lava': 1}, False),
        ]
        for name, br, exp_counts, check_solid_cli in cases:
            with self.subTest(name=name):
                added = self.room + entity_block('func_detail', br)
                counts, err = parse_map_text(added)
                self.assertEqual(counts, exp_counts)
                self.assertEqual(err, '')
                if check_solid_cli:
                    rc, out, cli_err = run_cli(self.room, added)
                    self.assertEqual(rc, 1, f'{name}: stdout={out} stderr={cli_err}')
                    self.assertIn('COLLISION DIFFERS', out)
                    self.assertIn('PROJECTILE COLLISION DIFFERS', out)
                    self.assertEqual(cli_err, '')

    def test_entity_token_and_face_precedence_rules(self):
        cube_br = brush_block(self.cube)
        # Value decoy '"target" "classname"' must not hijack next epair
        txt = self.room + '{\n"target" "classname"\n"origin" "0 0 0"\n"classname" "func_detail"\n' + cube_br + '\n}\n'
        self.assertEqual(parse_map_text(txt)[0], {'solid': 7, 'proj': 7})

        # Comments with quotes, backslash parity, bare epair, repeated key keeps last, case sensitivity
        txt = (
            self.room +
            '{\n'
            '// a "quoted" comment\n'
            '"wad" "c:\\foo\\"\n'
            '"msg" "say \\"hi\\" \\\\"\n'
            '"CLASSNAME" "func_illusionary"\n'
            'classname func_illusionary\n'
            '" classname " "FUNC_DETAIL"\n'
            + cube_br + '\n}\n'
        )
        self.assertEqual(parse_map_text(txt)[0], {'solid': 7, 'proj': 7})

        # Degenerate no-normal *lava face in slot 1 is dropped before contents -> cube stays solid
        degen_lava = '( 0 0 0 ) ( 1 0 0 ) ( 2 0 0 ) *lava 0 0 0 1 1'
        txt = self.room + entity_block('func_detail', '{\n' + degen_lava + '\n' + '\n'.join(self.cube) + '\n}')
        counts, err = parse_map_text(txt)
        self.assertEqual(counts, {'solid': 7, 'proj': 7})
        self.assertIn('no normal', err)

        # Mixed face contents: *lava in slot 1 wins (lava + warning); *lava in slot 6 loses (solid + warning)
        slot1 = [self.cube[0].replace('wall1', '*lava')] + self.cube[1:]
        slot6 = self.cube[:-1] + [self.cube[-1].replace('wall1', '*lava')]
        c1, e1 = parse_map_text(self.room + entity_block('func_detail', brush_block(slot1)))
        c6, e6 = parse_map_text(self.room + entity_block('func_detail', brush_block(slot6)))
        self.assertEqual(c1, {'solid': 6, 'proj': 6, 'lava': 1})
        self.assertIn('mix face content types', e1)
        self.assertEqual(c6, {'solid': 7, 'proj': 7})
        self.assertIn('mix face content types', e6)


if __name__ == '__main__':
    unittest.main()
