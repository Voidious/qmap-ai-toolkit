"""Prove a visual-only build did not change collision: compare the SOLID space of two generated
.map files on a voxel grid (default 8-unit, supports sub-unit floats e.g. --step 0.5). Counts every
brush qbsp puts in the player collision hull -- both axis-aligned boxes and general convex brushes
(ramps, prisms, chamfers, veneers) via half-space planes -- and reports on stderr what it ignored,
so a brush flavour the rules below do not know about is named rather than silently dropped.
Water, slime and lava volumes are not solid, so they are excluded from the solid space and each
compared as its own class: a *water pool retextured *lava occupies the same volume but is a very
different room, and that shows up as a lava/water difference rather than vanishing.

Scope: the player collision hull (qbsp hulls 1 and 2) plus liquid contents. Two things it does
not claim, both measured rather than assumed:
  - Projectile collision. 'clip' and 'sky*' are exactly as solid as a wall to a player, so
    retexturing a wall to either is reported identical -- correctly for this scope -- but hull 0
    differs: a 'clip' brush is absent from hull 0 entirely, so rockets and hitscan pass through,
    and 'sky*' makes a SKY leaf that swallows them. Covering that means a second hull-0 pass, not
    a wider allowlist.
  - Solid/liquid overlap. The classes are compared independently, so reshaping a liquid brush
    buried inside an unchanged solid wall reports a liquid difference even though solid wins the
    BSP CSG and a player can reach neither. That is a false positive, not a false negative, which
    is the safe direction for a tool whose job is to refuse to certify.

Usage: python3 collide_cmp.py old.map new.map [--step 8]"""
from collections import Counter
import itertools
import math
import re
import sys

import numpy as np

PT_RE = re.compile(r'\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)')
# The whole .map lexical grammar, in parse_token()'s own precedence order (common/parser.cc), so
# that one left-to-right scan reproduces it. The order is the point: parse_token() tests for a
# comment before a quote and for a quote before a bare run, so a comment marker swallows the
# quotes after it while a quote swallows the '//' after it.
TOKEN_RE = re.compile(r'''
      (?://|;)[^\n]*                 # a comment, to end of line. Matched so it is consumed, then
                                     # dropped -- parse_token() does not return it as a token.
    | "( (?: [^"\\]                  # 1: a quoted token, to its closing quote. No newline case in
           | \\"(?![\r\n])           # parse_token()'s copy loop, so it may span lines. A '\'
           | \\(?!"(?![\r\n]))       # takes the next character with it, so an escaped quote does
         )* )"                       # not end the token -- unless it sits at end of line, which
                                     # qbsp warns about and treats as the terminator ("c:\foo\").
    | ([{}])(?![^\x00-\x20])         # 2: a brace on its own. Split out of the next alternative
                                     # only so a walk can skip a brush's faces without building a
                                     # string for each; it changes no token, because where the
                                     # lookahead fails the next alternative matches the same run.
                                     # '{foo' really is one token, which is how parse_token()
                                     # reads it too -- its bare branch does not stop at a brace.
    | ([^\x00-\x20]+)                # 3: any other token: parse_token()'s `while (*pos > 32)`
''', re.X)
BRACE = 2                            # the one group a brush-interior walk has to look at
# the whitespace parse_entity_dict() trims off a key, spelled out rather than left to str.strip():
# it tests std::isspace, which in qbsp's locale is exactly these six ASCII characters
KEY_WS = ' \t\n\r\v\f'
MAX_SLICE = 50_000_000        # ~50 MB per 2D bool slice
MAX_TOTAL_VOXELS = 10_000_000_000  # ~10G voxel evaluations (~25-35s); refuse legibly instead of hanging

HINT_TEX = frozenset(('hint', 'hintskip'))
# Content classes, each compared independently: (class, label, DIFFERS banner, space noun).
# Independently, because a brush that changes class -- a wall retextured '*lava', a '*water' pool
# retextured '*lava' -- leaves one set and joins another, so both report a difference. Lumping the
# liquids together as one "non-solid" space would miss a water->lava swap, which fills exactly the
# same volume. 'solid' is always compared; a liquid class absent from both maps is skipped.
CLASSES = (('solid', 'collision', 'COLLISION DIFFERS', 'solid space'),
           ('water', 'water contents', 'WATER CONTENTS DIFFER', 'water volume'),
           ('slime', 'slime contents', 'SLIME CONTENTS DIFFER', 'slime volume'),
           ('lava', 'lava contents', 'LAVA CONTENTS DIFFER', 'lava volume'))
LIQUIDS = ('water', 'slime', 'lava')


def face_class(tex):
    """The qbsp content *type* one face texture asks for, by ericw-tools' Quake rules
    (face_get_contents, common/bspfile.cc). 'hint'/'hintskip' mean EWT_VISCONTENTS_EMPTY -- no
    contents at all, which is why the first-face rule skips over them -- and 'origin' brushes are
    discarded before the hulls are built.

    These are qbsp's types, not this tool's comparison classes: 'clip' and 'sky' are separate
    types that both measure solid in the player hull, and SOLID_TYPES folds them in. Keeping them
    distinct here is what lets the mixed-contents warning fire where qbsp's does. 'skip' and
    'trigger' really are EWT_VISCONTENTS_SOLID -- the names mean nothing to qbsp -- as are
    '!'-prefixed names, which are liquid only in Half-Life."""
    t = tex.lower()
    if t in HINT_TEX:
        return 'hint'
    if t == 'origin':
        return 'origin'
    if t == 'clip':
        return 'clip'
    if t.startswith('*'):
        return ('lava' if t[1:].startswith('lava') else
                'slime' if t[1:].startswith('slime') else 'water')
    if t.startswith('sky'):
        return 'sky'
    return 'solid'


# Content types that are indistinguishable in the player collision hull: measured at 180 clipnodes
# each against a 12-clipnode control. They differ in hull 0 -- a 'clip' brush is absent from it
# entirely, so projectiles pass through, and 'sky*' makes a SKY leaf that swallows them -- which is
# outside this tool's stated scope (see the module docstring).
SOLID_TYPES = frozenset(('solid', 'clip', 'sky'))
LIQUID_TYPES = frozenset(LIQUIDS)

# Brush entities ericw-tools qbsp merges into the world model (IsWorldBrushEntity, qbsp/map.cc),
# each mapped to the content types a brush there still contributes to a hull after the
# entity-level rules in Brush_GetContents() and BrushFromContents() have run. Everything else
# becomes its own BSP model and is out of scope. Classnames are compared case-insensitively, as
# qbsp's Q_strcasecmp does.
#
# Measured by compiling a 128-unit cube in a sealed room per entity/texture pair and reading the
# BSP, never inferred: clipnodes for the player hull, hull-0 leaf contents for the liquids. Three
# of the five rows exist only because a measurement contradicted a reading of the source.
#   - The whole detail family is solid. func_detail / func_detail_wall / func_detail_fence all
#     raise the clipnode count, so reaching for func_detail to cut vis cost still blocks players.
#   - func_detail_illusionary keeps real liquids. qbsp converts a brush there to illusionary mist
#     behind `if (contents.is_any_solid())` (qbsp/brush.cc), so a '*lava' face is never converted
#     and keeps CONTENTS_LAVA in hull 0 -- the hull SV_PointContents reads -- while adding zero
#     clipnodes. A clipnode probe cannot see that at all; it took the leafs lump.
#   - func_illusionary_visblocker is the trap in both directions. It passes IsWorldBrushEntity(),
#     so "count everything that predicate accepts" would wrongly make its walls solid: qbsp
#     replaces its contents with ILLUSIONARY_VISBLOCKER (qbsp/map.cc, string_iequals branch) and
#     a plain or '*lava' brush there measures at the control. But that replacement masks off
#     EWT_ALL_VISIBLE_CONTENTS only, and PLAYERCLIP is an *invisible* content, so a 'clip' brush
#     keeps it -- and unlike func_detail_illusionary, visblocker is not `continue`d out of hulls
#     1/2 before qbsp/brush.cc converts clip to CONTENTS_SOLID there. Measured: a 'clip' cube in
#     func_illusionary_visblocker is 180 clipnodes, exactly as solid to a player as a wall.
WORLD_ENTITY_TYPES = {
    'worldspawn':                  SOLID_TYPES | LIQUID_TYPES,
    'func_group':                  SOLID_TYPES | LIQUID_TYPES,
    'func_detail':                 SOLID_TYPES | LIQUID_TYPES,
    'func_detail_wall':            SOLID_TYPES | LIQUID_TYPES,
    'func_detail_fence':           SOLID_TYPES | LIQUID_TYPES,
    'func_detail_illusionary':     LIQUID_TYPES,
    'func_illusionary_visblocker': frozenset(('clip',)),
}


def brush_contents(texes):
    """(qbsp content type, mixed-contents?) for one brush, from its face textures in file order.

    Three qbsp rules, all measured rather than read off the source:
      - A single 'hint'/'hintskip' face anywhere drops the whole brush from the collision hulls,
        whatever the other five faces say (MapBrush_IsHint tests *any* face), and forces its
        contents empty in hull 0 as well (qbsp/brush.cc), so it is not a liquid either. Reading
        only face_get_contents() gets this backwards: hint returns *empty* contents there, which
        the first-face rule below skips over, predicting solid.
      - Otherwise the first face *with contents* in file order decides -- Brush_GetContents()
        `continue`s past empty ones, and only hint/hintskip are empty. So face order in the .map
        file decides whether a brush with one '*' face is a pool or a wall: '*lava' on face 1 of 6
        measures non-solid, the same brush with '*lava' on face 6 measures solid.
      - qbsp prints 'brush has multiple face contents (X vs Y), the former will be used' when any
        later face's content *type* differs from that base. Measured, that includes 'clip' or
        'sky*' sharing a brush with ordinary solid, even though all three are equally solid to a
        player -- and it fires on a hint brush too, over its non-hint faces. 'skip' and 'trigger'
        do not warn, because they are plain solid.

    The type comes back unfolded -- 'clip' and 'sky' separate from 'solid' -- because the entity
    the brush sits in can care about the difference even though a player cannot: see
    WORLD_ENTITY_TYPES on func_illusionary_visblocker. brushes() folds SOLID_TYPES into the one
    'solid' comparison class afterwards."""
    fcs = [face_class(t) for t in texes]
    typed = [f for f in fcs if f != 'hint']       # the faces Brush_GetContents() actually weighs
    mixed = len(set(typed)) > 1
    if not typed or 'hint' in fcs:
        return 'hint', mixed
    return typed[0], mixed


def entities(txt):
    """Yield (entity text, classname or None) for every entity block in a .map file.

    Walks tokens the way map_file_t::parse / map_entity_t::parse / parse_entity_dict do
    (common/mapfile.cc), because nothing about .map structure is decided by anything else. Every
    rule below was measured against qbsp with a 128-unit cube in a sealed room -- 12 clipnodes if
    the cube reached no hull, 180 if its entity merged into the world as func_detail, 24 if the
    entity became its own submodel -- and every one of them was a wrong answer first.

    What a token is, which is the whole reason this is a token walk and not a search:
      - A key and a value are the same kind of token, so only position tells them apart. An epair
        whose *value* is the word classname does not make the next epair's key a classname:
        '"target" "classname"' then '"origin" "0 0 0"' then a real '"classname" "func_detail"'
        compiles solid (180), where searching for the key matched the decoy and read the classname
        as 'origin', dropping a solid entity. The same decoy followed by '"func_detail" "1"' and
        no real classname is a submodel (24), where searching read 'func_detail' and counted it as
        world geometry. Wrong in both directions.
      - A comment is not a token at all, so it cannot be ignored -- it has to be consumed.
        parse_token() tests for '//' or ';' before it tests for a quote, so one double quote in a
        comment would shift a naive pairing by one for the rest of the entity. Scanning for the
        alternatives in parse_token()'s order reproduces its precedence in both directions: a
        comment marker swallows the quotes after it, and a quote swallows the '//' after it, so
        '// a "comment"', a ';' comment, a trailing comment and '"wad" "a//b.wad"' all read
        correctly (180). A '}' inside a comment is not a brace either.
      - A quoted token runs to its closing quote across newlines, which is not the same thing as
        a value sitting on another line than its key. '"message" "line1<newline>line2"' is one
        value (180); a pattern that ended the token at the newline read two half-tokens.
      - A '\\' takes the next character into the token with it, so an escaped quote does not end
        it: '"message" "say \\"hi\\" now"' is one value (180). The exception is '\\"' at end of
        line, which qbsp warns about and treats as the terminator -- that is the '"wad" "c:\\foo\\"'
        shape certain editors emit, and it also reads at 180.
      - A token need not be quoted. parse_token()'s other branch takes any run of characters above
        ASCII 32, so 'classname func_detail' is a valid epair and compiles solid (180) -- and a
        quote-only scan did not merely miss it, it mis-paired every quoted token after it, because
        'message "hi"' puts an odd number of quoted tokens ahead of the rest of the entity.
      - '{' and '}' are ordinary tokens to parse_token(); map_entity_t::parse() makes them
        structural by comparing the token text in a key slot, without asking whether it was
        quoted. So a brace inside a quoted *value* is text -- '"message" "a{b"' compiles at 180,
        while counting brace characters merged the whole file into one entity block.

    What qbsp then does with the pairs:
      - The value must be on the key's line, read with PARSE_SAMELINE. A newline between the two
        makes qbsp refuse the map outright ("parse_token: line is incomplete"), as does a comment
        there, so reading across one would be describing maps that cannot compile. Tabs, runs of
        spaces and several epairs on one line are all fine, as is the entity header on the line
        with its opening brace (180) -- an anchored line-start pattern missed a solid entity.
      - A key is whitespace-trimmed, a value is not. parse_entity_dict() erases leading and
        trailing std::isspace from the key token before storing it, so '" classname "',
        '"<tab>classname<tab>"' and a newline-padded key all mean classname (180). Internal
        whitespace is untouched, so '"class name"' is a different key (24).
      - A repeated key keeps its *last* value. parse_entity_dict() stores pairs with
        entdict_t::set() (common/entdata.cc), which overwrites `it->second` in place rather than
        appending, so find() returning the first match finds the overwritten one. '"classname"
        "func_illusionary"' then '"classname" "func_detail"' is merged into the world (180) and
        the same two reversed is a submodel (24): stopping at the first is wrong both ways.
      - The key is compared case-sensitively, with `key == it->first`, so qbsp does not recognise
        '"CLASSNAME"' as a classname at all (24, not 180) and a '"CLASSNAME"' pair does not
        overwrite a real one (180). Only the classname *value* is matched case-insensitively, by
        the callers, which is where qbsp uses Q_strcasecmp.
    """
    start, depth, key, key_end, cls, refused = None, 0, None, 0, None, False
    for m in TOKEN_RE.finditer(txt):
        kind = m.lastindex                  # None for a comment, which is not a token at all
        if depth >= 2:
            # inside a brush, which parse_brush() consumes. Only its nesting matters here -- and
            # it does nest, because the brush-primitives format wraps its faces in a second brace
            # pair -- so skip every other token without paying to extract it.
            if kind == BRACE:
                depth += 1 if m.group(BRACE) == '{' else -1
            continue
        if kind is None:
            continue
        tok = m.group(kind)
        if key is not None:
            # a value slot takes any token at all, '{' and '}' included: they are only structural
            # where map_entity_t::parse() looks at them, which is the key slot
            if '\n' in txt[key_end:m.start()]:
                refused = True          # PARSE_SAMELINE: qbsp refuses this map, so stop reading
            elif key.strip(KEY_WS) == 'classname':
                cls = tok
            key = None
        elif tok == '{':
            if depth == 0:
                start, cls, refused = m.start(), None, False
            depth += 1
        elif tok == '}':
            if depth == 1:
                yield txt[start:m.end()], cls
            depth = max(depth - 1, 0)
        elif depth == 1 and not refused:
            key, key_end = tok, m.end()


def parse_brush(br):
    """Return (aabb_lo, aabb_hi, (N, D), is_aabb, geom_key, face_textures, no_normal_faces) for one
    brush, or None if degenerate. Quake .map face winding: (p3 - p1) x (p2 - p1) points OUTWARD,
    so inside is n.x <= d.

    Face textures come back in file order, and only for the faces qbsp itself keeps. A face whose
    three plane points give no normal is dropped by ParseBrushFace() (qbsp/map.cc) before it is
    appended to brush.faces, so neither MapBrush_IsHint() nor Brush_GetContents() can see its
    texture: measured, a degenerate '*lava' face in slot 1 ahead of six wall faces compiles solid,
    and a degenerate 'hint' face in slot 1 does not drop the brush. Recording its texture anyway
    would let a face qbsp discarded decide the brush's contents, in either direction."""
    planes, texes, no_normal = [], [], 0
    for line in br.split('\n'):
        pts = list(PT_RE.finditer(line))
        if len(pts) < 3:
            continue
        p1, p2, p3 = (np.array([float(v) for v in pts[k].groups()]) for k in range(3))
        n = np.cross(p3 - p1, p2 - p1)
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            no_normal += 1
            continue
        n /= ln
        planes.append((n, float(np.dot(n, p1))))
        # the texture name is the first token after the third ( x y z ) plane point, in both the
        # standard and the Valve 220 face format (whose [ s ] [ t ] axes follow the name)
        rest = line[pts[2].end():].split()
        texes.append(rest[0] if rest else '')
    if len(planes) < 4:
        return None
    N = np.array([p[0] for p in planes])
    D = np.array([p[1] for p in planes])
    # Canonical geometry key (independent of textures/ordering) for exact common-brush prefiltering
    gkey = tuple(sorted(
        (round(float(n[0]) + 0.0, 6), round(float(n[1]) + 0.0, 6), round(float(n[2]) + 0.0, 6), round(float(d) + 0.0, 4))
        for n, d in planes
    ))
    # Fast path: pure axis-aligned 6-face box
    if len(planes) == 6 and np.all(np.max(np.abs(N), axis=1) > 1.0 - 1e-6):
        lo, hi = [None, None, None], [None, None, None]
        for n, d in planes:
            ax = int(np.argmax(np.abs(n)))
            if n[ax] < 0:
                lo[ax] = -d
            else:
                hi[ax] = d
        if all(v is not None for v in lo + hi):
            lo_a, hi_a = np.array(lo), np.array(hi)
            if np.all(hi_a > lo_a + 1e-6):
                return (lo_a, hi_a, (N, D), True, gkey, texes, no_normal)
            return None
    # General convex brush: exact bounding box from feasible plane-triple intersections
    verts = []
    m = len(planes)
    for i, j, k in itertools.combinations(range(m), 3):
        M = N[[i, j, k]]
        if abs(np.linalg.det(M)) < 1e-6:
            continue
        v = np.linalg.solve(M, D[[i, j, k]])
        if np.all(N @ v <= D + 1e-3):
            verts.append(v)
    if len(verts) < 4:
        return None
    V = np.array(verts)
    lo_a, hi_a = V.min(0), V.max(0)
    if np.any(hi_a <= lo_a + 1e-6):
        return None
    return (lo_a, hi_a, (N, D), False, gkey, texes, no_normal)


def brushes(path):
    """Brushes per content class, with a stderr note accounting for every one ignored.

    A brush entity's classname decides which of qbsp's content types still reach a hull from
    inside it (WORLD_ENTITY_TYPES); its face textures decide which type the brush is
    (brush_contents). A brush counts only if its entity keeps its type: an ordinary wall in
    func_detail_illusionary and a '*lava' pool in func_illusionary_visblocker are both ignored,
    as is every brush in an entity that becomes its own BSP model.

    The note is what keeps this blind spot from coming back: a classname or texture flavour these
    rules do not know about is reported by name instead of vanishing from the comparison."""
    out = {k: [] for k, _, _, _ in CLASSES}
    skipped, mixed, no_normal = 0, 0, 0
    no_collision, submodel, no_contents = Counter(), Counter(), Counter()
    for e, found in entities(open(path).read()):
        cls = found or '(no classname)'
        brs = re.findall(r'\{\n(\(.*?)\n\}', e, re.S)
        kept = WORLD_ENTITY_TYPES.get(cls.lower())
        if kept is None:
            if brs:                    # lights, spawns and items have no brushes: nothing ignored
                submodel[cls] += len(brs)
            continue
        for br in brs:
            pb = parse_brush(br)
            if pb is None:
                skipped += 1
                continue
            *geom, texes, dropped = pb
            no_normal += dropped
            typ, is_mixed = brush_contents(texes)
            mixed += is_mixed
            cmp_class = 'solid' if typ in SOLID_TYPES else typ
            if cmp_class not in out:   # 'hint'/'origin' -- or a type no class covers yet
                # name the face that decided it, not texes[0]: a hint face in slot 3 drops the
                # brush, and reporting the slot-1 wall texture there would be actively misleading
                no_contents[next((t.lower() for t in texes if face_class(t) == typ), typ)] += 1
                continue
            if typ not in kept:
                no_collision[cls] += 1   # e.g. solid in func_detail_illusionary: mist, in no hull
                continue
            out[cmp_class].append(tuple(geom))
    if skipped:
        print(f'WARNING: {path}: skipped {skipped} degenerate/unbounded brush(es)', file=sys.stderr)
    if no_normal:
        print(f'WARNING: {path}: {no_normal} face(s) have three plane points with no normal; qbsp '
              f'drops them before reading their texture ("Brush plane with no normal"), so they '
              f'decide nothing here either -- but a generator emitting one is a bug',
              file=sys.stderr)
    if mixed:
        print(f'WARNING: {path}: {mixed} brush(es) mix face content types (e.g. one "*", "clip" or '
              f'"sky*" face among five ordinary solid ones); qbsp takes the first face in file '
              f'order and warns -- check the texture theme slots, this is usually a mistake',
              file=sys.stderr)
    for tally, why in ((no_collision, 'whose entity drops them from every collision hull'),
                       (submodel, 'in submodel entities (own collision hull, solidity set at runtime)'),
                       (no_contents, 'whose face textures give them no collision contents')):
        if tally:
            named = ', '.join(f'{c} x{n}' for c, n in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0])))
            print(f'note: {path}: ignored {sum(tally.values())} brush(es) {why}: {named}',
                  file=sys.stderr)
    return out


def merge_boxes(boxes, tol=1e-6):
    comps = []
    for blo, bhi in boxes:
        mlo, mhi = list(blo), list(bhi)
        while True:
            keep, grew = [], False
            for clo, chi in comps:
                if (chi[0] >= mlo[0] - tol and chi[1] >= mlo[1] - tol and chi[2] >= mlo[2] - tol and
                        clo[0] <= mhi[0] + tol and clo[1] <= mhi[1] + tol and clo[2] <= mhi[2] + tol):
                    mlo = [min(mlo[0], clo[0]), min(mlo[1], clo[1]), min(mlo[2], clo[2])]
                    mhi = [max(mhi[0], chi[0]), max(mhi[1], chi[1]), max(mhi[2], chi[2])]
                    grew = True
                else:
                    keep.append((clo, chi))
            comps = keep
            if not grew:
                break
        comps.append((mlo, mhi))
    return comps


def roi_grid(comps, s):
    snapped = []
    for roi_lo, roi_hi in comps:
        ilo = [math.floor(float(v) / s) for v in roi_lo]
        ihi = [max(lo_i + 1, math.ceil(float(v) / s)) for lo_i, v in zip(ilo, roi_hi)]
        snapped.append((ilo, ihi))
    specs, total, max_sl = [], 0, 0
    for ilo, ihi in merge_boxes(snapped, tol=-1):
        nx, ny, nz = ihi[0] - ilo[0], ihi[1] - ilo[1], ihi[2] - ilo[2]
        sl = nx * ny
        max_sl = max(max_sl, sl)
        total += sl * nz
        specs.append((np.array([ilo[0] * s, ilo[1] * s, ilo[2] * s]),
                      np.array([ihi[0] * s, ihi[1] * s, ihi[2] * s]),
                      nx, ny, nz))
    return specs, total, max_sl


def compare(A, B, step, kind, label, differs, space):
    """Voxel-compare one content class's space between the two maps. True if they differ.
    Exits 2 if --step cannot be resolved within the memory/time budget."""
    # Exact prefilter: any symmetric difference must lie inside the bbox of brushes whose geometry
    # is not present in both maps. Cluster differing brushes into overlapping AABB components so
    # distant changed corners don't inflate one giant ROI box across empty space between them.
    cA, cB = Counter(b[4] for b in A), Counter(b[4] for b in B)
    common = cA & cB
    remA, remB = cA - common, cB - common
    if not remA and not remB:
        print(f'{label} identical (all {len(A)} {kind} brush geometries identical)')
        return False

    diff_brushes = [b for b in A if b[4] in remA] + [b for b in B if b[4] in remB]
    comps = merge_boxes([(b[0], b[1]) for b in diff_brushes])

    # Finest parallel-plane gap among differing brushes: warns when --step is too coarse to resolve
    # thin cracks/slivers (e.g. a 1-unit gap between two shifted wedge planes).
    plane_groups = {}
    for _, _, (N, D), _, _ in diff_brushes:
        for n, d in zip(N, D):
            for c in n:
                if abs(c) > 1e-6:
                    sgn = 1.0 if c > 0 else -1.0
                    break
            else:
                continue
            cn = (round(float(n[0] * sgn) + 0.0, 5), round(float(n[1] * sgn) + 0.0, 5), round(float(n[2] * sgn) + 0.0, 5))
            plane_groups.setdefault(cn, []).append(float(d * sgn))
    min_gap = None
    for ds in plane_groups.values():
        ds = sorted(ds)
        for a_, b_ in zip(ds, ds[1:]):
            g_ = b_ - a_
            if g_ > 1e-4 and (min_gap is None or g_ < min_gap):
                min_gap = g_
    rec = min_gap / 2.0 if min_gap is not None else None
    gap_s = f'{min_gap:g}' if min_gap is not None else None
    unit = ('unit' if gap_s == '1' else 'units') if gap_s is not None else None
    under_resolved = min_gap is not None and step >= min_gap - 1e-6
    rec_fits, rec_over = True, None
    if rec is not None:
        _, rec_voxels, rec_max_slice = roi_grid(comps, rec)
        rec_fits = rec_max_slice <= MAX_SLICE and rec_voxels <= MAX_TOTAL_VOXELS
        if rec_max_slice > MAX_SLICE:
            rec_over = f'{rec_max_slice / (1024 ** 2):.1f} MiB/slice, over {MAX_SLICE / (1024 ** 2):.1f} MiB limit'
        elif rec_voxels > MAX_TOTAL_VOXELS:
            rec_over = f'{rec_voxels / 1e9:.2f}G voxels, over {MAX_TOTAL_VOXELS / 1e9:g}G limit'

    if rec is not None and rec_fits and rec > step + 1e-9:
        budget_tail = f'use a larger --step (finest differing plane gap is {gap_s} {unit}; --step {rec:g} suffices)'
    elif rec is not None and not rec_fits:
        budget_tail = (f'cannot resolve {gap_s}-unit features inside budget '
                       f'(--step {rec:g} needs {rec_over}); compare a narrower pair or use a coarser --step')
    else:
        budget_tail = 'use a larger --step'

    roi_specs, total_voxels, _ = roi_grid(comps, step)
    for lo, hi, nx, ny, nz in roi_specs:
        if nx * ny > MAX_SLICE:
            mb = (nx * ny) / (1024 ** 2)
            print(f'ERROR: {label}: ROI 2D slice {(nx, ny)} ({mb:.1f} MiB per slice at step={step:g}) '
                  f'exceeds limit; {budget_tail}', file=sys.stderr)
            sys.exit(2)
    if total_voxels > MAX_TOTAL_VOXELS:
        gv = total_voxels / 1e9
        print(f'ERROR: {label}: total ROI work {gv:.2f}G voxels across {len(roi_specs)} ROI(s) at '
              f'step={step:g} exceeds {MAX_TOTAL_VOXELS / 1e9:g}G limit; {budget_tail}', file=sys.stderr)
        sys.exit(2)
    if under_resolved:
        warn_tail = f'try --step {rec:g}' if rec_fits else f'resolving at --step {rec:g} needs {rec_over}; compare a narrower pair'
        print(f'WARNING: {label}: differing geometry has parallel planes as close as {gap_s} {unit}; '
              f'--step {step:g} may not resolve them ({warn_tail})', file=sys.stderr, flush=True)
    if total_voxels > 500_000_000:
        print(f'checking {label}: {total_voxels / 1e9:.2f}G voxels across {len(roi_specs)} ROI(s) at '
              f'step={step:g}...', file=sys.stderr, flush=True)

    def vox_slice(bs, lo, nx, ny, zc):
        g = np.zeros((nx, ny), bool)
        for blo, bhi, (N, D), is_aabb, _ in bs:
            if zc < blo[2] - 1e-4 or zc > bhi[2] + 1e-4:
                continue
            ix0 = max(0, int(np.ceil((blo[0] - lo[0]) / step - 0.5 - 1e-9)))
            ix1 = min(nx, int(np.floor((bhi[0] - lo[0]) / step - 0.5 + 1e-9)) + 1)
            iy0 = max(0, int(np.ceil((blo[1] - lo[1]) / step - 0.5 - 1e-9)))
            iy1 = min(ny, int(np.floor((bhi[1] - lo[1]) / step - 0.5 + 1e-9)) + 1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            if is_aabb:
                g[ix0:ix1, iy0:iy1] = True
            else:
                xs = lo[0] + (np.arange(ix0, ix1) + 0.5) * step
                ys = lo[1] + (np.arange(iy0, iy1) + 0.5) * step
                inside = np.ones((ix1 - ix0, iy1 - iy0), bool)
                for n, d in zip(N, D):
                    rhs = d - n[2] * zc + 1e-4
                    if abs(n[0]) < 1e-9 and abs(n[1]) < 1e-9:
                        if rhs < 0:
                            inside[:] = False
                            break
                    else:
                        inside &= ((n[0] * xs)[:, None] + (n[1] * ys)[None, :] <= rhs)
                        if not inside.any():
                            break
                g[ix0:ix1, iy0:iy1] |= inside
        return g

    total_diff, sample_pts, shapes = 0, [], []
    for lo, hi, nx, ny, nz in roi_specs:
        shapes.append((nx, ny, nz))
        subA = [b for b in A if bool(np.all(b[1] > lo - 1e-6) and np.all(b[0] < hi + 1e-6))]
        subB = [b for b in B if bool(np.all(b[1] > lo - 1e-6) and np.all(b[0] < hi + 1e-6))]
        for iz in range(nz):
            zc = lo[2] + (iz + 0.5) * step
            diff = vox_slice(subA, lo, nx, ny, zc) ^ vox_slice(subB, lo, nx, ny, zc)
            if diff.any():
                idx = np.argwhere(diff)
                total_diff += len(idx)
                for ix, iy in idx[:max(0, 5 - len(sample_pts))]:
                    sample_pts.append((float(lo[0] + (ix + 0.5) * step), float(lo[1] + (iy + 0.5) * step), float(zc)))

    if total_diff:
        caveat = f'; features down to {gap_s} {unit} not examined' if under_resolved else ''
        print(f'{differs}: {total_diff} voxels (step={step:g}, {len(roi_specs)} ROI(s){caveat}), e.g.', sample_pts)
        return True
    if under_resolved:
        out_tail = f'rerun with --step {rec:g}' if rec_fits else f'resolving at --step {rec:g} exceeds budget, compare a narrower pair'
        print(f'{label}: no difference found at step={step:g}, {len(roi_specs)} ROI(s) {shapes} '
              f'(features down to {gap_s} {unit} unresolved; {out_tail})')
        return False
    print(f'{label} identical ({space} matches voxel for voxel, step={step:g}, '
          f'{len(roi_specs)} ROI(s) {shapes})')
    return False


def main():
    args = sys.argv[1:]
    step = 8.0
    if '--step' in args:
        idx = args.index('--step')
        if idx + 1 >= len(args):
            print('usage: collide_cmp.py old.map new.map [--step N]', file=sys.stderr)
            sys.exit(2)
        try:
            step = float(args[idx + 1])
        except ValueError:
            print(f'invalid --step value: {args[idx + 1]}', file=sys.stderr)
            sys.exit(2)
        if not math.isfinite(step) or step <= 0:
            print(f'--step must be positive, got {step}', file=sys.stderr)
            sys.exit(2)
        args = args[:idx] + args[idx + 2:]
    if len(args) != 2:
        print('usage: collide_cmp.py old.map new.map [--step N]', file=sys.stderr)
        sys.exit(2)

    pA, pB = args[0], args[1]
    A, B = brushes(pA), brushes(pB)
    na = sum(not b[3] for b in A['solid'])
    nb = sum(not b[3] for b in B['solid'])
    print(f'{pA}: {len(A["solid"])} solid brushes ({na} non-axis), '
          f'{pB}: {len(B["solid"])} solid brushes ({nb} non-axis)', flush=True)
    liq = [f'{k} {len(A[k])} -> {len(B[k])}' for k in LIQUIDS if A[k] or B[k]]
    if liq:
        print('liquid brushes (not solid, each class compared separately): ' + ', '.join(liq), flush=True)

    differed = False
    for kind, label, banner, space in CLASSES:
        if kind != 'solid' and not A[kind] and not B[kind]:
            continue
        differed |= compare(A[kind], B[kind], step, kind, label, banner, space)
    if differed:
        sys.exit(1)


if __name__ == '__main__':
    main()
