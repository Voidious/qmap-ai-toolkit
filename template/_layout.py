# =========================================================================
# LAYOUT - this file IS the map. Replace the demo below with your own design.
#
# Units: Quake units on a 16-grid; a player is 32 wide, 56 tall; a step is 16; a jump clears 48.
# With SYM = 'rotate' or 'mirror', write the x > 0 half; calls with sym=True add the copy, and
# pieces that straddle x = 0 (the middle) are written once with sym=False.
# Primitives (see _core.py for every argument):
#   carve(rect, floor, ceiling, theme, door=False, sky=False, strip=None)  hollow out a room
#   fill(rect, z0, z1, mat)          solid: None = structure; 'pillar', 'crate', 'stand', 'pad', ...
#   stairs(x0, y0, x1, y1, axis, z_from, z_to, run=32, rev=False)        a straight flight
#   terrace(platform_rect, h, side, z0=0)  broad wall-to-wall steps down one side of a platform
#   pyramid(block_rect, h, sides, z0=0)    steps down several sides; corners wrap
#   lamp(x, y, ceiling, value) / room_lamps(rect, ceiling, step, value)
#   spawn(x, y, floor, angle, label) / team_spawn(x, y, floor, angle, team)
#   perch(rect, z) / teleporter(...) / jumppad(...) / liquid(...) / panel(...) / inlay(...) / oculus(...)
#   strip_ramp(...) / strip_ramp_pos(...)  light strips that follow stairs (see GUIDE section 6)
#   ramp(rect, axis, z0, z1, rev=False)    v3: a true slope; walls beside it get sloped bands
#   prism(points, z0, z1) / chamfer(rect, corner, size, z0, z1) / diag_wall(x0, y0, x1, y1, thick, z0, z1)
#                                          v3: angled walls, cut corners, many-sided pillars
#   label(x, y, text, z)                   names on the plan image
# =========================================================================

# --- DEMO (delete): an octagonal central hall with a plinth, an east wing with a raised gallery,
#     and a sunken room to the north down a broad stair, with a ramp up to a ledge and an octagonal
#     pillar. Builds in all three SYM modes.

# central hall, straddling x = 0: written once
carve((-384, -384, 384, 384), 0, 384, 'hall', sym=False)
fill((-64, -64, 64, 64), BOT, 48, None, sym=False)                      # plinth
pyramid((-64, -64, 64, 64), 48, ('-x', '+x', '-y', '+y'), sym=False)    # its steps, all four sides
inlay((-64, -64, 64, 64), 48, 'bk_stand', sym=False)                    # a plate that fits it exactly
fill((128, 128, 192, 192), 0, 384, 'pillar')                            # columns (+ copy)
fill((128, -192, 192, -128), 0, 384, 'pillar')
room_lamps((-384, -384, 384, 384), 384, step=256, value=520, sym=False)
for _c in ('ne', 'nw', 'se', 'sw'):
    chamfer((-384, -384, 384, 384), _c, 128, 0, 384, sym=False)           # v3: octagonal hall
label(0, -150, 'HALL 0')

# east wing (+ copy): a doorway, a room, a raised gallery with broad steps, a hook perch
carve((384, -64, 512, 64), 0, 128, 'hall', door=True)
carve((512, -320, 1024, 320), 0, 352, 'wing')
fill((832, -320, 1024, 320), BOT, 128, None)                            # gallery (128)
terrace((832, -320, 1024, 320), 128, '-x')                             # 7 broad steps down its west side
perch((576, 288, 704, 320), 224)
room_lamps((512, -320, 1024, 320), 352, step=256, value=480)
label(640, -200, 'WING 0'), label(928, -200, 'gallery 128', 128)

# sunken room to the north, straddling x = 0: down a broad stair from a doorway in the hall
carve((-128, 384, 128, 512), 0, 128, 'hall', door=True, sym=False)
carve((-128, 512, 128, 704), -96, 224, 'low', sym=False)
stairs(-128, 512, 128, 704, 'y', -96, 0, rev=True, sym=False)          # rises toward the hall
carve((-384, 704, 384, 1088), -96, 224, 'low', sym=False)
strip_ramp((-128, 512, 128, 704), 48, 144, 144, sym=False)             # strip follows the stairs
room_lamps((-384, 704, 384, 1088), 224, step=256, value=420, sym=False)
panel((-64, 1080, 64, 1088), 64, 192, 'bk_panel', tex_px=256, sym=False)  # placeholder picture, 128 wide, thin in y
fill((-384, 960, 384, 1088), BOT, 0, None, sym=False)                  # v3: a ledge along the north wall (0)
strip_ramp((-384, 960, 384, 1088), 144, 144, 144, sym=False)          # the ledge's strip 144 above it
ramp((-384, 768, -256, 960), 'y', -96, 0, sym=False)                   # v3: ramp up to it along the west wall (foot clear)
carve((-512, 704, -384, 960), -96, 160, 'alcove', strip=-48, sym=False) # v3.5: alcove beside ramp (exercises veneer + architrave)
room_lamps((-512, 704, -384, 960), 160, step=256, value=340, sym=False)
_oct = [(192 + 40 * math.cos(math.radians(22.5 + 45 * k)), 832 + 40 * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)]
prism([(round(x), round(y)) for x, y in _oct], -96, 224, 'pillar', sym=False)   # v3: octagonal pillar
label(0, 900, 'LOW -96', -96), label(0, 1024, 'ledge 0', 0)

# spawns (+ copies)
spawn(-256, -256, 0, 45, 'hall')
spawn(640, 64, 0, 180, 'wing')
spawn(960, -192, 128, 180, 'gallery')
spawn(-128, 800, -96, 0, 'low', sym=False)
spawn(320, 760, -96, 180, 'low', sym=False)
