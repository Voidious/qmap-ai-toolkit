
# =========================================================================
# LAYOUT (asymmetric - every call sym=False)
#   pit -96, main floor 0, balcony / walk 160, tower stand 288
# =========================================================================
S = dict(sym=False)

# --- HUB (centre): balcony along the north wall, grand stair in its middle, a low plinth, two columns
carve((-384, -384, 384, 384), 0, 448, 'hub', **S)
fill((-384, 256, 384, 384), BOT, 160, 'ledge', **S)                  # balcony (160)
terrace((-128, 256, 128, 384), 160, '-y')                            # grand stair down to the floor
fill((-64, -224, 64, -96), BOT, 48, 'ledge', **S)                    # plinth (48)
pyramid((-64, -224, 64, -96), 48, ('-x', '+x', '-y', '+y'))
fill((-256, -256, -192, -192), 0, 448, 'pillar', **S)
fill((192, -64, 256, 0), 0, 448, 'pillar', **S)
room_lamps((-384, -384, 384, 256), 448, step=256, value=600, **S)
FLOOR_DECALS.append((-64, -224, 64, -96, 48, 'ly_medal'))      # b3: mosaic medallion on the RL plinth
labels += [(0, 64, 'HUB\n0'), (100, 344, 'balcony 160')]

# --- TOWER (west): tall room, a high stand in the NE corner reached by a wall-to-wall broad stair
carve((-1088, -192, -576, 768), 0, 576, 'tower', **S)
fill((-896, 448, -576, 768), BOT, 288, 'ledge', **S)                 # stand (288)
terrace((-896, 448, -576, 768), 288, '-y')                           # broad stair, 17 steps
fill((-1024, -32, -960, 32), 0, 576, 'pillar', **S)
carve((-576, -64, -384, 64), 0, 128, 'corr', door=True, **S)         # tower <-> hub (ground)
room_lamps((-1088, -192, -576, 448), 576, step=256, value=940, **S)
labels += [(-832, -96, 'TOWER\n0'), (-736, 560, 'stand 288')]
# b3: observatory - an oculus to the night sky, a bronze-ringed frame round it, and a compass
# rose inlaid in the floor where the moonlight falls (texture only: the solid is unchanged)
oculus((-864, 32, -736, 160), 576)
CEIL_DECALS.append((-896, 0, -704, 192, 576, 'ly_ocring'))
FLOOR_DECALS.append((-896, -64, -704, 128, 0, 'ly_rose'))

# --- the climb: from the hub balcony's west end, an enclosed stair up to the tower stand
carve((-512, 256, -384, 768), 160, 416, 'walk', **S)
stairs(-512, 384, -384, 640, 'y', 160, 288, **S)
fill((-512, 640, -384, 768), BOT, 288, None, **S)
carve((-576, 640, -512, 768), 288, 416, 'walk', door=True, **S)      # onto the stand
labels += [(-448, 512, 'climb')]
lights.append((-448, 512, 330, 230))                                 # b3: fill light in the climb (no fixture: same solid)

# --- PIT (south-west): sunken floor, a rim along the north side with broad steps down
carve((-832, -1024, 0, -512), -96, 320, 'pit', **S)
fill((-832, -640, 0, -512), BOT, 0, 'ledge', **S)                    # rim (0)
terrace((-832, -640, 0, -512), 0, '-y', z0=-96)
fill((-576, -928, -512, -864), -96, 320, 'pillar', **S)
fill((-448, -1024, -384, -800), -96, 320, None, **S)                 # pier: splits the pit floor into two bays
fill((-160, -992, -96, -928), -96, -32, 'crate', **S)
carve((-128, -512, 0, -384), 0, 128, 'corr', door=True, **S)         # pit <-> hub
carve((-768, -512, -640, -192), 0, 128, 'corr', **S)                 # pit <-> tower
for lx in (-640, -192):                                              # pier splits the pit: 2 lamps a side
    for ly in (-928, -736):
        lamp(lx, ly, 320, 500, False)
labels += [(-416, -940, 'PIT\n-96'), (-640, -576, 'rim 0')]

# --- LOW PASSAGE: pit floor -> duel hall (the pit's flank route)
carve((0, -896, 320, -768), -96, 32, 'low', **S)
carve((320, -896, 512, -768), -96, 128, 'low', **S)
stairs(320, -896, 512, -768, 'x', -96, 0, **S)
room_lamps((0, -896, 320, -768), 32, step=192, value=240, **S)
labels += [(416, -832, 'low')]

# --- DUEL HALL (east): open and flat, a low stepped platform and two columns
carve((512, -896, 1088, 128), 0, 384, 'duel', **S)
fill((704, -448, 896, -256), BOT, 64, 'ledge', **S)                  # platform (64)
pyramid((704, -448, 896, -256), 64, ('-x', '+x', '-y', '+y'))
fill((640, -704, 704, -640), 0, 384, 'pillar', **S)
fill((800, -144, 864, -80), 0, 384, 'pillar', **S)                   # b2: off the gallery stair's corner, 64+ clear of both stairs
fill((992, -544, 1088, -480), 0, 384, None, **S)                     # wall stub (b2: 48 clear of the platform steps): a south bay off the open hall
carve((384, -64, 512, 64), 0, 128, 'corr', door=True, **S)          # duel <-> hub
room_lamps((512, -896, 1088, 128), 384, step=256, value=680, **S)   # b4: black walls - a little more lamp
labels += [(800, 32, 'DUEL\n0')]
FLOOR_DECALS.append((704, -448, 896, -256, 64, 'ly_dais'))         # b5: mosaic laurel on the YA platform

# --- GALLERY (north-east, 160): from the hub balcony's east end, overlooking the duel hall's north
#     end, with broad steps down into it - the upper loop hub -> balcony -> gallery -> duel -> hub
carve((512, 128, 1088, 512), 160, 352, 'gal', **S)                   # b4: own theme (black fresco)
carve((384, 256, 512, 384), 160, 288, 'walk', door=True, **S)         # balcony -> gallery
terrace((896, 128, 1088, 512), 160, '-y')                           # steps down into the duel hall
fill((640, 320, 704, 384), 160, 352, 'pillar', **S)
room_lamps((512, 128, 1088, 512), 352, step=256, value=420, **S)
labels += [(704, 448, 'GALLERY 160')]

# --- spawns: 16, chosen by pick_spawns.py (MIND=288)
spawn(-512, -992, -96, 135, 'pit', sym=False)
spawn(-800, -544, 0, 0, 'pit', sym=False)
spawn(-32, -992, -96, 135, 'pit', sym=False)
spawn(-288, -256, 0, 90, 'hub', sym=False)
spawn(192, -256, 0, 45, 'hub', sym=False)
spawn(256, 224, 0, 225, 'hub', sym=False)
spawn(-928, 448, 0, 270, 'tower', sym=False)
spawn(-608, 512, 288, 270, 'tower', sym=False)
spawn(-864, 128, 0, 315, 'tower', sym=False)
spawn(-128, 0, 0, 0, 'hub', sym=False)
spawn(480, -32, 0, 0, 'passage', sym=False)
spawn(928, -160, 0, 270, 'duel', sym=False)
spawn(1056, -608, 0, 180, 'duel', sym=False)
spawn(576, -320, 0, 270, 'duel', sym=False)
spawn(544, 320, 160, 180, 'walk', sym=False)
spawn(928, 480, 160, 270, 'walk', sym=False)

# --- items ----------------------------------------------------------------
