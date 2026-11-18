"""ctf_bastion - Capture the Flag map generator for QuakeWorld / KTX (8-12 players, 16 spawns).

Symmetric by 180-degree rotation: the blue (team2) half is written out, red (team1) is its
rotated copy. A tall mid hall with the Quad, three routes to each base (high balcony route,
main corridor, low undercroft), a tall base hall and a flag room with a gallery.
Same grid / detail / output machinery as relay.
"""
import json
import math
import sys

NAME = 'ctf_bastion_b19'
LIGHT_SCALE = 0.52
C = 16                      # grid cell size (units)
XMIN, XMAX = -2432, 2432
YMIN, YMAX = -960, 960
BOT, TOP = -256, 768
NX, NY = (XMAX - XMIN) // C, (YMAX - YMIN) // C

# --- textures: b1 borrows ca_crucible's set as layout placeholders -------
ZONE_OF = {'mid': 'mid', 'blue': 'bh', 'red': 'rh', 'blueflag': 'bk', 'redflag': 'rk',
           'corridor_b': 'br', 'upper_b': 'br', 'side_b': 'br', 'under_b': 'bl',
           'corridor_r': 'rr', 'upper_r': 'rr', 'side_r': 'rr', 'under_r': 'rl', 'side_m': 'mid'}
GLASS_Z = {}


def textures(kind, zone, role):
    """(top, bottom, side) texture names for a brush piece - fortress set (texgen_bastion.py)."""
    z = ZONE_OF.get(zone, 'mid')
    flr, ceil = f'bs_{z}_flr', f'bs_{z}_ceil'
    if zone == 'side_m':           # b14: the neutral side-route stretch is mostly stair - floor matches the treads
        flr = 'bs_tread'
    if kind == 'wall':
        side = {'wall': f'bs_{z}_wall', 'base': 'bs_base', 'strp': f'bs_{z}_cond',
                'trim': 'bs_trim', 'frame': f'bs_{z}_wall', 'glass': f'bs_{z}_wall'}[role]
        return flr, ceil, side
    return {
        'ledge': (flr, ceil, f'bs_{z}_wall'),
        'rail': ('bs_tread', ceil, 'bs_base'),
        'stair': ('bs_tread', ceil, 'bs_riser'),
        'flank': ('bs_tread', ceil, 'bs_riser'),
        'pillar': (('bs_pmid96',) * 3) if z == 'mid' else (('bs_pillar_b',) * 3) if z[0] == 'b'
                  else (('bs_pillar_r',) * 3) if z[0] == 'r' else ('bs_pillar',) * 3,
        'perch': (ceil, ceil, ceil),               # b18: slab edges in the same stone as top and underside          # b17: perch top = its coffered underside (square - any orientation)
        'stand_q': ('bs_quad', ceil, 'bs_riser'),
        'stand_b': ('bs_stand_b', ceil, 'bs_riser'),
        'stand_r': ('bs_stand_r', ceil, 'bs_riser'),
        'lamp': ('bs_lampbox', 'bs_light', 'bs_lampbox'),
    }[kind]


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
STEP_KICK = {f'{k}_{t}' for k in ('corridor', 'under', 'side') for t in 'brm'}
ZONE_FLOOR = {'mid': 0, 'blue': 0, 'red': 0, 'blueflag': 0, 'redflag': 0,
              **{f'{k}_{t}': z for k, z in (('corridor', 0), ('upper', 192), ('side', -128), ('under', -128)) for t in 'brm'}}
STRIPE_Z = {'mid': 128, 'blue': 128, 'red': 128, 'blueflag': 128, 'redflag': 128,
            **{f'{k}_{t}': z for k, z in (('corridor', 128), ('upper', 288), ('side', 288), ('under', 16)) for t in 'brm'}}
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


pillar_rects = []   # b18: whole column footprints - faces are textured from the column's corner


def fill(r, z0, z1, mat, sym=True):
    if mat == 'ledge':
        mat = None            # b13: platforms are plain structure, banded like any wall
    for rr in _both(r, sym):
        if mat == 'pillar':
            pillar_rects.append((*rr, z1))
        for i, j in cells(rr):
            col = _subtract(cols[i][j], z0, z1)
            col.append([z0, z1, mat])
            col.sort()
            cols[i][j] = col


def stairs(x0, y0, x1, y1, axis, z_from, z_to, run=32, sym=True, base=None, rev=False, flank=None):
    """Steps of 16 rising along +axis ('x' or 'y') from z_from+16 to z_to (rev: rising along -axis)."""
    n = (z_to - z_from) // 16
    length = (x1 - x0) if axis == 'x' else (y1 - y0)
    assert length == n * run, (length, n, run)
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
        lights.append((px, py, ceil - 24, round(value * LIGHT_SCALE)))


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


def terrace(r, h, side, z0=0):
    """Plinth steps down from a raised edge of height h on one side (walk up from anywhere along it)."""
    for cc in range(1, (h - z0) // 16):
        s = 16 * cc
        rr = {'-x': (r[0] - s, r[1], r[0] - s + 16, r[3]), '+x': (r[2] + s - 16, r[1], r[2] + s, r[3]),
              '-y': (r[0], r[1] - s, r[2], r[1] - s + 16), '+y': (r[0], r[3] + s - 16, r[2], r[3] + s)}[side]
        fill(rr, BOT, h - s - 16, None, sym=False)
        fill(rr, h - s - 16, h - s, 'flank', sym=False)


def pyramid(r, h, sides, z0=0):
    """Broad steps down from a raised block on several sides; corners wrap, so each level
    is one continuous L-shaped step (walk up from anywhere along those sides)."""
    n = (h - z0) // 16
    x0, y0, x1, y1 = r
    ext = 16 * (n - 1)
    X0, X1 = x0 - (ext if '-x' in sides else 0), x1 + (ext if '+x' in sides else 0)
    Y0, Y1 = y0 - (ext if '-y' in sides else 0), y1 + (ext if '+y' in sides else 0)
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

pipes = []        # (no pipe runs in relay; the lamp placer keeps clear of them)


# --- CTF helpers -----------------------------------------------------------------------------
SIDE_ROT = {'-x': '+x', '+x': '-x', '-y': '+y', '+y': '-y'}
team_spawns = []   # (x, y, floor_z, angle, team)  team 2 = blue (written), team 1 = red (rotated copy)


def team_spawn(x, y, z, angle):
    team_spawns.append((x, y, z, angle, 2))
    team_spawns.append((-x, -y, z, (angle + 180) % 360, 1))


def terrace2(r, h, side, z0=0):
    terrace(r, h, side, z0)
    terrace(rot(r), h, SIDE_ROT[side], z0)


def pyramid2(r, h, sides, z0=0, both=True):
    pyramid(r, h, sides, z0)
    if both:
        pyramid(rot(r), h, tuple(SIDE_ROT[s] for s in sides), z0)


def carve_team(r, z0, z1, th_blue, th_red, **kw):
    """Base pieces: blue theme on the written half, red theme on the rotated copy."""
    carve(r, z0, z1, th_blue, sym=False, **kw)
    carve(rot(r), z0, z1, th_red, sym=False, **kw)


perches = []       # (rect, floor z): hook-only ledges (written half + rotation)


def perch(r, z, depth=16):
    """A slab ledge high on a wall, floor at z, air underneath: reached with the grappling hook."""
    fill(r, z - depth, z, 'perch')
    perches.append((r, z))
    perches.append((rot(r), z))


def strip_z(th, f):
    """b15: side routes - the light strip runs level at the undercroft's height (floor + 144) from
    the low end, climbs with the stairs, and levels off at the high route's height (288)."""
    if th in ('side_b', 'side_r', 'side_m'):
        return min(f + 144, 288)
    return STRIPE_Z[th]
