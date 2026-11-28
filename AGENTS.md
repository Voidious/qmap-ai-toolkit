# AGENTS.md

Instructions for coding agents working *in* the `qmap-ai-toolkit` repository.

- **`README.md`** is the human-facing overview (workflow, example prompts, model notes, licensing).
- **`GUIDE.md`** is the field guide for **designing, building, verifying, and texturing Quake 1 /
  QuakeWorld maps** with this toolkit. If your task is building a map, read `GUIDE.md` first
  (especially Section 3 before designing and Section 9 before texturing).
- **This file (`AGENTS.md`)** is about how to maintain, test, and extend the toolkit codebase
  itself.

## Setup & environment

There is no `pyproject.toml`, packaging step, or virtual-env lockfile -- tools are plain Python 3
scripts run directly from the repo (`python3 qmap/<tool>.py ...`).

- **Unit tests**: Python 3 stdlib + `numpy` + `pillow` (renderer tests). `collide_cmp.py`
  needs only stdlib + `numpy`. No `ericw-tools` or external `.bsp` files are required for tests.
- **Full toolkit** (`vprofile.py`, `ctfprofile.py`, `itemprofile.py`, `render.py`, `section.py`,
  `iso.py`, `makewad.py`, `texgen*.py`, `plan.py`, `views.py`, `demos/`): `numpy`, `pillow`,
  `scipy`, `matplotlib`, `numba`.
  - `qmap/vprofile.py` (and `qmap/ctfprofile.py` / `qmap/itemprofile.py`, which import it) requires
    `numba`. Without `numba`, the `TestVprofilePassageWidth` tests in `tests/test_checks.py` and
    `TestCtfRouteIndependence` tests in `tests/test_ctfprofile.py` are skipped rather than failing.
    Run in a Python environment with `numba` installed whenever you touch `vprofile.py`,
    `ctfprofile.py`, `itemprofile.py`, or `gallery/profiles/`.
- **Map compilation** (only needed to smoke-test `template/build.sh` or rebuild `examples/`):
  [`ericw-tools`](https://github.com/ericwa/ericw-tools) built from source with `ERICW` pointing
  to the build directory containing `qbsp/qbsp`, `vis/vis`, and `light/light`, plus `bash`. On
  Windows, run `build.sh` (and `numba`-dependent checks if `numba` is installed in WSL) from
  WSL/Linux.
- **Optional playtest tools**: a QuakeWorld client (such as `ezQuake`) for visual inspection and
  screenshots, and `mvdsv` for capturing `edicts` dumps for `qmap/itemcheck.py`.

## Build / test / verify

Run the full regression suite from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

A change isn't done until the full `tests/` suite passes. Check the test output for skipped
`numba` tests whenever your change touches `qmap/vprofile.py`, `qmap/ctfprofile.py`, or `qmap/itemprofile.py`.

When changing `template/` or the compilation/check pipeline (`qmap/check.py`, `qmap/vprofile.py`,
`qmap/makewad.py`, `qmap/render.py`), also run an end-to-end `template/` smoke build if `ERICW`
is available:

```bash
export ERICW=/path/to/ericw-tools/build
cd template
python3 texgen_blockout.py bktex
python3 ../qmap/makewad.py mymap_b1.wad $(cat wad_args.txt)
bash build.sh
python3 plan.py mymap_b1.json plan.png "Template demo"
python3 ../qmap/section.py mymap_b1.json section.png y=0 x=0
python3 ../qmap/iso.py mymap_b1.json iso.png cut=100 cut=300
python3 views.py mymap_b1.bsp views.png
```

Clean up all generated files in `template/` afterwards (`gen_map.py`, `bktex/`, `wad_args.txt`,
`*.wad`, `*.map`, `*.bsp`, `*.json`, `*.log`, `*.prt`, `*.lit`, `*.vis`, `*.pts`, `*.png`) --
there is no `.gitignore` filtering build outputs, so check `git status` before committing.

There is no configured formatter, linter, or pre-commit hook yet. Match the style of the
surrounding file and keep diffs clean and scoped.

## Code conventions

- **Flat `qmap/` script imports**: scripts under `qmap/` import siblings directly (`import
  vprofile`, `import texgen`, `import render`), expecting either direct CLI execution
  (`python3 qmap/<script>.py`) or `qmap/` on `sys.path` (as `tests/` does).
- **Template concatenation model**: `template/build.sh` concatenates `_core.py _layout.py
  _itemh.py _items.py _out.py > gen_map.py` and runs `gen_map.py`. Those five files share one
  flat global namespace at runtime rather than importing each other, so keep helper names,
  settings (`NAME`, `SYM`, `XMIN`/`XMAX`, etc.), and globals consistent across all five.
- **Versioning (`VERSION` is single source of truth)**:
  - Root `VERSION` holds 3-part SemVer (`MAJOR.MINOR.PATCH`, trailing newline required).
  - The top heading in `CHANGES.md` must match `VERSION` (`# v<VERSION> ...`). Keep ticket IDs
    out of `CHANGES.md` bullets.
  - Top-level doc headings (`README.md`, `GUIDE.md`, `qmap/ITEMS.md`, `qmap/RENDERING.md`, `qmap/TEXCHECK.md`)
    and `template/` file banners (`_core.py`, `_out.py`, `plan.py`, `texgen_blockout.py`, `views.py`) must not
    hardcode release numbers or the old name `qmap-toolkit`. `tests/test_version.py` enforces
    all of these plus valid relative links/anchors in `README.md`.
- **CLI exit-code vs stdout conventions**:
  - `qmap/collide_cmp.py` signals results via exit codes (`0` identical, `1` collision/contents
    differ, `2` under-resolved or voxel-budget refusal).
  - `qmap/check.py` and `qmap/vprofile.py --check` print diagnostics (`PROBLEMS`, `TRAPS`,
    `BLIND POCKETS`, narrow passages) to stdout and exit `0` so `template/build.sh` (which runs
    with `set -e`) completes both checks in one run. Don't silently change these exit-code
    contracts without updating `template/build.sh` and `GUIDE.md`.
- **Extending the toolkit**: `template/`, `qmap/`, and `GUIDE.md` are meant to grow as real map
  designs and playtests outgrow them. Prototype map-specific primitives inside a map folder
  first, then fold the clean, general version into `template/` or `qmap/` (and document any
  hard-won gotcha in `GUIDE.md` Section 9).

## Invariants (don't relax these without asking)

- **`qmap/check.py` `exec()` globals compatibility**: `contact.py`, `sightlines.py`, `routes.py`,
  `flagtime.py`, `pick_spawns.py`, and `pick_spawns_sym.py` load `check.py` via
  `exec(open('check.py').read(), g)` (where `g` has no `'__name__'` key) and read its
  module-level globals (`d`, `C`, `XMIN`, `YMIN`, `NX`, `NY`, `BOT`, `TOP`, `cols`, `AIR`,
  `solid_at`, `nodes`, `neighbours`, `bfs`, `spawns`, `snodes`, `reach`, `r0`, `TELEPORTS`).
  Keep the `if globals().get('__name__') in ('__main__', None):` block and
  `globals().update(_res['env'])` intact -- `test_exec_compat_for_contact_sightlines_and_routes`
  guards this.
- **Zero third-party or id Software assets**: never commit third-party or id Software `.bsp`
  files, `.wad` files, textures, or map sources. All textures are synthesized procedurally from
  code and quantized to `qmap/quake_palette.lmp` (LibreQuake, BSD-3-Clause; keep
  `qmap/quake_palette.LICENSE.txt`). Reference benchmarks in `gallery/profiles/` and
  `gallery/items/` store aggregate measurement JSON/tables only -- never redistribute reference
  BSPs.
- **Keep `examples/` reproducible**: `examples/ca_lyceum`, `examples/ctf_circuit`,
  `examples/ctf_strata`, and `examples/ctf_bastion` are frozen reference snapshots that rebuild
  cleanly (with byte-identical `.map` output) from this repo. Do not edit `examples/` when
  evolving `template/` unless intentionally fixing a broken example build.
- **`qmap/collide_cmp.py` matches live `ericw-tools qbsp`**: `WORLD_ENTITY_TYPES`, brush/comment
  parsing, and the 6-class hull-0 + player-hull comparison (`solid`, `proj`, `sky`, `water`,
  `slime`, `lava`) are calibrated against live `qbsp` output. Don't alter entity/texture
  classification or parser rules without verifying against real `qbsp` and updating
  `tests/test_collide_cmp.py`.
- **Keep `template/` clean and buildable**: `template/` must compile cleanly as-is into its small
  demo map and must not accumulate generated build artifacts in git.

## Architecture map

### Root & documentation

| Path | Responsibility |
| --- | --- |
| `README.md` | Human-facing overview, example prompts, workflow summary, model table, licensing. |
| `GUIDE.md` | End-to-end map-making field guide (process, design, verticality, sizing, item economy, gotchas). |
| `VERSION` | Single source of truth for toolkit SemVer (`MAJOR.MINOR.PATCH`). |
| `CHANGES.md` | Release changelog (top heading must match `VERSION`). |
| `gallery/` | Plans and renders for the nine gallery maps (`GALLERY.md`), verticality & CTF benchmarks (`profiles/profiles.json`, `profiles/large_refs.json`, `profiles/ctf_refs.json`), and item-placement study (`items/`). |
| `examples/` | Four frozen, reproducible reference maps (`ca_lyceum`, `ctf_circuit`, `ctf_strata`, `ctf_bastion`). |

### `template/` -- starting point for each new map

| File | Responsibility |
| --- | --- |
| `_core.py` | Per-map settings (`NAME`, `TITLE`, `SYM`, bounds, light scale), 16-unit multi-floor column grid, building primitives (`carve`, `fill`, `stairs`, `terrace`, `pyramid`, `ramp`, `prism`, `chamfer`, `diag_wall`, `teleporter`, `jumppad`, `liquid`, `panel`, `inlay`, `oculus`, `strip_ramp`, `split_halves`), and texture mapping. |
| `_layout.py` | Demo room layout, stairs/ramps, lamps, and spawns (replaced per map). |
| `_itemh.py`, `_items.py` | Pickup placement helper and item list. |
| `_out.py` | `.map` + `.json` writer: per-face texturing, wall bands, Valve 220 axes on prisms, sloped ramp bands, and 16-unit floor minlight skins. |
| `texgen_blockout.py` | Procedural zone-coloured blockout textures with 32/64/128-unit height marks. |
| `build.sh` | Concatenates `_core.._out` -> `gen_map.py` -> `qbsp` -> `vis` -> `light` -> `check.py` -> `vprofile.py --check --targets`. |
| `plan.py`, `views.py` | Top-down multi-level floor plan and software-rendered preview sheet with ezQuake brightness readouts. |

### `qmap/` -- shared verification, analytics, rendering & texture tools

| Module | Responsibility |
| --- | --- |
| `check.py` | Grid-level checks on generator JSON: reachability, one-way traps, blind pockets, spawn sightlines, item margins, perches, stair feet, 16-unit slots, and prism separation (`--min-prism-sep`). |
| `vprofile.py` | Compiled BSP29 player-hull check (`--check`: traps, narrow passages `--min-passage`, blind pockets, unreachable items), verticality benchmark (`--targets --ref duel\|large`), and travel-distance sizing (`numba` required). |
| `ctfprofile.py` | Compiled BSP29 CTF route-independence diagnostic: walk (hook-off) and grapple (hook-on) flag routes, LOS-separated midfield lanes, single-vantage choke detection, flag exits/sightlines, and two-panel PNG plots (`numba` required). |
| `collide_cmp.py` | Dual-hull (`solid` player hull + hull-0 `proj`/`sky`/`water`/`slime`/`lava`) voxel comparator auditing visual-pass collision diffs (proving zero change on texture-only builds or verifying only declared decorative edits). |
| `texcheck.py`, `TEXCHECK.md` | Source/BSP texture alignment and visual hazards: courses, seams, portals, WADs, illusionary contents, sky overlaps, and dark standable floors; opt-in `TEXCHECK=1` build integration. |
| `pick_spawns.py`, `pick_spawns_sym.py` | Spawn solvers maximizing spawns with zero mutual eye-level line of sight (asymmetric or `rotate`/`mirror`). |
| `routes.py`, `flagtime.py` | 8-way Dijkstra walking routes and timings on `check.py`'s floor graph. |
| `sightlines.py` | Longest straight eye-level sightlines per floor level along X and Y. |
| `contact.py` | Clan Arena pacing proxy comparing spawn spread against a reference map. |
| `itemprofile.py`, `ITEMS.md` | BSP29 pickup inventory, directed RL/LG/armor/MH route matrices, trio diagnostics, and non-destructive `--move` evaluation. |
| `itemcheck.py` | Offline verification of generated pickup coordinates against a captured MVDSV `edicts` dump. |
| `render.py`, `view_sheet.py`, `RENDERING.md` | BSP29 previews with companion RGB lightmaps, ezQuake lighting controls, camera checks, and shared-camera before/after sheets. |
| `section.py`, `iso.py` | Vertical slice diagrams and multi-height isometric cutaways from generator JSON. |
| `makewad.py` | Packs palette-quantized PNGs (including `_fbr` fullbrights) into a Quake WAD2 using `quake_palette.lmp`. |
| `fsq.py` | 3x3-tiled serpentine Floyd-Steinberg error-diffusion quantizer over Quake palette subsets. |
| `texgen.py`, `texgen_cistern.py`, `texgen_runic.py` | Reusable procedural texture generators and palette quantization helpers. |
| `strip_ill.py` | Legacy helper for stripping illusionary entities from `.map` files. |

### `demos/` -- QuakeWorld MVD analysis

| Module | Responsibility |
| --- | --- |
| `mvd.py` | Minimal QuakeWorld `.mvd` reader (standard short/8 coordinates, player positions, frags, flag prints). |
| `vert.py` | In-play movement verticality (`floor_change_per_1000`, `airborne` share) from parsed demos. |
| `ca_run.py`, `ctf_run.py` | Reference Clan Arena and CTF match analysis scripts (written around KTX demo naming; meant to be adapted per group). |

## Tests

Unit and regression tests live in `tests/` using Python's stdlib `unittest`:

- `tests/test_texcheck.py` -- texture transforms, course/seam/portal phase, WAD/source parsing,
  sky overlap, dark compiled floors/player clearance, CLI contracts, and template anchor consistency.

- `tests/test_render.py` -- synthetic BSP29/.lit parsing, RGB normalization and lightmap
  response, liquid UVs, fullbrights, camera solidity/near-plane intersections, and paired sheets.

- `tests/test_checks.py` -- `check.py` (prism separation, blind pockets, `exec()` globals
  compatibility, docstring coverage), `gallery/profiles/large_refs.json` invariants, and
  `numba`-gated `vprofile.py` checks (synthetic clipnode passage width, real-hull blind pockets,
  `--targets --ref duel|large`).
- `tests/test_ctfprofile.py` -- `gallery/profiles/ctf_refs.json` schema & classic-only invariant,
  plus `numba`-gated `ctfprofile.py` checks (single open center vs. walled side tunnels, off-route
  vantage-grid chokes and route-1 pre-filtering, geodesic U-shape progress, flag exits, walk-time
  swim/tele graph, `func_wall` hull-0 LOS, hook-edge & anchor-range kernels, CLI batch/fast-skip
  handling, report formatting, and end-to-end synthetic BSP `ctf_profile()` + `draw()`).
- `tests/test_collide_cmp.py` -- `collide_cmp.py` (7x11 entity x texture matrix, hull-0 and
  player-hull CLI scenarios, ROI merging/overlap masking against brute force, `.map` parser
  comment/brushDef/quoting hardening).
- `tests/test_version.py` -- `VERSION` SemVer format, `CHANGES.md` heading alignment, absence of
  hardcoded version numbers or `qmap-toolkit` in doc titles and `template/` banners, and
  `README.md` local link/anchor validation.

Keep all tests self-contained: no `ericw-tools`/`qbsp` binaries, no external `.bsp` or `.mvd`
files, and no network access. Build synthetic grids (`MiniGrid`), synthetic `.map` inputs, or
synthetic clipnode trees in memory / temporary directories, and add regression tests whenever
changing logic in `qmap/` or doc/versioning invariants.
