"""MAP GENERATOR CORE (template, qmap-ai-toolkit).

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


def _side_rot(side):
    """Symmetric copy of a cardinal side ('-x', '+x', '-y', '+y') using current SYM."""
    return ({'-x': '+x', '+x': '-x', '-y': '+y', '+y': '-y'} if SYM == 'rotate' else
            {'-x': '+x', '+x': '-x', '-y': '-y', '+y': '+y'})[side]


SIDE_ROT = ({'-x': '+x', '+x': '-x', '-y': '+y', '+y': '-y'} if SYM == 'rotate' else
            {'-x': '+x', '+x': '-x', '-y': '-y', '+y': '+y'})


def _sym_axis_sign(axis, sg):
    """Symmetric copy of a signed axis direction (axis, sg in {-1, +1})."""
    flip = SYM == 'rotate' or axis == 'x'
    return -sg if flip else sg


def _fill_air(i, j, z0, z1, mat):
    """Replace only AIR intervals in cols[i][j] within [z0, z1] with stand-in `mat`,
    preserving existing solid so floors/ceilings never leak to the void."""
    if z1 <= z0:
        return
    col, z = cols[i][j], z0
    for a, b, _m in sorted(col):
        if b <= z or a >= z1:
            continue
        if a > z:
            col.append([z, a, mat])
        z = max(z, b)
    if z < z1:
        col.append([z, z1, mat])
    col.sort()


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
STRIPE_Z = {}       # theme -> z of its light strip; default floor + 144; 10**6 = no strip
NOCAP = set()       # (i, j, ceiling z): openings whose low ceiling gets no cornice (arcades)
NOARCH = set()      # (i, j, bottom z): overhangs whose bottom edge gets no architrave lintel


def carve(r, z0, z1, th, sky=False, sym=True, door=False, nocap=False, noarch=False, strip=None):
    """Hollow out a room: air from floor z0 to ceiling z1 over rect r, theme th.
    door=True: a passage (framed, takes the colour of the rooms around it, no bands of its own).
    The first carve of a theme sets its main floor (ZONE_FLOOR) and light-strip height (strip=,
    default floor + 144; strip=10**6 for none)."""
    if not door:
        zone(th)
        ZONE_FLOOR.setdefault(th, z0)
        STRIPE_Z.setdefault(th, z0 + 144 if strip is None else strip)
    for rr in _both(r, sym):
        if nocap:
            NOCAP.update((i, j, z1) for i, j in cells(rr))
        if noarch:
            NOARCH.update((i, j, z1) for i, j in cells(rr))
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


SLOPED_CEILS = []  # (rect, axis, sg, z_lo, z_hi, top_z, tex, v_base)
PENDANT_LAMPS = [] # (x, y, z_mount, z_stem_top): non-solid pendant lamps hung beneath sloped roofs
TRUSSES = []       # (rect, axis, z_bot, z_top, beam_h, knee, tie, tex, solid)
BUTTRESSES = []    # (rect, side, z0, z1, top_depth, taper, tex, solid)
ARCH_TRIMS = []    # (rect, axis, z_spring, z_crown, segs, depth, width, tex)
DIAG_RAMPS = []    # (x0, y0, x1, y1, width, z0, z1, base, thick)
PRISM_META = []    # parallel to PRISMS: dict(group, wrap_u, fit_u, u_period, edge_uvs)
_GROUP_SEQ = 0


def _next_group():
    global _GROUP_SEQ
    _GROUP_SEQ += 1
    return _GROUP_SEQ


def ceil_height_at(x, y, ceil_z, half=16):
    """Minimum ceiling underside height over [x-half, x+half] x [y-half, y+half]
    for any sloped/vaulted ceiling whose top meets ceil_z."""
    z_best = float(ceil_z)
    for rr, axis, sg, z_lo, z_hi, top_z, _tex, _vb in SLOPED_CEILS:
        if not (z_lo < ceil_z <= top_z + 1e-3):
            continue
        if (rr[2] <= x - half + 1e-6 or rr[0] >= x + half - 1e-6 or
                rr[3] <= y - half + 1e-6 or rr[1] >= y + half - 1e-6):
            continue
        u0, u1 = (rr[0], rr[2]) if axis == 'x' else (rr[1], rr[3])
        run = u1 - u0
        if run <= 1e-6:
            continue
        c = x if axis == 'x' else y
        ov0 = max(u0, c - half)
        ov1 = min(u1, c + half)
        if sg > 0:
            z_min = z_lo + (z_hi - z_lo) * (ov0 - u0) / run
        else:
            z_min = z_lo + (z_hi - z_lo) * (u1 - ov1) / run
        if z_min < z_best:
            z_best = z_min
    return z_best


def _truss_hits(px, py, z_lo, z_hi, half=16):
    """True when a lamp box/light volume overlaps any overhead truss."""
    for tr, _axis, zb, zt, bh, knee, _tie, _tex, _solid in TRUSSES:
        tz0 = zb - max(0, knee)
        tz1 = max(zt, zb + bh)
        if (tr[0] < px + half and tr[2] > px - half and
                tr[1] < py + half and tr[3] > py - half and
                tz0 < z_hi and tz1 > z_lo):
            return True
    return False


def lamp(x, y, ceil, value=380, sym=True):
    """Ceiling lamp: flush fixture at z = ceil on flat ceilings, or a non-solid pendant fixture
    hung below sloped/vaulted roofs so lamps never clip into angled ceilings.
    Note: direct lamp() calls do not skip low eaves or dodge trusses — use room_lamps() for
    automatic >= 96u headroom and truss-avoidance checks (a stderr note is emitted if a direct
    sloped pendant has < 96u headroom)."""
    pts = [(x, y)] + ([sym_pt(x, y)] if symmetric(sym) else [])
    for px, py in pts:
        z_box = ceil_height_at(px, py, ceil, half=16)
        if z_box < ceil - 1e-3:
            z_mount = int(math.floor(z_box))
            fl = _floor_below_rect((px - 16, py - 16, px + 16, py + 16), z_mount)
            if z_mount - fl < 96:
                print(f'note: lamp({px}, {py}, ceil={ceil}) under slope has only {z_mount - fl}u headroom (< 96); '
                      f'prefer room_lamps() or raise eave', file=sys.stderr)
            z_ctr = int(math.ceil(ceil_height_at(px, py, ceil, half=0)))
            PENDANT_LAMPS.append((px, py, z_mount, max(z_mount, z_ctr)))
            lights.append((px, py, z_mount - 40, round(value * LIGHT_SCALE)))
        else:
            fill((px - 16, py - 16, px + 16, py + 16), ceil - 8, ceil, 'lamp', sym=False)
            lights.append((px, py, ceil - 40, round(value * LIGHT_SCALE)))


def room_lamps(r, ceil, step=256, value=380, sym=True):
    x0, y0, x1, y1 = r
    nx = max(1, round((x1 - x0) / step))
    ny = max(1, round((y1 - y0) / step))
    placed = 0
    for a in range(nx):
        for b in range(ny):
            x = x0 + (x1 - x0) * (2 * a + 1) // (2 * nx)
            y = y0 + (y1 - y0) * (2 * b + 1) // (2 * ny)
            p = _lamp_spot(r, x // 16 * 16, y // 16 * 16, ceil)
            if p:
                lamp(p[0], p[1], ceil, value, sym)
                placed += 1
    if not placed:
        print(f'note: room_lamps({r}, ceil={ceil}) placed 0 lamps (no non-sky ceiling spot found)', file=sys.stderr)


def _lamp_spot(r, x, y, ceil, reach=160):
    """Nearest spot to (x, y) inside r where a ceiling lamp's box and its light are both in air
    (call room_lamps after the room's pillars, baffles, sloped ceilings, and trusses).
    None if nothing within reach."""
    def clear(px, py):
        if not (r[0] + 16 <= px <= r[2] - 16 and r[1] + 16 <= py <= r[3] - 16):
            return False
        z_eff = ceil_height_at(px, py, ceil, half=16)
        z_mount = int(math.floor(z_eff)) if z_eff < ceil - 1e-3 else ceil
        if _truss_hits(px, py, z_mount - 48, z_mount, half=16):
            return False
        for qx in (px - 16, px):
            for qy in (py - 16, py):
                i, j = (qx - XMIN) // C, (qy - YMIN) // C
                # Require an actual non-sky solid ceiling right at z == ceil (rejects both flush
                # and recessed sky oculi / taller openings).
                if not any(a == ceil and m != 'sky' for a, b, m in cols[i][j]):
                    return False
                # No solid (except sloped-ceiling stand-in above z_mount) in [z_mount - 48, z_mount]
                for a, b, m in cols[i][j]:
                    if m == 'ceil_slope' and a >= z_mount - 1:
                        continue
                    if a < z_mount and b > z_mount - 48:
                        return False
                # Beneath sloped roofs, keep lamps at least 96u above the floor underneath
                if z_mount < ceil:
                    fl_below = [b for a, b, m in cols[i][j] if b <= z_mount - 48]
                    if not fl_below or z_mount - max(fl_below) < 96:
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
        terrace(rot(r), h, _side_rot(side), z0, sym=False)
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
        pyramid(rot(r), h, tuple(_side_rot(s) for s in sides), z0, sym=False)
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


def _add_prism(pts, z0, z1, kind=None, sym=True, meta=None):
    """Internal prism helper storing exact 4-tuple in PRISMS and parallel metadata in PRISM_META."""
    pts = [tuple(p) for p in pts]
    area = sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1] for k in range(len(pts)))
    assert area > 0, f'prism {pts}: points must be counter-clockwise'
    m0 = dict(meta or {})
    copies = [(pts, m0)]
    if symmetric(sym):
        assert not m0.get('edge_uvs'), 'edge_uvs callers must emit symmetric copies explicitly'
        q = [sym_pt(x, y) for x, y in pts]
        m1 = dict(m0)
        if m1.get('group') is not None:
            m1['group'] = _next_group()
        copies.append((q if SYM == 'rotate' else q[::-1], m1))
    for P, mp in copies:
        PRISMS.append((P, z0, z1, kind))
        PRISM_META.append(mp)
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
                _fill_air(i, j, z0, z1, m)


def prism(points, z0, z1, kind=None, sym=True, wrap_u=False, fit_u=False, u_period=None):
    """Solid vertical prism on a convex footprint (points counter-clockwise, seen from above): a
    diagonal wall, a chamfered corner, an octagonal pillar, a wedge. kind None: each face is banded
    like the room it looks into (kickplate, strip, cornice), with its texture running along the angled
    face (Valve 220 axes, so nothing stretches); other kinds ('pillar', ...) take that kind's textures.
    wrap_u=True wraps U continuously around consecutive faces instead of resetting at each vertex;
    fit_u=True gently scales U so a closed perimeter lands on an integer multiple of u_period.
    The grid gets a stand-in for the checks: in every cell the prism overlaps, the air in [z0, z1]
    becomes mat 'diag' (solid to the checks, never written - the prism brush covers it; no lamp or
    band lands on a face hidden inside the prism). Named kinds keep their mat on cells wholly inside.
    Solid already in the cell stays, so a prism may start below the floor (z0 = BOT) safely.
    Call it AFTER the carves of the space it stands in: a later carve hollows its stand-in again."""
    meta = {'wrap_u': wrap_u, 'fit_u': fit_u, 'u_period': u_period} if (wrap_u or fit_u) else {}
    _add_prism(points, z0, z1, kind=kind, sym=sym, meta=meta)


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


# =========================================================================
# NON-BOX ARCHITECTURE: sloped/vaulted ceilings, arches/trusses/buttresses,
# curved walls/rotundas/cylinders, diagonal ramps
# =========================================================================
def _add_sloped_ceil_one(rr, axis, sg, z_lo, z_hi, top_z, tex, v_base):
    """Register one ceiling wedge (no sym copy) and populate its conservative 'ceil_slope' grid stand-in."""
    x0, y0, x1, y1 = rr
    run = (x1 - x0) if axis == 'x' else (y1 - y0)
    assert run > 0.01 and top_z > z_lo + 0.01 and z_hi >= z_lo - 1e-6 and top_z >= z_hi - 1e-6, (
        f'sloped_ceil {rr}: invalid bounds z_lo={z_lo}, z_hi={z_hi}, top_z={top_z}'
    )
    SLOPED_CEILS.append((rr, axis, sg, z_lo, z_hi, top_z, tex, v_base))
    u0, u1 = (x0, x1) if axis == 'x' else (y0, y1)
    i0 = max(0, int(math.floor((x0 - XMIN) / C)))
    i1 = min(NX, int(math.ceil((x1 - XMIN) / C)))
    j0 = max(0, int(math.floor((y0 - YMIN) / C)))
    j1 = min(NY, int(math.ceil((y1 - YMIN) / C)))
    for i in range(i0, i1):
        cx0, cx1 = XMIN + i * C, XMIN + (i + 1) * C
        if cx1 <= x0 + 1e-6 or cx0 >= x1 - 1e-6:
            continue
        for j in range(j0, j1):
            cy0, cy1 = YMIN + j * C, YMIN + (j + 1) * C
            if cy1 <= y0 + 1e-6 or cy0 >= y1 - 1e-6:
                continue
            ov0 = max(u0, cx0 if axis == 'x' else cy0)
            ov1 = min(u1, cx1 if axis == 'x' else cy1)
            if ov1 <= ov0 + 1e-6:
                continue
            if sg > 0:
                z_min = z_lo + (z_hi - z_lo) * (ov0 - u0) / run
            else:
                z_min = z_lo + (z_hi - z_lo) * (u1 - ov1) / run
            z_bot_cell = int(math.floor(z_min))
            z_top_cell = int(math.ceil(top_z))
            if z_bot_cell < z_top_cell:
                _fill_air(i, j, z_bot_cell, z_top_cell, 'ceil_slope')


def sloped_ceil(r, axis, z_lo, z_hi, rev=False, top_z=None, tex=None, sym=True):
    """Sloped ceiling wedge or slanted overhang over rect r: underside rises linearly from z_lo
    to z_hi along +axis ('x' or 'y'; rev=True: along -axis), solid up to top_z (default z_hi).
    Carve the room up to top_z first so the grid shell seals the void leak-free. Call before
    room_lamps() so ceiling lamps hang cleanly beneath the slope without clipping."""
    tz = z_hi if top_z is None else top_z
    sg = -1 if rev else 1
    _add_sloped_ceil_one(r, axis, sg, z_lo, z_hi, tz, tex, 0.0)
    if symmetric(sym):
        _add_sloped_ceil_one(rot(r), axis, _sym_axis_sign(axis, sg), z_lo, z_hi, tz, tex, 0.0)


def gable_ceil(r, axis, z_eave, z_ridge, ridge=None, top_z=None, tex=None, sym=True):
    """Pitched gable ceiling over rect r: slopes rise across `axis` ('x' or 'y') from z_eave at
    both side walls to z_ridge at `ridge` (default midpoint of r along axis). Carve the room up
    to top_z (default z_ridge) first, and call before room_lamps()."""
    x0, y0, x1, y1 = r
    u0, u1 = (x0, x1) if axis == 'x' else (y0, y1)
    mid = (u0 + u1) / 2 if ridge is None else ridge
    assert u0 < mid < u1, f'gable_ceil {r}: ridge {mid} must lie strictly inside ({u0}, {u1})'
    tz = z_ridge if top_z is None else top_z
    if axis == 'x':
        r_lo, r_hi = (x0, y0, mid, y1), (mid, y0, x1, y1)
    else:
        r_lo, r_hi = (x0, y0, x1, mid), (x0, mid, x1, y1)
    sloped_ceil(r_lo, axis, z_eave, z_ridge, rev=False, top_z=tz, tex=tex, sym=sym)
    sloped_ceil(r_hi, axis, z_eave, z_ridge, rev=True, top_z=tz, tex=tex, sym=sym)


def _emit_barrel_vault_one(rr, axis, z_spring, z_crown, segs, top_z, tex):
    x0, y0, x1, y1 = rr
    u0, u1 = (x0, x1) if axis == 'x' else (y0, y1)
    mid = (u0 + u1) / 2.0
    half = (u1 - u0) / 2.0
    h_arch = z_crown - z_spring
    pts = []
    for k in range(segs + 1):
        ang = math.pi * (1.0 - k / segs)
        uk = u0 if k == 0 else (u1 if k == segs else round(mid + half * math.cos(ang), 2))
        zk = z_spring if k in (0, segs) else round(z_spring + h_arch * math.sin(ang), 2)
        pts.append((uk, zk))
    arc = 0.0
    for k in range(segs):
        ua, za = pts[k]
        ub, zb = pts[k + 1]
        seg_r = (ua, y0, ub, y1) if axis == 'x' else (x0, ua, x1, ub)
        L = math.hypot(ub - ua, zb - za)
        if zb >= za:
            _add_sloped_ceil_one(seg_r, axis, 1, za, zb, top_z, tex, arc)
        else:
            # Descending facet: slope rises along -axis from zb (at ub) to za (at ua);
            # _out.py runs V continuously along +axis starting at v_base = arc at ua.
            _add_sloped_ceil_one(seg_r, axis, -1, zb, za, top_z, tex, arc)
        arc += L


def barrel_vault(r, axis, z_spring, z_crown, segs=6, top_z=None, tex=None, sym=True):
    """Segmented arched barrel vault over rect r spanning across `axis` ('x' or 'y'), springing
    from z_spring at both walls up to z_crown at the centre (segs >= 2 flat facets with continuous
    Valve 220 UV wrapping across the arch). Carve the room up to top_z (default z_crown) first."""
    assert segs >= 2 and z_crown > z_spring, f'barrel_vault {r}: need segs >= 2 and z_crown > z_spring'
    tz = z_crown if top_z is None else top_z
    _emit_barrel_vault_one(r, axis, z_spring, z_crown, segs, tz, tex)
    if symmetric(sym):
        _emit_barrel_vault_one(rot(r), axis, z_spring, z_crown, segs, tz, tex)


def arch_door(r, axis, z0, z1, th, arch_h=None, segs=6, trim=False, tex=None, sym=True):
    """Arched doorway over rect r from floor z0 to crown z1, arch spanning across `axis` ('x' or
    'y'; walk-through direction is perpendicular to axis). Carves the opening (door=True) and
    fills the upper spandrels with solid convex vault wedges, keeping jamb spring height >= z0 + 56
    so players never snag. trim=True adds thin non-solid (func_detail_illusionary) arch ring trim
    on both doorway faces (v4.1 bounded decorative collision policy)."""
    span = (r[2] - r[0]) if axis == 'x' else (r[3] - r[1])
    if arch_h is None:
        arch_h = min(span // 2, max(16, (z1 - z0) - 80))
    z_spring = z1 - arch_h
    assert arch_h > 0 and z_spring >= z0 + 56, (
        f'arch_door {r}: spring height {z_spring} < z0 + 56 ({z0 + 56}); raise z1 or lower arch_h'
    )
    carve(r, z0, z1, th, sym=sym, door=True, nocap=True, noarch=True)
    barrel_vault(r, axis, z_spring, z1, segs=segs, top_z=z1, tex=tex, sym=sym)
    if trim:
        for rr in _both(r, sym):
            ARCH_TRIMS.append((rr, axis, z_spring, z1, segs, 4, 10, EDGE_TEX))
            # Keep wall lamps clear of the arch trim mouths
            if axis == 'x':
                pipes.append((rr[0] - 12, rr[1] - 4, z_spring, rr[2] + 12, rr[3] + 4, z1 + 12))
            else:
                pipes.append((rr[0] - 4, rr[1] - 12, z_spring, rr[2] + 4, rr[3] + 12, z1 + 12))


def _floor_below_rect(rr, z_ref):
    """Highest solid floor below z_ref across rect rr (used for v4.1 overhead solidity policy)."""
    x0, y0, x1, y1 = rr
    i0 = max(0, int(math.floor((x0 - XMIN) / C)))
    i1 = min(NX, int(math.ceil((x1 - XMIN) / C)))
    j0 = max(0, int(math.floor((y0 - YMIN) / C)))
    j1 = min(NY, int(math.ceil((y1 - YMIN) / C)))
    best = BOT
    for i in range(i0, i1):
        for j in range(j0, j1):
            for _a, b, _m in cols[i][j]:
                if b < z_ref and b > best:
                    best = b
    return best


def truss(r, axis, z_bot, z_top=None, beam_h=16, knee=0, tie=True, tex=None, solid=None, sym=True):
    """Overhead ceiling beam or pitched king-post roof truss spanning across `axis` ('x' or 'y')
    over rect r (narrow side = beam thickness). When z_top > z_bot + beam_h, adds pitched rafters
    meeting at the apex (plus a king post when space allows); knee > 0 adds diagonal wall knee
    braces. solid=None follows the v4.1 bounded decorative policy: solid (worldspawn) when lowest
    underside is >= 96u above floor underneath, non-solid (func_detail_illusionary) otherwise."""
    zt = (z_bot + beam_h) if z_top is None else z_top
    assert zt >= z_bot + beam_h and beam_h >= 4 and knee >= 0, (
        f'truss {r}: need z_top >= z_bot + beam_h ({z_bot + beam_h}), beam_h >= 4, knee >= 0'
    )
    for rr in _both(r, sym):
        if solid is None:
            fl = _floor_below_rect(rr, z_bot)
            is_solid = (z_bot - knee) >= fl + 96
        else:
            is_solid = bool(solid)
        TRUSSES.append((rr, axis, z_bot, zt, beam_h, knee, tie, tex, is_solid))
        pipes.append((rr[0], rr[1], z_bot - knee, rr[2], rr[3], zt))
        if is_solid:
            x0, y0, x1, y1 = rr
            i0 = max(0, int(math.floor((x0 - XMIN) / C)))
            i1 = min(NX, int(math.ceil((x1 - XMIN) / C)))
            j0 = max(0, int(math.floor((y0 - YMIN) / C)))
            j1 = min(NY, int(math.ceil((y1 - YMIN) / C)))
            for i in range(i0, i1):
                for j in range(j0, j1):
                    _fill_air(i, j, int(z_bot), int(z_bot + beam_h), 'ceil_slope')


def buttress(r, side, z0, z1, top_depth=0, taper='top', tex=None, solid=True, sym=True):
    """Wall-mounted sloped buttress (taper='top', wide at bottom z0 tapering to top_depth at z1)
    or overhead cantilevered corbel (taper='bottom', wide at top z1 tapering to top_depth at z0)
    projecting inward from wall `side` ('-x', '+x', '-y', '+y') over rect r.
    Set solid=False along tight strafe corridors to emit as func_detail_illusionary (v4.1 policy)."""
    assert side in ('-x', '+x', '-y', '+y') and taper in ('top', 'bottom') and z1 > z0
    depth = (r[2] - r[0]) if side in ('-x', '+x') else (r[3] - r[1])
    assert 0 <= top_depth < depth, f'buttress {r}: top_depth {top_depth} must be in [0, {depth})'
    copies = [(r, side)]
    if symmetric(sym):
        copies.append((rot(r), _side_rot(side)))
    for rr, sd in copies:
        BUTTRESSES.append((rr, sd, z0, z1, top_depth, taper, tex, bool(solid)))
        pipes.append((rr[0], rr[1], z0, rr[2], rr[3], z1))
        if solid:
            x0, y0, x1, y1 = rr
            axis = 'x' if sd in ('-x', '+x') else 'y'
            sg = 1 if sd in ('-x', '-y') else -1
            wall_u = x0 if sd == '-x' else x1 if sd == '+x' else y0 if sd == '-y' else y1
            d_bot = depth if taper == 'top' else top_depth
            d_top = top_depth if taper == 'top' else depth
            dd = d_bot - d_top
            i0 = max(0, int(math.floor((x0 - XMIN) / C)))
            i1 = min(NX, int(math.ceil((x1 - XMIN) / C)))
            j0 = max(0, int(math.floor((y0 - YMIN) / C)))
            j1 = min(NY, int(math.ceil((y1 - YMIN) / C)))
            fl = _floor_below_rect(rr, z0 + 1)
            mat = 'ceil_slope' if z0 >= fl + 56 else 'diag'
            for i in range(i0, i1):
                cx0, cx1 = XMIN + i * C, XMIN + (i + 1) * C
                if cx1 <= x0 + 1e-6 or cx0 >= x1 - 1e-6:
                    continue
                for j in range(j0, j1):
                    cy0, cy1 = YMIN + j * C, YMIN + (j + 1) * C
                    if cy1 <= y0 + 1e-6 or cy0 >= y1 - 1e-6:
                        continue
                    # Conservative height interval of the sloped wedge inside this cell
                    c_near = ((cx0 - wall_u) if sg > 0 else (wall_u - cx1)) if axis == 'x' else (
                        (cy0 - wall_u) if sg > 0 else (wall_u - cy1))
                    c_near = max(0.0, c_near)
                    if c_near >= depth - 1e-6:
                        continue
                    if taper == 'top':
                        # Solid from z0 up to z where d(z) = c_near
                        t_hi = 1.0 if c_near <= d_top else (d_bot - c_near) / dd
                        za, zb = int(z0), int(math.ceil(z0 + (z1 - z0) * min(1.0, max(0.0, t_hi))))
                    else:
                        t_lo = 0.0 if c_near <= d_bot else (c_near - d_bot) / (-dd)
                        za, zb = int(math.floor(z0 + (z1 - z0) * min(1.0, max(0.0, t_lo)))), int(z1)
                    if zb > za:
                        _fill_air(i, j, za, zb, mat)


def cylinder(cx, cy, radius, z0, z1, sides=12, kind='pillar', angle0=None, parts=None,
             fit_u=True, u_period=None, sym=True):
    """Multi-sided circular column at (cx, cy) with radius `radius` and `sides` facets (default 12),
    with continuous Valve 220 UV wrapping around the circumference. When kind == 'pillar' and
    PILLAR_PARTS is enabled and z1 - z0 >= 96, splits into 32u base / shaft / 32u capital unless
    parts=False."""
    assert sides >= 3 and radius > 0 and z1 > z0, f'cylinder: invalid sides={sides}, radius={radius}, z=({z0},{z1})'
    a0 = (180.0 / sides) if angle0 is None else angle0
    pts = [
        (round(cx + radius * math.cos(math.radians(a0 + 360.0 * k / sides)), 2),
         round(cy + radius * math.sin(math.radians(a0 + 360.0 * k / sides)), 2))
        for k in range(sides)
    ]
    use_parts = (kind == 'pillar' and PILLAR_PARTS and z1 - z0 >= 96) if parts is None else bool(parts)
    per = u_period if u_period is not None else (64 if kind in ('pillar', 'pbase', 'pcap') else 128)
    if use_parts and z1 - z0 >= 96:
        segs = [(z0, z0 + 32, 'pbase'), (z0 + 32, z1 - 32, 'pillar'), (z1 - 32, z1, 'pcap')]
    else:
        segs = [(z0, z1, kind)]
    for za, zb, k_ in segs:
        prism(pts, za, zb, kind=k_, sym=sym, wrap_u=True, fit_u=fit_u, u_period=per)


def _emit_curved_wall_one(cx, cy, r_in, r_out, a0, a1, z0, z1, segs, kind, fit_u, u_period):
    gid = _next_group()
    in_pts, out_pts = [], []
    for k in range(segs + 1):
        ang = math.radians(a0 + (a1 - a0) * k / segs)
        ca, sa = math.cos(ang), math.sin(ang)
        in_pts.append((round(cx + r_in * ca, 2), round(cy + r_in * sa, 2)))
        out_pts.append((round(cx + r_out * ca, 2), round(cy + r_out * sa, 2)))
    in_lens = [math.hypot(in_pts[k + 1][0] - in_pts[k][0], in_pts[k + 1][1] - in_pts[k][1]) for k in range(segs)]
    out_lens = [math.hypot(out_pts[k + 1][0] - out_pts[k][0], out_pts[k + 1][1] - out_pts[k][1]) for k in range(segs)]
    p_in, p_out = sum(in_lens), sum(out_lens)
    su_in = (p_in / (max(1, round(p_in / u_period)) * u_period)) if fit_u and u_period else 1.0
    su_out = (p_out / (max(1, round(p_out / u_period)) * u_period)) if fit_u and u_period else 1.0
    s_in, s_out = 0.0, 0.0
    for k in range(segs):
        quad = [in_pts[k], out_pts[k], out_pts[k + 1], in_pts[k + 1]]
        # Edge 1: out_pts[k] -> out_pts[k+1] (CCW, outer arc)
        # Edge 3: in_pts[k+1] -> in_pts[k] (CW along quad, inner arc)
        edge_uvs = {
            1: (s_out, su_out),
            3: (p_in - (s_in + in_lens[k]), su_in),
        }
        _add_prism(quad, z0, z1, kind=kind, sym=False, meta={'group': gid, 'edge_uvs': edge_uvs})
        s_in += in_lens[k]
        s_out += out_lens[k]


def curved_wall(cx, cy, r_in, r_out, a0, a1, z0, z1, segs=8, kind=None, fit_u=False, u_period=128, sym=True):
    """Segmented curved wall arc centred at (cx, cy) with inner/outer radii r_in < r_out,
    sweeping counter-clockwise from a0 to a1 degrees, height z0..z1, with continuous Valve 220
    UV wrapping around both inner and outer arcs. Call after carve() of the room it sits in."""
    assert 0 < r_in < r_out and a1 > a0 and segs >= 1 and (a1 - a0) / segs < 150, (
        f'curved_wall: invalid r=({r_in},{r_out}), angles=({a0},{a1}), segs={segs}'
    )
    _emit_curved_wall_one(cx, cy, r_in, r_out, a0, a1, z0, z1, segs, kind, fit_u, u_period)
    if symmetric(sym):
        scx, scy = sym_pt(cx, cy)
        if SYM == 'rotate':
            _emit_curved_wall_one(scx, scy, r_in, r_out, a0 + 180.0, a1 + 180.0, z0, z1, segs, kind, fit_u, u_period)
        else:
            _emit_curved_wall_one(scx, scy, r_in, r_out, 180.0 - a1, 180.0 - a0, z0, z1, segs, kind, fit_u, u_period)


def _poly_area(pts):
    return 0.5 * sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1]
                     for k in range(len(pts)))


def _clip_poly_hp(poly, ax, ay, nx, ny, eps=1e-6):
    """Keep the half-plane (p - a) . n <= 0 of a convex CCW polygon."""
    if len(poly) < 3:
        return []
    out = []
    s = poly[-1]
    ds = (s[0] - ax) * nx + (s[1] - ay) * ny
    for e in poly:
        de = (e[0] - ax) * nx + (e[1] - ay) * ny
        if de <= eps:
            if ds > eps:
                t = ds / (ds - de)
                out.append((s[0] + t * (e[0] - s[0]), s[1] + t * (e[1] - s[1])))
            out.append(e)
        elif ds <= eps:
            t = ds / (ds - de)
            out.append((s[0] + t * (e[0] - s[0]), s[1] + t * (e[1] - s[1])))
        s, ds = e, de
    # Deduplicate near-identical consecutive vertices
    clean = []
    for p in out:
        if not clean or math.hypot(p[0] - clean[-1][0], p[1] - clean[-1][1]) > 1e-3:
            clean.append(p)
    if len(clean) >= 2 and math.hypot(clean[0][0] - clean[-1][0], clean[0][1] - clean[-1][1]) <= 1e-3:
        clean.pop()
    return clean if len(clean) >= 3 and _poly_area(clean) > 1.0 else []


def _ray_box_hit(cx, cy, dx, dy, x0, y0, x1, y1):
    """Intersection of ray (cx, cy) + t*(dx, dy) (t > 0) with box [x0, x1] x [y0, y1] -> (x, y, side_t)."""
    ts = []
    if dx > 1e-9:
        ts.append((x1 - cx) / dx)
    elif dx < -1e-9:
        ts.append((x0 - cx) / dx)
    if dy > 1e-9:
        ts.append((y1 - cy) / dy)
    elif dy < -1e-9:
        ts.append((y0 - cy) / dy)
    t = min(v for v in ts if v > 0)
    hx, hy = cx + t * dx, cy + t * dy
    hx = min(max(hx, x0), x1)
    hy = min(max(hy, y0), y1)
    return (round(hx, 2), round(hy, 2))


def _box_perim_param(x, y, x0, y0, x1, y1):
    """CCW perimeter parameter around box [x0, x1] x [y0, y1], starting at (x1, y0) going +y."""
    W, H = x1 - x0, y1 - y0
    eps = 0.05
    if abs(x - x1) <= eps and y > y0 + eps:
        return y - y0
    if abs(y - y1) <= eps and x < x1 - eps:
        return H + (x1 - x)
    if abs(x - x0) <= eps and y < y1 - eps:
        return H + W + (y1 - y)
    if abs(y - y0) <= eps and x > x0 + eps:
        return 2 * H + W + (x - x0)
    # Corners
    if abs(x - x1) <= eps and abs(y - y0) <= eps:
        return 0.0
    if abs(x - x1) <= eps and abs(y - y1) <= eps:
        return H
    if abs(x - x0) <= eps and abs(y - y1) <= eps:
        return H + W
    return 2 * H + W


def _opening_angle(spec):
    return {'+x': 0.0, '+y': 90.0, '-x': 180.0, '-y': 270.0}[spec] if isinstance(spec, str) else float(spec)


def _emit_rotunda_one(cx, cy, radius, z0, z1, th, sides, angle0, openings, sky, strip, fit_u, u_period):
    x0 = int(math.floor((cx - radius) / C)) * C
    x1 = int(math.ceil((cx + radius) / C)) * C
    y0 = int(math.floor((cy - radius) / C)) * C
    y1 = int(math.ceil((cy + radius) / C)) * C
    r_box = (x0, y0, x1, y1)
    carve(r_box, z0, z1, th, sky=sky, sym=False, strip=strip)
    a0 = (180.0 / sides) if angle0 is None else angle0
    v_pts = []
    w_pts = []
    for k in range(sides):
        ang = math.radians(a0 + 360.0 * k / sides)
        ca, sa = math.cos(ang), math.sin(ang)
        v_pts.append((round(cx + radius * ca, 2), round(cy + radius * sa, 2)))
        w_pts.append(_ray_box_hit(cx, cy, ca, sa, x0, y0, x1, y1))
    lens = [math.hypot(v_pts[(k + 1) % sides][0] - v_pts[k][0], v_pts[(k + 1) % sides][1] - v_pts[k][1])
            for k in range(sides)]
    perim = sum(lens)
    su = (perim / (max(1, round(perim / u_period)) * u_period)) if fit_u and u_period else 1.0
    W, H = x1 - x0, y1 - y0
    P_box = 2 * (W + H)
    corners = [((x1, y1), H), ((x0, y1), H + W), ((x0, y0), 2 * H + W), ((x1, y0), 0.0)]
    norm_ops = []
    for op in openings:
        if len(op) == 3:
            ang_spec, width, z_top = op
            z_lo_op = z0
        else:
            ang_spec, width, z_lo_op, z_top = op
        norm_ops.append((_opening_angle(ang_spec), float(width), z_lo_op, z_top))
    gid = _next_group()
    s_cur = 0.0
    for k in range(sides):
        kn = (k + 1) % sides
        vk, vkn = v_pts[k], v_pts[kn]
        wk, wkn = w_pts[k], w_pts[kn]
        pk = _box_perim_param(wk[0], wk[1], x0, y0, x1, y1)
        pkn = _box_perim_param(wkn[0], wkn[1], x0, y0, x1, y1)
        span_p = (pkn - pk) % P_box
        between = []
        for c_pt, cp in corners:
            dp = (cp - pk) % P_box
            if 0.05 < dp < span_p - 0.05:
                between.append((dp, c_pt))
        between.sort()
        raw_poly = [vk, wk] + [c_pt for _, c_pt in between] + [wkn, vkn]
        poly = []
        for p in raw_poly:
            if not poly or math.hypot(p[0] - poly[-1][0], p[1] - poly[-1][1]) > 1e-3:
                poly.append(p)
        if len(poly) >= 2 and math.hypot(poly[0][0] - poly[-1][0], poly[0][1] - poly[-1][1]) <= 1e-3:
            poly.pop()
        if len(poly) < 3 or _poly_area(poly) <= 1.0:
            s_cur += lens[k]
            continue
        # Inner wall line: vkn -> vk with continuous UV offset from vkn
        Lk = lens[k]
        ux, uy = (vk[0] - vkn[0]) / Lk, (vk[1] - vkn[1]) / Lk
        u_at_vkn = perim - (s_cur + Lk)
        pieces = [(poly, z0, z1)]
        for ang_deg, width, z_lo_op, z_top_op in norm_ops:
            rad = math.radians(ang_deg)
            dx, dy = math.cos(rad), math.sin(rad)
            px, py = -dy, dx
            hw = width / 2.0
            next_pieces = []
            for pp, za, zb in pieces:
                if zb <= z_lo_op or za >= z_top_op:
                    next_pieces.append((pp, za, zb))
                    continue
                back = _clip_poly_hp(pp, cx, cy, dx, dy)
                front = _clip_poly_hp(pp, cx, cy, -dx, -dy)
                if back:
                    next_pieces.append((back, za, zb))
                if front:
                    left = _clip_poly_hp(front, cx - px * hw, cy - py * hw, px, py)
                    right = _clip_poly_hp(front, cx + px * hw, cy + py * hw, -px, -py)
                    mid = _clip_poly_hp(
                        _clip_poly_hp(front, cx - px * hw, cy - py * hw, -px, -py),
                        cx + px * hw, cy + py * hw, px, py,
                    )
                    if left:
                        next_pieces.append((left, za, zb))
                    if right:
                        next_pieces.append((right, za, zb))
                    if mid:
                        if za < z_lo_op:
                            next_pieces.append((mid, za, min(zb, z_lo_op)))
                        if zb > z_top_op:
                            next_pieces.append((mid, max(za, z_top_op), zb))
            pieces = next_pieces
        for pp, za, zb in pieces:
            if zb <= za + 0.01:
                continue
            pp_r = [(round(a, 2), round(b, 2)) for a, b in pp]
            # Attach continuous inner-wall UV to any edge collinear with vkn -> vk
            edge_uvs = {}
            n_ = len(pp_r)
            for ek in range(n_):
                ea, eb = pp_r[ek], pp_r[(ek + 1) % n_]
                eL = math.hypot(eb[0] - ea[0], eb[1] - ea[1])
                if eL < 1e-3:
                    continue
                edx, edy = (eb[0] - ea[0]) / eL, (eb[1] - ea[1]) / eL
                if edx * ux + edy * uy > 0.999:
                    # Signed perpendicular distance from ea to line vkn -> vk
                    perp_d = abs((ea[0] - vkn[0]) * (-uy) + (ea[1] - vkn[1]) * ux)
                    if perp_d < 0.2:
                        t_along = (ea[0] - vkn[0]) * ux + (ea[1] - vkn[1]) * uy
                        edge_uvs[ek] = (u_at_vkn + t_along, su)
            _add_prism(pp_r, za, zb, kind=None, sym=False, meta={'group': gid, 'edge_uvs': edge_uvs})
        s_cur += Lk
    return r_box


def rotunda(cx, cy, radius, z0, z1, th, sides=12, angle0=None, openings=(), sky=False, strip=None,
            fit_u=True, u_period=128, sym=True):
    """Leak-safe circular / multi-sided room centred at (cx, cy) with inner radius `radius`, floor
    z0, ceiling z1, theme th, and `sides` faceted walls with continuous Valve 220 UV wrapping.
    Carves the enclosing 16-grid box and tiles the outer spandrels with exact disjoint convex
    perimeter wedges so nothing leaks or creates hollow cavities behind the curved wall.
    `openings`: iterable of (side_or_angle, width, z_top) or (side_or_angle, width, z_lo, z_top)
    doorway cuts through the curved wall (e.g. ('+y', 128, 160)); returns the carved bounding box."""
    assert sides >= 4 and radius >= 32 and z1 > z0
    r_box = _emit_rotunda_one(cx, cy, radius, z0, z1, th, sides, angle0, openings, sky, strip, fit_u, u_period)
    if symmetric(sym):
        scx, scy = sym_pt(cx, cy)
        s_ops = []
        for op in openings:
            a_ = op[0]
            sa_ = _side_rot(a_) if isinstance(a_, str) else sym_ang(float(a_))
            s_ops.append((sa_, *op[1:]))
        sa0 = None if angle0 is None else (
            (angle0 + 180.0) % 360.0 if SYM == 'rotate' else (180.0 - angle0) % 360.0
        )
        _emit_rotunda_one(scx, scy, radius, z0, z1, th, sides, sa0, s_ops, sky, strip, fit_u, u_period)
    return r_box


def diag_ramp(x0, y0, x1, y1, width, z0, z1, base=None, thick=None, sym=True):
    """Diagonal / non-axial ramp rising linearly from low centre (x0, y0, z0) to high centre
    (x1, y1, z1) with perpendicular width `width`. Walkable up to 45 degrees (0 < rise <= run);
    15-35 degrees plays best. Solid down to `base` (default z0), or a sloped elevated slab of
    vertical thickness `thick` so players can pass underneath the high end. Writes a stepped grid
    stand-in ('ramp') for checks and a Valve 220 walking brush in the floor-minlight skin."""
    dx, dy = x1 - x0, y1 - y0
    run = math.hypot(dx, dy)
    rise = z1 - z0
    assert width >= 32 and 0 < rise <= run + 1e-6, (
        f'diag_ramp ({x0},{y0})->({x1},{y1}): rise {rise} over run {run:.1f} invalid or width {width} < 32'
    )
    copies = [(x0, y0, x1, y1)]
    if symmetric(sym):
        sx0, sy0 = sym_pt(x0, y0)
        sx1, sy1 = sym_pt(x1, y1)
        copies.append((sx0, sy0, sx1, sy1))
    for ax0, ay0, ax1, ay1 in copies:
        DIAG_RAMPS.append((ax0, ay0, ax1, ay1, width, z0, z1, base, thick))
        ddx, ddy = ax1 - ax0, ay1 - ay0
        L = math.hypot(ddx, ddy)
        fx, fy = ddx / L, ddy / L
        lx, ly = -fy, fx
        hw = width / 2.0
        P = [
            (ax0 - lx * hw, ay0 - ly * hw),
            (ax1 - lx * hw, ay1 - ly * hw),
            (ax1 + lx * hw, ay1 + ly * hw),
            (ax0 + lx * hw, ay0 + ly * hw),
        ]
        xs, ys = [p[0] for p in P], [p[1] for p in P]
        z_base = z0 if base is None else base
        i0 = max(0, int(math.floor((min(xs) - XMIN) / C)))
        i1 = min(NX, int(math.ceil((max(xs) - XMIN) / C)))
        j0 = max(0, int(math.floor((min(ys) - YMIN) / C)))
        j1 = min(NY, int(math.ceil((max(ys) - YMIN) / C)))
        for i in range(i0, i1):
            cx_ = XMIN + i * C + C / 2.0
            for j in range(j0, j1):
                cy_ = YMIN + j * C + C / 2.0
                if not _inside(P, cx_, cy_):
                    continue
                t = max(0.0, min(L, (cx_ - ax0) * fx + (cy_ - ay0) * fy))
                h = int(round(z0 + rise * t / L))
                zlo_c = max(z_base, h - thick) if thick is not None else z_base
                if h > zlo_c:
                    _fill_air(i, j, int(zlo_c), int(h), 'ramp')
