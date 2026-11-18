# Building Quake 1 / QuakeWorld maps with an AI model — field guide

This guide and toolkit come out of building five multiplayer maps for a QuakeWorld group:
Clan Arena (Agora, Vigil, Crucible, Cistern), FFA (Relay), and CTF (Bastion). The maps went
through roughly 80 builds of feedback from real play and in-client screenshots. Everything
here was learned the hard way. Read it before starting, and treat the **Gotchas** section as
mandatory.

The code is a starting point, not a framework: each map's *layout* and *texture style* are
written fresh per map on top of the shared core. Expect to read and adapt the code.

---

## 1. What's in the box

```
qmap/                       shared core - reuse as is
  check.py                  map checker: reachability (walk/jump/teleport/push), traps,
                            item placement, spawn line-of-sight; run on the generator's JSON
  render.py                 software BSP renderer (lightmaps + textures) for preview images
  texgen.py                 heightmap/noise/colourise helpers for procedural textures
  texgen_runic.py           palette quantising (fullbright-aware), saving, rivets, glyphs,
                            emblem/medallion rendering (polygon shapes -> raised cast emblem)
  texgen_cistern.py         stone helpers: ashlar courses with per-block tone, water stains
  makewad.py                PNGs (already in Quake palette) -> WAD2
  quake_palette.lmp         Quake palette (from LibreQuake, BSD-3; licence file alongside)
  pick_spawns.py            spawn solver: max set of spots with no mutual line of sight
  pick_spawns_sym.py        same, for maps symmetric by 180-degree rotation (pairs)
  strip_ill.py, collide_cmp.py   prove a "visual-only" build didn't change collision
  flagtime.py               CTF: shortest walking route between flags, per route
examples/ctf_bastion/       a complete map: generator parts, texture generator, plan and
                            preview scripts, build.sh (rebuilds the shipped map exactly)
demos/                      MVD (multi-view demo) reader + CTF and Clan Arena analysis
```

Requirements: Python 3 with numpy, pillow, scipy, matplotlib; **ericw-tools** (qbsp, vis,
light) built from source; a QuakeWorld client (ezQuake) for the human to test in.

Rebuild the example (proves your setup works):

```
cd examples/ctf_bastion
export ERICW=/path/to/ericw-tools/build
python3 texgen_bastion.py btex
python3 ../../qmap/makewad.py ctf_bastion_b19.wad $(for n in $(cat btex_names.txt); do printf "%s=btex/%s.png " $n $n; done)
bash build.sh                      # generator -> qbsp -> vis -> light -> check.py
python3 views_ctf.py ctf_bastion_b19.bsp views.png
```

---

## 2. Working with the human (the process that worked)

1. **Spec**: mode (CA / FFA / TDM / CTF), player count (target and soft max), favourite and
   disliked maps, symmetric or not. Ask nothing else up front.
2. **Layout blockout** with placeholder textures that make areas distinguishable. Deliver:
   `.bsp`, `.map`, `.wad`, a top-down **plan image** (both levels, items, spawns), **preview
   renders**, a README. The human runs around in-game and reports.
3. **Layout fix rounds** — structural changes only. Re-run every check each build.
4. **Visual pass** — ask the human to pick a style (offer 3–4 concrete options with a
   recommendation). Collision must stay identical; prove it with `collide_cmp.py`.
5. **Texture touch-up rounds** driven by the human's in-client screenshots. These find things
   your renderer can't: palette tints, lightmap seams, misaligned edges. Expect many rounds of
   small nits; fix the whole *class* of problem each time, not just the pictured spot.
6. **Every build gets a new filename** (`name_bN`). QuakeWorld clients cache by name and
   will not re-download a changed map that kept its name.
7. For each fix, send a **before/after render** of the exact spot, and say what caused it.

---

## 3. Generator architecture

* **Grid**: 16-unit columns. `cols[i][j]` is a list of solid segments `[z0, z1, material]`.
  Rooms are `carve(rect, floor, ceiling, theme)`; solid blocks are `fill(rect, z0, z1, mat)`.
  Stairs: `stairs()` (one run), `terrace()` (wall-to-wall broad steps down one side of a
  platform), `pyramid()` (steps that wrap corners). Greedy merging turns columns into brushes.
* **Symmetry**: `sym=True` writes a 180-degree rotated copy (`rot()`); team maps write one half.
* **Themes / zones**: every carved space has a theme; `ZONE_OF` maps theme -> texture set,
  `ZONE_FLOOR` and `STRIPE_Z` give each zone its floor and light-strip heights.
* **Faces are textured from the space they face**, not from the brush: a wall's texture comes
  from the room on that side. That's what keeps bands continuous around corners.
* **Wall bands** (bottom to top): kickplate (`base`), wall, light strip (`strp`, fullbright),
  wall, cornice (`trim`). Doorways get a frame. Bands are cut into separate brushes at the
  band heights.
* **Detail is non-solid** (`func_detail_illusionary`): wall lamps, emblems, pipes. It never
  changes collision.
* **Floor minlight**: walkable tops are split into a thin skin brush inside a
  `func_group` with `_minlight`, so floors never go black while walls stay moody. Use a
  **16-unit** skin for new maps: with 8 (still in the Bastion example's `_out.py`, line
  ~254) the lower half of 16-tall risers and sills can go dark where no lamp reaches.
* The generator also writes a **JSON** of the grid, spawns, items, perches — that's what
  `check.py`, the spawn solver and the plan renderer read.

---

## 4. Checks — run them every build

* **qbsp leak** = failure. **Spawns**: no two can see each other (`pick_spawns*.py` solves
  for the largest set; ~16 for 12–14 players); spacing ≥ ~256; keep them ≥ 192 from weapons,
  armour and powerups, and out of flag rooms.
* **Connectivity**: every spawn reaches every other; every item reachable (teleports and push
  pads are graph edges; gap jumps need the landing ≥ 24 lower).
* **Trap check**: every reachable spot has a route back (reverse reachability). Catches
  pits you can drop into but not leave.
* **Item margin**: QW servers drop items whose bounding box starts in solid — keep a clear
  4×4-cell floor margin around each item.
* **Visual-only builds**: strip illusionary entities and voxel-compare solids against the
  last build (`collide_cmp.py`): 0 differing voxels or explain why.
* **Wall lamps**: validate every one — solid wall behind it extending past both edges, air in
  front, not overlapping a band.
* **CTF timing**: `flagtime.py`. Measure *route length in units*, then convert with a pace.

---

## 5. Textures (all original, generated in code)

* Generate RGB procedurally, then **quantise to the Quake palette**. Fullbright (glowing)
  colours are palette indices **224–254**; assign those indices directly for light strips,
  lamps, emblem glows. There is **no bright green fullbright**.
* **Palette trap**: the darkest greys come in two families — indices 0–15 are neutral, 32–47
  are blue-grey. A "neutral charcoal" quantises into the blue ramp and reads as blue in game.
  Force neutral surfaces onto 0–15 (see `neutralize()` in the Bastion texture generator).
* Low-saturation noise can quantise into **green or purple specks** (e.g. water stains on
  dark stone). Check the quantised PNG, not your RGB.
* **Size textures to the object**: box sides as tall as the box; column faces exactly one
  face wide; panels sized so whole panels fit between kickplate, strip and cornice
  (e.g. 64×48 panels).
* **Anchor textures to the object**, both axes: boxes and columns from their own corner and
  top (a column built from several brushes must use the *whole column's* corner/top); flag
  stands and plates centred; walls from the band below them (kickplate top, or strip top).
* Light strips have clamps every 32: shift by half a clamp so clamps land on step corners
  when a strip climbs stairs.
* Emblems: polygon shapes rendered as raised cast metal on a medallion (see
  `tex_sigil`); sized ⅔ of first instinct; mirrored faces need the texture scale sign fixed.

---

## 6. Lighting

* ericw `light` with `-extra4 -minlight 5 -minlight_dirt 0`; floors get their own minlight.
* The human's eye is the reference. Calibrate your renderer to their screenshots once
  (client brightness ≈ 255·(raw/255)^0.55). Reference measures in this project: DM2 ~35,
  gothic map ~32–43, preferred maps ~48–58. "As dark as gameplay allows; no black floors; not
  fiesta-bright."
* Tall rooms need stronger ceiling lamps; dark stone needs extra fill. **Free-standing
  columns** get unlit faces when lamps hang directly above them — add soft fill lights beside
  each face, or hang lamps over the lanes, not the centreline.
* Lamp colour carries mood (warm lamps / cool sun); team colour lives in **textures and
  fullbright strips**, not coloured lightmaps (not all clients load them).

---

## 7. Gameplay lessons

* **Stairs** must be walkable from the side. Use wall-to-wall broad steps; avoid zigzag side
  treads; never let a bottom step poke into a doorway (move the door flush instead).
* Leave ≥ 64 behind crates/cover near doors (32 = exactly a player, reads as blocked).
* **trigger_push replaces velocity** — angle the push (e.g. pitch −78) for jump pads.
* Lava needs a texture named `*lava…`; water `*water…`.
* Teleporters: `trigger_teleport` + `info_teleport_destination`; make a "pad" a real
  teleporter or don't make it look like one.
* **KTX CTF**: flags `item_flag_team1/2`; base spawns `info_player_team1/2` (also write
  `info_player_teamN_deathmatch` for `k_ctf_based_spawn 2`); `info_player_deathmatch` are
  respawns *and* rune spots. KTX `ctf` mode defaults: deathmatch 3 (weapons stay),
  based spawn 1, hook off, runes off, GA on spawn. The **grapple sticks to sky** — avoid sky
  over CTF play space, or accept that it's an anchor. Check in game: `status1`, `status2`.
* **Hook-only perches** (CTF) are a great second layer: slab ledges too high to jump to,
  stocked with ammo (not health/armour), square-patterned tops so orientation doesn't matter.

### What real demos showed (22 CA + 5 CTF games of this group)

* **Clan Arena**: ~80–85% of kills are rocket; median kill distance ~190–390 units; first
  kill 5–12 s into a round; rounds ~35–55 s on good maps (74 s on a too-big map). dm6 =
  hub + 3 distinct rooms + short corridors; corridors are low-lethality transit. Players live
  on high ground when it exists; open floors/pits become kill zones.
* **CTF**: real carriers move ~250–350 u/s (hook use is light in practice); solo test runs
  with the hook are ~2× faster than real captures — don't panic about fast solo times.
  Captures convert ~1 in 5 pickups. About half of carrier deaths happen at/near the enemy flag:
  design flag-room exits deliberately. Loops let carriers kite (ctf1); a straight spine makes
  mid irrelevant (ctf3); a maze with close flags is disliked (ctf6). Aim ~5,000–6,000 units of
  route between flags.

---

## 8. Gotchas (each cost at least one round of feedback)

1. Wall lamps placed per-cell clip into corners, hang off pillars and sit on light strips —
   place them on **straight runs of room wall**, centred, at one height per wall, then validate.
2. Kickplate logic: no kickplate on raised platforms… but a balcony that *is* a route needs
   one. A kickplate stepping down beside short steps looks bad — end it instead.
3. The top step of a stair is the platform's edge — texture it as a step (riser), not wall.
4. A thin sliver of wall between a strip and an opening above it wants a trim band (sill).
5. A face exactly 16 tall at a floor edge was half-dark — minlight skin must be 16, not 8.
6. Generator scripts that concatenate parts must be **regenerated** before building (a
   stale combined file silently rebuilt the old map).
7. Rebuilding a WAD from a name list can drop textures added by hand (lava!) — diff the WAD
   contents against the previous build.
8. Changing geometry breaks the spawn set (a moved crate opens a sightline) — re-solve.
9. The spawn solver must consider doorway passages, or it under-counts.
10. Floor pattern alignment: a pattern cut across a narrow ledge reads as an error — shift it
    so whole tiles fit, or use a plain texture on narrow strips.
11. Never estimate in prose what you can compute: routes, timings, brightness, sightlines.

---

## 9. Demo analysis (MVD)

`demos/mvd.py` reads QuakeWorld MVD demos: player positions (~70 Hz), dead state, effects
(flag carriers glow: effects bit 16/32), prints (obituaries, flag events, round results).
Coords are short/8 unless FTE float-coords is negotiated; unknown messages skip the rest of
their block. `ctf_run.py` and `ca_run.py` produce the stats and heatmaps quoted above. A
top-down heatmap of time spent reconstructs any map's layout without the BSP.

---

## 10. Licensing

All textures here are generated from code. The palette is LibreQuake's (BSD-3, notice
included). Don't copy id's or other maps' textures, and don't redraw known emblems or logos.
Release maps with their `.map` source.

## 11. Starting a new map with another model

Give the model this guide and the toolkit, then: copy `examples/ctf_bastion/` to a new
folder, keep `_core.py`, `_out.py`, `_itemh.py`; rewrite `_layout.py` and `_items.py`; write
a new `texgen_<style>.py` from the Bastion one; set the map name in `_core.py`, `_out.py`
(message, wad) and `build.sh`. Insist that the model renders and checks before delivering,
and that you send in-client screenshots for every visual round.
