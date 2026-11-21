"""MAP GENERATOR CORE (template, qmap-toolkit v3).

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
NAME = 'mymap_b1'                 # every build gets a new name: QW clients cache maps by name
TITLE = 'My Map (beta 1)'         # worldspawn message
SYM = 'none'                      # 'none'   - asymmetric (write everything; ca_lyceum)
                                  # 'rotate' - 180-degree rotation about the origin (ctf_bastion)
                                  # 'mirror' - mirror about x = 0, north stays north (ctf_circuit)
                                  # with symmetry you write the x > 0 half; sym=True calls add the copy
LIGHT_SCALE = 0.5                 # global lamp scale: pale materials need less, dark ones more
FLOOR_SKIN = 16                   # minlight skin on walkable tops (16, never 8: see GUIDE gotchas)
FLOOR_MINLIGHT = 30               # no walkable floor goes black
PILLAR_PARTS = True               # columns >= 96 tall get a 32-unit base and capital ('pbase'/'pcap')
C = 16                            # grid cell size (units)
XMIN, XMAX = -1536, 1536
YMIN, YMAX = -1536, 1536
BOT, TOP = -256, 640
NX, NY = (XMAX - XMIN) // C, (YMAX - YMIN) // C
INTERMISSION = ('0 0 400', '30 45 0')       # origin, mangle

# =========================================================================
# TEXTURES - which texture each kind of surface gets, per zone. The template uses the blockout
# set from texgen_blockout.py (bk_*): flat colours per zone, height marks, so rooms are easy to
# tell apart in a layout build. A visual pass replaces this mapping and the texture generator.
# =========================================================================
ZONE_OF = {}                      # theme -> blockout zone 'z0'..'z7' (blue z0, red z7; others in carve order)
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


def textures(kind, th, role):
    """(top, bottom, side) texture names for a brush piece of `kind` in theme `th`;
    for kind 'wall', `role` is the band: wall / wall_lo (below SPLIT_Z) / base (kickplate) /
    strp (light strip) / trim (cornice, sill) / band (the TRIM_Z course, TRIM_H tall) / glass."""
    z = zone(th)
    flr, ceil = f'bk_{z}_flr', f'bk_{z}_ceil'
    if kind == 'wall':
        side = {'wall': f'bk_{z}_wall', 'wall_lo': f'bk_{z}_wall', 'base': 'bk_base', 'strp': f'bk_{z}_strp',
                'trim': 'bk_trim', 'band': 'bk_trim', 'frame': f'bk_{z}_wall', 'glass': f'bk_{z}_wall'}[role]
        return flr, ceil, side
    return {
        'ledge': (flr, ceil, f'bk_{z}_wall'),
        'rail': ('bk_tread', ceil, 'bk_base'),
        'stair': ('bk_tread', ceil, 'bk_riser'),
        'flank': ('bk_tread', ceil, 'bk_riser'),
        'bridge': ('bk_tread', ceil, 'bk_trim'),
        'pillar': ('bk_pillar',) * 3,
        'pbase': ('bk_pbase',) * 3,
        'pcap': ('bk_pcap',) * 3,
        'perch': ('bk_perch',) * 3,
        'crate': ('bk_cratetop', 'bk_cratetop', 'bk_crate'),
        'stand': ('bk_stand', ceil, 'bk_riser'),
        'pad': ('bk_pad', ceil, 'bk_trim'),
        'lamp': ('bk_lampbox', 'bk_light', 'bk_lampbox'),
        'sky': ('sky_bk',) * 3,
    }[kind]


EDGE_TEX = 'bk_trim'              # edges of non-solid panels, trigger brushes


def fixture_tex(th):
    """Wall lamp texture for a room of theme th."""
    return 'bk_wlamp'


def light_color(th):
    """Lamp colour for a room of theme th (shows only with a .lit-aware client; keep it subtle)."""
    return '255 226 190'


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
TRIM_Z = {}         # theme -> z of an extra string-course trim carried through tall air ('band' role)
TRIM_H = 16         # its height (ctf_strata: 32, a coal seam where the slab between floors is)
SPLIT_Z = {}        # theme -> z below which walls take the 'wall_lo' stone (stratified tall rooms)
SUN = {'_sunlight': '160', '_sun_mangle': '35 -62 0', '_sunlight2': '40'}   # worldspawn sky light
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
                if any(a == ceil and m == 'sky' for a, b, m in cols[i][j]):
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


# =========================================================================
# v3: TEAM HALVES - lights and lamps by half (ctf_strata)
# =========================================================================
def side_of(th):
    """'b' or 'r': which team's half a theme is in (split_halves() gives copy-half rooms a '_r')."""
    return 'r' if th == 'red' or th.endswith('_r') else 'b'


def split_halves(themes):
    """Every shared theme gets a twin for the copy half ('lower' -> 'lower_r', cells with x < 0), so
    textures() / fixture_tex() / light_color() can colour strips and lamps by team half: wherever you
    stand, the lights say whose half it is. Call once, at the end of the layout. In textures(), strip
    the suffix to find the material (th[:-2]) and use side_of(th) for the team colour."""
    for i in range(NX):
        if XMIN + i * C + C / 2 >= 0:
            continue
        for j in range(NY):
            if theme[i][j] in themes:
                theme[i][j] += '_r'
            if (i, j) in rooms:
                rooms[(i, j)] = [(z0, z1, th + '_r' if th in themes else th, d) for z0, z1, th, d in rooms[(i, j)]]
    for d in (ZONE_FLOOR, STRIPE_Z, TRIM_Z, SPLIT_Z, GLASS_Z, ZONE_OF):
        for th in themes:
            if th in d:
                d[th + '_r'] = d[th]


# =========================================================================
# v3: RAMPS - true slopes, not steps
# =========================================================================
RAMPS = []          # (rect, axis, sign, z0, z1, bands): floor rises z0 -> z1 along sign*axis


def ramp(r, axis, z0, z1, rev=False, bands=True, sym=True):
    """A real slope: the floor over rect r rises from z0 at its low end to z1 at its high end, along
    +axis ('x' or 'y'; rev=True: along -axis). Ramps keep a player's speed where stairs bump it, and
    let them ramp-jump; QW maps are full of them. Walkable up to 45 degrees (rise <= run); 15-35
    plays best. The floor under r should already be at z0 (the ramp sits on it).
    The grid gets a stepped stand-in for the checks (mat 'ramp', never written as brushes); the .map
    gets one wedge brush. bands=True: where a wall runs along a side of the ramp, its kickplate and
    light strip are drawn on a slope (illusionary overlays) from the low room's bands to the high
    room's, and that wall's own flat bands are left off over the ramp's length."""
    run = (r[2] - r[0]) if axis == 'x' else (r[3] - r[1])
    assert 0 < z1 - z0 <= run, f'ramp {r}: rise {z1 - z0} over run {run} is steeper than 45 degrees'
    copies = [(r, -1 if rev else 1)]
    if symmetric(sym):
        flip = SYM == 'rotate' or axis == 'x'
        copies.append((rot(r), (1 if rev else -1) if flip else (-1 if rev else 1)))
    for rr, sg in copies:
        RAMPS.append((rr, axis, sg, z0, z1, bands))
        lo_edge = (rr[0] if sg > 0 else rr[2]) if axis == 'x' else (rr[1] if sg > 0 else rr[3])
        ft = ((lo_edge - 32, rr[1], lo_edge, rr[3]) if sg > 0 else (lo_edge, rr[1], lo_edge + 32, rr[3])) if axis == 'x' \
            else ((rr[0], lo_edge - 32, rr[2], lo_edge) if sg > 0 else (rr[0], lo_edge, rr[2], lo_edge + 32))
        stair_feet.append((ft, z0))
        for i, j in cells(rr):
            c0 = (XMIN + i * C) if axis == 'x' else (YMIN + j * C)           # cell's low corner on the axis
            d = (c0 - rr[0]) if (axis == 'x' and sg > 0) else (rr[2] - c0 - C) if axis == 'x' else \
                (c0 - rr[1]) if sg > 0 else (rr[3] - c0 - C)
            h = z0 + (z1 - z0) * d / run                                       # slope height at the cell's low edge
            h = int(h)
            if h > z0:
                col = _subtract(cols[i][j], z0, h)
                col.append([z0, h, 'ramp'])
                col.sort()
                cols[i][j] = col


# =========================================================================
# v3: PRISMS - angled walls, chamfered corners, many-sided pillars
# =========================================================================
PRISMS = []         # (points, z0, z1, kind)


def _overlaps(pts, x0, y0, x1, y1, eps=0.5):
    """Does the convex polygon pts (counter-clockwise) overlap the box by more than eps? (separating axes)"""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    if max(xs) <= x0 + eps or min(xs) >= x1 - eps or max(ys) <= y0 + eps or min(ys) >= y1 - eps:
        return False
    for k in range(len(pts)):
        ax, ay = pts[k]
        bx, by = pts[(k + 1) % len(pts)]
        nx, ny = by - ay, -(bx - ax)                      # outward normal of a CCW edge
        L = math.hypot(nx, ny)
        if min(nx * (cx - ax) + ny * (cy - ay) for cx in (x0, x1) for cy in (y0, y1)) >= eps * L:
            return False
    return True


def _inside(pts, x, y, eps=0.01):
    """Point inside (or on) a convex CCW polygon."""
    n = len(pts)
    for k in range(n):
        (ax, ay), (bx, by) = pts[k], pts[(k + 1) % n]
        if (bx - ax) * (y - ay) - (by - ay) * (x - ax) < -eps:
            return False
    return True


def prism(points, z0, z1, kind=None, sym=True):
    """Solid vertical prism on a convex footprint (points counter-clockwise, seen from above): a
    diagonal wall, a chamfered corner, an octagonal pillar, a wedge. kind None: each face is banded
    like the room it looks into (kickplate, strip, cornice), with its texture running along the angled
    face (Valve 220 axes, so nothing stretches); other kinds ('pillar', ...) take that kind's textures.
    The grid gets a stand-in for the checks: in every cell the prism overlaps, the air in [z0, z1]
    becomes mat 'diag' (solid to the checks, never written - the prism brush covers it; no lamp or
    band lands on a face hidden inside the prism). Named kinds keep their mat on cells wholly inside.
    Solid already in the cell stays, so a prism may start below the floor (z0 = BOT) safely.
    Call it AFTER the carves of the space it stands in: a later carve hollows its stand-in again."""
    pts = [tuple(p) for p in points]
    area = sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1] for k in range(len(pts)))
    assert area > 0, f'prism {pts}: points must be counter-clockwise'
    copies = [pts]
    if symmetric(sym):
        q = [sym_pt(x, y) for x, y in pts]
        copies.append(q if SYM == 'rotate' else q[::-1])
    for P in copies:
        PRISMS.append((P, z0, z1, kind))
        xs, ys = [p[0] for p in P], [p[1] for p in P]
        for i in range(max(0, int((min(xs) - XMIN) // C)), min(NX, int((max(xs) - XMIN) // C) + 1)):
            for j in range(max(0, int((min(ys) - YMIN) // C)), min(NY, int((max(ys) - YMIN) // C) + 1)):
                x, y = XMIN + i * C, YMIN + j * C
                if kind not in (None, 'ledge') and all(_inside(P, x + a, y + b) for a in (0, C) for b in (0, C)):
                    m = kind
                elif _overlaps(P, x, y, x + C, y + C):
                    m = 'diag'           # v3.1: any overlap, not just the centre: the checks must never
                                         # see a gap wider than it is (a 24-unit gap read as 32 in concept C)
                else:
                    continue
                # only the AIR in [z0, z1] becomes the stand-in: solid already there (the floor under
                # a prism that starts below it) stays and is written, or a cell only partly under the
                # prism would leave a hole down to the void
                col, z = cols[i][j], z0
                for a, b, _m in sorted(col):
                    if b <= z or a >= z1:
                        continue
                    if a > z:
                        col.append([z, a, m])
                    z = max(z, b)
                if z < z1:
                    col.append([z, z1, m])
                col.sort()


def chamfer(r, corner, size, z0, z1, sym=True):
    """Cut a room's corner at 45 degrees: a triangular prism with legs `size` along the two walls
    meeting at `corner` ('ne', 'nw', 'se', 'sw') of the carved rect r. Four of them make an octagon."""
    x = r[2] if 'e' in corner else r[0]
    y = r[3] if 'n' in corner else r[1]
    sx = -1 if 'e' in corner else 1
    sy = -1 if 'n' in corner else 1
    tri = [(x, y), (x + sx * size, y), (x, y + sy * size)]
    if sx * sy < 0:
        tri = tri[::-1]
    prism(tri, z0, z1, None, sym)


def diag_wall(x0, y0, x1, y1, thick, z0, z1, sym=True):
    """A straight wall from (x0, y0) to (x1, y1) at any angle, `thick` units thick (centred)."""
    L = math.hypot(x1 - x0, y1 - y0)
    nx, ny = -(y1 - y0) / L * thick / 2, (x1 - x0) / L * thick / 2
    quad = [(x0 - nx, y0 - ny), (x1 - nx, y1 - ny), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)]
    prism([(round(a, 2), round(b, 2)) for a, b in quad], z0, z1, None, sym)
