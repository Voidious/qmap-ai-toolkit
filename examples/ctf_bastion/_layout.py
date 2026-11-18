
# =========================================================================
# LAYOUT - blue (team2) half written out; sym=True adds the 180-degree red copy
#   undercroft -128, main floor 0, balconies / ledges / upper route 192
# =========================================================================

# --- Mid hall (shared): tall, pillars to hook, Quad on a low dais, one ledge per team
carve((-448, -576, 448, 576), 0, 576, 'mid')
fill((160, 160, 256, 256), 0, 576, 'pillar')                    # 4 pillars (2 written + rotations)
fill((160, -256, 256, -160), 0, 576, 'pillar')
fill((-64, -64, 64, 64), BOT, 16, None, sym=False)              # Quad dais: basalt plate, gold ring
fill((-64, -64, 64, 64), 16, 32, 'stand_q', sym=False)
pyramid((-64, -64, 64, 64), 32, ('-x', '+x', '-y', '+y'))
fill((128, 448, 448, 576), BOT, 192, 'ledge')                   # blue ledge (NE) / red ledge (SW)
carve((128, 448, 448, 576), 192, 576, 'mid')                    # b6: ledge is a room floor - kickplate runs on into the high route
pyramid2((128, 448, 448, 576), 192, ('-x', '-y'))               # broad steps wrapping its open corner
room_lamps((-448, -576, 448, 576), 576, step=256, value=470)     # b7: dimmer flood ...
lights.append((0, 0, 240, 520))                                  # ... and a bright pool over the Quad
lights.append((0, 0, 120, 260))
for _sx in (1, -1):                                              # b8: fill light in the gaps beside each column,
    for _sy in (1, -1):                                          # so the outer faces are not left unlit
        for _z in (112, 352):
            lights.append((_sx * 368, _sy * 208, _z, 300, 1.0))
            lights.append((_sx * 208, _sy * 384, _z + 128, 300, 1.0))   # clear of the ledge steps
labels += [(0, -150, 'MID\n0'), (300, 520, 'ledge 160'.replace('160', '192'))]

# --- Main route: corridor mid <-> base, a pillar splits it into two lanes
carve_team((448, -128, 896, 128), 0, 224, 'corridor_b', 'corridor_r')                # straight leg from mid
fill((640, -32, 704, 32), 0, 224, 'pillar')                     # splits it into two lanes
carve_team((896, -128, 1152, 320), 0, 224, 'corridor_b', 'corridor_r')               # dogleg: turns toward the hall's far corner
carve_team((1152, 128, 1216, 320), 0, 224, 'corridor_b', 'corridor_r', door=True)    # enters the base hall at its north-west
for _x in (544, 800):                                            # b13: one lamp over each lane (centreline lamps
    for _y in (-80, 80):                                         # left the pillar's lane faces unlit)
        lamp(_x, _y, 224, value=300)
room_lamps((896, -128, 1152, 320), 224, step=256, value=340)

# --- High route: from the team's mid ledge to the base balcony
carve_team((448, 448, 1216, 576), 192, 352, 'upper_b', 'upper_r')
room_lamps((448, 448, 1216, 576), 352, step=256, value=300)
labels += [(832, 600, 'upper 192')]

# --- Low route: stairs down from mid, the undercroft, up into the base hall through a stair pit
carve_team((448, 144, 704, 272), -128, 192, 'under_b', 'under_r', door=True)      # door in mid's east wall, north of the corridor
stairs(448, 144, 704, 272, 'x', -128, 0, rev=True)
carve_team((704, 128, 832, 272), -128, 96, 'under_b', 'under_r')                   # turn south ...
carve_team((704, -128, 832, 128), -128, -16, 'under_b', 'under_r')                 # ... under the corridor ...
carve_team((704, -192, 832, -128), -128, 96, 'under_b', 'under_r')                 # ... into the undercroft
carve_team((704, -704, 1216, -192), -128, 96, 'under_b', 'under_r')
fill((864, -480, 928, -416), -128, 96, 'pillar')
fill((1024, -608, 1088, -544), -128, 96, 'pillar')
room_lamps((704, -704, 1216, -192), 96, step=256, value=280)
carve_team((1216, -576, 1472, -448), -128, 0, 'under_b', 'under_r')
stairs(1216, -576, 1472, -448, 'x', -128, 0)                     # pit up into the base hall
# back way: tunnel under the base hall, up into the south wing
carve_team((1216, -704, 1600, -608), -128, 32, 'under_b', 'under_r')
stairs(1472, -704, 1600, -608, 'x', -128, -64)
carve_team((1600, -704, 1728, -608), -64, 96, 'under_b', 'under_r')
stairs(1600, -704, 1728, -608, 'x', -64, 0, run=32)
room_lamps((1216, -704, 1600, -608), 32, step=256, value=220)
labels += [(960, -270, 'UNDERCROFT\n-128')]

# --- Side route (north; the rotated copy runs along the south): bypasses mid entirely.
#     Branches off this team's high route (192), runs outside mid's north wall, then a long
#     stair down into the OTHER team's undercroft (-128). The south copy mirrors it.
carve_team((640, 576, 768, 640), 192, 352, 'side_b', 'side_r', door=True)        # opening in the high route's north wall
carve_team((448, 640, 768, 768), -128, 352, 'side_b', 'side_r')    # team colour near each base ...
carve_team((-448, 640, 448, 768), -128, 352, 'side_m', 'side_m')   # ... b13: neutral alongside mid
carve_team((-704, 640, -448, 768), -128, 352, 'side_r', 'side_b')
def _side_floor(x):
    return -128 if x < -384 else (192 if x >= 256 else -128 + 16 * ((x + 384) // 32 + 1))
for _x in (-384, -160, 64, 288):                                  # b13: the dark basalt stretch needs its own light
    for _s in (1, -1):
        lights.append((_s * _x, _s * 704, _side_floor(_x) + 112, 260, 1.0))
fill((256, 640, 768, 768), BOT, 192, None)                       # high end (192)
stairs(-384, 640, 256, 768, 'x', -128, 192)                      # long stair down toward the far undercroft
room_lamps((-704, 640, 768, 768), 352, step=320, value=320)
labels += [(500, 704, 'side route 192'), (-560, 720, 'side -128')]

# --- Base hall: tall, balcony along the far wall (high route lands here), broad steps down
carve_team((1216, -576, 1728, 576), 0, 512, 'blue', 'red')
fill((1216, 384, 1728, 576), BOT, 192, 'ledge')
carve_team((1216, 384, 1728, 576), 192, 512, 'blue', 'red')     # b6: balcony is a room floor - kickplate links high route and north wing
pyramid2((1472, 384, 1728, 576), 192, ('-y', '-x'))
room_lamps((1216, -576, 1728, 384), 512, step=256, value=640)
labels += [(1470, -40, 'BASE HALL\n0'), (1340, 480, 'balcony 192')]

# --- The keep: the flag room sits behind the base hall with no door straight through.
#     Ground way in: hall -> south wing -> south door.  High way: balcony -> north wing -> gallery.
carve_team((1856, -320, 2240, 320), 0, 384, 'blueflag', 'redflag')
fill((1856, 192, 2240, 320), BOT, 192, 'ledge')                  # gallery over the flag (192)
fill((1984, -64, 2112, 64), BOT, 32, None, sym=False)            # flag stand: iron plate with the team ring
fill((1984, -64, 2112, 64), 32, 48, 'stand_b', sym=False)
fill(rot((1984, -64, 2112, 64)), BOT, 32, None, sym=False)
fill(rot((1984, -64, 2112, 64)), 32, 48, 'stand_r', sym=False)
pyramid2((1984, -64, 2112, 64), 48, ('-x', '+x', '-y', '+y'))
room_lamps((1856, -320, 2240, 192), 384, step=256, value=420)
# south wing (floor 0): opens off the hall's far corner and the back tunnel; door north into the keep
carve_team((1728, -704, 2240, -448), 0, 256, 'blue', 'red')
carve_team((2048, -448, 2176, -320), 0, 128, 'blueflag', 'redflag', door=True)
room_lamps((1728, -704, 2240, -448), 256, step=256, value=320)
# north wing (192): continues the balcony; door south onto the gallery
carve_team((1728, 448, 2240, 576), 192, 352, 'blue', 'red')
carve_team((1984, 320, 2112, 448), 192, 320, 'blueflag', 'redflag', door=True)
room_lamps((1728, 448, 2240, 576), 352, step=256, value=300)
labels += [(2048, -200, 'KEEP\n(flag)'), (1984, -600, 'south wing'), (2112, 256, 'gallery 192'), (1984, 520, 'north wing 192')]

# --- b13: soft fill light on every side of each free-standing column (the room lamps are too far
#     from their faces to reach them), written for both halves
for (_x0, _y0, _x1, _y1, _f, _c) in ((640, -32, 704, 32, 0, 224), (864, -480, 928, -416, -128, 96),
                                     (1024, -608, 1088, -544, -128, 96)):
    _cx, _cy = (_x0 + _x1) / 2, (_y0 + _y1) / 2
    _z = _f + min(80, (_c - _f) // 2)
    for _px, _py in ((_x0 - 48, _cy), (_x1 + 48, _cy), (_cx, _y0 - 48), (_cx, _y1 + 48)):
        for _s in (1, -1):
            for _zz in sorted({_z, _c - 40}):
                lights.append((int(_s * _px), int(_s * _py), _zz, 130, 1.0))

# --- Hook-only perches (grappling hook or rocket jump): high on the busiest walls
perch((384, -192, 448, 192), 352)          # mid: high on this team's end wall, over its corridor mouth
perch((-128, 512, 128, 576), 384)          # mid: centre of the long wall, above this team's stepped ledge
perch((1408, -576, 1664, -512), 320)       # base hall: opposite the balcony, covers the hall and the wing opening
perch((2176, -128, 2240, 128), 272)        # keep: behind the flag stand
labels += [(416, 0, 'perch 352'), (0, 544, 'perch 384'), (1536, -544, 'perch 320'), (2208, 0, 'perch 272')]

# --- Team emblems (non-solid panels): ice crystal for blue, flame for red
sigil((1720, -160, 1728, 32), 224, 416, 'bs_sig_ice', 'bs_sig_fire')     # base hall far wall, seen on arrival
sigil((1856, -96, 1864, 96), 160, 352, 'bs_sig_ice', 'bs_sig_fire')      # keep wall facing the flag

# --- team start spawns (KTX: info_player_team1/2; red = rotated copy)
for _x, _y in ((1312, -352), (1440, -320), (1568, -352), (1664, -224),
               (1312, -32), (1472, -96), (1600, 96), (1664, -448)):
    team_spawn(_x, _y, 0, 180)

# --- spawns (16 = 8 rotated pairs): DM respawns and rune points, chosen by pick_spawns_sym.py -
#     no two (or their rotations) see each other, >= 320 apart, none in or beside a flag room
for x, y, z, a, lab in [
        (736, 736, 192, 180, 'side route'),
        (512, 480, 192, 0, 'upper'),
        (224, -352, 0, 45, 'mid S'),
        (288, 224, 0, 270, 'mid N'),
        (1024, 288, 0, 270, 'dogleg'),
        (736, 160, -128, 270, 'under N'),
        (1024, -288, -128, 315, 'undercroft'),
        (1408, -384, 0, 180, 'base hall')]:
    spawn(x, y, z, a, lab)

# --- items ----------------------------------------------------------------
