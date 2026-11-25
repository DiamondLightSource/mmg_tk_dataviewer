"""
Plotting functions for XMCD spectra, each drawing onto a list of matplotlib axes,
so the same plot can be drawn in the window and in a larger pop-out window
"""
import numpy as np

from mmg_toolbox.xas import SpectraContainer
from mmg_toolbox.plotting.matplotlib import plot_lines
from ..style import CURRENT
from .analysis import Result, SERIES_AXES

POL1, POL2, DIFF = 'C0', 'C3', 'C2'
SERIES_PLOTS = ['Sum rule moments', 'Dichroism spectra', 'Averaged XAS', 'Dichroism at energy']


def edge_lines(ax, scan: SpectraContainer):
    """Dotted lines at the absorption edges (container.add_edge_lines is always black)"""
    try:
        edges = scan.get_edges()
    except ValueError:
        return
    for edge in edges:
        ax.axvline(edge.energy, color=CURRENT['muted'], lw=0.8, ls=':')


def scan_label(scan: SpectraContainer) -> str:
    m = scan.metadata
    return f"{m.scan_no} {m.pol} {m.mag_field:+.3g}T"


def legend(ax, size: int = 7):
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=size, frameon=False)


def draw_scans(axes, scans: list[SpectraContainer], mode: str, background: bool = False):
    """Spectra of several scans, coloured by polarisation and dashed for negative fields"""
    ax = axes[0]
    pol1 = scans[0].metadata.pol if scans else ''
    for scan in scans:
        spectra = scan.spectra.get(mode) or next(iter(scan.spectra.values()))
        colour = POL1 if scan.metadata.pol == pol1 else POL2
        style = '--' if scan.metadata.mag_field < 0 else '-'
        spectra.plot(ax, color=colour, ls=style, lw=1, label=scan_label(scan))
        if background:
            spectra.plot_bkg(ax, color=colour, ls=':', lw=1, label='_')
    if scans:
        edge_lines(ax, scans[0])
    ax.set_xlabel('E [eV]')
    legend(ax)


def draw_pair(axes, scan1: SpectraContainer, scan2: SpectraContainer, mode: str, background: bool = False,
              alpha: float = 1.0):
    """Top: both processed spectra (and backgrounds). Bottom: their difference"""
    ax1, ax2 = axes[:2]
    for scan, colour in ((scan1, POL1), (scan2, POL2)):
        scan.spectra[mode].plot(ax1, color=colour, lw=1, alpha=alpha, label=scan_label(scan))
        if background:
            scan.spectra[mode].plot_bkg(ax1, color=colour, ls=':', lw=1, alpha=alpha, label='_')
    difference = scan1.spectra[mode] - scan2.spectra[mode]
    ax2.axhline(0, color=CURRENT['muted'], lw=0.8)
    difference.plot(ax2, color=DIFF, lw=1, alpha=alpha, label='difference')
    for ax in (ax1, ax2):
        edge_lines(ax, scan1)
    ax2.set_xlabel('E [eV]')
    legend(ax1)


def draw_average(axes, result: Result):
    """Each polarisation with its average, both averages, and the dichroism"""
    mode, diff = result.mode, result.diff
    for ax, average, name, colour in ((axes[0], result.pol1, diff.spectra1.name, POL1),
                                      (axes[1], result.pol2, diff.spectra2.name, POL2)):
        for scan in average.parents:
            scan.spectra[mode].plot(ax, color=colour, lw=0.7, alpha=0.4, label='_')
        average.spectra[mode].plot(ax, color=colour, lw=1.5, label=f"{name} average")
        ax.set_title(f"{name} ({len(average.parents)} scans)", fontsize=9)
    result.pol1.spectra[mode].plot(axes[2], color=POL1, lw=1.2, label=diff.spectra1.name)
    result.pol2.spectra[mode].plot(axes[2], color=POL2, lw=1.2, label=diff.spectra2.name)
    axes[2].set_title('Averages', fontsize=9)
    axes[3].axhline(0, color=CURRENT['muted'], lw=0.8)
    result.spectra.plot(axes[3], color=DIFF, lw=1.2, label=diff.name)
    axes[3].set_title(f"{diff.name}: {result.signal_ratio():.1%} of XAS", fontsize=9)
    for ax in axes[:4]:
        edge_lines(ax, diff)
        ax.set_xlabel('E [eV]')
        legend(ax)


def draw_sum_rules(axes, result: Result, split_energy: float):
    """Top: averaged spectra. Bottom: dichroism with the L3 (red) and L2 (blue) integration regions"""
    ax1, ax2 = axes[:2]
    result.pol1.spectra[result.mode].plot(ax1, color=POL1, lw=1.2, label=result.diff.spectra1.name)
    result.pol2.spectra[result.mode].plot(ax1, color=POL2, lw=1.2, label=result.diff.spectra2.name)
    ax2.axhline(0, color=CURRENT['muted'], lw=0.8)
    result.spectra.plot_sum_rules(ax2, split_energy=split_energy, edges=result.diff.get_edges(),
                                  color=DIFF, lw=1, label=result.diff.name)
    for ax in (ax1, ax2):
        edge_lines(ax, result.diff)
        ax.axvline(split_energy, color=CURRENT['text'], lw=1, ls='--')
    ax2.set_xlabel('E [eV]')
    legend(ax1)


def draw_series(axes, results: list[Result], x_name: str, kind: str, energy: float = 0):
    """Results of the series against field or temperature"""
    ax = axes[0]
    if not results:
        return
    x_values = [SERIES_AXES[x_name](r) for r in results]
    order = np.argsort(x_values)
    results = [results[i] for i in order]
    x_values = np.array(x_values)[order]
    unit = x_name.split()[-1].strip('()')
    if kind == 'Sum rule moments':
        orbital = np.array([r.orbital for r in results])
        spin = np.array([r.spin for r in results])
        ax.plot(x_values, orbital, 'o-', label='L')
        ax.plot(x_values, spin, 's-', label='S')
        with np.errstate(divide='ignore', invalid='ignore'):
            ax.plot(x_values, orbital / spin, '^--', label='L/S')
        ax.set_xlabel(x_name)
        ax.set_ylabel('μB')
    elif kind == 'Dichroism at energy':
        ax.plot(x_values, [r.signal_at(energy) for r in results], 'o-', label=f"{energy:g} eV")
        ax.set_xlabel(x_name)
        ax.set_ylabel('dichroism')
    else:
        if kind == 'Dichroism spectra':
            data = [(x, r.spectra.energy, r.spectra.signal) for x, r in zip(x_values, results)]
            lines, _ = plot_lines(ax, *data, line_spec='-', lw=1)
        else:
            data = [(x, s.energy, s.signal) for x, r in zip(x_values, results)
                    for s in (r.pol1.spectra[r.mode], r.pol2.spectra[r.mode])]
            lines, _ = plot_lines(ax, *data, line_spec='-', lw=1)
            for line in lines[1::2]:
                line.set_linestyle('--')
        step = len(lines) // len(results)
        for line, x in zip(lines[::step], x_values):
            line.set_label(f"{x:g} {unit}")
        ax.set_xlabel('E [eV]')
        edge_lines(ax, results[0].diff)
    legend(ax, 8)
