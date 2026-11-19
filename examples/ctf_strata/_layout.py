# =========================================================================
# ctf_strata - LAYOUT. Concept B, "Strata": two whole levels stacked one over the other.
#   LOWER HALLS (floor 0, ceiling 224) run underneath the whole way, base to base.
#   UPPER DECKS (floor 256) run on top of them. A 32-unit slab (224..256) separates the two.
#   MID ATRIUM: one tall room where the decks cross as bridges over the lower arena (Quad).
#   Each half has a WELL: a hole through the slab, a drop from the upper level (hook back up).
#   The FLAG sits on a mezzanine (128) between the levels: steps down to the base floor (0),
#   stairs up to the base balconies (256) that carry the decks.
# SYM = 'rotate': blue (team 2) is the x > 0 half, written here; red is its 180-degree copy.
# =========================================================================

for _t in ('atrium', 'lower', 'deck', 'deck2', 'well', 'under'):
    zone(_t)                       # blockout colours in a fixed order (b2: keeps b1's colours, 'under' new)

# --- MID ATRIUM (shared, x -512..512) --------------------------------------------------------
carve((-512, -832, 512, 832), 0, 640, 'atrium', sym=False)
fill((-512, 416, 512, 640), 224, 256, None)                     # north bridge (+ the south one)
# b2: SIDE LANES. Each side of the atrium becomes a two-storey covered lane, walled off from the
# open arena by an arcade wall (0..384): the UNDERCROFT below the bridge, the BRIDGE above it.
# A carrier can now cross mid without entering the arena: undercroft + stair + bridge, or the bridge.
carve((-512, 448, 512, 640), 0, 224, 'under')                   # undercroft beneath each bridge
fill((-512, 416, 512, 448), 0, 384, None)                       # arcade wall: arena | undercroft + bridge
carve((320, 416, 448, 448), 0, 160, 'under', door=True)         # door beside each team's arena arch
carve((-256, 416, -128, 448), 0, 160, 'under', door=True)       # door toward the far end
carve((-128, 416, 128, 448), 256, 352, 'atrium', door=True)     # loggia: the bridge's one window (drop to the Quad)
for _r in _both((-512, 416, 512, 448), True):
    perches.append((_r, 384))                                   # the wall's top (384) is a hook perch, nothing more
stairs(0, 640, 512, 832, 'x', 0, 256)                           # undercroft up to the bridge along the outer wall; foot faces the alcove
fill((-64, -64, 64, 64), BOT, 32, None, sym=False)              # Quad dais
inlay((-64, -64, 64, 64), 32, 'sd_stand_q', sym=False)
pyramid((-64, -64, 64, 64), 32, ('-x', '+x', '-y', '+y'), sym=False)
# b3: the pit is open to the night sky (moonlight: SUN in _core). One timber beam spans it over
# the Quad, end wall to end wall: a hook anchor, caged lamps hang from it. Its top (496) is low
# enough that nobody standing on it can see down into the covered bridges.
oculus((-512, -832, 512, 832), 640, sym=False)
NOCAP.update((i, j, 640) for i, j in cells((-512, -832, 512, 832)))     # no cornice at the pit's rim
fill((-512, -16, 512, 16), 464, 496, 'beam', sym=False)
perches.append(((-512, -16, 512, 16), 496))
for _x in (-384, -128, 128, 384):
    lamp(_x, 0, 464, 700, sym=False)
# b3: hook ledges high on each end wall, over the arena arch (ammo, not armour)
perch((464, -128, 512, 128), 400)
TRIM_Z.update({'atrium': 224})                                  # the coal seam band at the slab's level
strip_ramp((-512, 640, 512, 832), 128, 384, 128)                # strip climbs with each atrium stair
room_lamps((-512, 448, 512, 640), 224, step=256, value=400)     # undercrofts
inlay((-512, 512, 512, 576), 0, 'sd_rails')                     # b3: rails down each undercroft
label(0, -260, 'ARENA 0'), label(0, 544, 'bridge 256', 256), label(-256, 736, 'stairs 0-256')
label(-128, 512, 'undercroft 0')

# --- LOWER HALL (blue half): a low pillared undercroft under the decks --------------------------
carve((576, -640, 1856, 640), 0, 224, 'lower')
carve((512, 192, 576, 384), 0, 160, 'lower', door=True)         # arches to the atrium - offset, so no
carve((512, -640, 576, -448), 0, 160, 'lower', door=True)       # straight line runs base to base
fill((704, 192, 768, 384), 0, 224, None)                         # baffles just inside each arch: no long
fill((704, -640, 768, -448), 0, 224, None)                       # line from the atrium into the hall
for _x, _y in ((768, -544), (1280, -544), (1024, -288), (1536, -288),   # columns in staggered rows
               (768, 224), (1280, 224), (1024, 480), (1536, 480)):
    fill((_x, _y, _x + 64, _y + 64), 0, 224, 'pillar')
fill((1472, -192, 1600, 192), 0, 224, None)                     # pier facing the base gate: no line base -> hall
room_lamps((576, -640, 1856, 640), 224, step=320, value=470)
label(1216, -560, 'LOWER HALL 0')

# --- UPPER DECKS (blue half): north and south decks on top of the lower hall -----------------------
carve((512, 256, 1920, 640), 256, 480, 'deck')                  # north deck
fill((896, 448, 960, 640), 256, 480, None)                       # staggered wall stubs: a slalom,
fill((1024, 256, 1088, 448), 256, 480, None)                     # not a corridor you can see down
room_lamps((512, 256, 1920, 640), 480, step=320, value=380)
carve((512, -640, 1920, -256), 256, 480, 'deck2')               # south deck
fill((768, -448, 832, -256), 256, 480, None)
fill((1024, -640, 1088, -448), 256, 480, None)
room_lamps((512, -640, 1920, -256), 480, step=320, value=380)
label(1216, 590, 'N DECK 256', 256), label(1216, -590, 'S DECK 256', 256)

# --- WELL ROOM: links the two decks; a hole through the slab drops into the lower hall ---------------
carve((1088, -256, 1408, 256), 256, 480, 'well')
carve((1184, -64, 1312, 64), 0, 480, 'well')                     # the well (drop down / hook up)
room_lamps((1088, -256, 1408, 256), 480, step=256, value=380)
TRIM_Z.update({'well': 224})                                    # seam round the well shaft
label(1248, 160, 'WELL ROOM 256', 256), label(1248, -130, 'well')

# --- BASE (blue): a tall hall; balconies at 256 carry the decks in; the flag on a 128 mezzanine ----
carve((1856, -192, 1920, 192), 0, 192, 'lower', door=True)       # base gate from the lower hall
carve_pair((1920, -640, 2752, 640), 0, 576, 'blue', 'red')
fill((1920, 384, 2752, 640), BOT, 256, None)                     # north balcony (256)
fill((1920, -640, 2752, -384), BOT, 256, None)                   # south balcony (256)
fill((2496, -128, 2752, 128), BOT, 128, None)                    # flag mezzanine (128)
terrace((2496, -128, 2752, 128), 128, '-x')                      # broad steps down to the base floor
stairs(2496, 128, 2752, 384, 'y', 128, 256)                      # up to the north balcony
stairs(2496, -384, 2752, -128, 'y', 128, 256, rev=True)          # up to the south balcony
fill((2560, -64, 2688, 64), 128, 144, 'stand_b', sym=False)      # flag stands: agate slices
fill(rot((2560, -64, 2688, 64)), 128, 144, 'stand_r', sym=False)
perch((2704, -96, 2752, 96), 416)                               # b3: hook ledge above the flag
TRIM_Z.update({'blue': 224, 'red': 224})
strip_ramp((1920, -640, 2752, 640), 128, 384, 128)              # strip at floor + 128: mezzanine, stairs, balconies
room_lamps((1920, -640, 2752, 640), 576, step=320, value=660)
label(2200, 0, 'BASE 0'), label(2336, 512, 'balcony 256', 256), label(2624, -230, 'flag 128', 128)

# --- team starts (8 per base; red = rotated copy)
for _x, _y, _z, _a in ((2016, 256, 0, 180), (2016, -256, 0, 180), (2272, 320, 0, 180), (2272, -320, 0, 180),
                       (2048, 512, 256, 180), (2048, -512, 256, 180), (2496, 512, 256, 180), (2496, -512, 256, 180)):
    team_spawn(_x, _y, _z, _a)

# --- respawns (24 = 12 rotated pairs): DM respawns and rune points, chosen by pick_spawns_sym.py -
# no two (or their rotated copies) see each other; none within 448 of a flag
for x, y, z, a, lab in (
    (608, 288, 256, 180, 'deck'),
    (1792, 576, 256, 0, 'deck'),
    (1952, 352, 0, 270, 'blue'),
    (1696, -32, 0, 0, 'lower'),
    (1376, 0, 256, 225, 'well'),
    (1888, -608, 256, 0, 'deck2'),
    (864, -448, 256, 0, 'deck2'),
    (1312, -576, 0, 45, 'deck2'),
    (608, 480, 0, 270, 'deck'),
    (1568, 608, 0, 180, 'deck'),
    (1504, 224, 0, 225, 'lower'),
    (1280, -224, 0, 180, 'well'),
):
    spawn(x, y, z, a, lab)

# --- b4: WHICH WAY IS WHICH -------------------------------------------------------------------
# 1. Every strip bulb and wall lamp is team-coloured by half (split_halves): blue in x > 0, red in x < 0.
# 2. Painted mine signs at every junction, luminous paint. A sign on a wall running along the map
#    points both ways ('< RED | BLUE >' as you face it); a sign on a wall across the route names the
#    base that lies that way. The rotated copy of each sign is the mirror reading for the red half.
RB, BR = 'sd_sign_rb', 'sd_sign_br'          # facing +y (north walls): RB; facing -y (south walls): BR
for r, z, t, tc in [
        ((928, 636, 1120, 640), 64, RB, BR),       # lower hall, north wall
        ((1248, -640, 1440, -636), 64, BR, RB),    # lower hall, south wall
        ((96, 448, 288, 452), 64, BR, RB),         # undercroft (north), near the blue end
        ((-480, 828, -288, 832), 64, RB, BR),      # pit alcove, at the foot of the stair
        ((576, 636, 768, 640), 320, RB, BR),       # north deck, pit end
        ((1248, 636, 1440, 640), 320, RB, BR),     # north deck, by the RL (b6: moved off the base end)
        ((576, -640, 768, -636), 320, BR, RB),     # south deck, pit end
        ((1248, -640, 1440, -636), 320, BR, RB),   # south deck, by the SNG (b6: moved off the base end)
        ((160, 448, 352, 452), 296, BR, RB)]:      # bridge parapet: one per bridge (b6)
    panel(r, z, z + 32, t, tc, 192)
# b6: fewer signs - none where the base, a big pit board or another sign already says it.
# b5: a one-name tag only ever names its own half's team, so it always points toward that half's
# flag (no 'RED' tags in the blue half, no 'BLUE' in the red); the two-ended signs show both ways.
for r, z, t, tc in [
        ((1468, -64, 1472, 64), 64, 'sd_tag_b', 'sd_tag_r'),     # the pier, facing up the hall
        ((1404, -64, 1408, 64), 320, 'sd_tag_b', 'sd_tag_r')]:   # well room, east wall
    panel(r, z, z + 32, t, tc, 128)
panel((508, -96, 512, 96), 256, 352, 'sd_board_b', 'sd_board_r', 128)   # pit end walls: the big boards
split_halves(('atrium', 'under', 'lower', 'deck', 'deck2', 'well'))
