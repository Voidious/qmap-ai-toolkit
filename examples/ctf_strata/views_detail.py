import os, sys
sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from views_lanes import shot, sheet
from render import BSP
b = BSP(sys.argv[1])
CAMS = [('Lower hall under the well: the seam round the shaft', (1150, 0, 40), 0, -40),
        ('Pit end wall: slate, coal seam, quarry face, the hook ledge', (0, 0, 120), 0, -18),
        ('North deck into the blue north balcony: strip continuity', (1700, 450, 302), 0, 0),
        ('Stair channel top: the stair meets the bridge and the deck', (100, 736, 200), 0, -4),
        ('Blue base front wall from the flag: balcony edges, gate', (2400, 0, 200), 180, 4),
        ('Arena: loggia and undercroft doors, north side', (200, -200, 60), 100, -12)]
sheet([shot(b, *c) for c in CAMS], sys.argv[2])
