ca_lyceum_b5 - Clan Arena / TDM map for QuakeWorld, BETA 5 (visual pass)
=============================================================================
Target: 8-12 players, 16 spawns for up to 16. Also playable as TDM/FFA.
Install: copy ca_lyceum_b5.bsp to qw/maps/ (or id1/maps/), and
ca_lyceum_b5.wad next to it if your client wants it. Then: map ca_lyceum_b5

CHANGES IN BETA 5
  - YA platform: its own mosaic, fitted to the platform - a Greek-key border
    round all four edges and a gold victor's laurel wreath with a vermilion
    ribbon round a white star (was the hall floor, cut off-centre).
  - Duel hall and gallery floors: the mosaic grid is now centred on the room
    (it used to start at the west and north walls only), and both floors line up.
  - The climb (balcony up to the tower stand) and the two small doorways off
    the balcony now match the gallery: black stucco, vermilion pilasters,
    gold candelabra, fire bowls, a slate mosaic floor with a small white dot grid.
    A little more fill light in the climb for the darker walls.
  - Layout and collision still identical to beta 2 (checked voxel for voxel).

CHANGES IN BETA 4
  - Duel hall redone as a Pompeian "black room": black panels in vermilion
    frames with gilt lines, gold candelabra and rosettes; a black-and-white
    Roman mosaic floor with running Greek-key borders (laid out tessera by
    tessera so the key reads cleanly); black-painted beams with vermilion
    and gilt soffits. Replaces the red panels and the chequer floor.
  - Gallery over the duel hall to match: black stucco between vermilion
    pilasters with gold candelabra, same mosaic floor, fire bowls.
  - Duel hall and gallery lamps raised a little for the darker walls.
  - Layout and collision still identical to beta 2 (checked voxel for voxel).

VISUAL PASS: "LAMPLIT ACADEMY" (beta 3)
  A classical academy at night - every room its own material, lit by oil lamps.
    - Hub = atrium: cream marble ashlar, octagon-and-dot marble floor,
      coffered ceiling with gold rosettes, a mosaic medallion on the RL
      plinth, fluted marble columns with bases and capitals. Amber lamp band.
    - Tower = observatory: midnight-blue walls painted with gold stars and
      constellations, a starry painted ceiling with an OCULUS open to the
      night sky, and a bronze compass rose inlaid in the floor where the
      moonlight falls. Moon-white lamp band, star lamps.
    - Pit = amphitheatre: honey travertine, a sand arena floor, marble
      seating steps, timber ceiling. Firelight band, fire bowls.
    - Duel hall: black fresco and Greek-key mosaic (see beta 4).
      Gold band, fire bowls.
    - Gallery: black stucco and vermilion pilasters (see beta 4).
    - Climb: black stucco and vermilion pilasters like the gallery (see beta 5).
    - Passages: Roman brick and limestone flags.
    - Everywhere: porphyry dado with a bronze lip, dentil cornices.
  The layout and collision are identical to beta 2 (checked voxel for
  voxel); spawns and items unchanged. Brightness is on par with Cistern.
  The oculus is the only sky: rockets fired straight up into it vanish
  instead of exploding (576 units up, so it should never matter).

CHANGES IN BETA 2
  - Duel hall: the column at the foot of the gallery stairs moved off the
    stairs' corner, so the bottom steps land on open floor
  - Duel hall: the wall stub by the platform is 32 shorter
  - New check: the floor in front of every stair's bottom step is clear

DESIGN (from the CA demo study)
  - dm6's shape: a central hub with three distinct satellite rooms, each
    joined to the hub and to its neighbours, so every room has 2+ exits
  - Agora's height: a walkway network above the hub (balcony -> gallery,
    balcony -> climb -> tower stand) that comes back down at both ends
  - low ground with a purpose: the pit has the RA, cover and a low
    passage that flanks into the duel hall
  - sized for rocket fights: rooms 500-800 across, short connectors

LAYOUT (asymmetric; north is up on the plan)
  Main floor 0
    - Hub (centre): stepped plinth with the RL (48), two columns, a broad
      wall-to-wall grand stair up to the balcony; GA. Doors west (tower),
      south (pit rim) and east (duel hall)
    - Tower (west): tall room; a broad 17-step stair up to the stand (288);
      second RL in the strip under the stand's cliff; SSG in the corridor to the pit
    - Duel hall (east): open, two columns and a wall stub, a stepped
      platform with a YA (64); SNG at the south end
  Upper level 160 / 288
    - Balcony (160) across the north of the hub: YA
    - Gallery (160) north of the duel hall, open over it, with broad steps
      down into it - a second way between hub and duel hall
    - Climb: enclosed stair from the balcony's west end up to the tower
      stand (288): Mega and LG. So the stand has two ways in and a drop
  Sunken level -96
    - Pit (south-west): rim at 0 with broad steps down, a column and a
      pier that splits the floor; RA in the east bay, GL in the west bay
    - Low passage from the pit floor east to the duel hall (NG), stepping
      back up to 0 at the duel hall end

  Items: RA, Mega, 2x YA, GA, 2x RL, LG, GL, SNG, SSG, NG,
         health and ammo (TDM / FFA)

CHECKED IN THIS BUILD
  - compiles with no leaks; full vis; lightmaps; standard BSP29
  - 16 deathmatch spawns, picked by a solver: no spawn can see any other
    spawn, every pair at least 288 units apart (closest is 302), none
    within 192 of a weapon, armour or the Mega, spread over all areas
  - every spawn can reach every other; every item reachable, none on a
    spawn, none touching a wall or step edge
  - no traps: every reachable spot has a walk/jump route back
  - all stairs are broad wall-to-wall steps; every stair's foot is clear

TEXTURES
  All textures are generated from code (texgen_lyceum.py) and quantized to the
  Quake palette as distributed with LibreQuake (BSD-3). No third-party art.

FILES
  ca_lyceum_b5.bsp / .map / .wad
  ca_lyceum_b5_fix.png     platform, duel floor and climb, beta 4 vs beta 5
  ca_lyceum_b5_plan.png    top-down plan, both levels, items and spawns
  ca_lyceum_b5_views.png   preview renders
