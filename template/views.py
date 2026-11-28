"""Preview renders of a compiled .bsp (qmap-ai-toolkit, generic).
Edit CAMS for your map: (label, (x, y, z eye), yaw degrees (0 = +x, 90 = +y), pitch degrees (+ = DOWN, as in Quake; - looks up)).
Usage: python3 views.py map.bsp out.png [--before older.bsp] [--gamma 0.5 --contrast 1.2]
Both builds use the same CAMS, FOV, and lighting settings. Unsafe cameras are marked in red.
See qmap/RENDERING.md for calibration, JSON camera lists, and --strict-cameras."""
import os
import sys

sys.path.insert(0, os.environ.get('QMAP_CORE') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'qmap'))
from view_sheet import main as sheet_main, make_sheet  # noqa: E402

CAMS = [('hall from the south-west corner', (-300, -300, 60), 45, 0),
        ('hall: plinth and the doorway north', (0, -330, 60), 90, -4),
        ('east wing: gallery steps and the perch', (560, -280, 60), 40, 6),
        ('low room: ramp to the ledge, octagonal pillar', (330, 920, -36), 184, 4)]


def main(bsp, out, **options):
    return make_sheet(bsp, out, CAMS, **options)


if __name__ == '__main__':
    sheet_main(CAMS)
