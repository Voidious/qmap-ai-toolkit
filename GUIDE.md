# Building Quake 1 / QuakeWorld maps with an AI model — field guide

This guide and toolkit grew out of building nine initial multiplayer maps for one QuakeWorld group —
Clan Arena (Agora, Vigil, Crucible, Cistern, Lyceum), FFA (Relay), and CTF (Bastion, Circuit,
Strata) — followed by newer vertical layouts, ~85+ delivered builds of playtest and screenshot
feedback, demo analyses of the group's games, and quantitative height and item surveys against
classic QuakeWorld maps. Everything here was learned the hard way.

Read section 3 before you design anything (especially *Design for height*) and section 9 before
you texture anything. Treat the process, style notes, and numeric ranges here as **calibrated
starting points and diagnostics**, not rigid laws — adapt them to your mode, map concept, and
group's taste.

The code is a starting point, not a framework, and not a cage. Each map's layout and look are
written fresh on top of a shared core, and every map so far extended that core when the design
needed something it couldn't do. **The toolkit's limits are not the map's limits — extend
`template/`, `qmap/`, and this guide whenever a design or workflow outgrows them.**

---

## 1. What's in the box

```
template/               START HERE for a new map
  _core.py              settings (name, symmetry, bounds, light scale), the grid, every building
                        primitive, texture mapping - edit the SETTINGS block. v3: ramps, prisms
                        (chamfers, diagonal walls, octagonal pillars), team halves
  _layout.py            the map itself - a small demo you replace
  _itemh.py, _items.py  item helper / your items
  _out.py               .map + .json writer: per-face texturing, wall bands, lamp placer, skins;
                        v3: ramp wedges with sloped bands, prisms with Valve 220 texture axes
  texgen_blockout.py    plain zone-coloured textures for layout builds (height marks on walls)
  build.sh              generator -> qbsp -> vis -> light -> check.py -> vprofile.py --check --targets
  plan.py, views.py     top-down plan image; preview renders with a brightness readout
qmap/                   shared tools - reuse or extend as needed
  check.py              reachability (walk / jump / teleport / push), one-way traps, blind
                        pockets, spawn sightlines, item placement, perches, stair feet, 16-unit
                        slots, prism separation (< 64)
  pick_spawns.py        spawn solver: the largest set of spots with no mutual line of sight
  pick_spawns_sym.py    the same for symmetric maps (SYM=rotate or SYM=mirror)
  routes.py             walking routes and times between flags (or any two points), per run
  sightlines.py         longest straight sightline per floor level
  contact.py            Clan Arena pacing proxy (compare against a map the group likes)
  collide_cmp.py        audit visual-pass collision diffs (player + hull-0 voxel compare)
  render.py             software BSP renderer (lightmaps + textures) for preview images
  texgen.py, texgen_runic.py, texgen_cistern.py   procedural texture helpers, palette quantising
  fsq.py                error-diffusion quantising for colours the palette lacks (cream, ivory)
  makewad.py            palette PNGs -> WAD2;  quake_palette.lmp (LibreQuake, BSD-3)
  vprofile.py           compiled BSP29 player-hull check (--check: connectivity, traps, narrow
                        passages, blind pockets) + verticality & travel-distance profile (--targets)
  itemprofile.py, itemcheck.py, ITEMS.md   BSP29 item-economy diagnostics (inventories, directed
                        routes, RL/LG/resource trios, hypothetical --move) and MVDSV edict verification
  section.py, iso.py    side-on slices and isometric cutaways of a map from its JSON
  flagtime.py, strip_ill.py   older CTF timing / visual-build helpers
examples/               four finished maps whose Python sources rebuild cleanly from this folder
  ctf_bastion/          CTF, 180-degree rotation; rival forts; emblems, perches, side routes
  ctf_circuit/          CTF, mirror symmetry; "theta" racetrack; glazed-tile team colours,
                        strips that follow stairs, banners, inlays, a cupola, route timing
  ca_lyceum/            Clan Arena 8-12, asymmetric; hub + satellites; marble with error
                        diffusion, a sky oculus, columns with bases and capitals
  ctf_strata/           CTF, rotation; two stacked levels, covered side lanes, light wells;
                        stratified walls, team lights by half, direction signs, a sun
gallery/                plan + preview sheet of the nine maps, GALLERY.md; profiles/: height
                        surveys (JSON + comparison figures); items/: reference item-placement survey
demos/                  MVD demo reader (mvd.py), in-play verticality (vert.py), and reference
                        CA / CTF analysis scripts (ca_run.py, ctf_run.py)
tests/                  checked-in unit & regression tests (collide_cmp, check/vprofile, versioning)
VERSION                 canonical SemVer version file
```

Requirements: Python 3 with numpy, pillow, scipy, matplotlib, numba; **ericw-tools** (qbsp, vis, light)
built from source; a QuakeWorld client (ezQuake) for the human to test in.

Verify the Python checks and test suite first (no `qbsp` required):

```
python3 -m unittest discover -s tests
```

Prove your full compile pipeline by rebuilding an example (each generates textures, compiles the BSP,
and runs `check.py` + `vprofile.py`; `ctf_strata` also lists its verified `.map` md5 in section 13):

```
export ERICW=/path/to/ericw-tools/build
cd examples/ca_lyceum
python3 texgen_lyceum.py ltex
python3 ../../qmap/makewad.py ca_lyceum_b5.wad $(sed 's/.*/&=ltex\/&.png/' ltex_names.txt)
bash build.sh
python3 views_lyceum.py ca_lyceum_b5.bsp views.png
```
(ctf_circuit: `texgen_citadel.py ctex`, `ctex_names.txt`, `ctf_circuit_b5.wad`;
ctf_bastion and ctf_strata: see their build notes in section 13.)

---

## 2. Working with the human (the process that worked)

1. **Spec.** Mode (CA / FFA / TDM / CTF), player count (target and soft max), favourite and
   disliked maps, symmetric or not — plus any theme or gimmick the human already has in mind. Keep
   the kickoff brief instead of interrogating the human with a long questionnaire before sketching.
   Size the map for its mode and player count by **travel distance**, not floor area (section 3,
   *Sizing a map*).
2. **Concept.** Before any blockout, draw two or three *structurally different* overall shapes
   as a one-page sketch (see section 3), with a recommendation and rough route lengths. Compare
   them with the gallery. The human picks. This step is cheap and it is the one that decides
   whether a map is a fresh take or a repeat. **Draw each one in section (side-on) as well as in
   plan**: where the levels are, what looks down on what, which routes climb. A plan alone hides
   exactly the thing our maps were short of (section 3, *Design for height*).
3. **Layout blockout** with the blockout textures. Deliver `.bsp`, `.map`, `.wad`, a top-down
   **plan image**, **sections** and an **iso cutaway** (`section.py`, `iso.py`), **preview
   renders**, a README. The human runs around in game and reports.
4. **Layout fix rounds** — structural changes only. Re-run every check and read the height
   profile (`build.sh` prints it) each build. **Settle the layout before the visual pass**: signs,
   inlays, bands and lamps are anchored to the geometry, so a structural change after the visual
   pass costs a texture round as well.
5. **Visual pass** — ask the human to pick a style: 3–4 concrete options with a recommendation,
   each *different from the group's existing maps* (name them). Structural changes (rooms, doors,
   main floor heights, routes) stay in step 4, but **bounded decorative architecture is welcome**
   — raised item plinths (≤ 16 units so players step right up, or with their own steps), column
   bases and capitals, door/arch frames, buttresses, wall reliefs/statues, railings, overhead
   beams, and cupolas — as long as movement lanes stay smooth and snag-free. Still run
   `collide_cmp.py` as an audit (exit 0 on pure texture rounds; otherwise confirm every diff is
   declared and catch silent contents bugs — see section 5 and gotcha 31), list every collision
   change by location in the build notes, and re-run the full check suite whenever collision
   changes.
6. **Texture touch-up rounds** driven by the human's in-client screenshots. They find what your
   renderer can't: palette tints, lightmap seams, misaligned edges. Fix the whole *class* of
   problem each time, not just the pictured spot.
7. **When the human dislikes something but can't say what**, don't describe alternatives:
   **mock up 2–3 options and render them from the human's own screenshot angles.** (Lyceum's
   duel hall: the pick was instant once three versions were on screen.)
8. **Every build gets a new filename** (`name_bN`). QuakeWorld clients cache maps by name and
   will not re-download a changed map that kept its name.
9. For each fix, send a **before/after render** of the exact spot and say what caused it.
10. Small decorative or gameplay-neutral additions (item plinths, frames, statues, perches,
    banners, a cupola) can ride along with a visual pass — list every change that touches
    collision by location in the build notes and re-run the full check suite so the human knows
    exactly what to re-test (section 5, *Visual-pass collision audit*).

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
1. Read the gallery (`gallery/GALLERY.md`): nine skeletons already built for this group, and
   their height profiles.
2. Sketch two or three candidates that differ *in skeleton* from each other and from the
   gallery's — not just in room shapes. Ask: where is the high ground, where is the low ground,
   how many loops, what is the middle (a hall? solid? a courtyard? a bridge?), where do players
   meet first?
3. Measure before drawing conclusions: route lengths (`routes.py` on a quick blockout, or grid
   distance on the sketch), likely longest sightlines.
4. Recommend one, say in a line what is new about it and what classic it riffs on.

**Skeletons not tried yet** (starting points, not prescriptions): a figure-8 (two loops sharing a
courtyard); two hubs joined by parallel routes; a ring of rooms round an open court; one huge room
broken by structure; a vertical map (a tower, a shaft with rooms opening off it at many heights);
diagonal halls or octagonal rooms (buildable since v3). Strata did two full levels stacked.

**Starting from a copy anchors you.** Start a new map's layout from `template/` (an empty demo) —
not by copying the previous map's room coordinates. Reuse techniques and custom primitives freely
(look up how Circuit makes strips follow stairs, not where its rooms are), or write a fresh
generator altogether when a concept wants one.

**Extend the core when the design needs it.** Things added during these maps, each because a
design wanted it: mirror symmetry, light strips that follow stairs, floor and ceiling inlays,
picture panels, a sky oculus, columns with bases and capitals, hook-only perches, teleporters,
jump pads, liquids, team colours by half, stratified walls, signs, true ramps, angled walls
(chamfers, diagonal walls, octagonal pillars), overhang architraves, and exposed-ramp veneers.
Known gaps today: curved walls (beyond prism approximations), diagonal ramps, sloped ceilings,
doors, lifts, and moving brushes. If a design needs one, build it (see section 4, *Extending the
toolkit*).

### Design for height

**What the surveys found.** After nine maps the group felt the layouts lacked vertical complexity.
`vprofile.py` measured all nine against **two classic QuakeWorld reference pools** from their
collision hulls alone:
* **Five compact / duel classics** (`aerowalk`, `ztndm3`, `dapak12`, `naked3`, `naked4`;
  `gallery/profiles/profiles.json`) — 1on1 / small-team maps (`travel_median` 823–1,148).
* **Ten larger QuakeWorld classics** (`gallery/profiles/large_refs.json`) — six well-regarded
  custom multi-player maps (`skull`, `bravado`, `spinev2`, `ultrav`, `schloss`, `cmt4`;
  `travel_median` 905–1,738) plus four canonical 4v4 TDM classics (`dm3`, `e2m2tdm`, `cmt3`,
  `e1m2`; `travel_median` 1,939–2,277). (`dm2` is omitted from the automated `vprofile` ranges
  because ~20% of its floor is button/swim/rocket-jump-gated in the walk+jump model.)

The full per-map tables are in [`gallery/GALLERY.md`](gallery/GALLERY.md).

| measure | 5 compact classics | 10 larger classics | our first nine maps |
|---|---|---|---|
| route height change per 1000 units, item to item | **251–551** | **87–215** *(6 customs: 120–215)* | 61–229 |
| item pairs whose route changes level | 0.89–0.96 | 0.75–0.98 *(8 of 10 ≥ 0.84)* | 0.65–0.95 |
| effective levels (64-unit bands) | 3.9–5.2 | **4.3–9.0** *(6 customs: 4.3–7.6)* | 2.0–4.1 |
| share of floor on the biggest level | 0.28–0.41 | **0.22–0.37** | 0.43–0.78 |
| stacked share (two floors ≥ 64 apart) | 0.19–0.21 | 0.07–0.26 | 0.00–0.32 |
| floor that can see floor ≥ 64 below it | 0.46–0.62 | 0.25–0.66 | 0.23–0.55 |
| of what you see, share ≥ 64 above or below | 0.31–0.42 | 0.17–0.47 | 0.17–0.42 |
| wall area that is not axis-aligned | 0.03–0.22 | 0.03–0.30 | 0 |
| teleporters | 2–5 | 2–7 | 0–2 |

**What holds at every scale — and what changes on larger maps:**
* **No classic puts half its floor on one flat slab.** Across all 15 reference maps (compact and
  large alike), `dominant_level` stays at **0.22–0.41** — and across all 10 larger classics it
  never exceeds **0.37** (0.29–0.37 on the six customs; 0.22–0.37 on the four 4v4 TDM legends).
  Our early maps sat at 0.43–0.78 because they treated one main floor as the default and hung side
  trips off it.
* **Larger maps add *more* elevation bands, not wider flat slabs.** Effective levels climb from
  3.9–5.2 on the compact classics to **4.3–7.6** on the six larger customs (`skull` 5.98,
  `schloss` 6.67, `cmt4` 7.55) and **5.3–9.0** on `e1m2`/`e2m2tdm`/`dm3`/`cmt3`.
* **Every reference map uses angled walls (`0.03–0.30`) and active teleporters (`2–7`).**
  Teleporters are also what keep larger multi-level footprints tight to traverse (`skull` has
  2,031k sq units of floor yet plays at `travel_median` 905).
* **Route height change per 1,000 units drops naturally with horizontal scale.** None of the 10
  larger classics hits the duel cohort's `≥ 250`: height span grows slowly (~270–688 units) while
  horizontal travel between pickups roughly doubles, so `route_vert_per_1000` sits at **120–215**
  on the six larger customs (`bravado` 215, `skull` 214, `schloss` 195, `cmt4` 187, `spinev2` 131,
  `ultrav` 120) and **87–212** on the four 4v4 TDM classics (`e1m2` 212, `cmt3` 187, `dm3` 162,
  `e2m2tdm` 87). Crucially, **`route_level_pairs` stays high (0.84–0.98 on 8 of 10)**: routes still
  change level on almost every item trip, just over longer horizontal runs. Do not force duel-scale
  `≥ 250` onto a large map.
* **Stacking and overlooks depend on architectural style.** `bravado` and `spinev2` both have
  `stacked_share = 0.07` and still feel strongly vertical through terraced levels and sightlines
  (`bravado`: `overlook 0.66`, `cross_sight 0.38`, `eff_levels 4.30`), while open/atrium-linked
  larger maps (`skull` 0.55/0.47, `schloss` 0.48/0.36, `dm3` 0.44/0.31, `cmt3` 0.46/0.30) keep
  high overlooks whereas walled room-and-corridor layouts (`ultrav` 0.25/0.23, `e2m2tdm` 0.29/0.18,
  `cmt4` 0.40/0.24) trade wide sightlines for tighter compartmentalized fights.

**Stacked is not vertical.** Strata stacks more floor than any classic (0.32 of the footprint has
a floor over or under it) and is still the flattest map to *play* (route height 61, dominant level
0.56, 2.5 effective levels): two big slabs, each crossed on its own level, a few links between
them. What counts is how often a route climbs or drops and what you see above and below you, not
how many storeys there are. Its light wells (holes in the slab you can look through, drop down and
hook back up) were the feature the group singled out.

**Targets.** `build.sh` runs `vprofile.py --check --targets` (`VPROFILE=0` skips it). For larger
multi-player or 4v4 TDM maps, run `vprofile.py map.bsp --targets --ref large` to compare against
the ten larger classics instead of the five compact duel classics. Treat both reference tables as
**diagnostics and comparisons, not release gates or proof of gameplay quality** — report where a
map sits, and never add token teleporters or move good items solely to push a metric across a
threshold. In particular, Clan Arena plays without item incentives, so item-route height cannot
validate CA circulation on its own.

**Give high ground a spatial counter.** Verticality works best when an upper advantage has a local
answer built into the fighting space: a short turn out of sight, a sheltered route passing
underneath, a second approach from another angle, or a drop that trades height for a faster
interception. Design a few concrete combat situations (attack, retreat, pursuit, counter) in plan
and section rather than chasing height statistics in the abstract.

**Techniques the classics use:**
1. **Put the items at different heights** so every item-to-item run climbs or drops. Key items
   on their own levels, with two ways up to each (one fast and exposed, one slow and covered).
2. **Many medium levels, not two slabs.** Steps of 48–128 between floors: terraces, ledges,
   sunken pits, raised walkways inside a room. Break the biggest level up.
3. **Overlooks everywhere.** Balconies, windows, holes in floors, low walls and railings: from
   most of the floor you should see floor below you, and be seen from above.
4. **Links inside rooms, not only between them.** Ramps and broad stairs within a room; drops
   (one-way down, cheap and fun); jump-ups to ledges (≤ 44 standing, more with a run); pads.
5. **Teleporters** as vertical links where the mode suits (2–5 in the classics).
6. **Angled walls** break the boxy read: chamfered corners, diagonal walls, octagonal pillars.

**Section first.** Sketch a concept in section before the plan, and check every blockout with
`section.py` (side-on slices) and `iso.py` (an isometric cutaway per level); `gallery/profiles/`
shows Strata's two slabs at a glance. If every section looks like a layer cake, the routes will run
along the layers.

### Item economy and relative placement (v3.4)

For TDM/FFA, design a resource circuit, not a scatter of pickups. Mark RL, LG,
each armor, MH and powerups in plan **and section** before small supplies. Give
each a role: premium control, an alternate strong weapon, lower-tier recovery,
an exposed commitment, or an interceptable timing route. CA's mod may suppress
items, so resource incentives cannot repair its physical circulation.

**Read clusters, not just pairs.** RL near RA can be intentional; adding the
only LG to the same easily controlled fight can remove the other team's strong
weapon option. Check the routes from each armor and MH to **both** strong guns,
the cost of visiting RL/LG/resource trios, drop-versus-climb asymmetry, and what
one position can actually see. Straight-line separation alone is not control.
Two RLs mean moving LG away from one can create a new cluster around the other.
Nearby GA can intentionally support a recovery weapon without duplicating a
premium RA/YA bundle; that tradeoff still needs actual games.

**Counts and quantities are different from frequency — and larger does not mean more RLs.**
The five compact classics carry 3–4 armors, two RLs and one LG, and the six larger custom classics
mostly follow that pattern (`skull`, `bravado`, `spinev2`, `cmt4`, `schloss`: 2–3 RLs, 0–1 LG,
2–3 armors, 1–2 MHs; `ultrav` drops RA/MH for 3 RLs, 2×YA, GA, Quad). By contrast, canonical 4v4
TDM maps (`dm3`, `cmt3`, `e2m2tdm`, `e1m2`) deliberately hold **only 1 RL and 1 LG** (0 LG on
`e1m2`) and **2–3 armors**, creating contested team control over scarce strong guns while putting
extra supply into **1–3 MHs, powerups (Quad, Pent, Ring), and deeper mid-tier recovery caches**
(145–600 ordinary HP, 100–375 nails/shells). Count small/big ammo separately. MH, ordinary health,
armor absorption, weapon pickup ammo, backpacks, and configured respawn rules are not
interchangeable — never multiply a duel map's inventory by floor area or player count.

**What holds across all reference sizes for trio control:** on every map with supported RL + LG +
armor/MH trios across both the compact survey (`aerowalk`, `ztndm3`, `dapak12`) and the larger
survey (`spinev2`, `skull`, `ultrav`, `dm3`, `cmt3`, `e2m2tdm`), `itemprofile.py` measures **0 /
256 common-eye samples** — no single sampled standing position can lock down both strong weapons
plus a major armor or Megahealth. (On maps like `cmt4`, `schloss`, `bravado`, and `e1m2`, one or
more endpoints are unresolved in the walk+jump model and stay reported as unknown rather than 0.)

**Give small supplies a reason.** In our group's TDM demos, spawn and mid-tier weapons (SG, SSG,
SNG) account for ~36% of kills and combat distance shrinks ~80–100 units compared to CA (195–216u
vs 291u) as teams fight over item pockets and recovery routes. Some ammo belongs near its gun;
some belongs on an alternate route to sustain a carrier's or out-of-control team's rotation. Paired
modest health and shell/nail caches away from RL/RA hot zones give trailing players a real recovery
loop. A dead-end reward should justify the commitment, but do not answer every quiet corner with
another premium item or bundle every useful resource in one safe spot.

Use `qmap/itemprofile.py map.bsp --json items.json --png-dir figures` for
inventories, directed matrices and diagnostic trios. `--inventory-only` is fast;
`--move LG1=x,y,floor` compares a hypothetical placement without editing a BSP.
See [`qmap/ITEMS.md`](qmap/ITEMS.md) and the evidence in
[`gallery/items/README.md`](gallery/items/README.md). Unknown routes stay unknown;
a sampled eye ray is not a promise about splash, all vantages, or real movement.
No single distance or diagnostic score establishes good balance.

After an item pass, re-run the full generator/compiled collision checks and
spawn margins, inspect the updated plan/sections, and verify live item settling
where practical (`qmap/itemcheck.py` can check a captured MVDSV edict dump).
Then test actual TDM/FFA pickup pressure and control transitions. Item-route
verticality changes when the key-item set changes: adding GA can lower that
metric without flattening any geometry. Keep the item-set change explicit and
do not move good resources simply to maximize a height statistic.

**Sizing a map: by travel and mode, not by floor area.** Helix (`2,070k` floor) and `skull`
(`2,031k` floor) both carry more floor than any of the five compact classics (`1,083k–1,600k`) yet
play at duel/compact travel speed (`797` and `905`): stacked floor adds area, not distance, and
pads, drops, and teleporters shorten trips. `vprofile.py` measures **travel** — the median and
90th-percentile walking distance between random spots on reachable floor (teleporters, pads, and
drops included) — and `build.sh` prints a size line.

| travel median (90%) | reference & toolkit maps | typical mode / player count |
|---|---|---|
| 797–950 (1234–1745) | helix, naked3, relay, skull, aerowalk | duel / FFA 2–6; Clan Arena 4–10 |
| 966–1160 (1478–2283) | bravado, naked4, spinev2, dapak12, crucible, lyceum, ultrav, dm6, cistern, ztndm3 | duel / FFA 4–8; Clan Arena 6–12; compact 4v4 TDM |
| 1200–1400 (2095–2260) | agora, vigil | Clan Arena / FFA / TDM 8–12+ |
| 1600–2300 (2896–4828) | schloss, cmt4, dm3, e2m2tdm, cmt3, e1m2 | full 4v4 TDM / large FFA (too slow for 8–12p CA) |
| 1831–3045 (3506–5373) | bastion, strata, circuit | CTF (8–12+) |

**Mode changes the right travel band.** `travel_median` 1,600–2,300 is canonical 4v4 TDM territory
(`schloss` 1,616, `cmt4` 1,738, `dm3` 1,939, `e2m2tdm` 2,162, `cmt3` 2,189, `e1m2` 2,277) because
teams hold wings, time items, and regroup. In Clan Arena, where there are no item timers and rounds
end on elimination, that same scale drags: in our group's demos, 8-player CA on `cmt4` (1,738) ran
a **74 s** median round (longer than `ctf1` at 70 s), while `spinev2` (1,014), `dm6` (1,097),
`ztndm3` (1,148), and `ca_agora` (1,273) sat cleanly in the **35–45 s** sweet spot. For an 8–12p
CA map with strong verticality, aim travel at ~1,050–1,350 even if total floor area reaches
2,200k–2,800k, using teleporters, drops, and compact loops to keep transit brisk. Adjust these
bands as your own group plays more.

**In real play** (`demos/vert.py` on the group's demos): floor height changed per 1000 units
travelled was ~100–125 on dm6, 148 dm2, 91 dm4, ~150–165 ctf1, 159 ctf3, 138 ctf6, and ~100–118 on
ca_agora; players were airborne 17–26% of the time. These are lower than the route measure
(players linger and fight on a level), so compare in-play numbers only with in-play numbers.
Measure our new maps the same way once the group has played them.

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
* **Wall bands** (bottom to top, `template/_out.py`'s default look): kickplate (`base`), wall,
  light strip (`strp`, fullbright), wall, cornice (`trim`); a sill trim under raised openings;
  a gated bottom overhang architrave (`NOARCH` / `carve(..., noarch=False)` opts out); risers on
  edges only a step tall. Wall texture is anchored to the band below it (kickplate top, or the
  room's own strip top), so panels line up — anchored to the room's nominal strip, not to a strip
  climbing beside stairs. These bands are a default, not a requirement: outdoor areas, caverns, or
  custom visual passes can omit strips (`strip=10**6`), skip caps/architraves (`nocap`, `noarch`),
  or replace `_out.py`'s banding logic.
* **Non-solid fixtures** (`func_detail_illusionary`): wall lamps, panels, banners, and light trim
  that should never snag movement or block rockets (avoid `*` liquids or `sky*` on illusionary
  brushes — see gotcha 31). Substantial decorative architecture within reach (item plinths, column
  bases, statues, arch frames) may be solid when kept snag-free; see section 5.
* **Ramps** (v3): `ramp(rect, axis, z0, z1, rev=False)` — the floor over rect rises from z0 to z1
  along +axis (`rev`: along −axis), as one wedge brush. Rise ≤ run (45°, QW's walkable limit);
  15–35° plays best. The grid holds a stepped stand-in (mat `'ramp'`, never written) so the checks
  see something walkable, and the ramp's foot is registered for the stair-feet check. Walls beside
  a ramp get a **sloped kickplate and strip** (illusionary overlays) from the foot room's strip to
  the head room's strip; give the head room its own `strip_ramp` / strip height so they meet. When
  a ramp's lateral side faces a differently themed room, `_out.py` slices off a 1-unit `worldspawn`
  veneer with that room's bands while keeping the walking wedge in the minlight floor skin.
* **Prisms** (v3): `prism(points, z0, z1, kind=None)` — solid on a convex footprint, points
  counter-clockwise from above; `chamfer(rect, corner, size, z0, z1)` cuts a room corner at 45°
  (four make an octagon); `diag_wall(x0, y0, x1, y1, thick, z0, z1)`. Faces are written with
  **Valve 220 texture axes** (qbsp reads the format per face, so they mix with standard faces),
  so stone runs along an angled face without stretching. `kind=None`: each face is banded like
  the room it faces (outward air probes march in 8-unit steps past `'diag'` cells so kickplate,
  strip, and cornice continue round chamfers without reading through thin walls); other kinds
  (`'pillar'`...) take that kind's textures. Every cell the prism overlaps gets grid stand-in
  `'diag'` (replacing only air so floors underneath never leak; never written, never given a lamp),
  while cells wholly inside a named-kind prism (`kind not in (None, 'ledge')`) keep that mat.
* **Team halves** (v3, Strata): `split_halves(themes)` at the end of the layout renames each
  listed theme to `<theme>_r` on the copy half (x < 0) and copies its heights, so `textures()`,
  `fixture_tex()` and `light_color()` can colour strips and lamps by team: `side_of(th)` gives
  `'b'` or `'r'`; `th[:-2]` is the material.
* **More wall bands** (v3): `TRIM_Z[theme]` adds a string course `TRIM_H` tall (role `'band'`);
  `SPLIT_Z[theme]` gives walls below that height a second stone (role `'wall_lo'`), for tall
  rooms in layers. `SUN` holds the worldspawn sunlight keys for maps with sky. `room_lamps()`
  nudges ceiling lamps off pillars/baffles and skips flush or recessed sky oculi.
* **Floor minlight**: walkable tops get a 16-unit skin brush in a `func_group` with `_minlight`
  so floors never go black while walls stay moody. Free-standing blocks (crates, columns) get it
  too, so their sides aren't black.
* The generator writes a **JSON** (grid, themes, spawns, team spawns, items, perches, stair feet,
  lights, labels, teleports, pushes, liquids, decals, ramps, prisms) that the checker, solvers,
  route tools, and plan/section/iso renderers read.

### Extending the toolkit & evolving this guide

Treat `template/` and `qmap/` as an evolving workshop, not a frozen specification:

* **Let the map design lead.** When a layout wants geometry or mechanics the template lacks
  (curved walls, diagonal ramps, sloped ceilings, doors, lifts, moving platforms, non-grid arches,
  or custom lighting/banding), prototype it directly in that map's generator rather than bending
  the design to fit the grid.
* **Add new checks and analyzers when real play reveals a blind spot.** Almost every tool in
  `qmap/` (`vprofile.py`, `itemprofile.py`, `collide_cmp.py`, `section.py`, `iso.py`, prism
  separation, passage width, blind pockets) was built because a real playtest caught something
  earlier checks missed.
* **Promote proven wins cleanly.** Once an extension or check proves useful, fold it back into
  `template/` or `qmap/`, add unit/regression tests in `tests/` (`python3 -m unittest discover -s
  tests`), keep `examples/` reproducible, and distill any general lesson or gotcha into this guide.

---

## 5. Checks — run them every build

* **qbsp leak** = failure. **Spawns**: no two can see each other (`pick_spawns*.py` solves for
  the largest set; ~16 is good headroom for 8–12 players, while classic duel and 4v4 maps often
  use 6–14); typical defaults are spacing ≥ ~256–288, ≥ 192 from weapons, armour and powerups, and
  out of flag rooms. Re-solve after any geometry change.
* **Exit codes vs diagnostic output**: `check.py` and `vprofile.py --check` exit 0 by default so
  `build.sh` (which runs under `set -e`) completes and prints every diagnostic section in one run
  — read their stdout headings (`PROBLEMS:`, `TRAPS:`, `BLIND POCKETS:`, `NARROW PASSAGE`, etc.)
  rather than relying on exit code alone. Conversely, `collide_cmp.py` and `itemcheck.py` signal
  failure via non-zero exit code.
* **Connectivity**: every spawn reaches every other; every item reachable. **Unreached floor**
  is reported at every height: crate tops and decoration are expected (say so), anything else
  is a bug.
* **Traps**: every reachable spot has a walk/jump route back to the spawns (no one-way drops into
  dead pits).
* **Blind pockets**: reachable floor with only one way in or out, no item and no spawn, and
  geodesic depth greater than its opening width (`check.py` on the grid, and `vprofile.py --check`
  on the real player hull so prism-sealed halls are caught too). Either open a second exit, shorten
  the alcove, or put a deliberate reward in it.
* **Prism separation**: distance from every `prism()` obstacle footprint to every other prism,
  `fill()` rect, and wall at walkable height (`check.py`, fails below 64; configurable via
  `--min-prism-sep N`). Walkable `'bridge'` slabs are skipped; wall-attached structural prisms
  (`chamfer`, `diag_wall`) are allowed flush contact with their mounting wall; freestanding prisms
  (pillars, cover blocks) must stay clear of every solid.
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
* **Visual-pass collision audit** (`collide_cmp.py old.map new.map`): the old "zero collision
  change" rule protected three real things — keeping the playtested layout intact, preventing
  movement snags from solid detail, and catching silent contents changes (retexturing to `clip`,
  `sky*`, or `*liquid` changes what rockets and players hit). You don't need zero change to protect
  all three; you need changes to be **bounded, snag-free, and declared**:
  - **Pure texture / lighting builds** (such as texture touch-up rounds): `collide_cmp.py` must
    **exit 0**.
  - **Visual passes with decorative architecture**: small, gameplay-neutral solid additions are
    allowed — raised item plinths/daises (keep a single step `≤ 16` units since QW's step height
    is `18`, or build steps onto it so pickups don't become jumps), column bases and capitals,
    door/arch frames, buttresses, wall reliefs/statues/niches, railings, skylight beams, and
    cupolas. Structural layout changes (rooms, connections, main floor heights, routes, major
    cover) still belong in layout rounds.
  - **Solid vs. non-solid boundary**: substantial detail within player reach (plinths, column
    bases, statues, sturdy frames) should usually be **solid** so players don't walk or shoot
    straight through solid-looking geometry — *provided* active strafe lanes stay smooth at player
    height (`0..72` units: recess wall ornaments, and avoid protruding pilasters, 16-unit notches,
    catch-lips, or squeezes). Keep thin surface trim, plaques/banners, low-profile detail along
    tight lanes, and light out-of-reach filigree/cornices **non-solid** (`func_detail_illusionary`,
    never with `*` or `sky*` textures) so they can't snag jumps or block rockets; structural
    overhead beams and arch lintels (`≥ 96` units above floor) may be solid when you want real
    cast shadows and solid rocket collision.
  - **Audit and re-verify every collision change**: run `collide_cmp.py` on every visual build and
    verify that every reported diff corresponds to a declared addition (any undeclared diff —
    especially hull-0 projectile, sky, or liquid contents — is a bug to fix). **List every
    intentional collision change by location** in the build notes so the human knows what to
    re-test, and **re-run the full check suite** whenever collision changes: `check.py` (traps,
    pockets, 16-unit slots, stair feet, prism separation, item margins, and spawn sightlines —
    re-solving spawns if needed), `vprofile.py --check` (real 32×32×56 player hull: narrow
    passages, traps, pockets, unreachable items), plus `itemprofile.py` / `sightlines.py` if
    pickups or major sightlines moved.
  - **Reading `collide_cmp.py` output**: check the exit code, not just the first stdout line — it
    compares both the player hull (hulls 1/2) and hull 0 (projectile solid, sky, and
    water/slime/lava contents), so stdout can say "collision identical" on the player pass while
    `PROJECTILE COLLISION DIFFERS`, `SKY CONTENTS DIFFER`, or `LAVA CONTENTS DIFFER` on a later
    pass takes the exit code to 1 (`echo $?` or run under `set -e`). It counts every brush qbsp
    puts in the world hulls — `worldspawn`, `func_group`, `func_detail` / `func_detail_wall` /
    `func_detail_fence`, plus `func_detail_illusionary` liquids/sky and
    `func_illusionary_visblocker` `clip`, with face textures read for contents — and prints a
    `note:` line accounting for every ignored brush. Gotcha 31 has the full solidity rules —
    several are not what you would guess.
* **Brightness**: `views.py` prints a mean per view; keep it in the range of the group's maps.
* **Player-hull check** (`vprofile.py map.bsp --check`, run by `build.sh`, v3.1): connectivity,
  one-way traps, **narrow passages** (`--min-passage`, default `64` effective width = `32` units
  to spare on axial walls, reporting `(x, y, z)` and the two opposing solids), **blind pockets**,
  and unreachable items on the compiled map's **real collision** with a 32×32×56 player (walk,
  jump, gaps, drops, teleporters, pads; no rocket jumps). It is the authority on whether you can
  get somewhere and back: `check.py`'s grid treats the player as one 16-unit cell, so it cannot
  see a gap narrower than 32 next to an angled brush, a tight pinch between two solids where a
  32×32 body barely fits, or a ceiling that catches a player still half on the step above.
  Hook-only perches are listed as a note, not an error.
* **Height** (`vprofile.py map.bsp --targets`, run by `build.sh`): each measure against the five
  classics' range — `ok`, `LOW`, `HIGH`, or `ok+` (past the range in the good direction). Works on
  any BSP29, so you can profile a map the group names as a reference. `--json` and `--png-dir`
  write the numbers and a height map.
* **Look at it side-on** every layout round: `section.py map.json out.png y=0 x=1200` (slices;
  floor you can stand on in white, air coloured by height, items and spawns near the cut) and
  `iso.py map.json out.png cut=200 cut=470 view=sw` (an isometric cutaway, one panel per cut
  height).

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
  brightness ≈ 255·(raw/255)^0.55). Our group's taste sat around ~45–60 on preferred maps (DM2 ~35,
  gothic map ~32–43): "as dark as gameplay allows; no black floors; not fiesta-bright." Calibrate
  the target band to your own group's preferred maps and client gamma.
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

* **Stairs**: avoid jagged 16-unit zigzag side treads on open flanks (they look messy and snag
  movement) — use broad wall-to-wall steps, walled stairwells, clean plinth flanks, or ramps. Keep
  bottom steps from poking into doorways and leave clear floor across the stair foot.
* Leave ≥ 64 behind cover near doors (32 = exactly a player, reads as blocked); no 16-unit notches.
* **trigger_push replaces velocity** — angle the push (pitch about −60 to −80) for jump pads.
* Liquids need texture names starting `*water` / `*slime` / `*lava` (packed via `makewad.py` using
  `name=path.png` pairs, e.g. `*bk_water=bktex/liquid_bk_water.png` in `wad_args.txt`).
* **KTX CTF**: flags `item_flag_team1/2`; base spawns `info_player_team1/2` (also written as
  `..._deathmatch` for `k_ctf_based_spawn 2`); `info_player_deathmatch` are respawns *and* rune
  spots. KTX `ctf` defaults: deathmatch 3 (weapons stay), based spawn 1, hook off, runes off, GA
  on spawn. Check in game: `status1`, `status2`. KTX names demos by mode — a demo called `ca_...`
  on a CTF map is a Clan Arena game.
* **Hook-only perches** are a good second layer in CTF: slabs too high to jump to, stocked with
  ammo or small health, not armour.

### What real demos showed (group CA, TDM, FFA, and CTF games)

* **Clan Arena** (initial 22 CA + follow-up 39 CA demos): ~80–85% of kills are rocket, ~15% LG;
  median kill distance ~290 units (range ~190–390); first kill ~6–12 s into a round; rounds ~35–55 s
  on well-sized maps (`spinev2` 35 s, `ca_agora` 40 s, `ztndm3` 42 s, `dm6` 45 s). Oversized maps
  drag CA rounds past a minute (`ctf1` 70 s, `cmt4` 74 s). Players live on high ground when it
  exists (high-ground killers >48u above victims reach 15–26% on overlook-rich maps like `ca_agora`,
  `spinev2`, and `dm2`); open floors and pits without cover become kill zones. *These are findings
  to design against, not a layout to copy.*
* **TDM & FFA** (10 TDM + 20 FFA demos, 3,755 kills): median kill distance shrinks ~80–100 units vs
  CA (**216 u** in TDM, **195 u** in FFA vs **291 u** in CA) because players contest item rooms and
  fight with close-range recovery weapons. In TDM, RL drops to 46% while spawn/mid-tier weapons
  (SG 25%, SNG 5%, SSG 5%) drive ~36% of kills; in FFA, RL is 59% and LG 17%. High-ground advantage
  stays prominent on vertical maps (`aerowalk` 24%, `ztndm3` 20%, `cmt4` 17%, `dm3` 15%). In-play
  floor height change sits around ~98–110 per 1,000 units travelled across modes (16–18% airborne).
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
18. **Wall stone misaligned beside stairs** (Strata): walls were anchored to the strip, and the
    strip climbs with the stairs, so the stone slid up the wall step by step. Anchor wall stone to
    the room's nominal strip (`STRIPE_Z + 16`); only the strip itself climbs.
19. A ramp whose foot runs into a wall (the template's own demo): the stair-feet check catches
    ramps too. Leave 32 of clear floor in front of the low end.
20. **Camera pitch in `render.py`: positive looks DOWN**, as in Quake. A preview that "looks too
    dark" may simply be pointing at the ceiling — check the sign before blaming the lighting.
21. Stacked is not vertical (section 3): a map can have two full storeys and play flat. Read the
    route height change, not the stacking.
22. Grid cells under a prism must all be stand-ins (`'diag'`), not structure: the lamp placer saw
    a structure cell's face beside a part-covered air cell as a wall and could hang a lamp inside
    the prism. Anything that only exists as a brush (ramp, prism) needs a grid stand-in the
    writer skips. Two more ways to get it wrong, both found on the first map built with v3:
    a stand-in must replace only *air* (a prism from `BOT` once replaced the floor under its
    part-covered edge cells and leaked to the void), and prisms go *after* the carves they sit
    in (a later carve hollowed a chamfer's stand-in and lamps went inside it).
23. **The player is 32 wide and 56 tall; the grid checker thinks in 16-unit cells.** Concept C (the
    quarry) passed `check.py` and was broken in game twice: a rock column 24 units from a tunnel
    mouth (the grid saw 32), and a stair dropping into an 80-tall tunnel - standing on the edge of
    the second step, your body is already under the tunnel's ceiling and too tall for it, so you
    can't step down. The player-hull check (section 5) catches both; read it every build.
    Stairs that run down under a ceiling need ceiling ≥ (second step's top + 56) at the edge, or
    the tunnel's ceiling raised over the bottom steps.
24. **`trigger_teleport` brushes are invisible in-client** (`ca_saddle`): a bare `teleporter()`
    leaves players walking into unmarked wall patches. Pair each teleporter with a non-solid
    framed archway (`func_detail_illusionary`, locally anchored per face — not world-aligned
    `0 0`), an animated `*` warp curtain (`func_illusionary`), a threshold floor inlay pulled
    cleanly in front of the frame depth (not buried under the threshold), a beacon light, and an
    exit landing pad. Exclude teleporter gates in `torches()` so wall lamps never clip behind the
    lintel.
25. **ezQuake ignores `texinfo` translation offsets on `*` turbulent liquids** (`ca_saddle`):
    `render.py` honors texture offsets on `*` surfaces, so a teleporter swirl can look centered in
    offline renders while rendering shifted in ezQuake (`EmitWaterPolys` computes UVs from world
    coordinates). Align 64-wide teleporter portals so `(cx - 32) % 64 == 0` and verify in-client.
26. **Multi-tier wings with ramps need per-level sub-themes** (`ca_saddle`): the first `carve()`
    of a theme pins `STRIPE_Z` to that floor, so a climbing flank sharing one theme drops its
    light strip into upper floors and breaks sloped ramp strips. Split tiers into sub-themes
    (`wing_lo/mid/hi`) so every tier's strip sits at `floor + 128` and sloped ramp strips connect
    corner-to-corner. Avoid baking continuous horizontal straps into wall textures on multi-tier
    or ramped hallways, and cover horizontal-to-slope light-strip bends with non-solid junction
    collars (`func_detail_illusionary`) so the 1–2u overlay parallax step never shows as a notch.
27. **Size crate/object textures to exact height and width GCD** (`ca_saddle`): a 48-tall crate
    using a 32×32 side tile shows 1.5 squares vertically (merging into the floor with no base
    rail) and 2.5 squares on an 80-wide side. Quake WAD2 allows any multiple of 16 (`64×48`,
    `96×64`, `16×64`, `64×16`) — make crate sides exact crate height with a bottom foot rail and a
    horizontal bay period that divides every crate width (16 divides both 64 and 80).
28. **Wood palette trap (olive end of the 80–95 ramp)**: in `qmap/quake_palette.lmp`, indices
    **80–85** are olive/dark-khaki (`(19,19,0)` to `(67,55,0)`), while 90–95 are warm mid-browns.
    Exclude 80–85 from error-diffusion wood palettes (`fsq.py`) or warm timber picks up a
    greenish cast under lamplight while keeping 90–95 for rich wood tones.
29. **Redundant overlapping `carve()` calls overwrite room themes**: carving a connecting stair
    rect with the adjacent room's theme inside an already-carved room carves zero new space while
    overwriting `theme`, bleeding the neighbour's ceiling and overhang textures into the main room.
30. **Ship `.lit` alongside `.bsp` when using colored lights**: `ericw-tools light` automatically
    writes colored lightmaps to `<map>.lit` whenever `_color` lights are present (see section 7);
    copy and package `.lit` with `.bsp` while keeping gameplay/team read clear without `.lit`.
31. **What is solid to a player — and to a rocket — is not what you would guess.** `collide_cmp.py`
    follows the rules below. They were measured by compiling a 128-unit cube per flavour and
    reading the BSP, never inferred from the qbsp source — which on its own is not enough twice
    over: it states one rule in a way that reads backwards (`hint`, below), and projectile /
    liquid rules live in a different hull from player collision, so the two need different
    instruments. **Player collision** is the clipnode count (hulls 1/2) against an empty control;
    **projectile collision, sky, and liquid contents** are leaf contents in hull 0 (what point
    traces and `SV_PointContents` read). Hulls 1/2 drop every non-solid brush, so clipnodes cannot
    see a liquid at all, and treat `clip` and `sky*` identically to a wall.
    * **Solid**: `worldspawn`, `func_group`, and the whole detail family — `func_detail`,
      `func_detail_wall`, `func_detail_fence`. Detail is *not* automatically non-solid; only
      `func_detail_illusionary` is. If you reach for `func_detail` to cut vis cost, it still
      blocks players and projectiles.
    * **No player collision**: `func_detail_illusionary`, and `func_illusionary_visblocker` — a
      trap, because it passes qbsp's own `IsWorldBrushEntity()` test yet has no collision for an
      ordinary textured brush (it blocks vis only, so its face count rises while its clipnode
      count does not). Both have exceptions, immediately below.
    * **But "no player collision" is not "no contents", in both directions.**
      `func_detail_illusionary` **still makes real lava and real sky in hull 0**: qbsp converts a
      brush there to illusionary mist only when `contents.is_any_solid()` is true, so neither a
      `*` liquid nor a `sky*` face is converted — a `*lava` brush keeps `CONTENTS_LAVA` (will
      still burn you) and a `sky*` brush keeps `CONTENTS_SKY` (will still swallow rockets), while
      adding zero clipnodes. Do not put a `*` or `sky*` texture on a decal or fixture brush.
      `func_illusionary_visblocker` discards every *visible* content, sky and liquids included,
      whatever the texture says — but `clip` is an **invisible** content, so it survives in hulls
      1/2, and a `clip` brush in a `func_illusionary_visblocker` **is as solid to a player as a
      wall** (while remaining hull-0 empty so projectiles pass through). Each entity therefore gets
      its own per-hull rule; there is no one "illusionary means non-solid".
    * **`*`-prefixed faces make a liquid, not a solid.** `template/_out.py` writes `liquid()`
      pools as plain `worldspawn` brushes, so a pool sits in the same brush list as the walls and
      is only distinguishable by its texture. `!water` is a Half-Life name: here it is solid in
      both hulls.
    * **`clip`, `skip`, `sky*` and `trigger` are all solid to a player — but diverge for
      projectiles.** In hulls 1/2 all four block players identically. In hull 0 (point traces:
      rockets, nails, hitscan), `skip` and `trigger` are still `CONTENTS_SOLID`, `clip` is absent
      (projectiles pass straight through), and `sky*` writes a `CONTENTS_SKY` leaf (blocks and
      deletes the missile). `hint`, `hintskip` and `origin` have no contents in any hull.
    * **A mixed-texture brush is decided by its first face in file order.** One `*lava` face in
      slot 1 turns a whole wall into a pool; the same face in slot 6 leaves it solid. qbsp warns
      `brush has multiple face contents`, and so does `collide_cmp.py` — including when the odd
      face is `clip` or `sky*`, which are as solid as a wall to players but differ in hull 0.
      It almost always means a texture landed in a wall or floor theme slot by mistake.
      The exception is `hint` / `hintskip`: **one such face anywhere** removes the brush from the
      collision hull entirely *and* empties its contents in hull 0, whatever the other five faces
      say — so it beats liquids and sky too. qbsp's `IsHintName()` treats the two names
      identically, so `hintskip` on its own drops a brush exactly as `hint` does.
    * `func_wall`, `func_illusionary` and `trigger_*` become separate BSP models with their own
      hulls, and their real solidity is set at runtime by the progs, not the BSP. `collide_cmp.py`
      lists them in its `note:` line instead of comparing them; a map that depends on one of them
      for collision needs checking by hand.
    * **`collide_cmp.py` compares both hulls independently.** A wall retextured `clip` reports
      player-identical and `PROJECTILE COLLISION DIFFERS` (exit 1); retextured `sky*`, it reports
      player-identical and both `PROJECTILE COLLISION DIFFERS` and `SKY CONTENTS DIFFER` (exit 1).
      Because each class is compared on its own, reshaping a liquid (or sky/clip) brush buried
      inside an unchanged solid wall reports a difference nobody can feel — a conservative false
      alarm rather than a miss.
32. **Pass/fail connectivity at 32×32 is not enough (`ca_mesas_b1`).** The next order of problem
    past gotcha 23 is when connectivity still passes and the layout is still broken in play: a
    column 5 units from a hall mouth seals the hall onto the mesa while the hall stays connected at
    its far end, columns merge into an unintended wall, a 320-long empty hall becomes a blind dead
    end, or a 40-unit squeeze lets a 32×32 player pass while reading as blocked. `check.py` now
    enforces prism separation (`< 64`, `--min-prism-sep`) and empty blind pockets (`depth > width`),
    and `vprofile.py --check` reports narrow passages (`--min-passage`, default `64`) with both
    opposing solids as well as real-hull blind pockets.

---

## 10. Demo analysis (MVD)

`demos/mvd.py` reads QuakeWorld MVD demos: player positions (~70 Hz), dead state, effects (flag
carriers glow: effects bit 16/32), prints (obituaries, flag events, round results). Coords are
short/8 unless FTE float-coords is negotiated; unknown messages skip the rest of their block.
`demos/ca_run.py` and `demos/ctf_run.py` are reference scripts tailored to this group's KTX demo
filenames and match prints — adapt them for your own server's conventions. A top-down heatmap of
time spent reconstructs any map's layout without the BSP. Analyse demos of *your own* maps once
the group plays them — that is the best feedback there is.

`vert.py` (v3, used by both scripts) measures height in real play: `floor_change_per_1000` (the
floor under each player — a rolling minimum of height over 0.6 s, so jumps don't count — changed
per 1000 units travelled), `z_range`, and `airborne` (share of time off the floor). Numbers for
the group's games are in section 3.

---

## 11. Licensing

All textures here are generated from code. The palette is LibreQuake's (BSD-3, notice included).
Don't copy id's or other maps' textures; don't redraw known emblems, logos or characters. Release
maps with their `.map` source.

---

## 12. Starting a new map

1. Copy `template/` to a new folder. Set `NAME`, `TITLE`, `SYM`, bounds in `_core.py`.
2. Do the **concept step** (section 3) — plan *and* section for each candidate, with where the
   items sit in height — and get the human's pick.
3. Delete the demo in `_layout.py` and `_items.py`; write the layout.
4. Blockout textures and build:
   ```
   python3 texgen_blockout.py bktex
   python3 ../qmap/makewad.py mymap_b1.wad $(cat wad_args.txt)
   bash build.sh
   python3 plan.py mymap_b1.json plan.png "My Map beta 1"
   python3 ../qmap/section.py mymap_b1.json section.png y=0 x=0
   python3 ../qmap/iso.py mymap_b1.json iso.png cut=100 cut=300
   python3 views.py mymap_b1.bsp views.png        # edit CAMS in views.py first
   ```
   `build.sh` does not generate the `.wad`, so run `makewad.py` first (`views.py` needs the `.wad`
   in the working directory). `build.sh` ends with `check.py` and `vprofile.py --check --targets`;
   read both every build.
5. Solve spawns (`pick_spawns.py` or `pick_spawns_sym.py`), measure routes and sightlines, fix,
   rebuild, deliver with the plan, sections, views, README.
6. Visual pass: write `texgen_<style>.py` (borrow techniques from the examples' generators),
   replace `textures()` / `fixture_tex()` / `light_color()` in `_core.py`, and add any bounded
   decorative architecture (plinths, frames, columns, wall reliefs, overhead beams — see section
   5). Audit diffs with `collide_cmp.py` (gotcha 31: what counts as solid), list every intentional
   collision change by location in the build notes, and re-run the full check suite if collision
   changed.

High-leverage habits worth keeping: render and check before delivering; a new filename every build
(`_bN`) so QW clients don't serve cached copies; and in-client screenshots from the human for every
visual round.

---

## 13. Example notes

* `ctf_bastion` (v1 example, unchanged): `python3 texgen_bastion.py btex`, then
  `python3 ../../qmap/makewad.py ctf_bastion_b19.wad $(for n in $(cat btex_names.txt); do printf "%s=btex/%s.png " $n $n; done)`, `bash build.sh`.
  Its `_out.py` predates some v2 fixes (8-unit floor skin, no sill bands) — prefer the template's.
* `ctf_circuit`: `routes.py` (named runs) and `routes_fig.py` draw the three runs;
  `pick_spawns_sym.py` with `SYM=mirror HALF_X0=128 HALF_X1=3104 FLAGR=512`.
* `ca_lyceum`: `details_lyceum.py` renders the close-ups used in texture rounds.
* `ctf_strata` (b6, written on the v3 core before ramps and prisms existed):
  `python3 texgen_dig.py dtex`, `python3 ../../qmap/makewad.py ctf_strata_b6.wad $(cat wad_args.txt)`,
  `bash build.sh` (the .map's md5 is `52657ae18a754e83ecc00f0f3a928723`). Techniques: `split_halves`
  for team lights by half, `SPLIT_Z`/`TRIM_Z` for stratified walls, two-ended direction signs
  (`signcheck.py` lists what you can see from each spawn), `SUN` for moonlight through the oculus,
  `views_lanes.py` / `views_first.py` / `views_detail.py` for lane, first-person and close-up renders,
  `texsheet.py` for a texture contact sheet.
* Three of the examples (`ca_lyceum`, `ctf_circuit`, `ctf_strata`) include their shipped
  `README.txt` with change history (`ctf_bastion` predates that habit).
