"""b3 first look: the pit and a base, close up."""
import os, sys
sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'qmap'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from views_lanes import shot, sheet
from render import BSP
b = BSP(sys.argv[1])
CAMS = [('Pit: arena from blue\'s arena arch, Quad, beam, night sky', (488, 300, 60), 196, -8),
        ('Pit: from the north alcove, the stair up to the bridge, seam under the bridge', (-480, 790, 60), 0, -10),
        ('Pit: on the covered north bridge (256)', (440, 560, 302), 180, 6),
        ('Pit: undercroft rails toward red\'s hall', (480, 544, 46), 180, 2),
        ('Blue base: flag on its agate stand, the perch above', (2250, 0, 200), 0, 6),
        ('Blue base: from the south balcony (256) across to the gate', (2600, -560, 302), 160, 14),
        ('Red base from the mezzanine (128)', (-2560, 0, 174), 0, 4),
        ('Blue lower hall: room-and-pillar slate, timber roof', (1500, 400, 60), 200, 0)]
sheet([shot(b, *c) for c in CAMS], sys.argv[2])
