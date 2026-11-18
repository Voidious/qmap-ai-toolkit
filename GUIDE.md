# Building Quake 1 / QuakeWorld maps with an AI model — field guide (v2)

This guide and toolkit come out of building eight multiplayer maps for one QuakeWorld group:
Clan Arena (Agora, Vigil, Crucible, Cistern, Lyceum), FFA (Relay) and CTF (Bastion, Circuit).
They went through about 80 delivered builds of feedback from real play and in-client screenshots,
plus an analysis of 29 demos of the group's games. Everything here was learned the hard way.

Read section 3 before you design anything and section 9 before you texture anything.

The code is a starting point, not a framework, and not a cage. Each map's layout and look are
written fresh on top of a shared core, and every map so far extended that core when the design
needed something it couldn't do. **The toolkit's limits are not the map's limits.**

---

## 1. What's in the box

```
template/               START HERE for a new map
  _core.py              settings (name, symmetry, bounds, light scale), the grid, every building
                        primitive, texture mapping - edit the SETTINGS block
  _layout.py            the map itself - a small demo you replace
  _itemh.py, _items.py  item helper / your items
  _out.py               .map + .json writer: per-face texturing, wall bands, lamp placer, skins
  texgen_blockout.py    plain zone-coloured textures for layout builds (height marks on walls)
  build.sh              generator -> qbsp -> vis -> light -> check.py
  plan.py, views.py     top-down plan image; preview renders with a brightness readout
qmap/                   shared tools - reuse as is
  check.py              reachability (walk / jump / teleport / push), traps, spawn sightlines,
                        item placement, perches, stair feet, 16-unit slots
  pick_spawns.py        spawn solver: the largest set of spots with no mutual line of sight
  pick_spawns_sym.py    the same for symmetric maps (SYM=rotate or SYM=mirror)
  routes.py             walking routes and times between flags (or any two points), per run
  sightlines.py         longest straight sightline per floor level
  contact.py            Clan Arena pacing proxy (compare against a map the group likes)
  collide_cmp.py        prove a visual-only build didn't change collision (voxel compare)
  render.py             software BSP renderer (lightmaps + textures) for preview images
  texgen.py, texgen_runic.py, texgen_cistern.py   procedural texture helpers, palette quantising
  fsq.py                error-diffusion quantising for colours the palette lacks (cream, ivory)
  makewad.py            palette PNGs -> WAD2;  quake_palette.lmp (LibreQuake, BSD-3)
  flagtime.py, strip_ill.py   older CTF timing / visual-build helpers
examples/               three finished maps that rebuild byte-identical from this folder
  ctf_bastion/          CTF, 180-degree rotation; rival forts; emblems, perches, side routes
  ctf_circuit/          CTF, mirror symmetry; "theta" racetrack; glazed-tile team colours,
                        strips that follow stairs, banners, inlays, a cupola, route timing
  ca_lyceum/            Clan Arena 8-12, asymmetric; hub + satellites; marble with error
                        diffusion, a sky oculus, columns with bases and capitals
gallery/                plan + preview sheet of all eight maps, and GALLERY.md
demos/                  MVD demo reader + CTF and Clan Arena analysis
```

Requirements: Python 3 with numpy, pillow, scipy, matplotlib; **ericw-tools** (qbsp, vis, light)
built from source; a QuakeWorld client (ezQuake) for the human to test in.

Prove your setup by rebuilding an example (each prints check results; the .map must match the
shipped one byte for byte):

```
export ERICW=/path/to/ericw-tools/build
cd examples/ca_lyceum
python3 texgen_lyceum.py ltex
python3 ../../qmap/makewad.py ca_lyceum_b5.wad $(sed 's/.*/&=ltex\/&.png/' ltex_names.txt)
bash build.sh
python3 views_lyceum.py ca_lyceum_b5.bsp views.png
```
(ctf_circuit: `texgen_citadel.py ctex`, `ctex_names.txt`, `ctf_circuit_b5.wad`;
ctf_bastion: see its build notes in section 13.)

---

## 2. Working with the human (the process that worked)

1. **Spec.** Mode (CA / FFA / TDM / CTF), player count (target and soft max), favourite and
   disliked maps, symmetric or not. Ask nothing else up front.
2. **Concept.** Before any blockout, draw two or three *structurally different* overall shapes
   as a one-page sketch (see section 3), with a recommendation and rough route lengths. Compare
   them with the gallery. The human picks. This step is cheap and it is the one that decides
   whether a map is a fresh take or a repeat.
3. **Layout blockout** with the blockout textures. Deliver `.bsp`, `.map`, `.wad`, a top-down
   **plan image**, **preview renders**, a README. The human runs around in game and reports.
4. **Layout fix rounds** — structural changes only. Re-run every check each build.
5. **Visual pass** — ask the human to pick a style: 3–4 concrete options with a recommendation,
   each *different from the group's existing maps* (name them). Collision must stay identical;
   prove it with `collide_cmp.py`.
6. **Texture touch-up rounds** driven by the human's in-client screenshots. They find what your
   renderer can't: palette tints, lightmap seams, misaligned edges. Fix the whole *class* of
   problem each time, not just the pictured spot.
7. **When the human dislikes something but can't say what**, don't describe alternatives:
   **mock up 2–3 options and render them from the human's own screenshot angles.** (Lyceum's
   duel hall: the pick was instant once three versions were on screen.)
8. **Every build gets a new filename** (`name_bN`). QuakeWorld clients cache maps by name and
   will not re-download a changed map that kept its name.
9. For each fix, send a **before/after render** of the exact spot and say what caused it.
10. Small additions (perches, banners, a cupola) can ride along with a visual pass — list every
    change that touches collision separately so the human knows what to re-test.

---

## 3. Design: fresh takes on classics

**What went wrong once.** Three maps in a row (Relay, Cistern, Lyceum) came out with the same
skeleton: a central hall at floor level, a broad stair up to a balcony strip along the north
edge, a sunken band along the south, a tall room in the west. Nobody chose it. Each map was
started by copying the previous map's files, the copied layout and heights became the default,
and the demo finding "hub + satellite rooms" read as a recipe that confirmed the habit. The
textures differed; the maps still felt alike. The group noticed before the builder did.

**What "fresh" means — and what it doesn't.** Freshness lives in the map's *skeleton* (how the
big spaces connect, where the levels are, how routes loop) and in its *identity* (one strong
idea per room, a distinct look). It does **not** mean avoiding proven building blocks. Hubs,
balconies, loops, broad stairs, a high ground with two ways up, a low route with cover, a
contested powerup room — these are the vocabulary of every good map, and they should be reused
freely. Chasing novelty at the level of every room leads straight to wacky, unplayable design.
Aim for *a fresh take on a classic form*, not for something no one has seen.

**The concept step (do it every time):**
1. Read the gallery (`gallery/GALLERY.md`): eight skeletons already built for this group.
2. Sketch two or three candidates that differ *in skeleton* from each other and from the
   gallery's — not just in room shapes. Ask: where is the high ground, where is the low ground,
   how many loops, what is the middle (a hall? solid? a courtyard? a bridge?), where do players
   meet first?
3. Measure before drawing conclusions: route lengths (`routes.py` on a quick blockout, or grid
   distance on the sketch), likely longest sightlines.
4. Recommend one, say in a line what is new about it and what classic it riffs on.

**Skeletons not tried yet** (starting points, not prescriptions): rooms stacked over rooms (two
full levels linked by shafts); a figure-8 (two loops sharing a courtyard); two hubs joined by
parallel routes; a ring of rooms round an open court; one huge room broken by structure; a
vertical map (tower, multiple storeys); diagonal halls or octagonal rooms.

**Starting from a copy anchors you.** Start from `template/` (an empty demo) — not from the
last map's files. Use the examples for *techniques*: look up how Circuit makes strips follow
stairs, not where its rooms are.

**Extend the core when the design needs it.** Things added during these eight maps, each because
a design wanted it: mirror symmetry, light strips that follow stairs, floor and ceiling inlays,
picture panels, a sky oculus, columns with bases and capitals, hook-only perches, teleporters,
jump pads, liquids. Known gaps today: diagonal and curved walls (the grid is 16-unit axis-aligned
columns), sloped floors, doors and lifts, moving brushes. If a design needs one, write it.

---

## 4. Generator architecture (`template/`)

* **Grid**: 16-unit columns; `cols[i][j]` is a list of solid segments `[z0, z1, material]`. Rooms
  can stack (several air gaps per column). Greedy merging turns columns into brushes.
* **Symmetry** (`SYM` in `_core.py`): `'none'` (asymmetric — write everything), `'rotate'`
  (180-degree rotation; Bastion), `'mirror'` (about x = 0, north stays north; Circuit). With
  symmetry you write the x > 0 half; every primitive takes `sym=True` to add the copy, and things
  straddling the middle are written once with `sym=False`. Mirror keeps "the north route is the
  high route" true for both teams; rotation gives each team the same view of its own base.
* **Primitives**: `carve` (room; `door=True` for passages), `fill` (solid; `None` = structure,
  or a material), `stairs`, `terrace` (wall-to-wall broad steps off a platform edge), `pyramid`
  (steps on several sides, corners wrap), `lamp`/`room_lamps`, `spawn`, `team_spawn`,
  `carve_pair` (different theme on the copy: blue / red), `perch`, `teleporter`, `jumppad`,
  `liquid`, `panel` (non-solid picture: emblem, banner), `inlay` (floor/ceiling texture anchored
  to its own rect), `oculus` (ceiling becomes sky; texture only), `strip_ramp` /
  `strip_ramp_pos` (light strips that follow stairs), `label` (plan text).
* **Themes**: every carved space has a theme. The first carve of a theme sets its main floor
  (`ZONE_FLOOR`) and light-strip height (`STRIPE_Z`, default floor + 128). `textures()` maps
  (kind, theme, band) to texture names — replace it in the visual pass.
* **Faces are textured from the space they face**, not from the brush: a wall's texture comes
  from the room on that side. That keeps bands continuous round corners and lets one solid wall
  carry two rooms' looks.
* **Wall bands** (bottom to top): kickplate (`base`), wall, light strip (`strp`, fullbright),
  wall, cornice (`trim`); a sill trim under raised openings; risers on edges only a step tall.
  Wall texture is anchored to the band below it (kickplate top, or strip top), so panels line up.
* **Detail is non-solid** (`func_detail_illusionary`): wall lamps, panels, banners. It never
  changes collision.
* **Floor minlight**: walkable tops get a 16-unit skin brush in a `func_group` with `_minlight`
  so floors never go black while walls stay moody. Free-standing blocks (crates, columns) get it
  too, so their sides aren't black.
* The generator writes a **JSON** (grid, spawns, items, perches, stair feet, labels) that the
  checker, solvers, route tools and plan renderer read.

---

## 5. Checks — run them every build

* **qbsp leak** = failure. **Spawns**: no two can see each other (`pick_spawns*.py` solves for
  the largest set; 16 for 8–12 players with headroom); spacing ≥ ~256–288; ≥ 192 from weapons,
  armour and powerups; out of flag rooms. Re-solve after any geometry change.
* **Connectivity**: every spawn reaches every other; every item reachable. **Unreached floor**
  is reported at every height: crate tops and decoration are expected (say so), anything else
  is a bug.
* **Traps**: every reachable spot has a route back.
* **Stair feet**: the floor in front of every stair's bottom step must be clear across its full
  width — catches stairs running into a pillar or a wall stub.
* **16-unit slots**: gaps a player can see but not fit into (a notch between a stub and a step).
* **Items**: clear floor margin (QW servers drop items whose box starts in solid), not on a step
  edge, not on a spawn. **Perches** must need the hook (not reachable with a plain jump).
* **Routes** (`routes.py`): measure every distinct run between the flags with `--run`. Report
  units and seconds at 320 u/s (real carriers in our demos) and 460 u/s (a solo hook run).
* **Sightlines** (`sightlines.py`): a clear line the length of a route is usually a problem.
  On Circuit the first blockout had a line down the whole north arc; staggered rooms and offset
  lanes cut the longest to ~2,100 units within one half.
* **Pacing** (`contact.py`, CA): compare the spawn spread against a map the group likes.
* **Visual-only builds**: `collide_cmp.py old.map new.map` → "collision identical", or explain.
* **Brightness**: `views.py` prints a mean per view; keep it in the range of the group's maps.

---

## 6. Textures (all original, generated in code)

* Generate RGB procedurally, then **quantise to the Quake palette**. Fullbright (glowing)
  colours are palette indices **224–254**; assign them directly for strips, lamps, glows. There
  is **no bright green fullbright**.
* **Palette traps**: dark greys come in two families — 0–15 neutral, 32–47 blue-grey; a "neutral
  charcoal" quantises blue (`neutralize()` in Bastion's generator). Low-saturation noise turns
  into **green or purple specks**. **There is no cream or ivory**: pale marble goes pink or grey
  under nearest-colour quantising. `qmap/fsq.py` (error diffusion over the grey and warm ramps)
  mixes them into cream — use it for stone, plaster, wood; **never for saturated colour** (reds
  speckle). For mixed textures (glazed tile set in sandstone) diffuse the stone and quantise the
  tile to nearest colour through a mask (`examples/ctf_circuit/texgen_citadel.py`).
* **Look at the quantised PNG**, as a contact sheet, before building. Then look at the in-game
  result: the light changes it again (Pompeian red read as muddy brown under lamplight).
* **Size textures to the object**, **anchor them to the object** on both axes: boxes and columns
  from their own corner and top (a column built from several brushes uses the whole column's
  corner); plates and medallions from their own rect (`inlay`, `stand`); walls from the band
  below. **Floor patterns: centre them on the room** (`FLOOR_OFFSET`) — a pattern starting at one
  wall leaves a stray band along the other, and a pattern cut across a platform reads as an
  error; give platforms their own fitted texture.
* **Light strips that change level** must meet the strip in the room above and below at every
  corner. `strip_ramp` (floor + offset) works when the stairwell's walls line up with the rooms;
  when a neighbouring wall meets the stairwell part-way up, start the climb before the stairs with
  `strip_ramp_pos` (Circuit's cellar stairs). Clamps every 32: shift strips by half a clamp
  (`STRIP_SHIFT`) when clamps should land on step corners.
* Pictures (`panel`): emblems and banners on non-solid panels, the right way round from both
  sides; size them about two thirds of first instinct.
* **Each map needs its own look** — palette, materials, one idea per room. Before proposing
  styles, list the group's existing maps' looks and stay clear of them.

---

## 7. Lighting

* ericw `light` with `-extra4 -minlight 5 -minlight_dirt 0`; floors get their own minlight.
* The human's eye is the reference. Calibrate your renderer to their screenshots once (client
  brightness ≈ 255·(raw/255)^0.55). Measures in this project: DM2 ~35, gothic map ~32–43,
  preferred maps ~45–60. "As dark as gameplay allows; no black floors; not fiesta-bright."
* **Material changes brightness**: pale marble needed the global lamp scale cut by a third to
  sit with the other maps; black-painted walls needed lamps raised. Re-measure after a visual
  pass, not only after layout changes.
* Tall rooms need stronger ceiling lamps; hang them 40 below the ceiling (no glare pool on it).
  Free-standing columns get unlit faces under a lamp directly above — light the lanes beside them.
* Lamp colour carries mood; **team colour lives in textures and fullbright strips**, not in
  coloured lightmaps (not every client loads `.lit`).
* **Sky** is a texture on a ceiling; in CTF the **grapple sticks to sky**, so keep sky out of
  reach or accept it as an anchor.

---

## 8. Gameplay lessons

* **Stairs** must be walkable from the side: wall-to-wall broad steps; no zigzag side treads; a
  bottom step never pokes into a doorway; the foot of a stair is open floor across its width.
* Leave ≥ 64 behind cover near doors (32 = exactly a player, reads as blocked); no 16-unit notches.
* **trigger_push replaces velocity** — angle the push (pitch about −60 to −80) for jump pads.
* Liquids need texture names starting `*water` / `*slime` / `*lava`.
* **KTX CTF**: flags `item_flag_team1/2`; base spawns `info_player_team1/2` (also written as
  `..._deathmatch` for `k_ctf_based_spawn 2`); `info_player_deathmatch` are respawns *and* rune
  spots. KTX `ctf` defaults: deathmatch 3 (weapons stay), based spawn 1, hook off, runes off, GA
  on spawn. Check in game: `status1`, `status2`. KTX names demos by mode — a demo called `ca_...`
  on a CTF map is a Clan Arena game.
* **Hook-only perches** are a good second layer in CTF: slabs too high to jump to, stocked with
  ammo or small health, not armour.

### What real demos showed (22 CA + 7 CTF-map games of this group)

* **Clan Arena**: ~80–85% of kills are rocket; median kill distance ~190–390 units; first kill
  ~5–12 s into a round; rounds ~35–55 s on good maps. CA on a CTF-sized map (ctf1): ~70 s rounds,
  ~11 s to first contact — too big. dm6 = hub + distinct rooms + short corridors (corridors are
  low-lethality transit). Players live on high ground when it exists; open floors and pits become
  kill zones. *These are findings to design against, not a layout to copy.*
* **CTF**: real carriers move ~250–350 u/s; solo hook runs are much faster — don't panic about
  fast solo times. Captures convert ~1 in 5 pickups. About half of carrier deaths happen at or
  near the enemy flag: give flag rooms 2–3 exits. Loops let carriers kite (ctf1); a single
  straight spine makes mid irrelevant (ctf3); a maze with close flags is disliked (ctf6). Our maps:
  Bastion ~5,500 units flag to flag (~12–14 s for the group's fast runs), Circuit 6,100–7,300 by
  three runs (~13–16 s solo, ~19–23 s carrier pace); ctf1 caps took 20–21 s.
* **In a "theta" (two arcs plus a middle route)**, a cross-over through the middle can never be a
  shortcut between arcs — it adds the distance between them. Make the middle its own direct run.

---

## 9. Gotchas (each cost at least one round of feedback)

1. Wall lamps placed per cell clip into corners, hang off pillars and sit on strips — place them
   on straight runs of room wall, centred, one height per wall, clear of every strip *including
   strips that follow stairs*.
2. A kickplate stepping down beside stairs looks bad — keep it level and end it.
3. The top step of a stair is the platform's edge — texture it as a step (riser), not wall.
4. A thin sliver of wall between a strip and an opening above wants a sill trim.
5. A face exactly 16 tall at a floor edge was half dark — the minlight skin must be 16, not 8.
6. Generator scripts that concatenate parts must be **regenerated** before building (a stale
   combined file silently rebuilt the old map). `build.sh` does it every time.
7. Rebuilding a WAD from a name list can drop hand-added textures (lava!) — diff WAD contents.
8. Changing geometry breaks the spawn set — re-solve.
9. The spawn solver must consider doorway passages, or it under-counts.
10. A floor pattern cut across a narrow ledge or a platform reads as an error — fit it (inlay) or
    centre it on the room.
11. **Never estimate in prose what you can compute**: routes, timings, brightness, sightlines.
12. A stair's bottom step 16 units from a pillar: the stair runs into it. The stair-feet check
    catches it now; move the pillar off the stair's corner rather than narrowing the stair.
13. A strip that follows stairs must meet both rooms' strips **at the corners**, and a corner can
    sit part-way up the stairs when a neighbouring room's wall is offset (Circuit's undercroft
    met its stairwell two steps up). Check every corner in a render.
14. Decals and inlays must skip sky faces (an oculus is a sky ceiling over the same rect).
15. Checker: "unreached floor" used to ignore everything below 0 — fixed; re-run old maps.
16. Pale materials and dark materials change perceived brightness by a lot — re-light after a
    visual pass.
17. Three maps in a row with the same skeleton — see section 3.

---

## 10. Demo analysis (MVD)

`demos/mvd.py` reads QuakeWorld MVD demos: player positions (~70 Hz), dead state, effects (flag
carriers glow: effects bit 16/32), prints (obituaries, flag events, round results). Coords are
short/8 unless FTE float-coords is negotiated; unknown messages skip the rest of their block.
`ctf_run.py` and `ca_run.py` produce the stats and heatmaps quoted above. A top-down heatmap of
time spent reconstructs any map's layout without the BSP. Analyse demos of *your own* maps once
the group plays them — that is the best feedback there is.

---

## 11. Licensing

All textures here are generated from code. The palette is LibreQuake's (BSD-3, notice included).
Don't copy id's or other maps' textures; don't redraw known emblems, logos or characters. Release
maps with their `.map` source.

---

## 12. Starting a new map

1. Copy `template/` to a new folder. Set `NAME`, `TITLE`, `SYM`, bounds in `_core.py`.
2. Do the **concept step** (section 3) and get the human's pick.
3. Delete the demo in `_layout.py` and `_items.py`; write the layout.
4. Blockout textures and build:
   ```
   python3 texgen_blockout.py bktex
   python3 ../qmap/makewad.py mymap_b1.wad $(cat wad_args.txt)
   bash build.sh
   python3 plan.py mymap_b1.json plan.png "My Map beta 1"
   python3 views.py mymap_b1.bsp views.png        # edit CAMS in views.py first
   ```
5. Solve spawns (`pick_spawns.py` or `pick_spawns_sym.py`), measure routes and sightlines, fix,
   rebuild, deliver with the plan, views, README.
6. Visual pass: write `texgen_<style>.py` (borrow techniques from the examples' generators),
   replace `textures()` / `fixture_tex()` / `light_color()` in `_core.py`, verify with
   `collide_cmp.py`.

Insist on: render and check before delivering; a new name every build; in-client screenshots
from the human for every visual round.

---

## 13. Example notes

* `ctf_bastion` (v1 example, unchanged): `python3 texgen_bastion.py btex`, then
  `python3 ../../qmap/makewad.py ctf_bastion_b19.wad $(for n in $(cat btex_names.txt); do printf "%s=btex/%s.png " $n $n; done)`, `bash build.sh`.
  Its `_out.py` predates some v2 fixes (8-unit floor skin, no sill bands) — prefer the template's.
* `ctf_circuit`: `routes.py` (named runs) and `routes_fig.py` draw the three runs;
  `pick_spawns_sym.py` with `SYM=mirror HALF_X0=128 HALF_X1=3104 FLAGR=512`.
* `ca_lyceum`: `details_lyceum.py` renders the close-ups used in texture rounds.
* Each example's `README.txt` is the one shipped to the group, with its change history.
