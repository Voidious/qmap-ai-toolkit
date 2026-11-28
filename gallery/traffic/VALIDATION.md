# Topology traffic versus human occupancy

**Finding: shortest-route topology does not reliably separate hot and cold rooms
across this reference set.** It is useful as a structural hypothesis generator,
not a validated predictor of player occupancy or map quality. No thresholds were
fitted to these demos. In particular, the tested ztndm3 CA match has almost no
rank agreement, and its predicted hot quartile is less occupied than its cold one.

## Method and inputs

Computed from the existing local human MVD corpus (`Downloads/202611`) and
matching-name local BSPs, with default traffic settings and the stated modes.
The complete aggregate evidence, hashes, exact play windows, parser unknown-message
counts, projection coverage and per-demo correlations are in [`reference.json`](reference.json).
No BSPs, demos, textures or player identities are redistributed.

- Directed 16-unit `vprofile.build_floor_graph()`, equal-shortest-path splitting,
  spawn-pair CA demand and flag/base-exit CTF demand. These four maps use **all**
  their available demand pairs (42, 42, 182 and 60); pair sampling is not a source
  of uncertainty here. Modeled movement and endpoint placement remain approximations.
  Additional ztndm3 TDM/FFA checks use all 56/98 available item/mixed pairs.
- Alive player-seconds in complete CA rounds / CTF match windows. Two dm6
  recordings without complete round windows are explicitly omitted; no warmup
  fallback was used. Matched floor coverage excludes large sample gaps and
  unsupported airborne/swim/hook positions rather than inventing floor cells.
- Spearman rank correlation of patch mean predicted route share versus observed
  seconds per floor cell. Patches are graph-connected portions of 128-unit XY /
  64-unit Z bins, with at least four cells. Zero-occupancy patches participate.
  Hot/cold ratios compare observed density in predicted upper/lower quartiles,
  retaining ties. Correlations use ranks and are not frame-level sample tests.

## Results

| BSP / mode | Checked demos | Floor patches | Pooled rho | Per-demo median (range) | Hot/cold occupancy ratio | Matched player-time |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| dm6 / CA | 20 of 22 | 222 | 0.2064 | 0.2403 (0.0598..0.3420) | 0.9620 | 92.65..98.81% |
| ztndm3 / CA | 1 | 202 | 0.0240 | 0.0240 (one match) | 0.8802 | 97.60% |
| ca_agora / CA | 9 | 322 | 0.2935 | 0.2700 (0.1342..0.3754) | 1.3369 | 97.03..97.78% |
| ctf1 / CTF | 3 | 386 | 0.1492 | 0.1624 (0.1561..0.2031) | 1.1876 | 87.77..90.44% |
| ztndm3 / TDM | 2 | 202 | 0.1303 | 0.1476 (0.1302..0.1649) | 1.2178 | 97.16..99.00% |
| ztndm3 / FFA | 3 | 202 | 0.2394 | 0.1807 (0.1066..0.2476) | 1.7517 | 97.43..98.87% |

The metric is weakly positive on three maps, essentially uninformative on the
one ztndm3 match. Hot/cold quartiles separate occupancy in the expected direction
on agora and ctf1, **not** dm6 or ztndm3. A positive pooled rank correlation alone
is insufficient to claim robust hot-room separation.
The extra TDM/FFA recordings exercise the other demand modes and have weakly
positive agreement; they do not rescue the failed universal claim. Across all
six map/mode comparisons, **38 recordings are checked out of 40 candidates**.

dm6 has only **85.714% routed demand mass**: six of its 42 ordered spawn pairs
are disconnected in the shared movement model. Other maps route all selected
demand. This missingness is exposed, not normalized away in the coverage report;
cell scores condition on successfully routed pairs. Patches and neighboring
frames are dependent; neither these correlations nor the many player updates
provide independent-sample significance or cross-group generalization.
ztndm3's quad support is outside spawn reachability in the shared movement model,
so TDM/FFA explicitly report `QUAD1` unresolved and exclude it. This is a real
demand-coverage limitation, not evidence that quad traffic is unimportant.
Different demo hashes establish distinct recordings, not necessarily independent
matches or sessions; no train/test generalization claim is made.

## Reproduce

Use the BSP with the hash in `reference.json`, and supply that map's listed demos:

```bash
python3 qmap/trafficprofile.py dm6.bsp --mode ca --json dm6.traffic.json --png dm6.traffic.png
python3 demos/traffic.py dm6.bsp ca_match1.mvd ca_match2.mvd --mode ca \
  --skip-incomplete --json dm6.validation.json --png dm6.observed.png
```

Repeat for ztndm3 and ca_agora with `--mode ca`, and ctf1 with `--mode ctf`.
Omitted dm6 recordings are `ca_red_vs_blue[dm6]20260620-0223.mvd` and
`ca_red_vs_blue[dm6]20260620-0314.mvd`. Filename labels are checked, but the
minimal MVD reader does not verify a BSP checksum embedded by the server;
matching-name build identity and final roster interpretation remain limitations.

Floor-sliced predicted/observed figures accompany the development evidence.
They use independent column scales and explicitly label occupancy versus route
share; matching colors do not establish matching absolute quantities.

The implementation is regression-tested on synthetic hot bridges, low-demand
side regions, independent parallel routes, directed disconnection, teleport
costs and source-safe build diffs. Those tests establish graph behavior, not
human predictive validity. Better predictions would need additional behavioral
demand, tactical alternative routes and held-out human validation; that work
is not silently folded into this topology-only feature.
