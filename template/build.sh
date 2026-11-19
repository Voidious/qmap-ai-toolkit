#!/bin/bash
# generator -> qbsp -> vis -> light -> checks.   ERICW must point at your ericw-tools build.
set -e
cd "$(dirname "$0")"
T=${ERICW:?set ERICW to your ericw-tools build dir (with qbsp/ vis/ light/)}
QMAP=${QMAP_CORE:-$(cd "$(dirname "$0")/../qmap" && pwd)}
N=$(sed -n "s/^NAME = '\([^']*\)'.*/\1/p" _core.py)
cat _core.py _layout.py _itemh.py _items.py _out.py > gen_map.py
python3 gen_map.py .
rm -f $N.pts
$T/qbsp/qbsp -nopercent $N.map > qbsp.log 2>&1
[ -f $N.pts ] && { echo "LEAK - see $N.pts (a line from the void into the map)"; exit 1; }
$T/vis/vis -nopercent $N.bsp > vis.log 2>&1
$T/light/light -nopercent -extra4 -minlight 5 -minlight_dirt 0 $N.bsp > light.log 2>&1
grep -hiE "warn|error" qbsp.log vis.log light.log | grep -v "texture skip" | grep -v "invalid size data for $" || true
python3 $QMAP/check.py $N.json
# v3: how vertical is it? Each measure against the range of five classic QW maps (VPROFILE=0 skips)
[ "${VPROFILE:-1}" = "0" ] || python3 $QMAP/vprofile.py $N.bsp --targets
