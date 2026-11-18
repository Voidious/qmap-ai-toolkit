ctf_circuit_b5 - Capture the Flag map for QuakeWorld / KTX, BETA 5 (visual pass)
=======================================================================================
Target: 8-12 players. 16 team starts (8 per base) + 20 respawn / rune points.
Built for KTX CTF with the grappling hook on. Working title.
Install: copy ctf_circuit_b5.bsp to qw/maps/ (or id1/maps/), and
ctf_circuit_b5.wad next to it if your client wants it. Then: map ctf_circuit_b5

CHANGES IN BETA 5 (visual only - collision identical to beta 4, checked voxel for voxel)
  - Forecourt stairs down to the cellar (both bases): the undercroft opens
    beside the two lowest steps, so its wall meets the stairwell two steps up,
    and the light strip used to arrive there 32 high. The strip now climbs at
    the stair slope from the undercroft corner and starts its descent two steps
    before the top of the stairs, out on the forecourt walls - so it meets the
    undercroft strip, the cellar strip and the forecourt strip exactly, on both
    walls of the stairwell, in one straight line.
  - Wall lanterns now check the stepped strips too, so none can sit on one.

CHANGES IN BETA 4 (visual only - collision identical to beta 3, checked voxel for voxel)
  - Stairs down to the cellar (forecourt and rear, both bases) and the chamber
    stairs down to the south court: the light strip runs one step lower, in a
    straight line parallel to the stairs, so it now meets the lower room's
    strip exactly at the corner (it used to arrive one step high).

CHANGES IN BETA 3 (visual only - collision identical to beta 2, checked voxel for voxel)
  - The light strips now follow the stairs between levels and join up with
    the strip in the room above or below, instead of stopping at the steps:
    forecourt and rear stairs up to the gatehouse and down to the cellar (both
    bases), and the stairs from the mid chamber down to the south court.

CHANGES IN BETA 2 - VISUAL PASS: "DESERT CITADEL"
  Two rival sandstone forts at dusk. Team colour lives in the glazed tilework:
  lapis and sky-blue for blue, cinnabar and terracotta for red, gold and black
  in the neutral middle.
    - Every wall's dado (kickplate) is a band of glazed star tiles in its
      half's colours; the lamp bands are pierced-brass strips glowing blue,
      ember or gold; the wall lanterns match.
    - Forecourts: sandstone ashlar, sandstone flags with a glazed tile where
      four flags meet, painted cedar beams. A team banner hangs between the
      flag-hall doors.
    - Flag halls: carved plaster walls (interlaced stars), a star-tile floor
      in team colours, painted coffers, two banners beside the back door, the
      flag on a glazed star medallion.
    - North arc: weathered sandstone, herringbone brick, cedar ceilings. The
      aqueduct bridge carries a glazed water channel down its middle.
    - South arc: cool limestone vaults and flagstones.
    - Spine: tiled tunnels - zellige panels in sandstone frames.
    - Mid chamber: carved plaster with gold, a gold-and-black star floor,
      painted coffers, and a gilded cupola raised over the Quad (the ceiling
      there goes up from 448 to 576).
  Gameplay additions (the only changes to the solid map):
    - Hook-only perches, each with a small stack:
        mid chamber end wall (288, over the spine mouth): rockets + small health
        aqueduct hall north wall (352, over the bridge): cells + small health
        forecourt west wall (256, beside the spine mouth): health + rockets
    - The cupola over the Quad (more headroom there).
  Everything else - rooms, routes, spawns, items - is as in beta 1. Brightness
  is on par with the other maps.

CONCEPT A, "CIRCUIT": a racetrack round a solid core.
  Blue base at the east end, red base at the west end. The map is a MIRROR
  image about the middle (not a rotation), so north is north for both teams:
  the north arc is always the high route and the south arc the low route.

  Three runs between the flags (a "theta"):
    - North arc, HIGH (192): gatehouse -> aqueduct hall (a bridge at 192 over
      a floor at 0, with an arch through) -> north court (Mega) -> mirror.
    - South arc, LOW (-128): cellar -> undercroft -> south court (RA) -> mirror.
    - The spine, straight through the core: forecourt -> offset lane ->
      junction room (GL) -> offset lane -> MID CHAMBER (Quad) -> mirror.
      Shortest and most contested.
  The chamber also links to the arcs: a drop from the north court (one way
  down, or hook back up) and broad stairs up from the south court. So a
  carrier on either arc can bail into the spine at the middle.

  The arcs' rooms are staggered north-south and the spine's lanes are offset,
  so there is no straight sightline along any route: the longest clear line
  anywhere is ~2,100 units, inside one half (gatehouse into the aqueduct hall).

FLAG-TO-FLAG (shortest walking line, measured on the grid)
                       units   at your Bastion pace   at a real carrier's pace
                               (460 u/s with hook)    (320 u/s)
  spine                ~6,130        ~13 s                 ~19 s
  south arc (low)      ~7,050        ~15 s                 ~22 s
  north arc (high)     ~7,240        ~16 s                 ~23 s
  For reference: ctf1 caps in your demos took 20-21 s; Bastion's shortest run
  is ~5,500 units (~12 s at your pace).

BASES (blue described; red is the mirror image)
  - Forecourt: the defence yard. The spine opens into its west wall; a broad
    wall-to-wall stair at its north end climbs to the gatehouse (192), another
    at its south end drops to the cellar (-128).
  - Flag hall: two doors from the forecourt and a back door behind the flag.
    The flag stand is deep in the hall (east of centre).
  - Rear passage behind the flag hall: stairs up to the gatehouse and down to
    the cellar. So a carrier has three ways out of the flag hall, and each
    leads to all three runs.
  - Team starts: 4 in the flag hall, 4 in the forecourt.

ITEMS (weapons stay in KTX CTF; each half has the same set; perch stacks above)
  Quad - mid chamber.  Mega - north court.  RA - south court.
  RL - middle of the aqueduct bridge.  LG - undercroft.  GL - spine junction.
  SNG - gatehouse.  SSG - cellar.  NG - flag hall.
  YA - north court (each side).  GA - south court (each side).
  Health and ammo along every run.

CHECKED IN THIS BUILD
  - compiles with no leaks; full vis; lightmaps; standard BSP29
  - everything reachable on foot, no traps (every spot has a way back)
  - respawns picked by a solver: no two (or their mirror copies) can see
    each other, none in a flag hall or near a flag
  - every stair's foot is clear across its full width; all stairs broad
  - items on clear floor, none on a spawn or touching a wall or step edge

TEXTURES
  All textures are generated from code (texgen_citadel.py) and quantized to the
  Quake palette as distributed with LibreQuake (BSD-3). No third-party art.

FILES
  ctf_circuit_b5.bsp / .map / .wad
  ctf_circuit_b5_plan.png    top-down plan, both levels, items and spawns
  ctf_circuit_b5_routes.png  the three runs drawn on the map
  ctf_circuit_b5_views.png   preview renders
  ctf_circuit_b5_corner.png  beta 4 vs beta 5: the stairwell strips meeting the undercroft
