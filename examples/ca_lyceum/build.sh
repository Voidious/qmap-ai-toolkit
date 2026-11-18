#!/bin/bash
# Rebuilds the shipped ca_lyceum_b5 exactly (see GUIDE section 1).  ERICW = your ericw-tools build dir.
set -e
cd "$(dirname "$0")"
T=${ERICW:?set ERICW to your ericw-tools build dir (with qbsp/ vis/ light/)}
QMAP=${QMAP_CORE:-$(cd "$(dirname "$0")/../../qmap" && pwd)}
N=ca_lyceum_b5
cat _core.py _layout.py _itemh.py _items.py _out.py > gen_map.py
python3 gen_map.py .
rm -f $N.pts
$T/qbsp/qbsp -nopercent $N.map > qbsp.log 2>&1
[ -f $N.pts ] && { echo "LEAK"; exit 1; }
$T/vis/vis -nopercent $N.bsp > vis.log 2>&1
$T/light/light -nopercent -extra4 -minlight 5 -minlight_dirt 0 $N.bsp > light.log 2>&1
grep -hiE "warn|error" qbsp.log vis.log light.log | grep -v "texture skip" | grep -v "invalid size data for $" || true
python3 $QMAP/check.py $N.json
