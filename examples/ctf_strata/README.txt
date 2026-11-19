ctf_strata_b6 - Capture the Flag map for QuakeWorld / KTX, BETA 6 (visual pass, touch-ups)
============================================================================================
Target: 8-12 players. 16 team starts (8 per base) + 24 respawn / rune points.
Built for KTX CTF with the grappling hook on. Working title.
Install: copy ctf_strata_b6.bsp to qw/maps/ (or id1/maps/), and ctf_strata_b6.wad
next to it if your client wants it. Then: map ctf_strata_b6

BETA 6 (collision identical to b5): FEWER SIGNS, none where something already says it
  - removed: the second sign along each bridge (one per bridge now); the undercroft
    sign facing the one at the foot of the pit stair; the sign on each arena face
    of the arcade wall (the big end-wall boards say it); the BLUE / RED tag by
    each base gate (the base is right there, and the pier tag is a step back).
  - moved: the deck signs at the base end now sit by the RL (north deck) and the
    SNG (south deck), like the lower-hall ones - away from the flag room.
  - now: 9 two-ended signs, 2 tags and 1 big board per half. Every respawn outside
    a base still sees a sign, except one that spawns facing straight through its
    own base gate (the base is the sign there; a sign is 96 units away).

BETA 5 (collision identical to b4)
  - A one-name sign only ever names its own half's team: no RED tags in the blue
    half, no BLUE tags in the red half. So every one-name sign also points toward
    its half's flag. Removed: the tags on the lower hall's mid-end wall, on the
    pier's gate side and on the well room's mid-end wall (wall lamps fill in).
    The two-ended '< RED | BLUE >' signs and the big pit boards stay. Every
    respawn outside a base still sees a sign where it stands.

BETA 4: WHICH WAY IS WHICH, AND A TEXTURE FIX (collision identical to b3)
  - Every light-strip bulb and wall lamp now takes its half's colour: blue in the
    blue half, red-orange in the red half (before, only the bases had them). The
    halfway line runs through the Quad: look along any wall to see whose half it is.
  - Painted mine signs in luminous paint at the junctions (16 per half since b5):
      walls along the route: '< RED | BLUE >' - each name's arrow points its way;
      walls across the route: 'BLUE' or 'RED' - that base lies that way;
      a big BLUE / RED board on each end wall of the pit, under the hook ledge.
    Checked from every respawn: each one sees a sign where it stands (40-450
    units away); the only ones that don't are inside a base, which is its own sign.
  - Fixed: the stone on the walls along the stairs by each flag stepped out of line
    with every step (the stone was anchored to the light strip, which climbs the
    stairs). It is now anchored to the room's level, so the courses run straight.

BETA 3: THE VISUAL PASS, "THE DIG" - an excavation through rock layers.
The rock tells you which floor you are on:
  - FLOOR 0 is dark blue-grey SLATE: the lower halls are room-and-pillar mine
    galleries (slate pillars left standing, iron-strapped, timber cribbing on top,
    timber-lagged roofs); the undercrofts are rockbolted and have mine rails down
    the middle - follow the rails, it's the covered side lane.
  - THE SLAB between floors is a black COAL SEAM, a band you see wherever the
    levels meet: round the pit, in the bases, round each well shaft.
  - FLOOR 256 is pale LIMESTONE: the north decks chalk with flint, the south decks
    banded ironstone (rust stripes), the well rooms grey limestone.
  - THE PIT (the atrium) is an open quarry under a night sky, lit by moonlight
    and caged lamps hanging from a timber beam over the Quad. Its walls show the
    whole section: slate below, the seam, a drilled quarry face above.
  - TEAM COLOUR lives in the mineral: lapis veins and blue lamps in the blue base,
    cinnabar veins and red-orange lamps in the red base; each flag sits on an
    agate slice, the Quad on a pale quartz one.
  - LIGHT STRIP: a cable of caged bulbs on a timber batten. It climbs with every
    stair (the pit stairs, the base stairs) and crosses the seam. Bulbs and wall
    lamps are blue in the blue half, red-orange in the red half (b4).
All textures are generated in code (texgen_dig.py), quantized to the Quake palette
from LibreQuake (BSD-3).

NEW IN BETA 3 (the only collision changes, checked voxel by voxel against b2):
  - a timber beam across the pit over the Quad (top at 496): a hook anchor. It is
    low enough that standing on it you can't see down into the covered bridges.
  - hook ledges: one high on the back wall of each base above the flag (416),
    one high on each pit end wall above the arena arch (400). Nothing on them.
  - the old ceiling lamps of the atrium are gone (it's open sky now).

BETA 2: SIDE LANES THROUGH MID
  In b1 every route crossed the open atrium. Now each side of the atrium is a
  two-storey covered lane, walled off from the arena by an arcade wall (0-384):
    - UNDERCROFT (floor 0): the space under each bridge, now a corridor. It joins
      one team's lower hall (through that team's side arch) to the stair up to the
      bridge, and has two doors into the arena: one right beside the other team's
      arena arch, one toward the far end.
    - BRIDGE (256): walled on the arena side (128 high: covers you even mid-jump),
      with one wide window, the loggia, over the Quad. Drop through it to the arena.
    - The atrium stairs now start in the undercroft (in the alcove past each
      bridge), so undercroft + stair + bridge is one covered climb.
  The arena in the middle stays open: Quad, both arena arches, four lane doors,
  the two loggias above and the deck ends overlooking it.
  Mid crossings for a carrier: through the arena (fastest, exposed); along a
  bridge (covered); in through an undercroft and up its stair to the bridge
  (covered, changes level); and the reverse, down a stair into an undercroft.
  The top of the arcade wall (384) is a hook perch, nothing more.

CONCEPT B, "STRATA": two whole levels, one stacked on the other.
  - LOWER HALLS (floor 0, ceiling 224) run underneath the whole way, base to base:
    a low pillared hall in each half.
  - UPPER DECKS (floor 256) run on top of them: a north deck and a south deck in
    each half, joined by a WELL ROOM in the middle of the half.
  - A 32-unit slab separates the two levels; you hear fights through it, not see them.
  - MID ATRIUM: the one tall room. An open arena with the Quad in the middle, a
    covered lane down each side (see above).
  - Each half has a WELL: a hole through the slab from the well room down into the
    lower hall. Drop down, or hook back up.
  - The FLAG sits on a mezzanine (128) between the levels at the back of each base:
    broad steps down to the base floor (the lower route), and stairs up to the
    base's north and south balconies (256), which carry the decks in.
  The map is a 180-degree rotation (like Bastion): each team sees its own base the
  same way.

THE RUNS, flag to flag (shortest walking line, measured on the grid)
                                         units   fast pace (460 u/s)  carrier (320 u/s)
  lower halls, through the arena         5,740       12.5 s              18 s
  upper decks and a bridge (covered)     6,050       13 s                19 s
  gate to gate without the arena         6,430       14 s                20 s
    (undercroft, stair, bridge, deck, drop down the well)
  The covered bridge costs a carrier under a second over the arena.
  For reference: Bastion ~5,500 units; Circuit 6,100-7,300; ctf1 caps took 20-21 s.

READABILITY (the risk this design carries)
  Only five kinds of link between the levels, all big and easy to read: the flag
  mezzanine (in each base), the base balconies, the atrium stairs (in the side
  lanes), the bridge loggias and deck ends (drop into the arena), and the wells
  (drop only, unless you hook or rocket jump).
  Each level stays a straight-ish run: the decks have staggered wall stubs (a
  slalom, not a corridor you can see down), the lower halls have columns, a
  baffle inside each arch and a pier facing each base gate. Longest straight
  sightline: ~1,900 units (along a bridge into the far deck); on the lower level
  ~1,260 anywhere.

BASES (blue described; red is the rotated copy)
  Base gate (floor 0) from the lower hall; balconies (256) from both decks; the
  flag on the mezzanine at the back. Three ways out for a carrier: steps down to
  the gate, stairs up to either balcony. Team starts: 4 on the base floor, 4 on the
  balconies.

ITEMS (weapons stay in KTX CTF; each half has the same set)
  Quad - the arena.  YA - one on each bridge.  Mega - each well room.
  RA - each lower hall, base end.  RL - north deck.  SNG - south deck.
  LG - lower hall.  GL - lower hall, atrium end.  SSG - base floor.
  NG - north balcony.  GA - south balcony.  Health and ammo on both levels,
  a health in each undercroft.

CHECKED IN THIS BUILD
  - compiles with no leaks; full vis; lightmaps; standard BSP29
  - everything reachable on foot (no hook needed), no traps
  - respawns picked by a solver: no two (or their rotated copies) can see each
    other, none near a flag or on the flag mezzanine (b2 only added walls, so b1's
    respawns still hold; re-checked)
  - every stair's foot is clear across its full width; no 16-unit slots
  - items on clear floor, none on a spawn, a wall or a step edge

FILES
  ctf_strata_b6.bsp / .map / .wad
  ctf_strata_b6_plan.png        top-down plan: lower level, upper level
  ctf_strata_b6_views.png       preview renders (same cameras as b2-b5)
  ctf_strata_b6_signs.png       before / after: each sign removed or moved
