"""Prove a visual-only build did not change collision: compare both the player collision hull
(qbsp hulls 1 and 2) and the projectile / point-trace hull (hull 0: solid, sky, and water/slime/lava
contents) of two generated .map files on a voxel grid (default 8-unit, supports sub-unit floats
e.g. --step 0.5). Counts every brush qbsp merges into the world hulls -- both axis-aligned boxes
and general convex brushes (ramps, prisms, chamfers, veneers) via half-space planes -- and reports
on stderr what it ignored, so a brush flavour the rules below do not know about is named rather than
silently dropped.

Classes compared (each independently, so retexturing a brush across classes always reports a
difference):
  - Player collision (hulls 1 & 2): ordinary solid, 'skip', 'trigger', 'clip', and 'sky*'.
  - Projectile collision (hull 0 SOLID): ordinary solid, 'skip', and 'trigger' -- excludes 'clip'
    (absent from hull 0, so rockets and hitscan pass through) and 'sky*' (hull-0 SKY leaf).
  - Sky contents (hull 0 SKY): blocks and deletes projectiles; includes 'sky*' in
    func_detail_illusionary, which drops player collision yet still writes a SKY leaf in hull 0.
  - Liquid contents (hull 0 WATER / SLIME / LAVA): each compared on its own, so a *water -> *lava
    swap shows up as both a water and a lava difference.

Known conservatism (false positive, not false negative):
  - Classes are compared independently, so reshaping a liquid (or sky/clip) brush buried inside an
    unchanged solid wall reports a difference even though solid wins the BSP CSG and nothing can
    reach it. That is the safe direction for a tool whose job is to refuse to certify.

Usage: python3 collide_cmp.py old.map new.map [--step 8]"""
from collections import Counter
import itertools
import math
import re
import sys

import numpy as np

PT_RE = re.compile(r'\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)')
# Comments inside a brush block: '//' or ';' at start of line or after <= 0x20 whitespace
# (matching parse_token()'s comment check; never consumes '\n' or mid-token '//' / ';').
BRUSH_COMMENT_RE = re.compile(r'(?:^|(?<=[\x00-\x20]))(?://|;)[^\n]*', re.M)
# Brush-primitives texture matrix `( ( a b c ) ( d e f ) )` sitting between the 3rd plane point
# and the texture name (parse_texture_def, common/mapfile.cc).
BP_MAT_RE = re.compile(r'\s*\(\s*\([^)]*\)\s*\([^)]*\)\s*\)')
# The whole .map lexical grammar, in parse_token()'s own precedence order (common/parser.cc), so
# that one left-to-right scan reproduces it. The order is the point: parse_token() tests for a
# comment before a quote and for a quote before a bare run, so a comment marker swallows the
# quotes after it while a quote swallows the '//' after it.
TOKEN_RE = re.compile(r'''
      (?://|;)[^\n]*                 # a comment, to end of line. Matched so it is consumed, then
                                     # dropped -- parse_token() does not return it as a token.
    | "( (?: [^"\\]                  # 1: a quoted token, to its closing quote. No newline case in
           | \\(?="[\r\n])           # parse_token()'s copy loop, so it may span lines. A '\' takes
           | \\(?!"[\r\n])[\s\S]     # the next character with it -- any character, a second '\'
         )* )"                       # included, which is why '\"' does not end the token and
                                     # '\\"' does. The one exception is the '\"' qbsp warns about
                                     # at end of line and treats as the terminator ("c:\foo\"):
                                     # there the '\' takes nothing and the quote closes.
    | ([{}])(?![^\x00-\x20])         # 2: a brace on its own. Split out of the next alternative
                                     # only so a walk can skip a brush's faces without building a
                                     # string for each; it changes no token, because where the
                                     # lookahead fails the next alternative matches the same run.
                                     # '{foo' really is one token, which is how parse_token()
                                     # reads it too -- its bare branch does not stop at a brace.
    | ([^\x00-\x20]+)                # 3: any other token: parse_token()'s `while (*pos > 32)`,
                                     # which it runs on a `const char *` -- signed, so qbsp counts
                                     # bytes 0x80-0xFF as whitespace and 0x7F as a token character.
                                     # Measured: 'classname<0x80>func_detail' is a valid unquoted
                                     # epair (180 clipnodes), with 0x7F it is one token and qbsp
                                     # refuses the map. This class gets 0x7F right and 0x80-0xFF
                                     # wrong, which needs a decided file encoding to fix rather
                                     # than a wider class -- open() decodes before the scan, so
                                     # on a UTF-8 locale such a byte raises UnicodeDecodeError
                                     # here and never reaches a token at all. No generator can
                                     # emit one and no texture name contains one.
''', re.X)
BRACE = 2                            # the one group a brush-interior walk has to look at
# the whitespace parse_entity_dict() trims off a key, spelled out rather than left to str.strip():
# it tests std::isspace, which in qbsp's locale is exactly these six ASCII characters
KEY_WS = ' \t\n\r\v\f'
MAX_SLICE = 50_000_000        # ~50 MB per 2D bool slice
MAX_TOTAL_VOXELS = 10_000_000_000  # ~10G voxel evaluations (~25-35s); refuse legibly instead of hanging

HINT_TEX = frozenset(('hint', 'hintskip'))
# Content classes, each compared independently: (class, label, DIFFERS banner, space noun).
# Independently, because a brush that changes class -- a wall retextured 'clip', 'sky1' or '*lava',
# or a '*water' pool retextured '*lava' -- leaves one set and joins another, so the affected passes
# report a difference. 'solid' (player hull) and 'proj' (hull-0 solid) are always compared; sky and
# liquid classes absent from both maps are skipped.
CLASSES = (('solid', 'collision',            'COLLISION DIFFERS',            'solid space'),
           ('proj',  'projectile collision', 'PROJECTILE COLLISION DIFFERS', 'projectile solid space'),
           ('sky',   'sky contents',         'SKY CONTENTS DIFFER',          'sky volume'),
           ('water', 'water contents',       'WATER CONTENTS DIFFER',        'water volume'),
           ('slime', 'slime contents',       'SLIME CONTENTS DIFFER',        'slime volume'),
           ('lava',  'lava contents',        'LAVA CONTENTS DIFFER',         'lava volume'))
LIQUIDS = ('water', 'slime', 'lava')


def face_class(tex):
    """The qbsp content *type* one face texture asks for, by ericw-tools' Quake rules
    (face_get_contents, common/bspfile.cc). 'hint'/'hintskip' mean EWT_VISCONTENTS_EMPTY -- no
    contents at all, which is why the first-face rule skips over them -- and 'origin' brushes are
    discarded before the hulls are built.

    These are qbsp's types, not this tool's comparison classes: 'clip' and 'sky' are kept distinct
    from 'solid' so the mixed-contents warning fires where qbsp's does, the entity table can apply
    per-hull rules, and the hull-0 pass can separate SOLID, SKY and EMPTY. 'skip' and 'trigger'
    really are EWT_VISCONTENTS_SOLID in every hull -- the names mean nothing to qbsp -- as are
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


# Content types that are indistinguishable in the player collision hull (hulls 1 & 2): measured at
# 24 clipnodes each against a 12-clipnode empty room control. They diverge in hull 0 (point traces /
# projectiles), where 'solid' ('wall1'/'skip'/'trigger') writes CONTENTS_SOLID, 'sky' writes
# CONTENTS_SKY (blocks and removes missiles), and 'clip' writes EMPTY (projectiles pass through).
PLAYER_SOLID_TYPES = frozenset(('solid', 'clip', 'sky'))
LIQUID_TYPES = frozenset(LIQUIDS)
HULL0_TYPES = frozenset(('solid', 'sky')) | LIQUID_TYPES
TRACKED_TYPES = PLAYER_SOLID_TYPES | HULL0_TYPES

# Brush entities ericw-tools qbsp merges into the world model (IsWorldBrushEntity, qbsp/map.cc),
# each mapped to (player_hull_types, hull0_types): which qbsp content types survive into hulls 1/2
# and hull 0 after Brush_GetContents() and BrushFromContents() have run. Everything else becomes
# its own BSP model and is out of scope. Classnames are matched case-insensitively (Q_strcasecmp).
#
# Measured across the full 7x10 (entity x texture) matrix by compiling a 128-unit cube in a sealed
# room and reading both clipnode counts (hulls 1/2) and the hull-0 leaf at the cube's centre:
#   - worldspawn, func_group, func_detail, func_detail_wall, func_detail_fence: identical in both
#     hulls -- solid/clip/sky block players; solid blocks projectiles (SOLID); sky swallows them
#     (SKY); liquids produce hull-0 liquid leaves; clip is hull-0 EMPTY.
#   - func_detail_illusionary: qbsp converts a brush to illusionary mist behind
#     `if (contents.is_any_solid())` (qbsp/brush.cc) and skips hulls 1/2 entirely. So solid and
#     clip vanish from every hull, while liquids AND 'sky*' (neither is `is_any_solid()`) survive
#     in hull 0 -- a 'sky1' cube in func_detail_illusionary adds 0 clipnodes yet writes a SKY leaf.
#   - func_illusionary_visblocker: Brush_GetContents() masks off EWT_ALL_VISIBLE_CONTENTS and
#     substitutes ILLUSIONARY_VISBLOCKER, stripping walls, sky and liquids from every hull. Because
#     PLAYERCLIP is an *invisible* content and visblocker is not skipped in hulls 1/2, 'clip' stays
#     solid to players (24 clipnodes) while remaining hull-0 EMPTY.
WORLD_ENTITY_TYPES = {
    'worldspawn':                  (PLAYER_SOLID_TYPES,   HULL0_TYPES),
    'func_group':                  (PLAYER_SOLID_TYPES,   HULL0_TYPES),
    'func_detail':                 (PLAYER_SOLID_TYPES,   HULL0_TYPES),
    'func_detail_wall':            (PLAYER_SOLID_TYPES,   HULL0_TYPES),
    'func_detail_fence':           (PLAYER_SOLID_TYPES,   HULL0_TYPES),
    'func_detail_illusionary':     (frozenset(),          LIQUID_TYPES | frozenset(('sky',))),
    'func_illusionary_visblocker': (frozenset(('clip',)), frozenset()),
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

    The type comes back unfolded -- 'clip' and 'sky' separate from 'solid' -- because both the
    entity table (WORLD_ENTITY_TYPES) and the hull-0 projectile pass care about the difference even
    though the player hull folds all three into 'solid'."""
    fcs = [face_class(t) for t in texes]
    typed = [f for f in fcs if f != 'hint']       # the faces Brush_GetContents() actually weighs
    mixed = len(set(typed)) > 1
    if not typed or 'hint' in fcs:
        return 'hint', mixed
    return typed[0], mixed


def entities(txt):
    """Yield (brush blocks, classname or None) for every entity block in a .map file.

    A brush block is its text from '{' to the matching '}' inclusive, exactly the span
    map_entity_t::parse() hands to parse_brush(); parse_brush() below ignores the brace lines
    along with every other line that holds no face.

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
      - A '\\' takes the next character into the token with it, whatever that character is, so an
        escaped quote does not end the token: '"message" "say \\"hi\\" now"' is one value (180).
        What it takes may be a second '\\', which then escapes nothing, so the parity of a run of
        backslashes is what decides: an odd run before the closing quote escapes it, an even run
        leaves it as the terminator. A value ending '\\\\"' therefore ends right there (180) and
        one ending '\\"' does not. Enumerating the two-character escapes instead of applying that
        one rule got every even run wrong, because a lone '\\' was then allowed to stand by
        itself and the last backslash of the run paired with the terminator and swallowed it --
        reading no classname for an entity qbsp merges into the world. The exception is '\\"' at
        end of line, which qbsp warns about and treats as the terminator: that is the
        '"wad" "c:\\foo\\"' shape certain editors emit, and it also reads at 180.
      - A token need not be quoted. parse_token()'s other branch takes any run of characters above
        ASCII 32, so 'classname func_detail' is a valid epair and compiles solid (180) -- and a
        quote-only scan did not merely miss it, it mis-paired every quoted token after it, because
        'message "hi"' puts an odd number of quoted tokens ahead of the rest of the entity.
      - '{' and '}' are ordinary tokens to parse_token(); map_entity_t::parse() makes them
        structural by comparing the token text in a key slot, without asking whether it was
        quoted. So a brace inside a quoted *value* is text -- '"message" "a{b"' compiles at 180,
        while counting brace characters merged the whole file into one entity block.
      - A brush is where a '{' lands in that same key slot, and nothing about its *layout* marks
        it. parse_brush() opens with parse_token(PARSE_PEEK), which skips whitespace and comments
        before deciding anything, so qbsp keeps a brush whose '{' is followed by a comment, a
        blank line, a trailing space, or its own first face on the same line. Measured: a wall
        cube written in any of those four shapes is a full 180 clipnodes, where a pattern
        requiring '{' + newline + '(' found no brush at all and dropped a solid one with no note
        -- the one way a brush could still leave this comparison silently.

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
    depth, brs, bstart, key, key_end, cls, refused = 0, [], 0, None, 0, None, False
    for m in TOKEN_RE.finditer(txt):
        kind = m.lastindex                  # None for a comment, which is not a token at all
        if depth >= 2:
            # inside a brush, whose faces parse_brush() reads. Only its nesting matters here --
            # and it does nest, because the brush-primitives format wraps its faces in a second
            # brace pair -- so skip bare tokens (kind == 3) without paying to extract them;
            # rare quoted tokens (kind == 1) are checked so a quoted '{'/' }' still balances.
            if kind == BRACE or (kind == 1 and m.group(1) in ('{', '}')):
                depth += 1 if m.group(kind) == '{' else -1
                if depth == 1:
                    brs.append(txt[bstart:m.end()])
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
                brs, cls, refused = [], None, False
            else:
                bstart = m.start()      # a '{' in an entity's key slot opens a brush
            depth += 1
        elif tok == '}':
            if depth == 1:
                yield brs, cls
            depth = max(depth - 1, 0)
        elif depth == 1 and not refused:
            key, key_end = tok, m.end()


def parse_brush(br):
    """Return (aabb_lo, aabb_hi, (N, D), is_aabb, geom_key, face_textures, no_normal_faces) for one
    brush block as entities() yields it -- braces included -- or None if degenerate. Comments
    ('//' and ';') are stripped first so a commented-out face line cannot masquerade as a face;
    any remaining line with fewer than three plane points (braces, 'brushDef' header, blank lines)
    is ignored. Quake .map face winding: (p3 - p1) x (p2 - p1) points OUTWARD, so inside is
    n.x <= d.

    Face textures come back in file order, and only for the faces qbsp itself keeps. A face whose
    three plane points give no normal is dropped by ParseBrushFace() (qbsp/map.cc) before it is
    appended to brush.faces, so neither MapBrush_IsHint() nor Brush_GetContents() can see its
    texture: measured, a degenerate '*lava' face in slot 1 ahead of six wall faces compiles solid,
    and a degenerate 'hint' face in slot 1 does not drop the brush. Recording its texture anyway
    would let a face qbsp discarded decide the brush's contents, in either direction."""
    planes, texes, no_normal = [], [], 0
    for line in BRUSH_COMMENT_RE.sub('', br).split('\n'):
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
        # the texture name is the first token after the third ( x y z ) plane point in standard
        # and Valve 220 faces, or after the ( ( ... ) ( ... ) ) matrix in brush-primitives faces
        tail = line[pts[2].end():]
        bm = BP_MAT_RE.match(tail)
        if bm:
            tail = tail[bm.end():]
        rest = tail.split()
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
    rules do not know about is reported by name instead of vanishing from the comparison. Which
    is also why the brushes come from entities()' token walk rather than a second scan of the
    entity text -- a brush a pattern does not recognise is not ignored for a reason, it is simply
    absent, and there is nothing left to name in a note."""
    out = {k: [] for k, _, _, _ in CLASSES}
    skipped, mixed, no_normal = 0, 0, 0
    no_collision, submodel, no_contents = Counter(), Counter(), Counter()
    for brs, found in entities(open(path).read()):
        cls = found or '(no classname)'
        kept = WORLD_ENTITY_TYPES.get(cls.lower())
        if kept is None:
            if brs:                    # lights, spawns and items have no brushes: nothing ignored
                submodel[cls] += len(brs)
            continue
        p_kept, h0_kept = kept
        for br in brs:
            pb = parse_brush(br)
            if pb is None:
                # a block holding no face at all is not a brush and is not worth a warning:
                # parse_brush() (common/mapfile.cc) pushes one only `if (brush.faces.size())`,
                # so qbsp drops '{ }' without comment. Measured: a sealed room plus a wall cube
                # plus an empty brush block compiles to the same clipnode count as without it.
                skipped += PT_RE.search(BRUSH_COMMENT_RE.sub('', br)) is not None
                continue
            *geom, texes, dropped = pb
            no_normal += dropped
            typ, is_mixed = brush_contents(texes)
            mixed += is_mixed
            if typ not in TRACKED_TYPES:   # 'hint'/'origin' -- or a type no class covers yet
                # name the face that decided it, not texes[0]: a hint face in slot 3 drops the
                # brush, and reporting the slot-1 wall texture there would be actively misleading
                no_contents[next((t.lower() for t in texes if face_class(t) == typ), typ)] += 1
                continue
            g = tuple(geom)
            added = False
            if typ in p_kept:
                out['solid'].append(g)
                added = True
            if typ in h0_kept:
                h0_cls = 'proj' if typ == 'solid' else typ
                if h0_cls in out:
                    out[h0_cls].append(g)
                    added = True
            if not added:
                no_collision[cls] += 1   # e.g. solid in func_detail_illusionary: mist, in no hull
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


def _box_vol(lo, hi):
    return (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])


def merge_boxes(boxes, tol=1e-6, max_area=None, max_bloat=1.5):
    """Merge overlapping/touching AABBs when doing so does not substantially inflate volume.

    Each component tracks its non-compounding original input volume (orig_vol). Two boxes merge
    when one contains the other, or when their enclosing box has volume <= max_bloat * (orig_a +
    orig_b) (and, when max_area is set, XY slice area <= max_area). Containments, coplanar split
    walls, and slightly staggered adjacent brushes collapse cleanly into compact ROIs, while
    L-shaped / corner-overlapping boxes stay separate instead of inflating across empty space.
    Any remaining overlaps between ROIs are masked out on the integer voxel lattice in compare()."""
    comps = []  # (lo, hi, orig_vol)
    for blo, bhi in boxes:
        # Unwrap NumPy scalars to native Python numbers so inner-loop comparisons stay fast.
        mlo = [v.item() if hasattr(v, 'item') else v for v in blo]
        mhi = [v.item() if hasattr(v, 'item') else v for v in bhi]
        morig = _box_vol(mlo, mhi)
        while True:
            keep, grew = [], False
            mvol = _box_vol(mlo, mhi)
            for clo, chi, corig in comps:
                if (chi[0] >= mlo[0] - tol and chi[1] >= mlo[1] - tol and chi[2] >= mlo[2] - tol and
                        clo[0] <= mhi[0] + tol and clo[1] <= mhi[1] + tol and clo[2] <= mhi[2] + tol):
                    ulo = [min(mlo[0], clo[0]), min(mlo[1], clo[1]), min(mlo[2], clo[2])]
                    uhi = [max(mhi[0], chi[0]), max(mhi[1], chi[1]), max(mhi[2], chi[2])]
                    uvol = _box_vol(ulo, uhi)
                    uarea = (uhi[0] - ulo[0]) * (uhi[1] - ulo[1])
                    cvol = _box_vol(clo, chi)
                    contained = uvol <= max(mvol, cvol) * (1.0 + 1e-9)
                    if ((contained or uvol <= max_bloat * (morig + corig) * (1.0 + 1e-9)) and
                            (max_area is None or uarea <= max_area)):
                        mlo, mhi, mvol = ulo, uhi, uvol
                        morig = max(morig, corig) if contained else (morig + corig)
                        grew = True
                        continue
                keep.append((clo, chi, corig))
            comps = keep
            if not grew:
                break
        comps.append((mlo, mhi, morig))
    return [(lo, hi) for lo, hi, _ in comps]


def roi_grid(comps, s):
    snapped = []
    for roi_lo, roi_hi in comps:
        ilo = [math.floor(float(v) / s) for v in roi_lo]
        ihi = [max(lo_i + 1, math.ceil(float(v) / s)) for lo_i, v in zip(ilo, roi_hi)]
        snapped.append((ilo, ihi))
    specs, total, max_sl = [], 0, 0
    for ilo, ihi in merge_boxes(snapped, tol=0, max_area=MAX_SLICE, max_bloat=1.0):
        nx, ny, nz = ihi[0] - ilo[0], ihi[1] - ilo[1], ihi[2] - ilo[2]
        sl = nx * ny
        max_sl = max(max_sl, sl)
        total += sl * nz
        specs.append((ilo, ihi,
                      np.array([ilo[0] * s, ilo[1] * s, ilo[2] * s]),
                      np.array([ihi[0] * s, ihi[1] * s, ihi[2] * s]),
                      nx, ny, nz))
    return specs, total, max_sl


def compare(A, B, step, kind, label, differs, space):
    """Voxel-compare one content class's space between the two maps.
    Returns (differed, status, message, roi_specs) where status is 'exact', 'voxel', 'differ',
    or 'unresolved'. Exits 2 if --step cannot be resolved within the memory/time budget."""
    # Exact prefilter: any symmetric difference must lie inside the bbox of brushes whose geometry
    # is not present in both maps. Cluster differing brushes into overlapping AABB components so
    # distant changed corners don't inflate one giant ROI box across empty space between them.
    cA, cB = Counter(b[4] for b in A), Counter(b[4] for b in B)
    common = cA & cB
    remA, remB = cA - common, cB - common
    if not remA and not remB:
        noun = 'projectile-solid' if kind == 'proj' else kind
        return False, 'exact', f'{label} identical (all {len(A)} {noun} brush geometries identical)', []

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
    for _, _, lo, hi, nx, ny, nz in roi_specs:
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

    loA = np.array([b[0] for b in A]) if A else np.empty((0, 3))
    hiA = np.array([b[1] for b in A]) if A else np.empty((0, 3))
    loB = np.array([b[0] for b in B]) if B else np.empty((0, 3))
    hiB = np.array([b[1] for b in B]) if B else np.empty((0, 3))

    total_diff, sample_pts, shapes, seen_boxes = 0, [], [], []
    for ilo, ihi, lo, hi, nx, ny, nz in roi_specs:
        shapes.append((nx, ny, nz))
        # Mask cells already covered by an earlier ROI on the shared integer lattice so
        # non-inflating overlapping ROIs never double-count voxels.
        overlaps = []
        for pilo, pihi in seen_boxes:
            ox0, ox1 = max(ilo[0], pilo[0]), min(ihi[0], pihi[0])
            oy0, oy1 = max(ilo[1], pilo[1]), min(ihi[1], pihi[1])
            oz0, oz1 = max(ilo[2], pilo[2]), min(ihi[2], pihi[2])
            if ox0 < ox1 and oy0 < oy1 and oz0 < oz1:
                overlaps.append((ox0 - ilo[0], ox1 - ilo[0],
                                 oy0 - ilo[1], oy1 - ilo[1],
                                 oz0 - ilo[2], oz1 - ilo[2]))
        seen_boxes.append((ilo, ihi))
        subA = [A[i] for i in np.flatnonzero(np.all((hiA > lo - 1e-6) & (loA < hi + 1e-6), axis=1))] if A else []
        subB = [B[i] for i in np.flatnonzero(np.all((hiB > lo - 1e-6) & (loB < hi + 1e-6), axis=1))] if B else []
        for iz in range(nz):
            zc = lo[2] + (iz + 0.5) * step
            diff = vox_slice(subA, lo, nx, ny, zc) ^ vox_slice(subB, lo, nx, ny, zc)
            if diff.any():
                for ox0, ox1, oy0, oy1, oz0, oz1 in overlaps:
                    if oz0 <= iz < oz1:
                        diff[ox0:ox1, oy0:oy1] = False
                if diff.any():
                    idx = np.argwhere(diff)
                    total_diff += len(idx)
                    for ix, iy in idx[:max(0, 5 - len(sample_pts))]:
                        sample_pts.append((float(lo[0] + (ix + 0.5) * step), float(lo[1] + (iy + 0.5) * step), float(zc)))

    if total_diff:
        caveat = f'; features down to {gap_s} {unit} not examined' if under_resolved else ''
        return (True, 'differ',
                f'{differs}: {total_diff} voxels (step={step:g}, {len(roi_specs)} ROI(s){caveat}), e.g. {sample_pts}',
                roi_specs)
    if under_resolved:
        out_tail = f'rerun with --step {rec:g}' if rec_fits else f'resolving at --step {rec:g} exceeds budget, compare a narrower pair'
        return (False, 'unresolved',
                f'{label}: no difference found at step={step:g}, {len(roi_specs)} ROI(s) {shapes} '
                f'(features down to {gap_s} {unit} unresolved; {out_tail})',
                roi_specs)
    return (False, 'voxel',
            f'{label} identical ({space} matches voxel for voxel, step={step:g}, '
            f'{len(roi_specs)} ROI(s) {shapes})',
            roi_specs)


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
    h0 = []
    if len(A['proj']) != len(A['solid']) or len(B['proj']) != len(B['solid']):
        h0.append(f'projectile-solid {len(A["proj"])} -> {len(B["proj"])}')
    if A['sky'] or B['sky']:
        h0.append(f'sky {len(A["sky"])} -> {len(B["sky"])}')
    if h0:
        print('hull-0 brushes: ' + ', '.join(h0), flush=True)
    liq = [f'{k} {len(A[k])} -> {len(B[k])}' for k in LIQUIDS if A[k] or B[k]]
    if liq:
        print('liquid brushes (not solid, each class compared separately): ' + ', '.join(liq), flush=True)

    differed = False
    ok_extra = []
    solid_res = None
    for kind, label, banner, space in CLASSES:
        if kind not in ('solid', 'proj') and not A[kind] and not B[kind]:
            continue
        # proj is always a subset of solid (WORLD_ENTITY_TYPES). When the clip/sky brushes excluded
        # from proj are geometry-identical between both maps and never intersect solid's diff ROIs,
        # proj's voxel comparison is mathematically identical to solid's -- skip re-voxelizing.
        if kind == 'proj' and solid_res is not None:
            pA_ids, pB_ids = {id(b) for b in A['proj']}, {id(b) for b in B['proj']}
            exA = [b for b in A['solid'] if id(b) not in pA_ids]
            exB = [b for b in B['solid'] if id(b) not in pB_ids]
            s_diff, s_status, s_line, s_rois = solid_res
            if (Counter(b[4] for b in exA) == Counter(b[4] for b in exB) and
                    not any(bool(np.all(b[1] > lo - 1e-6) and np.all(b[0] < hi + 1e-6))
                            for b in exA + exB for _, _, lo, hi, *_ in s_rois)):
                diff, status = s_diff, s_status
                line = (s_line.replace('COLLISION DIFFERS', banner, 1) if status == 'differ' else
                        s_line.replace('collision:', f'{label}:', 1) if status == 'unresolved' else s_line)
                differed |= diff
                if status in ('differ', 'unresolved'):
                    print(line, flush=True)
                else:
                    tag = 'voxel-identical' if status == 'voxel' else f'{len(A[kind])} identical'
                    ok_extra.append(f'{label} ({tag})')
                continue
        diff, status, line, rois = compare(A[kind], B[kind], step, kind, label, banner, space)
        if kind == 'solid':
            solid_res = (diff, status, line, rois)
        differed |= diff
        if kind == 'solid' or status in ('differ', 'unresolved'):
            print(line, flush=True)
        else:
            tag = 'voxel-identical' if status == 'voxel' else f'{len(A[kind])} identical'
            ok_extra.append(f'{label} ({tag})')
    if ok_extra:
        print('hull-0/contents identical: ' + ', '.join(ok_extra), flush=True)
    if differed:
        sys.exit(1)


if __name__ == '__main__':
    main()
