# Player-hull traffic and dead-wing analysis

`trafficprofile.py` predicts where mode-specific shortest routes concentrate on
the same **directed 16-unit player-hull graph** used by `vprofile.py`. It reports
approximate demand-weighted betweenness, predicted dead wings and overloaded
choke candidates, not actual player traffic or a map-balance score.

Requires the full toolkit Python environment: NumPy, SciPy, Numba, and Matplotlib
for PNGs. No engine, reference assets or demos are needed for ordinary analysis.

```bash
python3 qmap/trafficprofile.py map_b1.bsp --mode ca --json traffic.json --png traffic.png
python3 qmap/trafficprofile.py map_b1.bsp map_b2.bsp --mode tdm --png-dir figures/
python3 qmap/trafficprofile.py --diff map_b1.bsp map_b2.bsp --mode ffa --json diff.json --png shift.png
python3 demos/traffic.py dm6.bsp match1.mvd match2.mvd --mode ca --json validation.json --png observed.png
```

Diagnostics exit **0** (advisory). Input/configuration errors and explicit budget
refusals exit **2**. An analysis without usable demand reports missing coverage;
it does not label all floor dead or claim the map passed. JSON includes every
floor cell, endpoint projection, sampled pair, unreachable route and warning.
Output paths cannot overwrite input BSPs/demos, and PNG/JSON paths must differ.

## Movement and demand

The graph includes vprofile's walk/step, jump, directed drop, gap-jump, teleport
and simulated push-pad edges. Doors/plats count as open; `func_wall` is solid.
There is no new movement inference. Edge costs are vprofile model units, not
measured seconds: teleports cost 48 units rather than zero, preventing zero-cost
cycles from making shortest-path counts undefined. Parallel edges to the same
node use their minimum cost, not extra copies of the same route.

| Mode | Demand families |
| --- | --- |
| `ca` | Ordered deathmatch spawn-to-spawn pairs. |
| `tdm` | Ordered major-item pairs: RL/LG, armor, MH and major powerups, following `itemprofile.KEYS`. |
| `ffa` | Both spawn and major-item families, each with equal total demand. |
| `ctf` | Flag-to-flag, each flag to/from its own base exits, and cross-base exit pairs; equal total mass per available family. |
| `auto` | CTF if team-1 flag exists, otherwise FFA. Use an explicit mode for reproducible comparisons. |

Demand is **not** weighted by respawn timers, weapon strength, team strategy,
player count or observed demo behavior. Missing families are reported, and
remaining available families share the demand mass. Duplicate endpoint positions
do not create self-routes. Spawnflags excluding deathmatch suppress that endpoint.
Pickup projection reuses itemprofile's supported floor/touch stance rules.

CTF exits are continuing components of a 384-unit **directed geodesic shell**
(16 units inward / 32 outward), with at least three floor cells. Continuation
must reach the opposing flag without returning inside the base shell. Nearby
floor cells connect a component only through local walk/jump/drop edges. This
is a fixed-radius base-boundary heuristic, not semantic room recognition; small
maps may provide only flag routes. CTF uses the shared ground-floor graph,
**not** ctfprofile's extra free-swim/grapple graph. Hook-only travel is absent.

At most `--max-pairs 256` ordered pairs are sampled without replacement by
default, stratified across families with `--seed 0`. Family weight is preserved
after sampling. Pair enumeration is ordered by endpoint coordinates, avoiding
sampling changes from entity-list reordering. JSON records the possible/sample counts and selected IDs. Set a
larger cap (maximum 4096) to check convergence; no confidence interval is implied.
Refusals protect against over 512 endpoints, a million candidate pairs or 150,000
floor nodes. The underlying shared floor scan still runs before the node limit.

## What the scores mean

For each sampled source, Dijkstra distances define a shortest-path DAG. A
target-weighted [Brandes dependency accumulation](https://doi.org/10.1080/0022250X.2001.9990249)
splits demand in proportion to the number of equal shortest paths. Logarithmic
path counts avoid overflow in large grids. The absolute tie tolerance is 1e-7
model units. It does not distribute demand onto longer but tactically useful routes.

- `route_share`: fraction of **successfully routed** demand visiting a cell,
  including source/target cells. This is the heatmap quantity (0..1).
- `betweenness`: the same fractional demand excluding each pair's endpoints.
- `routed_weight` / `unreachable_weight`: successful versus missing selected
  demand. Disconnected directed pairs do not silently become zero-length routes.
- `relative_density`: mean route share on a local floor patch divided by mean
  route share on all spawn-reachable cells. This is not a probability.

All floor nodes are retained in JSON, with a separate spawn-reachable mask.
Maps without spawns or applicable endpoints remain inspectable but cannot
establish traffic/dead-wing coverage. Requesting TDM on an itemless CA map is
not a clean pass.

## Diagnostics and figures

Local floor patches lie within world-aligned `--patch-grid 128` XY squares and
64-unit height bands. They are split into actual local graph components, so two
rooms across a wall do not borrow one another's traffic. Diagnostic regions
join nearby walk/jump/drop cells (XY displacement at most 16 on each axis,
height change at most 44); teleports, long gaps and pads do not join regions.

- **Predicted dead wings:** contiguous low-density floor covering at least
  `--min-region-area 16384` square units, with patch density at most
  `--dead-fraction 0.05` of the map average.
- **Overloaded choke candidates:** connected patches with density at least
  `--choke-multiple 4` times average and peak endpoint-excluding cell betweenness
  at least `--choke-share 0.25`. A busy endpoint alone is not a choke. These can be hot hubs rather than narrow doorways;
  inspect geometry / vprofile passage widths before calling one a choke.

These are configurable **heuristics**, not thresholds calibrated to human
balance judgments. Near-wall floor, camping space or a longer alternate route
can be cold under shortest-path demand without being undesirable design.

PNGs show separate world-aligned 128-unit Z slices with a shared route-share
scale (up to 32 slices). Diffs use identical settings and resolved modes, common
world XY and floor height rounded to 4 units. Matched cells show signed raw
route-share shifts; added floor is green and removed floor gray. Before/after
use a common color scale and extent. Endpoint changes are reported explicitly:
different demand, unresolved mappings or sampled physical pairs are not a
geometry-only experiment; ID renaming alone does not change demand. Floor shifts across the
4-unit quantization boundary appear as added/removed, not forced matches.

## Human MVD comparison

`demos/traffic.py` compares alive **player-seconds**, not raw update counts, with
the prediction on the same reachable floor patches. CA uses complete KTX round
windows (countdown + 5 through round stats); other modes use match-begun/over
prints. There is no silent whole-demo fallback: incomplete recordings refuse
unless `--skip-incomplete` explicitly records/omits them. `--start` / `--end`
select explicit seconds; `--whole-demo` opts into possible warmup contamination.

Player intervals require alive endpoints and a gap at most 0.25 seconds. Player
origins are converted to feet (-24 units) and projected to nearby supported floor
(within 32 XY, floor at most 8 above / 96 below the feet). Rejected time and
matched fractions are reported. Duplicate demo bytes are refused; filename map
tags, when present, must match the BSP stem. This does not prove the recorded
build matches the BSP. Final roster team/name state and unknown message-block
tails remain limitations of the minimal MVD reader. CA/CTF/TDM select named
red/blue players; other team naming requires adapting that filter.

Spearman rank correlation is tie-aware, over patches with at least four cells,
including zero-occupancy patches. A visited-only correlation is also reported.
Predicted upper/lower quartile occupancy densities provide a hot/cold check;
ties are retained and constant predictions have no defined correlation. Results
include pooled occupancy, per-demo median/range, parser unknown-message counts,
input hashes and exact windows. No frame-level p-values or independent-sample
claims are made: spatial neighbors and frames are highly dependent. Occupancy
also measures fighting/camping time, whereas topology predicts traversal demand.

The measured reference validation and its limits are in
[`gallery/traffic/VALIDATION.md`](../gallery/traffic/VALIDATION.md).
