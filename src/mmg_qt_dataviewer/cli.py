"""
Command line interface for the Qt Dataviewer

    $ dataviewer-qt                     # experiment selection window for the default beamline
    $ dataviewer-qt i16                 # experiment selection window for a beamline
    $ dataviewer-qt /path/to/experiment # data viewer for a folder of NeXus files
    $ dataviewer-qt /path/to/scan.nxs   # NeXus viewer for a single file
"""
import os
import sys

from mmg_toolbox.utils.env_functions import get_beamline, get_beamline_from_directory
from .config import BEAMLINE_CONFIG, get_config
from .common import get_app, show_window


def run(*args: str):
    if any(arg in ('-h', '--help') for arg in args):
        print(__doc__)
        print(f"Available beamlines: {list(BEAMLINE_CONFIG)}")
        return
    get_app(theme=get_config().get('theme', 'system'))
    beamline = next((arg for arg in args if arg in BEAMLINE_CONFIG), get_beamline())
    for arg in args:
        if os.path.exists(arg):
            path = os.path.abspath(arg)
            config = get_config(beamline=get_beamline_from_directory(path, beamline))
            if os.path.isdir(path):
                from .data_viewer import DataViewer
                return show_window(DataViewer(path, config))
            from .nexus_viewer import NexusViewer
            return show_window(NexusViewer(path, config))
    from .title_window import TitleWindow
    return show_window(TitleWindow(beamline))


def cli_run():
    run(*sys.argv[1:])
