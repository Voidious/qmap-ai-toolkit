"""ca_lyceum - Clan Arena / TDM map generator for QuakeWorld (8-12 players, 16 spawns).

Asymmetric hub and satellites (from the demo study: dm6's structure, Agora's height and pace):
a hub hall with a balcony and grand stair, a tall tower room with a high stand reached by a
broad stair and a hidden climb from the balcony, a sunken pit room, and an open flat duel hall,
linked in loops (hub-tower-pit, hub-pit-duel) with a low passage giving the pit a purpose.
Same grid / detail / output machinery as cistern and bastion.
"""
import json
import math
import sys

NAME = 'ca_lyceum_b5'
LIGHT_SCALE = 0.42     # b3: pale marble reflects more - lamps turned down to keep the map as dark as the others
C = 16                      # grid cell size (units)
XMIN, XMAX = -1152, 1152
YMIN, YMAX = -1088, 832
BOT, TOP = -160, 640
NX, NY = (XMAX - XMIN) // C, (YMAX - YMIN) // C

# --- textures: b3 'lamplit academy' set (texgen_lyceum.py) ---------------
ZONE_OF = {'hub': 'atr', 'tower': 'obs', 'pit': 'amp', 'duel': 'pal', 'walk': 'stoa', 'corr': 'brk',
           'low': 'brk', 'gal': 'gal'}   # b4: the gallery over the duel hall gets the black fresco set
ZONE_OF['walk'] = 'cli'        # b5: the climb (and the two small doorways off the balcony) match it
GLASS_Z = {}


def textures(kind, zone, role):
    """(top, bottom, side) texture names for a brush piece."""
    z = ZONE_OF.get(zone, 'atr')
    flr, ceil = f'ly_{z}_flr', f'ly_{z}_ceil'
    if kind == 'wall':
        side = {'wall': f'ly_{z}_wall', 'base': 'ly_base', 'strp': f'ly_{z}_strp',
                'trim': 'ly_trim', 'frame': f'ly_{z}_wall', 'glass': f'ly_{z}_wall'}[role]
        return flr, ceil, side
    return {
        'ledge': (flr, ceil, f'ly_{z}_wall'),
        'rail': ('ly_tread', ceil, 'ly_base'),
        'stair': ('ly_tread', ceil, 'ly_riser'),
        'flank': ('ly_tread', ceil, 'ly_riser'),
        'bridge': ('ly_tread', ceil, 'ly_trim'),
        'pillar': ('ly_pillar', 'ly_pillar', 'ly_pillar'),
        'pcap': ('ly_pcap', 'ly_pcap', 'ly_pcap'),
        'pbase': ('ly_pbase', 'ly_pbase', 'ly_pbase'),
        'crate': ('ly_cratetop', 'ly_cratetop', 'ly_crate'),
        'machine': ('ly_cratetop', 'ly_cratetop', 'ly_crate'),
        'pad': ('ly_medal', ceil, 'ly_trim'),
        'jpad': ('ly_medal', ceil, 'ly_trim'),
        'lamp': ('ly_lampbox', 'ly_light', 'ly_lampbox'),
        'sky': ('sky_lyceum', 'sky_lyceum', 'sky_lyceum'),
    }[kind]


# b3: inlaid floor / ceiling pieces, textured from their own corner: (x0, y0, x1, y1, z, texture)
FLOOR_DECALS = []
CEIL_DECALS = []
# b5: floor patterns centred on their room: texture offset (s, t) per floor texture
FLOOR_OFFSET = {'ly_pal_flr': (48, 80), 'ly_gal_flr': (48, 80)}


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


def rot(r):
    x0, y0, x1, y1 = r
    return (-x1, -y1, -x0, -y0)


def _both(r, sym):
    return [r, rot(r)] if sym else [r]


doors = []         # (rect, z0, z1) openings that get a framed jamb and lintel
rooms = {}         # (i, j) -> [(z0, z1)] carve extents, to find a room's real floor under stairs
# Wall textures are aligned to each zone's main floor, so panels line up across the whole zone.
# b13: extra string-course trim (absolute z of its bottom) carried through tall air
TRIM_Z = {}
STEP_KICK = set()        # b3: dado stays level beside stairs (the stepped dado was rejected on bastion)
ZONE_FLOOR = {'hub': 0, 'tower': 0, 'pit': -96, 'duel': 0, 'walk': 160, 'corr': 0, 'low': -96, 'gal': 160}
STRIPE_Z = {'hub': 96, 'tower': 160, 'pit': 64, 'duel': 112, 'walk': 10 ** 6, 'corr': 10 ** 6, 'low': 10 ** 6, 'gal': 10 ** 6}
NOCAP = set()      # (i, j, ceiling z): openings whose low ceiling gets no cornice (arcades)


def carve(r, z0, z1, th, sky=False, sym=True, door=False, nocap=False):
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


pillar_rects = []   # whole column footprints - faces textured from the column's corner and top


def fill(r, z0, z1, mat, sym=True):
    if mat == 'ledge':
        mat = None            # b13: platforms are plain structure, banded like any wall
    for rr in _both(r, sym):
        if mat == 'pillar':
            pillar_rects.append((*rr, z1))
        # b3: columns get a moulded base and a capital (same solid, split into three pieces)
        segs = ([[z0, z0 + 32, 'pbase'], [z0 + 32, z1 - 32, 'pillar'], [z1 - 32, z1, 'pcap']]
                if mat == 'pillar' and z1 - z0 >= 96 else [[z0, z1, mat]])
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
    if not sym:
        lo = ('-' if not rev else '+') + axis
        stair_feet.append(({'-x': (x0 - 32, y0, x0, y1), '+x': (x1, y0, x1 + 32, y1),
                            '-y': (x0, y0 - 32, x1, y0), '+y': (x0, y1, x1, y1 + 32)}[lo], z_from))
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


lights = []        # (x, y, z, value)
spawns = []        # (x, y, floor_z, angle, label)
labels = []        # (x, y, text) for the plan


def lamp(x, y, ceil, value=380, sym=True):
    pts = [(x, y)] + ([(-x, -y)] if sym else [])
    for px, py in pts:
        fill((px - 16, py - 16, px + 16, py + 16), ceil - 8, ceil, 'lamp', sym=False)
        lights.append((px, py, ceil - 40, round(value * LIGHT_SCALE)))   # b3: 40 below - no glare pool on the ceiling


def room_lamps(r, ceil, step=256, value=380, sym=True):
    x0, y0, x1, y1 = r
    nx = max(1, round((x1 - x0) / step))
    ny = max(1, round((y1 - y0) / step))
    for a in range(nx):
        for b in range(ny):
            x = x0 + (x1 - x0) * (2 * a + 1) // (2 * nx)
            y = y0 + (y1 - y0) * (2 * b + 1) // (2 * ny)
            lamp(x // 16 * 16, y // 16 * 16, ceil, value, sym)


def spawn(x, y, z, angle, label, sym=True):
    spawns.append((x, y, z, angle, label))
    if sym:
        spawns.append((-x, -y, z, (angle + 180) % 360, label + "'"))




liquids = []       # (rect, z0, z1, texture): lava etc., written as world brushes, not in the grid
teleports = []     # (pad rect, pad top z, dest x, dest y, dest floor z, dest angle)


def lava(r, z0, z1, sym=True):
    for rr in _both(r, sym):
        liquids.append((rr, z0, z1, '*lava_cr'))


def teleporter(r, z, dx, dy, dz, ang, sym=True):
    teleports.append((r, z, dx, dy, dz, ang))
    if sym:
        teleports.append((rot(r), z, -dx, -dy, dz, (ang + 180) % 360))


decals = []        # (x0, y0, z0, x1, y1, z1, texture): non-solid emblem panels (func_detail_illusionary)


def sigil(r, z0, z1, tex_e, tex_w):
    """Emblem panel on the east half (tex_e) and its rotated copy on the west half (tex_w)."""
    decals.append((*r[:2], z0, *r[2:], z1, tex_e))
    rr = rot(r)
    decals.append((*rr[:2], z0, *rr[2:], z1, tex_w))


pushes = []        # (trigger rect, pad top z, dest x, dest y, dest floor z, speed, angles)


def jumppad(r, z, dx, dy, dz, speed, angles, tex='pad'):
    """trigger_push REPLACES velocity while touched, so the push is angled: it carries you forward."""
    fill(r, z - 8, z, tex, sym=False)
    pushes.append((r, z, dx, dy, dz, speed, angles))


stair_feet = []     # (rect, z): the strip in front of each stair's bottom step must be open floor


def terrace(r, h, side, z0=0):
    """Plinth steps down from a raised edge of height h on one side (walk up from anywhere along it)."""
    for cc in range(1, (h - z0) // 16):
        s = 16 * cc
        rr = {'-x': (r[0] - s, r[1], r[0] - s + 16, r[3]), '+x': (r[2] + s - 16, r[1], r[2] + s, r[3]),
              '-y': (r[0], r[1] - s, r[2], r[1] - s + 16), '+y': (r[0], r[3] + s - 16, r[2], r[3] + s)}[side]
        fill(rr, BOT, h - s - 16, None, sym=False)
        fill(rr, h - s - 16, h - s, 'flank', sym=False)
    e = 16 * ((h - z0) // 16 - 1)
    stair_feet.append(({'-x': (r[0] - e - 32, r[1], r[0] - e, r[3]), '+x': (r[2] + e, r[1], r[2] + e + 32, r[3]),
                        '-y': (r[0], r[1] - e - 32, r[2], r[1] - e), '+y': (r[0], r[3] + e, r[2], r[3] + e + 32)}[side], z0))


def pyramid(r, h, sides, z0=0):
    """Broad steps down from a raised block on several sides; corners wrap, so each level
    is one continuous L-shaped step (walk up from anywhere along those sides)."""
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


def water(r, z0, z1):
    liquids.append((r, z0, z1, '*water_cs'))

pipes = []        # (x0, y0, z0, x1, y1, z1): non-solid bronze pipes (detail only, no collision)


def pipe(x0, y0, z0, x1, y1, z1):
    pipes.append((x0, y0, z0, x1, y1, z1))


def oculus(r, z):
    """b3: the ceiling over r (whose underside is at z) becomes sky - texture only, same solid."""
    for i, j in cells(r):
        for sg in cols[i][j]:
            if sg[0] == z:
                sg[2] = 'sky'
