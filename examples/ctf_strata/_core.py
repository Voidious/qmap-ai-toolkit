"""MAP GENERATOR CORE (template, qmap-toolkit v2).

The generator is plain Python concatenated from parts (build.sh does it):
    _core.py   settings, grid, building primitives, texture mapping      <- edit the SETTINGS block
    _layout.py the map: rooms, stairs, lamps, spawns                      <- you write this
    _itemh.py  item helper
    _items.py  the items                                                  <- you write this
    _out.py    .map / .json writer (per-face texturing, bands, lamps, minlight skins)
The core is a starting point, not a cage: when a design needs something it can't do (a diagonal
wall, a curved room, a new kind of fixture), extend it. Every map so far added something here.
"""
import json
import math
import sys

# =========================================================================
# SETTINGS - per map
# =========================================================================
NAME = 'ctf_strata_b6'                # every build gets a new name: QW clients cache maps by name
TITLE = 'Strata (CTF, beta 6)'        # worldspawn message
SYM = 'rotate'                     # 'none'   - asymmetric (write everything; ca_lyceum)
                                  # 'rotate' - 180-degree rotation about the origin (ctf_bastion)
                                  # 'mirror' - mirror about x = 0, north stays north (ctf_circuit)
                                  # with symmetry you write the x > 0 half; sym=True calls add the copy
LIGHT_SCALE = 0.5                 # global lamp scale: pale materials need less, dark ones more
FLOOR_SKIN = 16                   # minlight skin on walkable tops (16, never 8: see GUIDE gotchas)
FLOOR_MINLIGHT = 30               # no walkable floor goes black
PILLAR_PARTS = True               # columns >= 96 tall get a 32-unit base and capital ('pbase'/'pcap')
C = 16                            # grid cell size (units)
XMIN, XMAX = -2880, 2880
YMIN, YMAX = -960, 960
BOT, TOP = -64, 704
NX, NY = (XMAX - XMIN) // C, (YMAX - YMIN) // C
INTERMISSION = ('0 -700 420', '25 90 0')       # origin, mangle

# =========================================================================
# TEXTURES - which texture each kind of surface gets, per zone. The template uses the blockout
# set from texgen_blockout.py (bk_*): flat colours per zone, height marks, so rooms are easy to
# tell apart in a layout build. A visual pass replaces this mapping and the texture generator.
# =========================================================================
ZONE_OF = {}                      # theme -> blockout colour zone 'z0'..'z7' (assigned in carve order)
BK_ZONES = ('z0', 'z1', 'z2', 'z3', 'z4', 'z5', 'z6', 'z7')
GLASS_Z = {}                      # theme -> z of a 96-tall window band (optional)


def zone(th):
    """Blockout colour zone of a theme. Themes named in ZONE_OF keep their zone; 'blue' and 'red'
    get the blue and red zones; the rest take the remaining zones in the order they are carved."""
    if th not in ZONE_OF:
        fixed = {'blue': 'z0', 'red': 'z7'}
        if th in fixed and fixed[th] not in ZONE_OF.values():
            ZONE_OF[th] = fixed[th]
        else:
            used = set(ZONE_OF.values()) | {'z0', 'z7'}
            free = [z for z in BK_ZONES if z not in used] or list(BK_ZONES)
            ZONE_OF[th] = free[0]
    return ZONE_OF[th]


# --- b3 visual pass: "The dig" (texgen_dig.py) ------------------------------------------------
# The rock tells you which floor you are on: slate at floor 0, a coal seam where the slab is,
# limestone at floor 256. Tall rooms (the pit, the bases, the well shafts) show all three.
FAMILY = {'lower': 'slate', 'under': 'slate', 'deck': 'chalk', 'deck2': 'iron', 'well': 'grey',
          'atrium': 'pit', 'blue': 'blue', 'red': 'red', 'room': 'slate'}
TRIM_H = 32                        # the TRIM_Z band is the 32-tall coal seam (the slab between floors)
SPLIT_Z = {'atrium': 224, 'blue': 224, 'red': 224}   # walls below the seam are slate
SUN = {'_sunlight': '120', '_sun_mangle': '20 -58 0', '_sunlight_color': '150 170 255',
       '_sunlight2': '40', '_sunlight2_color': '120 136 210'}      # moonlight on the pit


def side_of(th):
    """'b' or 'r': which team's half a theme is in (split_halves() gives red-half rooms a '_r')."""
    return 'r' if th == 'red' or th.endswith('_r') else 'b'


def split_halves(themes):
    """b4: every shared theme gets a red-half twin ('lower' -> 'lower_r') for cells with x < 0, so
    strips and wall lamps can be team-coloured by half: wherever you are, the lights say whose
    half it is. Call once at the end of the layout."""
    for i in range(NX):
        if XMIN + i * C + C / 2 >= 0:
            continue
        for j in range(NY):
            if theme[i][j] in themes:
                theme[i][j] += '_r'
            if (i, j) in rooms:
                rooms[(i, j)] = [(z0, z1, th + '_r' if th in themes else th, d) for z0, z1, th, d in rooms[(i, j)]]
    for d in (ZONE_FLOOR, STRIPE_Z, TRIM_Z, SPLIT_Z, GLASS_Z):
        for th in themes:
            if th in d:
                d[th + '_r'] = d[th]


def textures(kind, th, role):
    """(top, bottom, side) texture names for a brush piece of `kind` in theme `th`;
    for kind 'wall', `role` is the band: wall / wall_lo / base / strp / trim / band / glass."""
    team = side_of(th)
    th = th[:-2] if th.endswith('_r') else th
    fam = FAMILY.get(th, 'slate')
    wall = {'slate': 'sd_slateu' if th == 'under' else 'sd_slate', 'chalk': 'sd_chalk', 'iron': 'sd_irons',
            'grey': 'sd_greyl', 'pit': 'sd_pit', 'blue': 'sd_blue_hi', 'red': 'sd_red_hi'}[fam]
    wall_lo = {'pit': 'sd_slate', 'blue': 'sd_blue_lo', 'red': 'sd_red_lo'}.get(fam, wall)
    flr = {'slate': 'sd_ugflr' if th == 'under' else 'sd_slflr', 'chalk': 'sd_chflr', 'iron': 'sd_irflr',
           'grey': 'sd_grflr', 'pit': 'sd_pitflr', 'blue': 'sd_blue_flr', 'red': 'sd_red_flr'}[fam]
    ceil = {'slate': 'sd_soffit' if th == 'under' else 'sd_lagging', 'pit': 'sd_lmceil',
            'blue': 'sd_blue_ceil', 'red': 'sd_red_ceil'}.get(fam, 'sd_lmceil')
    base = 'sd_lmbase' if fam in ('chalk', 'iron', 'grey') else 'sd_ballast'
    strp = 'sd_cable_' + team                    # b4: blue bulbs in the blue half, red in the red half
    if kind == 'wall':
        side = {'wall': wall, 'wall_lo': wall_lo, 'base': base, 'strp': strp, 'trim': 'sd_trim',
                'band': 'sd_seam', 'frame': wall, 'glass': wall}[role]
        return flr, ceil, side
    return {
        'ledge': (flr, ceil, wall),
        'rail': ('sd_tread', ceil, base),
        'stair': ('sd_tread', ceil, 'sd_riser'),
        'flank': ('sd_tread', ceil, 'sd_riser'),
        'bridge': ('sd_tread', ceil, 'sd_trim'),
        'pillar': ('sd_pillar',) * 3,
        'pbase': ('sd_pbase',) * 3,
        'pcap': ('sd_crib',) * 3,
        'perch': ('sd_planks',) * 3,
        'beam': ('sd_beamt', 'sd_beamt', 'sd_beam'),
        'crate': ('sd_planks', 'sd_planks', 'sd_crib'),
        'stand': ('sd_stand_q', ceil, 'sd_riser'),
        'stand_b': ('sd_stand_b', ceil, 'sd_riser'),
        'stand_r': ('sd_stand_r', ceil, 'sd_riser'),
        'pad': ('sd_iron', ceil, 'sd_iron'),
        'lamp': ('sd_lampbox', 'sd_light', 'sd_lampbox'),
        'sky': ('sky_dig',) * 3,
    }[kind]


EDGE_TEX = 'sd_iron'              # edges of non-solid panels, trigger brushes


def fixture_tex(th):
    """Wall lamp texture: caged bulkhead lamps with team glass, by half (b4)."""
    return 'sd_wlamp_' + side_of(th)


def light_color(th):
    """Lamp colour (shows with a .lit-aware client): warm incandescent; the bases lean team."""
    if th in ('blue', 'red'):
        return {'blue': '170 192 255', 'red': '255 176 140'}[th]
    return '236 226 220' if side_of(th) == 'b' else '255 214 170'      # a faint lean by half


# =========================================================================
# GRID
# =========================================================================
# --- grid -----------------------------------------------------------------
# each column: list of [z0, z1, mat]; mat None = structural (takes zone theme)
cols = [[[[BOT, TOP, None]] for _ in range(NY)] for _ in range(NX)]
theme = [[None] * NY for _ in range(NX)]


def cells(r):
    x0, y0, x1, y1 = r
    assert all(v % C == 0 for v in r), r
    assert XMIN < x0 < x1 < XMAX and YMIN < y0 < y1 < YMAX, r
    for i in range((x0 - XMIN) // C, (x1 - XMIN) // C):
        for j in range((y0 - YMIN) // C, (y1 - YMIN) // C):
            yield i, j


def _subtract(col, z0, z1):
    out = []
    for a, b, m in col:
        if b <= z0 or a >= z1:
            out.append([a, b, m])
            continue
        if a < z0:
            out.append([a, z0, m])
        if b > z1:
            out.append([z1, b, m])
    return out


def sym_pt(x, y):
    """Where the symmetric copy of point (x, y) lands."""
    return (-x, -y) if SYM == 'rotate' else (-x, y)


def sym_ang(a):
    """The copy's facing for a written facing a (degrees, Quake yaw)."""
    return (a + 180) % 360 if SYM == 'rotate' else (180 - a) % 360


def rot(r):
    """The symmetric copy of a rect (rotation or mirror, per SYM)."""
    x0, y0, x1, y1 = r
    return (-x1, -y1, -x0, -y0) if SYM == 'rotate' else (-x1, y0, -x0, y1)


SIDE_ROT = ({'-x': '+x', '+x': '-x', '-y': '+y', '+y': '-y'} if SYM == 'rotate' else
            {'-x': '+x', '+x': '-x', '-y': '-y', '+y': '+y'})


def symmetric(sym=True):
    return sym and SYM != 'none'


def _both(r, sym):
    return [r, rot(r)] if symmetric(sym) else [r]


doors = []         # (rect, z0, z1) openings that get a framed jamb and lintel
rooms = {}         # (i, j) -> [(z0, z1)] carve extents, to find a room's real floor under stairs
# Wall textures are aligned to each zone's main floor, so panels line up across the whole zone.
TRIM_Z = {}         # theme -> z of an extra string-course trim carried through tall air
STEP_KICK = set()   # themes whose kickplate steps up and down beside stairs (usually: none - it looks bad)
ZONE_FLOOR = {}     # theme -> its main floor z (wall textures are anchored to it); set by carve()
STRIPE_Z = {}       # theme -> z of its light strip; default floor + 128; 10**6 = no strip
NOCAP = set()       # (i, j, ceiling z): openings whose low ceiling gets no cornice (arcades)


def carve(r, z0, z1, th, sky=False, sym=True, door=False, nocap=False, strip=None):
    """Hollow out a room: air from floor z0 to ceiling z1 over rect r, theme th.
    door=True: a passage (framed, takes the colour of the rooms around it, no bands of its own).
    The first carve of a theme sets its main floor (ZONE_FLOOR) and light-strip height (strip=,
    default floor + 128; strip=10**6 for none)."""
    if not door:
        zone(th)
        ZONE_FLOOR.setdefault(th, z0)
        STRIPE_Z.setdefault(th, z0 + 128 if strip is None else strip)
    for rr in _both(r, sym):
        if nocap:
            NOCAP.update((i, j, z1) for i, j in cells(rr))
        if door:
            doors.append((rr, z0, z1))
        for i, j in cells(rr):
            col = _subtract(cols[i][j], z0, z1)
            if sky:
                for s in col:
                    if s[0] == z1:
                        s[2] = 'sky'
            cols[i][j] = col
            rooms.setdefault((i, j), []).append((z0, z1, th, door))
            if not door:              # doorways take the colour of the walls around them
                theme[i][j] = th


pillar_rects = []   # whole column footprints - faces are textured from the column's corner


def fill(r, z0, z1, mat, sym=True):
    """Solid from z0 to z1 over rect r. mat None (or 'ledge') = structure, textured like the room
    it faces, with bands; other mats ('pillar', 'crate', 'stand', 'pad', ...) map through textures()."""
    if mat == 'ledge':
        mat = None            # platforms are plain structure, banded like any wall
    segs = ([[z0, z0 + 32, 'pbase'], [z0 + 32, z1 - 32, 'pillar'], [z1 - 32, z1, 'pcap']]
            if mat == 'pillar' and PILLAR_PARTS and z1 - z0 >= 96 else [[z0, z1, mat]])
    for rr in _both(r, sym):
        if mat == 'pillar':
            pillar_rects.append((*rr, z1))
        for i, j in cells(rr):
            col = _subtract(cols[i][j], z0, z1)
            col.extend([list(sg) for sg in segs])
            col.sort()
            cols[i][j] = col


def stairs(x0, y0, x1, y1, axis, z_from, z_to, run=32, sym=True, base=None, rev=False, flank=None):
    """Steps of 16 rising along +axis ('x' or 'y') from z_from+16 to z_to (rev: rising along -axis)."""
    n = (z_to - z_from) // 16
    length = (x1 - x0) if axis == 'x' else (y1 - y0)
    assert length == n * run, (length, n, run)
    lo = ('-' if not rev else '+') + axis
    ft = {'-x': (x0 - 32, y0, x0, y1), '+x': (x1, y0, x1 + 32, y1),
          '-y': (x0, y0 - 32, x1, y0), '+y': (x0, y1, x1, y1 + 32)}[lo]
    for rr in _both(ft, sym):
        stair_feet.append((rr, z_from))
    for k in range(n):
        h = z_from + 16 * ((n - k) if rev else (k + 1))
        if axis == 'x':
            r = (x0 + run * k, y0, x0 + run * (k + 1), y1)
        else:
            r = (x0, y0 + run * k, x1, y0 + run * (k + 1))
        # b9: only the top 16 of each step is 'stair' (tread + riser texture); the mass
        # underneath is plain structure, so buried or exposed sides get proper wall texturing
        fill(r, BOT if base is None else base, h - 16, None, sym)
        fill(r, h - 16, h, 'stair', sym)
        # side treads on an open flank: every step is walkable from the side (agora fix, built in)
        if flank:
            for cc in range(1, (h - z_from) // 16):
                s = 16 * cc
                rr = {'-x': (r[0] - s, r[1], r[0] - s + 16, r[3]), '+x': (r[2] + s - 16, r[1], r[2] + s, r[3]),
                      '-y': (r[0], r[1] - s, r[2], r[1] - s + 16), '+y': (r[0], r[3] + s - 16, r[2], r[3] + s)}[flank]
                fill(rr, BOT if base is None else base, h - s - 16, None, sym)
                fill(rr, h - s - 16, h - s, 'flank', sym)          # b2: plinth look, not stair edges


lights = []        # (x, y, z, value[, wait])
spawns = []        # (x, y, floor_z, angle, label)
labels = []        # (x, y, text, z) for the plan


def label(x, y, text, z=0):
    labels.append((x, y, text, z))


def lamp(x, y, ceil, value=380, sym=True):
    """Ceiling lamp: a lamp-box fixture flush with the ceiling at z = ceil, light 40 below it."""
    pts = [(x, y)] + ([sym_pt(x, y)] if symmetric(sym) else [])
    for px, py in pts:
        fill((px - 16, py - 16, px + 16, py + 16), ceil - 8, ceil, 'lamp', sym=False)
        lights.append((px, py, ceil - 40, round(value * LIGHT_SCALE)))


def room_lamps(r, ceil, step=256, value=380, sym=True):
    x0, y0, x1, y1 = r
    nx = max(1, round((x1 - x0) / step))
    ny = max(1, round((y1 - y0) / step))
    for a in range(nx):
        for b in range(ny):
            x = x0 + (x1 - x0) * (2 * a + 1) // (2 * nx)
            y = y0 + (y1 - y0) * (2 * b + 1) // (2 * ny)
            p = _lamp_spot(r, x // 16 * 16, y // 16 * 16, ceil)
            if p:
                lamp(p[0], p[1], ceil, value, sym)


def _lamp_spot(r, x, y, ceil, reach=160):
    """Nearest spot to (x, y) inside r where a ceiling lamp's box and its light are both in air
    (call room_lamps after the room's pillars and baffles). None if nothing within reach."""
    def clear(px, py):
        if not (r[0] + 16 <= px <= r[2] - 16 and r[1] + 16 <= py <= r[3] - 16):
            return False
        for qx in (px - 16, px):
            for qy in (py - 16, py):
                i, j = (qx - XMIN) // C, (qy - YMIN) // C
                if any(a < ceil and b > ceil - 48 for a, b, m in cols[i][j]):
                    return False
        return True
    for d in range(0, reach + 1, 16):
        ring = sorted({(x + dx, y + dy) for dx in range(-d, d + 1, 16) for dy in (-d, d)} |
                      {(x + dx, y + dy) for dy in range(-d, d + 1, 16) for dx in (-d, d)},
                      key=lambda p: ((p[0] - x) ** 2 + (p[1] - y) ** 2, p))
        for p in ring:
            if clear(*p):
                return p
    return None


def spawn(x, y, z, angle, label='', sym=True):
    """info_player_deathmatch at (x, y) standing on floor z, facing angle."""
    spawns.append((x, y, z, angle, label))
    if symmetric(sym):
        spawns.append((*sym_pt(x, y), z, sym_ang(angle), label + "'"))




liquids = []       # (rect, z0, z1, texture): lava etc., written as world brushes, not in the grid
teleports = []     # (pad rect, pad top z, dest x, dest y, dest floor z, dest angle)


def liquid(r, z0, z1, tex='*bk_water', sym=True):
    """Water / slime / lava volume (texture name decides: '*water..', '*slime..', '*lava..')."""
    for rr in _both(r, sym):
        liquids.append((rr, z0, z1, tex))


def teleporter(r, z, dx, dy, dz, ang, sym=True):
    """trigger_teleport over pad rect r (top at z) to (dx, dy) on floor dz, facing ang."""
    teleports.append((r, z, dx, dy, dz, ang))
    if symmetric(sym):
        teleports.append((rot(r), z, *sym_pt(dx, dy), dz, sym_ang(ang)))


decals = []        # (x0, y0, z0, x1, y1, z1, texture, texture width px): non-solid panels


def panel(r, z0, z1, tex, tex_copy=None, tex_px=256, sym=True):
    """Non-solid picture panel (emblem, banner, sign) - func_detail_illusionary, never collision.
    r is a thin rect against a wall (4-8 thick); the picture goes on both broad faces, scaled so the
    texture's width (tex_px pixels) spans the panel's width. tex_copy: the symmetric copy's picture
    (e.g. the other team's banner)."""
    decals.append((*r[:2], z0, *r[2:], z1, tex, tex_px))
    if symmetric(sym):
        rr = rot(r)
        decals.append((*rr[:2], z0, *rr[2:], z1, tex_copy or tex, tex_px))


pushes = []        # (trigger rect, pad top z, dest x, dest y, dest floor z, speed, angles)


def jumppad(r, z, dx, dy, dz, speed, pitch, yaw, sym=True):
    """trigger_push REPLACES velocity while touched, so the push is angled (pitch about -60..-80):
    it carries you forward as well as up. Pad block top at z."""
    fill(r, z - 8, z, 'pad', sym=sym)
    pushes.append((r, z, dx, dy, dz, speed, f'{pitch} {yaw} 0'))
    if symmetric(sym):
        pushes.append((rot(r), z, *sym_pt(dx, dy), dz, speed, f'{pitch} {sym_ang(yaw)} 0'))


stair_feet = []     # (rect, z): the strip in front of each stair's bottom step must be open floor


def terrace(r, h, side, z0=0, sym=True):
    """Broad wall-to-wall steps down from the edge `side` of a platform r of height h to floor z0
    (walk up from anywhere along that edge)."""
    if symmetric(sym):
        terrace(rot(r), h, SIDE_ROT[side], z0, sym=False)
    for cc in range(1, (h - z0) // 16):
        s = 16 * cc
        rr = {'-x': (r[0] - s, r[1], r[0] - s + 16, r[3]), '+x': (r[2] + s - 16, r[1], r[2] + s, r[3]),
              '-y': (r[0], r[1] - s, r[2], r[1] - s + 16), '+y': (r[0], r[3] + s - 16, r[2], r[3] + s)}[side]
        fill(rr, BOT, h - s - 16, None, sym=False)
        fill(rr, h - s - 16, h - s, 'flank', sym=False)
    e = 16 * ((h - z0) // 16 - 1)
    stair_feet.append(({'-x': (r[0] - e - 32, r[1], r[0] - e, r[3]), '+x': (r[2] + e, r[1], r[2] + e + 32, r[3]),
                        '-y': (r[0], r[1] - e - 32, r[2], r[1] - e), '+y': (r[0], r[3] + e, r[2], r[3] + e + 32)}[side], z0))


def pyramid(r, h, sides, z0=0, sym=True):
    """Broad steps down from a raised block on several sides; corners wrap, so each level
    is one continuous L-shaped step (walk up from anywhere along those sides)."""
    if symmetric(sym):
        pyramid(rot(r), h, tuple(SIDE_ROT[s] for s in sides), z0, sym=False)
    n = (h - z0) // 16
    x0, y0, x1, y1 = r
    ext = 16 * (n - 1)
    X0, X1 = x0 - (ext if '-x' in sides else 0), x1 + (ext if '+x' in sides else 0)
    Y0, Y1 = y0 - (ext if '-y' in sides else 0), y1 + (ext if '+y' in sides else 0)
    for sd in sides:
        stair_feet.append(({'-x': (X0 - 32, Y0, X0, Y1), '+x': (X1, Y0, X1 + 32, Y1),
                            '-y': (X0, Y0 - 32, X1, Y0), '+y': (X0, Y1, X1, Y1 + 32)}[sd], z0))
    for x in range(X0, X1, 16):
        for y in range(Y0, Y1, 16):
            dx = (x0 - x) // 16 if x < x0 else ((x - x1) // 16 + 1 if x >= x1 else 0)
            dy = (y0 - y) // 16 if y < y0 else ((y - y1) // 16 + 1 if y >= y1 else 0)
            d = max(dx, dy)
            if d == 0 or h - 16 * d <= z0:
                continue
            hh = h - 16 * d
            fill((x, y, x + 16, y + 16), BOT, hh - 16, None, sym=False)
            fill((x, y, x + 16, y + 16), hh - 16, hh, 'flank', sym=False)

pipes = []         # (x0, y0, z0, x1, y1, z1) non-solid pipe runs: the lamp placer keeps clear of them


# --- teams (CTF / TDM bases) ----------------------------------------------------------------
team_spawns = []   # (x, y, floor_z, angle, team)


def team_spawn(x, y, z, angle, team=2, sym=True):
    """Base start spawn (KTX CTF: info_player_team1 / team2). With symmetry, write team 2's and
    the copy becomes team 1's."""
    team_spawns.append((x, y, z, angle, team))
    if symmetric(sym):
        team_spawns.append((*sym_pt(x, y), z, sym_ang(angle), 3 - team))


def carve_pair(r, z0, z1, th, th_copy, **kw):
    """carve() with a different theme on the symmetric copy (e.g. 'blue' here, 'red' there)."""
    carve(r, z0, z1, th, sym=False, **kw)
    if SYM != 'none':
        carve(rot(r), z0, z1, th_copy, sym=False, **kw)


perches = []       # (rect, floor z): hook-only ledges


def perch(r, z, depth=16, sym=True):
    """A slab ledge high on a wall, floor at z, air underneath: reached with the grappling hook
    (or a rocket jump). Stock it with ammo, not armour."""
    fill(r, z - depth, z, 'perch', sym=sym)
    for rr in _both(r, sym):
        perches.append((rr, z))


# --- sky, inlays ------------------------------------------------------------------------------
FLOOR_DECALS = []   # (x0, y0, x1, y1, z, texture): floor tops at z over the rect take this texture,
CEIL_DECALS = []    # anchored to the rect's own corner (a medallion, a rose, a dome painting)
FLOOR_OFFSET = {}   # texture -> (s, t) offsets: centre a floor pattern on its room (see GUIDE)


def inlay(r, z, tex, ceiling=False, sym=True):
    """Floor (or ceiling) inlay: the surface at height z over rect r gets texture tex, starting at
    the rect's corner - so a 128 medallion fits a 128 plinth exactly."""
    for rr in _both(r, sym):
        (CEIL_DECALS if ceiling else FLOOR_DECALS).append((*rr, z, tex))


def oculus(r, z, sym=True):
    """Make the ceiling over r (whose underside is at z) sky - texture only, same solid.
    In CTF remember the grappling hook sticks to sky."""
    for rr in _both(r, sym):
        for i, j in cells(rr):
            for sg in cols[i][j]:
                if sg[0] == z:
                    sg[2] = 'sky'


# --- light strips that follow stairs -------------------------------------------------------
STRIP_RAMPS = []     # (rect, lo, hi, offset): strip at floor + offset, clamped to [lo, hi]
STRIP_RAMPS_POS = [] # (rect, axis, start, z0, lo, hi, sign): strip by position along an axis


def strip_ramp(r, lo, hi, off, sym=True):
    """Over r, the light strip sits at (floor + off), clamped to [lo, hi]: it runs level with the
    lower room's strip, climbs step by step with the stairs, and levels off at the upper room's.
    Pick off so it meets BOTH rooms' strips exactly at every corner (see GUIDE gotchas)."""
    for rr in _both(r, sym):
        STRIP_RAMPS.append((rr, lo, hi, off))


def strip_ramp_pos(r, axis, start, z0, lo, hi, sign=1, sym=True):
    """Over r, the strip climbs 16 per 32 units along +axis (sign=1) or -axis (sign=-1) from z0 at
    coordinate `start`, clamped to [lo, hi] - by POSITION, not by the floor under it. Lets the
    climb begin before the stairs, so it can reach a corner that sits part-way up them."""
    for k, rr in enumerate(_both(r, sym)):
        if k == 0:
            STRIP_RAMPS_POS.append((rr, axis, start, z0, lo, hi, sign))
        else:                             # the copy: the axis is flipped where the symmetry flips it
            flip = SYM == 'rotate' or axis == 'x'
            STRIP_RAMPS_POS.append((rr, axis, -start if flip else start, z0, lo, hi, -sign if flip else sign))


def strip_z(th, f, p=None, q=None):
    """Light-strip height for air of theme th with floor f in cell (p, q)."""
    if p is not None:
        x, y = XMIN + p * C + 8, YMIN + q * C + 8
        for (x0, y0, x1, y1), axis, start, z0, lo, hi, sign in STRIP_RAMPS_POS:
            if x0 <= x < x1 and y0 <= y < y1:
                cmin = (XMIN + p * C) if axis == 'x' else (YMIN + q * C)
                t = (cmin - start) if sign > 0 else (start - (cmin + C))
                return min(max(z0 + 16 * (t // 32), lo), hi)
        for (x0, y0, x1, y1), lo, hi, off in STRIP_RAMPS:
            if x0 <= x < x1 and y0 <= y < y1:
                return min(max(f + off, lo), hi)
    return STRIPE_Z.get(th, 10 ** 6)
