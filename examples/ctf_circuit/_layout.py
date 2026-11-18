# =========================================================================
# LAYOUT - blue (team2, EAST) half written out; sym=True adds the red MIRROR copy (x -> -x)
#   low arc -128, main floor 0, high arc 192
# Three runs between the bases (a 'theta'): north arc (high), south arc (low), and the spine
# through the solid core and the mid chamber (shortest, most contested). The chamber also
# links the arcs: a drop from the north court, stairs up from the south court.
# =========================================================================

# --- Mid chamber: Quad on a dais, four columns to hook round ---------------------------------
carve((-448, -448, 448, 448), 0, 448, 'mid', sym=False)
fill((192, 192, 256, 256), 0, 448, 'pillar')                    # 4 columns (2 written + mirror)
fill((192, -256, 256, -192), 0, 448, 'pillar')
fill((-64, 64, 64, 256), 0, 448, 'pillar', sym=False)          # central column: breaks the spine-to-spine sightline
fill((-64, -224, 64, -96), BOT, 16, None, sym=False)            # Quad dais, south of the column
fill((-64, -224, 64, -96), 16, 32, 'stand_q', sym=False)
pyramid((-64, -224, 64, -96), 32, ('-x', '+x', '-y', '+y'))
# b2: a gilded cupola rises over the Quad (448 -> 576); lamps round it, light from within it
carve((-192, -352, 192, 32), 448, 576, 'mid', sym=False)
CEIL_DECALS.append((-192, -352, 192, 32, 576, 'dc_dome'))
for _x, _y in ((336, 336), (336, 112), (112, 336), (336, -112), (336, -336), (112, 112)):
    lamp(_x, _y, 448, 600)                                          # (+ mirror)
lights.append((0, -160, 520, 330))
for _x in (-128, 128):
    lights.append((_x, -160, 470, 240, 1.0))
labels += [(0, -150, 'MID\nCHAMBER 0')]
# drop from the north court (192) into the chamber - one way down, or the hook back up
carve((-128, 448, 128, 960), 0, 448, 'mid', sym=False)
lamp(0, 704, 448, 300, sym=False)
carve((-128, 960, 128, 1280), 192, 448, 'high_m', sym=False)               # ledge from the north court to the drop
# broad stairs up from the south court (-128) into the chamber
carve((-128, -960, 128, -448), -128, 320, 'mid', sym=False)
stairs(-128, -960, 128, -448, 'y', -128, 0, run=64, sym=False)
carve((-128, -1280, 128, -960), -128, 160, 'low_m', sym=False)             # passage from the south court
lamp(0, -704, 320, 300, sym=False)
labels += [(0, 704, 'drop'), (0, -704, 'stairs')]

# --- The spine: chamber <-> forecourt through the core. Offset lanes either side of a junction
#     room, so there is no straight sightline from the chamber to the base.
carve_team((448, 64, 896, 256), 0, 192, 'spoke_b', 'spoke_r')             # west leg (north lane)
carve_team((896, -320, 1376, 320), 0, 288, 'spoke_b', 'spoke_r')          # junction room
fill((1088, -32, 1184, 64), 0, 288, 'pillar')
carve_team((1376, -256, 1824, -64), 0, 192, 'spoke_b', 'spoke_r')         # east leg (south lane): no lane overlaps the next
room_lamps((896, -320, 1376, 320), 288, step=256, value=380)
lamp(672, 160, 192, 260)
lamp(1600, -160, 192, 260)
labels += [(1136, -220, 'SPINE 0')]

# --- NORTH ARC (high, 192) --------------------------------------------------------------------
# (the arc's rooms are staggered north-south, so there is no straight line along the arc)
carve((-704, 1280, 704, 1664), 192, 448, 'high_m', sym=False)              # north court (Mega)
fill((-288, 1440, -224, 1504), 192, 448, 'pillar', sym=False)
fill((224, 1440, 288, 1504), 192, 448, 'pillar', sym=False)
room_lamps((-704, 1280, 704, 1664), 448, step=320, value=500, sym=False)
carve_team((704, 1280, 896, 1408), 192, 448, 'high_b', 'high_r')         # dog-leg from the aqueduct landing
labels += [(0, 1350, 'N COURT 192')]
# aqueduct hall: a bridge at 192 spans it; the floor (0) runs underneath with an arch through
carve_team((704, 704, 1824, 1280), 0, 512, 'high_b', 'high_r')
fill((704, 704, 896, 1280), BOT, 192, None)                     # west landing (joins the north court)
terrace2((704, 704, 896, 960), 192, '+x')                       # split by the bridge
terrace2((704, 1088, 896, 1280), 192, '+x')
fill((1632, 704, 1824, 1280), BOT, 192, None)                   # east landing (joins the gatehouse)
terrace2((1632, 704, 1824, 960), 192, '-x')
terrace2((1632, 1088, 1824, 1280), 192, '-x')
fill((896, 960, 1632, 1088), BOT, 192, None)                    # the bridge
carve_team((1200, 960, 1328, 1088), 0, 128, 'high_b', 'high_r')  # arch under it
FLOOR_DECALS += [(896, 992, 1632, 1056, 192, 'dc_canal'), (-1632, 992, -896, 1056, 192, 'dc_canal')]   # b2: the qanat channel along the bridge
room_lamps((704, 704, 1824, 1280), 512, step=320, value=560)
labels += [(1264, 1190, 'AQUEDUCT 0\nbridge 192')]
# gatehouse (192): along the base's north side, from the forecourt stair to the rear stair
carve_team((1824, 768, 3232, 1152), 192, 448, 'high_b', 'high_r')
fill((2368, 768, 2432, 1024), 192, 448, None)                   # wall stubs, staggered: the gatehouse
fill((2848, 896, 2912, 1152), 192, 448, None)                   # becomes a dog-leg with no straight line through
room_lamps((1824, 768, 3232, 1152), 448, step=320, value=380)
labels += [(2640, 1060, 'GATEHOUSE 192')]

# --- SOUTH ARC (low, -128) --------------------------------------------------------------------
carve((-704, -1664, 704, -1280), -128, 160, 'low_m', sym=False)            # south court (RA)
fill((-288, -1504, -224, -1440), -128, 160, 'pillar', sym=False)
fill((224, -1504, 288, -1440), -128, 160, 'pillar', sym=False)
room_lamps((-704, -1664, 704, -1280), 160, step=320, value=420, sym=False)
carve_team((704, -1408, 896, -1280), -128, 160, 'low_b', 'low_r')        # dog-leg from the undercroft
labels += [(0, -1350, 'S COURT -128')]
carve_team((704, -1280, 1824, -704), -128, 192, 'low_b', 'low_r')         # undercroft
fill((1024, -1024, 1088, -960), -128, 192, 'pillar')
fill((1440, -960, 1504, -896), -128, 192, 'pillar')
room_lamps((704, -1280, 1824, -704), 192, step=320, value=330)
labels += [(1520, -770, 'UNDERCROFT -128')]
carve_team((1824, -1152, 3232, -768), -128, 128, 'low_b', 'low_r')       # cellar: the base's south side
fill((2368, -1024, 2432, -768), -128, 128, None)                # staggered wall stubs, as in the gatehouse
fill((2848, -1152, 2912, -896), -128, 128, None)
room_lamps((1824, -1152, 3232, -768), 128, step=320, value=280)
labels += [(2640, -1060, 'CELLAR -128')]

# --- BASE ---------------------------------------------------------------------------------------
# forecourt: the defence yard; the spine opens into its west wall; broad stairs up to the
# gatehouse at its north end and down to the cellar at its south end
carve_team((1824, -512, 2336, 384), 0, 448, 'blue', 'red')
carve_team((1824, 384, 2336, 768), 0, 448, 'blue', 'red')
stairs(1824, 384, 2336, 768, 'y', 0, 192)
carve_team((1824, -768, 2336, -512), -128, 448, 'blue', 'red')
stairs(1824, -768, 2336, -512, 'y', -128, 0)
room_lamps((1824, -768, 2336, 768), 448, step=320, value=560)
labels += [(2080, -200, 'FORECOURT 0')]
# flag hall: two doors from the forecourt, a back door behind the flag
carve_team((2400, -448, 3040, 448), 0, 384, 'blueflag', 'redflag')
carve_team((2336, 192, 2400, 384), 0, 160, 'blueflag', 'redflag', door=True)
carve_team((2336, -384, 2400, -192), 0, 160, 'blueflag', 'redflag', door=True)
carve_team((3040, -64, 3104, 64), 0, 128, 'blueflag', 'redflag', door=True)
fill((2784, -64, 2912, 64), BOT, 32, None, sym=False)            # flag stands (deep in the hall)
fill((2784, -64, 2912, 64), 32, 48, 'stand_b', sym=False)
fill(rot((2784, -64, 2912, 64)), BOT, 32, None, sym=False)
fill(rot((2784, -64, 2912, 64)), 32, 48, 'stand_r', sym=False)
pyramid2((2784, -64, 2912, 64), 48, ('-x', '+x', '-y', '+y'))
room_lamps((2400, -448, 3040, 448), 384, step=256, value=460)
labels += [(2720, -260, 'FLAG HALL')]
# rear passage: behind the flag hall, stairs up to the gatehouse (north) and down to the cellar (south)
carve_team((3104, -384, 3232, 384), 0, 192, 'blue', 'red')
carve_team((3104, 384, 3232, 768), 0, 384, 'blue', 'red')
stairs(3104, 384, 3232, 768, 'y', 0, 192)
carve_team((3104, -768, 3232, -384), -128, 192, 'blue', 'red')
stairs(3104, -640, 3232, -384, 'y', -128, 0)
room_lamps((3104, -384, 3232, 384), 192, step=320, value=260)
room_lamps((3104, 384, 3232, 768), 384, step=320, value=260)
room_lamps((3104, -768, 3232, -384), 192, step=320, value=260)
labels += [(3168, 0, 'rear')]

# --- b3: light strips follow the stairs between levels (base 128 <-> gatehouse 288 / cellar 16,
#     chamber 128 <-> south court 16), so the bands join up instead of stopping at the steps
strip_ramp((1824, 384, 2336, 768), 128, 288, 128)       # forecourt stair up to the gatehouse
strip_ramp((3104, 384, 3232, 768), 128, 288, 128)       # rear stair up to the gatehouse
# b5: forecourt stair down to the cellar - the undercroft opens beside its two lowest steps, so the
#     strip must already be at the undercroft's height (16) two steps up, where the undercroft's north
#     wall meets the stairwell (y = -704). It climbs at the stair slope from there and reaches the
#     forecourt's height (128) two steps PAST the top of the stairs, out on the forecourt walls.
strip_ramp_y((1824, -768, 2336, -448), -704, 16, 16, 128)    # (cellar corner at y = -768: 16, flat, matches)
strip_ramp((3104, -768, 3232, -384), 16, 128, 128)      # rear stair down to the cellar   so it meets the cellar's
strip_ramp((-128, -960, 128, -448), 16, 128, 128, sym=False)   # chamber stairs  strip at the corner: a straight line, no clamp)

# --- b2: hook-only perches (grappling hook or rocket jump), each with a small stack
perch((384, -96, 448, 96), 288)            # mid chamber: high on the end wall, over the spine mouth
perch((1136, 1216, 1392, 1280), 352)       # aqueduct hall: north wall, over the middle of the bridge
perch((1824, 64, 1888, 320), 256)          # forecourt: west wall beside the spine mouth, a defender's post
labels += [(416, 0, 'perch 288'), (1264, 1250, 'perch 352'), (1856, 192, 'perch 256')]

# --- b2: team banners (non-solid panels): forecourt wall between the flag-hall doors,
#     and either side of the flag hall's back door
sigil((2328, -64, 2336, 64), 160, 416, 'dc_ban_b', 'dc_ban_r')
sigil((3032, 128, 3040, 256), 96, 352, 'dc_ban_b', 'dc_ban_r')
sigil((3032, -256, 3040, -128), 96, 352, 'dc_ban_b', 'dc_ban_r')

# --- team start spawns (KTX: info_player_team1/2; red = mirror copy)
for _x, _y in ((2464, 320), (2464, -320), (2976, 320), (2976, -320),
               (1952, 192), (1952, -320), (2208, 288), (2208, -288)):
    team_spawn(_x, _y, 0, 180)

# --- respawns (20 = 10 mirror pairs): DM respawns and rune points, chosen by pick_spawns_sym.py -
#     no two (or their mirror copies) see each other, >= 320 apart, none in a flag hall or near a flag
for x, y, z, a, lab in [
        (160, 224, 0, 270, 'chamber'),
        (320, 1472, 192, 225, 'n court'),
        (320, -1504, -128, 0, 's court'),
        (1248, 864, 0, 90, 'aqueduct floor'),
        (1792, 1248, 192, 180, 'aqueduct landing'),
        (928, 288, 0, 270, 'spine junction'),
        (1344, -896, -128, 0, 'undercroft E'),
        (992, -992, -128, 225, 'undercroft W'),
        (2144, 1120, 192, 180, 'gatehouse'),
        (2784, -800, -128, 225, 'cellar')]:
    spawn(x, y, z, a, lab)
