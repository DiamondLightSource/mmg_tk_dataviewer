"""
Configuration options, shared with the tk dataviewer (same config file)
"""
import os
import json

from mmg_toolbox.utils.env_functions import TMPDIR, get_beamline, get_user
import mmg_toolbox.beamline_metadata.config as beamline_config

BEAMLINE_CONFIG = beamline_config.BEAMLINE_CONFIG
CONFIG_FILE = os.path.join(TMPDIR, f'mmg_config_{get_user()}.json')
COLORMAPS = ['viridis', 'twilight', 'plasma', 'inferno', 'Greys', 'Blues', 'hot', 'jet', 'rainbow', 'Spectral']


class C(beamline_config.C):
    """Names used in config dict"""
    recent_data_directories = 'recent_data_directories'
    plot_marker = 'plot_marker'
    plot_linestyle = 'plot_linestyle'
    default_colormap = 'default_colormap'
    image_flip_y = 'image_flip_y'
    image_flip_x = 'image_flip_x'
    image_log = 'image_log'
    current_dir = 'current_dir'
    current_proc = 'current_proc'
    current_nb = 'current_nb'


CONFIG = {
    **beamline_config.CONFIG,
    C.conf_file: CONFIG_FILE,
    C.default_directory: os.path.expanduser('~'),
    C.recent_data_directories: [],
    C.image_flip_x: False,
    C.image_flip_y: True,
    C.image_log: False,
    C.plot_marker: None,
    C.plot_linestyle: None,
    C.default_colormap: 'twilight',
}


def default_config(beamline: str | None = None) -> dict:
    """Return the default config dict for a beamline"""
    cfg = CONFIG.copy()
    beamline = beamline or get_beamline()
    cfg.update(BEAMLINE_CONFIG.get(beamline, {}))
    return cfg


def get_config(beamline: str | None = None) -> dict:
    """Merge the user's saved config into the default beamline config"""
    user_config = {}
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            user_config = json.load(f)
    cfg = default_config(beamline)
    if beamline and user_config.get(C.beamline) not in (None, beamline):
        user_config.update(cfg)  # beamline defaults win when changing beamline
        return user_config
    cfg.update(user_config)
    return cfg


def roi_params(roi) -> tuple:
    """
    Return a config ROI as the 9 values used since mmg_toolbox 0.8:
        (name, cen_i, cen_j, wid_i, wid_j, det_name, peak_search, peak_rgn_i, peak_rgn_j)
    ROIs saved before then have only the first 6 values, and no peak search.
    """
    return (*roi, False, None, None)[:9]


def add_config_rois(filename: str, hdf_map, config: dict) -> list[tuple]:
    """
    Add the config ROIs for detectors in this file to the hdfmap, creating names like 'roi_total'.
    mmg_toolbox's NexusScan builds the expressions for fixed and peak-search ROIs.
    Returns the ROIs added, as 9 values.
    """
    from mmg_toolbox.nexus.nexus_scan import NexusScan
    rois = [roi_params(roi) for roi in config.get(C.roi) or [] if len(roi) in (6, 9)]
    rois = [roi for roi in rois if roi[5] in hdf_map.image_data]
    NexusScan(filename, hdf_map, {C.roi: rois})
    return rois


def roi_box(hdf, hdf_map, roi: tuple):
    """
    Return the pixel positions [[i, j], ...] of the corners of an ROI added by add_config_rois.
    Peak-search ROIs read the whole detector stack, so cache the result.
    """
    import numpy as np
    return np.asarray(hdf_map.eval(hdf, f"{roi[0]}_box"), dtype=float)


def save_config(config: dict):
    """Save the config dict to the config file"""
    filename = config.get(C.conf_file, CONFIG_FILE)
    with open(filename, 'w') as f:
        json.dump(config, f, indent=2)
