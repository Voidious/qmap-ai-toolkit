# 3D BSP Combat Exposure, Overlook Asymmetry & Disengage Analyzer

`combatprofile.py` runs `numba`-accelerated 3D visibility and time-to-cover diagnostics on any compiled Quake BSP29 map. It reuses `vprofile.py`'s walkable 16-unit player-hull floor nodes and exact hull-0 BSP tree raycasting (including static `func_wall` submodels) so every reachable floor cell is evaluated across all 3D azimuths and elevations — replacing `sightlines.py`'s 2D axial X/Y blind spots and extending `vprofile.py`'s map-wide overlook averages into spatial heatmaps and actionable hotspots.

Requires Python 3, `numpy`, `numba`, and `matplotlib` (for PNG heatmaps).

## Usage

```bash
# Single map with classic duel reference bands, JSON report, and floor-sliced PNG heatmap
python3 qmap/combatprofile.py map_b1.bsp --ref duel --json map_b1.combat.json --png map_b1.combat.png

# Larger 4v4 TDM / multi-player map against the 10-map large classic pool
python3 qmap/combatprofile.py map_b1.bsp --ref large --png-dir figs/

# Batch multiple maps (or compare against all 15 classics)
python3 qmap/combatprofile.py map_b1.bsp map_b2.bsp --ref all --png-dir figs/ --json batch.json

# Layout review diff mode (_b1 vs _b2) with metric deltas and spatial diff PNG
python3 qmap/combatprofile.py --diff map_b1.bsp map_b2.bsp --ref duel \
  --json diff.json --png map_b1_vs_b2.diff.png
```

Diagnostics exit **0** by default (advisory); invalid inputs or maps without reachable spawns exit **2**.

## Per-Cell Metrics

All metrics are computed on every reachable 16-unit player-hull floor node (`eye = floor + 46`, `body = floor + 32`), using exact iterative hull-0 BSP visibility against up to `--sample-cap` (default `1400`) deterministically bucketed, area-weighted 3D floor representatives (exact 16u all-pairs when reachable cells `<= sample_cap`):

1. **True 3D Combat Sightline Length (`sightline_3d_*`)**
   - Longest clear 3D distance (`sqrt(dx^2 + dy^2 + dz^2)`) from a reachable floor cell to any other reachable floor cell with unobstructed eye-to-body hull-0 LOS across arbitrary azimuths and elevations, up to `--max-sightline` (default `4096u`).
   - If any unobstructed line exceeds `--max-sightline`, it is capped at `--max-sightline` (rather than silently dropped), flagged in JSON (`sightline_capped` / `sightline_capped_cells`), and noted in the text report so you can raise `--max-sightline` on very large CTF or open maps.
   - Reports `p50`, `p90`, `max`, plus the top 5 spatially distinct sightlines with endpoints, 2D horizontal distance, `dz`, and elevation angle.

2. **Overlook Asymmetry (`overlooked_by_*`, `overlooks_*`, `overlook_net_*`)**
   - Within `--overlook-range` (default `1200u`, matching `vprofile.py`) and `--overlook-dz` (default `64u`), separates:
     - `overlooked_by`: reachable floor area `>= overlook_dz` **above** a cell that has direct eye-to-body LOS down onto it.
     - `overlooks`: reachable floor area `>= overlook_dz` **below** a cell that the cell can shoot down onto.
   - Signed asymmetry `overlook_net = overlooks_share - overlooked_by_share`:
     - **Strongly negative** (`overlook_net_p05` tail): **uncountered kill boxes** (low ground hammered from above with little counter-overlook).
     - **Strongly positive** (`overlook_net_p95` tail): **oppressive perches** (high ground dominating large floor area with little counter-overlook).
   - Also reports absolute high-ground area in thousands of square units (`overlooked_by_area_k_p90`, `overlooks_area_k_p90`) and clustered `killbox_share` / `perch_share` so kill-box and perch severity remain comparable across compact duel maps (`~1,080k–1,600k`) and large multi-player maps (`~1,400k–4,710k`).

3. **Disengage / Time-to-Cover (`disengage_*`)**
   - Minimum walking distance (and time at QuakeWorld's `320 u/s` `sv_maxspeed`) along `vprofile.build_floor_graph()`'s player-hull movement graph (walk/step, jump, drop, gap jump, push pad, and teleporters at `48u` = `0.15s`) to reach real cover via **any** of:
     - **Regional overlooker escape**: break hull-0 LOS from **`>= 50%`** of the dominant overlooker's high-ground region (active overlooking samples within `192u` horizontally and `<= 48u` vertically of the highest-threat vantage) **and** cut total `overlooked_by` area by **`>= 50%`**, without stepping into significantly higher exposure (`<= 1.15×`, or `<= 1.5×` when eliminating all overlookers completely),
     - **Exposure halving**: cut total visible-floor exposure area by **`>= 50%`**,
     - **Active-watcher break**: break LOS from **`>= 50%`** of the floor currently watching the starting cell without stepping into significantly higher total exposure (`<= 1.15×`) or newly overlooked ground (so turning a 90° corridor corner counts as real cover while open shooting galleries stay exposed), or
     - **Sheltered cover**: reach un-overlooked floor (`dom_obs < 0`) with visible area `<= 64k` sq units (`--shelter-area-k`, roughly a `256×256` enclosed room, capped at 15% of map area on tiny synthetic maps).
   - Cells that start un-overlooked and already see `<= shelter_area` count as already in cover (`0.0s`).

## Choosing `--ref` and Classic Reference Bands

Match `--ref` to your map's floor area and target player count:

- **`--ref duel`** (`1,083k–1,600k` sq u): 5 compact 1v1 / small FFA classics (`aerowalk`, `dapak12`, `naked3`, `naked4`, `ztndm3`).
- **`--ref large`** (`1,400k–4,710k` sq u): 10 larger multi-player and 4v4 TDM classics (`skull`, `bravado`, `spinev2`, `ultrav`, `schloss`, `cmt4`, `dm3`, `e2m2tdm`, `cmt3`, `e1m2`). Use `--ref large` for **Clan Arena 6–12** (`~3,000k–4,200k` sq u), 4v4 TDM, and larger arenas — comparing them to `--ref duel` flags sightline and overlooked-by bands from map scale alone.
- **`--ref all`**: full 15-classic envelope.

Measured across all 15 classic QuakeWorld reference maps in `gallery/profiles/combat_refs.json` (spatial kill-box and oppressive-perch warnings are also calibrated above each pool's classic ceilings so healthy classics emit zero false warnings):

| Metric | Duel Healthy (`n=5`) | Duel Extreme | Large Healthy (`n=10`) | Large Extreme |
| --- | --- | --- | --- | --- |
| `sightline_3d_p90` (u) | `936..1236` | `> 1550` | `979..1312` | `> 1700` |
| `sightline_3d_max` (u) | `1176..1585` | `> 2000` | `1298..1888` | `> 2400` |
| `exposure_p90` (share) | `0.246..0.322` | `> 0.420` | `0.095..0.302` | `> 0.400` |
| `overlooked_by_area_k_p90` (k sq u) | `89.3..177.5` | `> 240.0` | `65.0..187.6` | `> 250.0` |
| `overlook_net_p05` (kill-box tail) | `-0.129..-0.072` | `< -0.180` | `-0.103..-0.022` | `< -0.160` |
| `overlook_net_p95` (perch tail) | `0.099..0.134` | `> 0.200` | `0.027..0.147` | `> 0.220` |
| `killbox_share` (share) | `0.061..0.211` | `> 0.300` | `0.026..0.281` | `> 0.380` |
| `perch_share` (share) | `0.040..0.074` | `> 0.140` | `0.014..0.098` | `> 0.160` |
| `disengage_p50_s` (s) | `0.37..0.50` | `> 0.70` | `0.38..0.47` | `> 0.68` |
| `disengage_p90_s` (s) | `0.87..1.25` | `> 1.70` | `0.92..1.38` | `> 1.85` |
| `disengage_overlooked_p90_s` (s) | `0.82..1.15` | `> 1.55` | `0.73..1.32` | `> 1.75` |

## Heatmaps and Diff Mode

- **Floor-sliced PNG heatmaps (`--png` / `--png-dir`)** partition floor elevations into `1..4` natural Z bands (configurable with `--slices`) via 1D variance-minimizing breaks so stacked levels render on separate rows instead of hiding lower floors under bridges. Panels display world-coordinate `(x, y)` axes matching the coordinates printed in the text report, plotting 3D sightline length (with longest sightlines overlaid), diverging overlook asymmetry (`-killbox` red / `+perch` blue with yellow `x` and green `^` markers), and disengage time (with slow-zone `o` markers).
- **Layout diff mode (`--diff b1.bsp b2.bsp`)** compares every summary metric against the chosen reference pool (`improved`, `regressed`, `tighter`, `looser`, `unchanged`) using per-metric noise floors (`16u` lengths, `0.01` shares, `8k` sq u areas, `0.03s` times) to suppress sub-cell jitter. The shared-coordinate diff PNG uses a dark-centered diverging colormap (green = improved, dark slate = unchanged, red = worse) and overlays added-only floor in cyan and removed-only floor in violet so footprint changes stand out cleanly.

## Limitations

- Inherits `vprofile.py`'s static collision model: `func_wall` submodels are solid and block LOS, while moving `func_door`/`func_plat` entities are omitted.
- Disengage uses walking/stepping/jumping/dropping/teleporter/pad travel at `320 u/s`; bunnyhopping acceleration, rocket jumps, and CTF grapple hook disengages are not modeled.
- Outputs are layout diagnostics calibrated to classic QuakeWorld maps, not rigid release gates — an intentional central bowl or arena sniper lane can legitimately exceed a classic band if cover and disengage stay healthy.
