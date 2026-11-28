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
   - Longest clear 3D distance (`sqrt(dx^2 + dy^2 + dz^2)`) from a reachable floor cell to any other reachable floor cell with unobstructed eye-to-body hull-0 LOS across arbitrary azimuths and elevations.
   - Reports `p50`, `p90`, `max`, plus the top 5 spatially distinct sightlines with endpoints, 2D horizontal distance, `dz`, and elevation angle.

2. **Overlook Asymmetry (`overlooked_by_*`, `overlooks_*`, `overlook_net_*`)**
   - Within `--overlook-range` (default `1200u`, matching `vprofile.py`), separates:
     - `overlooked_by`: reachable floor area `>= 64u` **above** a cell that has direct eye-to-body LOS down onto it.
     - `overlooks`: reachable floor area `>= 64u` **below** a cell that the cell can shoot down onto.
   - Signed asymmetry `overlook_net = overlooks_share - overlooked_by_share`:
     - **Strongly negative** (`overlook_net_p05` tail): **uncountered kill boxes** (low ground hammered from above with little counter-overlook).
     - **Strongly positive** (`overlook_net_p95` tail): **oppressive perches** (high ground dominating large floor area with little counter-overlook).
   - Also reports absolute high-ground area in thousands of square units (`overlooked_by_area_k_p90`, `overlooks_area_k_p90`) so kill-box and perch severity remain comparable across compact duel maps (`~1,100k–1,600k`) and large 4v4 TDM maps (`~3,000k–4,700k`).

3. **Disengage / Time-to-Cover (`disengage_*`)**
   - Minimum walking distance (and time at QuakeWorld's `320 u/s` `sv_maxspeed`) along the player-hull movement graph (walk/step, jump, drop, gap jump, push pad, and teleporters at `48u` = `0.15s`) to **either**:
     - Break hull-0 LOS from the cell's **dominant overlooker** (the highest-threat overlooking vantage `>= 64u` above), **or**
     - Cut total visible-floor exposure area by **`>= 50%`**, **or**
     - Break LOS from **`>= 50%`** of the floor currently watching the starting cell without stepping into significantly higher total exposure (`<= 1.15×`) or newly overlooked ground (so turning a 90° corridor corner counts as real cover while open shooting galleries stay exposed).
   - Cells that are not overlooked and already see `<= 64k` sq units (`--shelter-area-k`, roughly a `256×256` enclosed room, capped at 15% of map area on tiny synthetic maps) count as already in cover (`0.0s`).

## Classic Reference Bands

Measured across all 15 classic QuakeWorld reference maps in `gallery/profiles/combat_refs.json` (the 5 compact duel classics from `profiles.json`: `aerowalk`, `dapak12`, `naked3`, `naked4`, `ztndm3`; and the 10 larger classics from `large_refs.json`: `skull`, `bravado`, `spinev2`, `ultrav`, `schloss`, `cmt4`, `dm3`, `e2m2tdm`, `cmt3`, `e1m2`):

| Metric | Duel Healthy (`n=5`) | Duel Extreme | Large Healthy (`n=10`) | Large Extreme |
| --- | --- | --- | --- | --- |
| `sightline_3d_p90` (u) | `936..1236` | `> 1550` | `979..1312` | `> 1700` |
| `sightline_3d_max` (u) | `1176..1585` | `> 2000` | `1298..1888` | `> 2400` |
| `exposure_p90` (share) | `0.246..0.322` | `> 0.420` | `0.095..0.302` | `> 0.400` |
| `overlooked_by_area_k_p90` (k sq u) | `89.3..177.5` | `> 240.0` | `65.0..187.6` | `> 250.0` |
| `overlook_net_p05` (kill-box tail) | `-0.129..-0.072` | `< -0.180` | `-0.103..-0.022` | `< -0.160` |
| `overlook_net_p95` (perch tail) | `0.099..0.134` | `> 0.200` | `0.027..0.147` | `> 0.220` |
| `disengage_p50_s` (s) | `0.30..0.36` | `> 0.55` | `0.28..0.44` | `> 0.65` |
| `disengage_p90_s` (s) | `0.78..1.20` | `> 1.65` | `0.72..1.37` | `> 1.85` |
| `disengage_overlooked_p90_s` (s) | `0.62..0.84` | `> 1.20` | `0.59..1.40` | `> 1.80` |

## Heatmaps and Diff Mode

- **Floor-sliced PNG heatmaps (`--png` / `--png-dir`)** partition floor elevations into `1..4` natural Z bands (configurable with `--slices`) via 1D variance-minimizing breaks so stacked levels render on separate rows instead of hiding lower floors under bridges. Each row plots 3D sightline length (with longest sightlines overlaid), diverging overlook asymmetry (`-killbox` red / `+perch` blue with yellow `x` and green `^` markers), and disengage time (with slow-zone `o` markers).
- **Layout diff mode (`--diff b1.bsp b2.bsp`)** compares every summary metric against the chosen reference pool (`improved`, `regressed`, `tighter`, `looser`, `unchanged`) and renders a shared-coordinate per-slice delta heatmap (green = shorter sightlines / less extreme asymmetry / faster disengage; red = worse).

## Limitations

- Inherits `vprofile.py`'s static collision model: `func_wall` submodels are solid and block LOS, while moving `func_door`/`func_plat` entities are omitted.
- Disengage uses walking/stepping/jumping/dropping/teleporter/pad travel at `320 u/s`; bunnyhopping acceleration, rocket jumps, and CTF grapple hook disengages are not modeled.
- Outputs are layout diagnostics calibrated to classic QuakeWorld maps, not rigid release gates — an intentional central bowl or arena sniper lane can legitimately exceed a classic band if cover and disengage stay healthy.
