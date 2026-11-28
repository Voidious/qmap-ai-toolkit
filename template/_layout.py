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
#   ramp(rect, axis, z0, z1, rev=False)    true slope; walls beside it get sloped bands
#   diag_ramp(x0, y0, x1, y1, width, z0, z1, base=None, thick=None)  diagonal / non-axial ramp
#   prism(points, z0, z1) / chamfer(rect, corner, size, z0, z1) / diag_wall(x0, y0, x1, y1, thick, z0, z1)
#                                          angled walls, cut corners, many-sided pillars
#   sloped_ceil / gable_ceil / barrel_vault  sloped, pitched & vaulted ceilings (lamp-aware)
#   arch_door / truss / buttress           arched doorways, overhead trusses, wall buttresses
#   curved_wall / rotunda / cylinder       curved arcs, circular rooms & columns (continuous UVs)
#   label(x, y, text, z)                   names on the plan image
# =========================================================================

# --- DEMO (delete): an octagonal central hall with a plinth, an east wing with a gabled roof,
#     trusses, buttresses, an arched doorway, and a diagonal ramp, a sunken north room with a
#     barrel vault, slanted alcove ceiling, axial ramp, and 12-sided column, and a south rotunda
#     with a curved baffle wall. Builds cleanly in all three SYM modes.

# central hall, straddling x = 0: written once
carve((-384, -384, 384, 384), 0, 384, 'hall', sym=False)
fill((-64, -64, 64, 64), BOT, 48, None, sym=False)                      # plinth
pyramid((-64, -64, 64, 64), 48, ('-x', '+x', '-y', '+y'), sym=False)    # its steps, all four sides
inlay((-64, -64, 64, 64), 48, 'bk_stand', sym=False)                    # a plate that fits it exactly
fill((128, 128, 192, 192), 0, 384, 'pillar')                            # columns (+ copy)
fill((128, -192, 192, -128), 0, 384, 'pillar')
room_lamps((-384, -384, 384, 384), 384, step=256, value=520, sym=False)
for _c in ('ne', 'nw', 'se', 'sw'):
    chamfer((-384, -384, 384, 384), _c, 128, 0, 384, sym=False)           # octagonal hall
label(0, -150, 'HALL 0')

# east wing (+ copy): arched doorway, gabled roof with trusses & buttresses, gallery, diagonal ramp
arch_door((384, -64, 512, 64), 'y', 0, 160, 'hall', arch_h=48, trim=True)
carve((512, -320, 1024, 320), 0, 384, 'wing')
fill((832, -320, 1024, 64), BOT, 128, None)                             # gallery (128)
terrace((832, -320, 1024, -128), 128, '-x')                             # broad steps on south side
diag_ramp(640, 224, 864, 0, 96, 0, 128)                                 # 45-deg ramp onto open gallery corner
perch((704, 288, 800, 320), 224)
gable_ceil((512, -320, 1024, 320), 'y', 288, 384)                       # pitched gable ceiling (eave 288 >= perch+64)
truss((640, -320, 664, 320), 'y', 288, 384, beam_h=16, knee=32)         # solid overhead king-post trusses
truss((800, -320, 824, 320), 'y', 288, 384, beam_h=16, knee=32)
buttress((608, -320, 640, -288), '-y', 0, 288, top_depth=8)             # sloped wall buttresses
buttress((608, 288, 640, 320), '+y', 0, 288, top_depth=8)
room_lamps((512, -320, 1024, 320), 384, step=256, value=480)            # pendant lamps clear gable & trusses
label(640, -200, 'WING 0'), label(928, -200, 'gallery 128', 128)

# sunken room to the north, straddling x = 0: barrel vault, slanted alcove, axial ramp, circular column
carve((-128, 384, 128, 512), 0, 128, 'hall', door=True, sym=False)
carve((-128, 512, 128, 704), -96, 224, 'low', sym=False)
stairs(-128, 512, 128, 704, 'y', -96, 0, rev=True, sym=False)          # rises toward the hall
carve((-384, 704, 384, 1088), -96, 224, 'low', sym=False)
strip_ramp((-128, 512, 128, 704), 48, 144, 144, sym=False)             # strip follows the stairs
panel((-64, 1080, 64, 1088), 64, 192, 'bk_panel', tex_px=256, sym=False)  # placeholder picture, 128 wide, thin in y
fill((-384, 960, 384, 1088), BOT, 0, None, sym=False)                  # a ledge along the north wall (0)
strip_ramp((-384, 960, 384, 1088), 144, 144, 144, sym=False)           # the ledge's strip 144 above it
ramp((-384, 768, -256, 960), 'y', -96, 0, sym=False)                   # axial ramp up to it (foot clear)
carve((-512, 704, -384, 960), -96, 160, 'alcove', strip=-48, sym=False) # alcove beside ramp (veneer + architrave)
sloped_ceil((-512, 704, -384, 960), 'x', 112, 160, sym=False)          # slanted ceiling over alcove
barrel_vault((-384, 704, 384, 960), 'y', 144, 224, segs=6, sym=False)  # barrel vault over sunken bay
cylinder(192, 832, 40, -96, 224, sides=12, kind='pillar', sym=False)   # 12-sided circular column (continuous UV)
room_lamps((-384, 704, 384, 1088), 224, step=256, value=420, sym=False)
room_lamps((-512, 704, -384, 960), 160, step=256, value=340, sym=False)
label(0, 900, 'LOW -96', -96), label(0, 1024, 'ledge 0', 0)

# south rotunda, straddling x = 0: arched entry, 12-sided circular room, curved cover wall
arch_door((-64, -512, 64, -384), 'x', 0, 160, 'hall', arch_h=48, trim=True, sym=False)
_rot_box = rotunda(0, -736, 224, 0, 288, 'rotunda', sides=12, openings=[('+y', 128, 160)], sym=False)
curved_wall(0, -736, 64, 96, 210, 330, 0, 96, segs=4, sym=False)        # curved cover baffle inside rotunda
room_lamps(_rot_box, 288, step=256, value=460, sym=False)
label(0, -736, 'ROTUNDA 0')

# spawns (+ copies)
spawn(-256, -256, 0, 45, 'hall')
spawn(640, 64, 0, 180, 'wing')
spawn(960, -192, 128, 180, 'gallery')
spawn(-128, 800, -96, 0, 'low', sym=False)
spawn(320, 760, -96, 180, 'low', sym=False)
spawn(128, -736, 0, 180, 'rotunda', sym=False)
