"""
XMCD analysis state, independent of Qt: processing chains, pairs, averages, sum rules and code generation

    steps = [Step('divide_by_preedge'), Step('remove_background', {'name': 'flat'})]
    pairs = find_pairs(load_scans(*files), by='polarisation')
    result = Result.calculate(pairs, steps, mode='tey')
    print(to_script([result]))
"""
from __future__ import annotations

import json
import inspect
import functools
import datetime
from dataclasses import dataclass, field

import numpy as np

from mmg_toolbox import xas
from mmg_toolbox.xas import SpectraContainer, SpectraContainerSubtraction
from mmg_toolbox.xas.spectra import BACKGROUND_FUNCTIONS, BACKGROUND_DOCSTRINGS
from mmg_toolbox.xas.absorption_edges import Element

# SpectraContainer methods offered as processing steps, with a short description
PROCESSES = {
    'divide_by_preedge': 'Divide by the mean signal in the pre-edge region',
    'divide_by_postedge': 'Divide by the mean signal in the post-edge region',
    'divide_by_jump': 'Divide by the edge jump between start and end',
    'divide_by_peak': 'Divide by the maximum signal',
    'divide_by_signal_at_energy': 'Divide by the signal at an energy',
    'trim': 'Trim the energy range',
    'shift': 'Shift the energy axis',
}
BACKGROUND = 'remove_background'
DEFAULT_STEPS = (('divide_by_preedge', {}), (BACKGROUND, {'name': 'flat'}))
AUTO = None  # parameter value filled in by mmg_toolbox, e.g. edge energies


@dataclass
class Step:
    """A processing step: a SpectraContainer method name and its keyword arguments"""
    method: str
    kwargs: dict = field(default_factory=dict)

    def __post_init__(self):
        self.kwargs = {**self.defaults(), **self.kwargs}

    def function(self):
        if self.method == BACKGROUND:
            return BACKGROUND_FUNCTIONS[self.kwargs.get('name', 'flat')]
        return getattr(SpectraContainer, self.method)

    def defaults(self) -> dict:
        """Parameters of the step with their default values (AUTO if there is no default)"""
        skip = {'self', 'energy', 'signal'}
        params = {
            name: AUTO if p.default is inspect.Parameter.empty else p.default
            for name, p in inspect.signature(self.function()).parameters.items()
            if name not in skip and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        }
        return {'name': self.kwargs.get('name', 'flat'), **params} if self.method == BACKGROUND else params

    def description(self) -> str:
        if self.method == BACKGROUND:
            return BACKGROUND_DOCSTRINGS[self.kwargs['name']]
        return PROCESSES.get(self.method, self.method)

    def arguments(self) -> dict:
        """Keyword arguments to pass, leaving out values mmg_toolbox fills in"""
        return {k: v for k, v in self.kwargs.items() if v is not AUTO}

    def label(self) -> str:
        args = self.arguments()
        name = f"background: {args.pop('name')}" if self.method == BACKGROUND else self.method.replace('_', ' ')
        values = ', '.join(f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in args.items())
        return f"{name} ({values})" if values else name

    def code(self) -> str:
        """Python code calling this step on a SpectraContainer, e.g. .remove_background('flat', ev_from_start=5)"""
        args = self.arguments()
        parts = [repr(args.pop('name'))] if self.method == BACKGROUND else []
        parts += [f"{k}={v!r}" for k, v in args.items()]
        return f".{self.method}({', '.join(parts)})"

    def apply(self, scan: SpectraContainer) -> SpectraContainer:
        return getattr(scan, self.method)(**self.arguments())

    def copy(self) -> Step:
        return Step(self.method, dict(self.kwargs))


def default_steps() -> list[Step]:
    return [Step(method, dict(kwargs)) for method, kwargs in DEFAULT_STEPS]


def apply_chain(scan: SpectraContainer, steps: list[Step]) -> SpectraContainer:
    """Apply each processing step in turn, returning the processed SpectraContainer"""
    return functools.reduce(lambda s, step: step.apply(s), steps, scan)


def chain_code(steps: list[Step]) -> str:
    return 'scan' + ''.join(step.code() for step in steps)


"""Scans and pairs"""


def load_scan(filename: str, dls_loader: bool = False) -> SpectraContainer:
    """Load a single XAS scan (files are loaded one at a time so none are filtered out)"""
    return xas.load_xas_scans(filename, dls_loader=dls_loader)[0]


def condition(scan: SpectraContainer) -> str:
    """Measurement condition shared by a pair, e.g. 'Fe L3,2 T=10K B=+5T'"""
    m = scan.metadata
    return f"{m.element} {m.edge} T={m.temp:.3g}K B={m.mag_field:+.3g}T"


def _group(scans, key) -> list[list[SpectraContainer]]:
    groups: dict = {}
    for scan in scans:
        groups.setdefault(key(scan), []).append(scan)
    return list(groups.values())


def find_pairs(scans: list[SpectraContainer], by: str = 'polarisation') -> list[tuple[SpectraContainer, SpectraContainer]]:
    """
    Pair scans with opposite polarisation (at the same field and temperature)
    or opposite field (at the same polarisation and temperature), in scan order.
    The first scan of each pair is the first polarisation or the positive field.
    """
    pairs = []
    if by == 'field':
        for group in _group(scans, lambda s: (s.metadata.element, round(s.metadata.temp), s.metadata.pol)):
            positive = [s for s in group if s.metadata.mag_field > 0]
            negative = [s for s in group if s.metadata.mag_field < 0]
            pairs += list(zip(positive, negative))
    else:
        key = lambda s: (s.metadata.element, round(s.metadata.temp), round(s.metadata.mag_field, 1))
        for group in _group(scans, key):
            pairs += xas.polarised_pairs(*group)
    return sorted(pairs, key=lambda p: min(p[0].metadata.scan_no, p[1].metadata.scan_no))


@dataclass(eq=False)
class Pair:
    scan1: SpectraContainer
    scan2: SpectraContainer
    include: bool = True

    def numbers(self) -> tuple[int, int]:
        return self.scan1.metadata.scan_no, self.scan2.metadata.scan_no

    def files(self) -> tuple[str, str]:
        return self.scan1.metadata.filename, self.scan2.metadata.filename

    def is_field_pair(self) -> bool:
        return self.scan1.metadata.pol == self.scan2.metadata.pol

    def condition(self) -> str:
        m = self.scan1.metadata
        if self.is_field_pair():
            return f"{m.element} {m.edge} T={m.temp:.3g}K '{m.pol}' B=±{abs(m.mag_field):.3g}T"
        return condition(self.scan1)

    def label(self) -> str:
        m1, m2 = self.scan1.metadata, self.scan2.metadata
        if self.is_field_pair():
            return f"{m1.scan_no} B{m1.mag_field:+.3g} − {m2.scan_no} B{m2.mag_field:+.3g}"
        return f"{m1.scan_no} {m1.pol} − {m2.scan_no} {m2.pol}"

    def warnings(self) -> list[str]:
        """Reasons the two scans may not be a good pair"""
        m1, m2 = self.scan1.metadata, self.scan2.metadata
        out = []
        if m1.element != m2.element or m1.edge != m2.edge:
            out.append(f"different edges: {m1.element} {m1.edge} / {m2.element} {m2.edge}")
        if abs(m1.temp - m2.temp) > 1:
            out.append(f"different temperatures: {m1.temp:.3g} / {m2.temp:.3g} K")
        if m1.pol == m2.pol and abs(m1.mag_field + m2.mag_field) > 0.1:
            out.append("same polarisation without opposite fields")
        if m1.pol != m2.pol and abs(m1.mag_field - m2.mag_field) > 0.1:
            out.append(f"different fields: {m1.mag_field:+.3g} / {m2.mag_field:+.3g} T")
        if abs(m1.mag_field) < 0.01 and m1.pol == m2.pol:
            out.append("zero field")
        e1, e2 = m1.energy, m2.energy
        if abs(np.min(e1) - np.min(e2)) > 1 or abs(np.max(e1) - np.max(e2)) > 1:
            out.append("different energy ranges")
        return out


"""Sum rules"""


def n_holes(element: str, oxidation: int = 0) -> float | None:
    """Number of d-holes of an ion from mmg_toolbox, or None if unknown (e.g. rare earths)"""
    try:
        return float(Element(element).d_holes(oxidation))
    except (ValueError, KeyError):
        return None


@dataclass
class Result:
    """Averaged spectra, dichroism and sum rules from a set of included pairs"""
    pairs: list[tuple[str, str]]
    steps: list[Step]
    mode: str
    pol1: SpectraContainer
    pol2: SpectraContainer
    diff: SpectraContainerSubtraction
    n_holes: float | None = None
    split_energy: float | None = None
    orbital: float = np.nan
    spin: float = np.nan
    dls_loader: bool = False

    @classmethod
    def calculate(cls, pairs: list[Pair], processed: dict[int, SpectraContainer], steps: list[Step],
                  mode: str, dls_loader: bool = False) -> Result:
        """Average the processed first and second scans of the included pairs and subtract them"""
        included = [p for p in pairs if p.include]
        if not included:
            raise ValueError('No pairs are included')
        pol1 = xas.average_scans(*(processed[id(p.scan1)] for p in included))
        pol2 = xas.average_scans(*(processed[id(p.scan2)] for p in included))
        return cls([p.files() for p in included], [s.copy() for s in steps], mode, pol1, pol2, pol1 - pol2,
                   dls_loader=dls_loader)

    @property
    def spectra(self):
        return self.diff.spectra[self.mode]

    @property
    def metadata(self):
        return self.diff.metadata

    def default_split_energy(self) -> float:
        try:
            return float(self.diff.get_edges().split_energy())
        except ValueError:
            return float(np.mean(self.spectra.energy))

    def sum_rules(self, holes: float, split_energy: float) -> tuple[float, float]:
        """Calculate the orbital and spin moments using mmg_toolbox, storing the parameters"""
        self.n_holes, self.split_energy = holes, split_energy
        self.diff.set_sum_rule_parameters(holes, split_energy)
        self.orbital, self.spin = self.spectra.calculate_sum_rules(holes, split_energy=split_energy)
        return self.orbital, self.spin

    def signal_ratio(self) -> float:
        return self.diff.calculate_signal_ratio()[self.mode]

    def peak_energy(self) -> float:
        return float(self.spectra.energy[np.argmax(abs(self.spectra.signal))])

    def signal_at(self, energy: float) -> float:
        return self.spectra.signal_at_energy(energy)

    def label(self) -> str:
        return self.diff.label()

    def report(self) -> str:
        m = self.metadata
        lines = [
            f"{self.label()}",
            f"pairs: {len(self.pairs)}, mode: {self.mode}",
            f"process: {chain_code(self.steps)}",
            f"max signal: {self.signal_ratio():.2%} of XAS",
            f"element: {m.element} {m.edge}, n_holes = {self.n_holes}",
            f"L3/L2 split energy: {self.split_energy} eV",
        ]
        lines += [f"L = {self.orbital:.3f} μB", f"S = {self.spin:.3f} μB",
                  f"L/S = {self.orbital / self.spin:.3f}" if self.spin else "L/S = -"]
        return '\n'.join(lines)

    def file_name(self, extension: str = '.nxs') -> str:
        m = self.metadata
        scan_nos = sorted(self.diff.get_raw_metadata('scan_no').values())
        static = f"{m.pol}" if 'field' in self.diff.name else f"B{m.mag_field:+.3g}T"
        name = f"{scan_nos[0]}-{scan_nos[-1]}_{self.diff.name}_{m.element}_T{m.temp:.3g}K_{static}"
        return name.replace(' ', '_') + extension

    def write_nexus(self, filename: str):
        """Write the averages, dichroism and sum rule parameters to a NeXus file"""
        self.diff.set_sum_rule_parameters(self.n_holes, self.split_energy)
        self.diff.write_nexus(filename)


SERIES_AXES = {
    'Field (T)': lambda r: r.metadata.mag_field,
    'Temperature (K)': lambda r: r.metadata.temp,
}


def series_table(results: list[Result], energy: float | None = None) -> tuple[list[str], list[list]]:
    """Header and rows of the sum rule values of each result"""
    header = ['label', 'field_T', 'temperature_K', 'n_holes', 'split_eV', 'L', 'S', 'L/S', 'signal_ratio']
    rows = []
    for r in results:
        ratio = r.orbital / r.spin if r.spin else np.nan
        rows.append([r.label(), r.metadata.mag_field, r.metadata.temp, r.n_holes, r.split_energy,
                     r.orbital, r.spin, ratio, r.signal_ratio()])
    if energy is not None:
        header.append(f'signal_at_{energy:g}eV')
        for row, r in zip(rows, results):
            row.append(r.signal_at(energy))
    return header, rows


"""Code generation"""


def _sections(results: list[Result], output_dir: str = '') -> list[tuple[str, str]]:
    """(markdown, code) sections that repeat the analysis of each result"""
    sections = [(
        "# XMCD analysis\nGenerated by the MMG Data Viewer XMCD Visualiser on "
        f"{datetime.datetime.now():%Y-%m-%d %H:%M}",
        "import os\nimport numpy as np\nimport matplotlib.pyplot as plt\nfrom mmg_toolbox import xas\n\n"
        f"output_dir = {output_dir!r}\nresults = []"
    )]
    for n, r in enumerate(results, start=1):
        files1 = ''.join(f"\n    {f1!r}," for f1, f2 in r.pairs)
        files2 = ''.join(f"\n    {f2!r}," for f1, f2 in r.pairs)
        code = (
            f"files1 = [{files1}\n]\nfiles2 = [{files2}\n]\n"
            f"mode = {r.mode!r}\n\n"
            "def process(scan):\n"
            f"    return {chain_code(r.steps)}\n\n"
            f"scans1 = [process(scan) for scan in xas.load_xas_scans(*files1, dls_loader={r.dls_loader})]\n"
            f"scans2 = [process(scan) for scan in xas.load_xas_scans(*files2, dls_loader={r.dls_loader})]\n"
            "pol1 = xas.average_scans(*scans1)\npol2 = xas.average_scans(*scans2)\n"
            "diff = pol1 - pol2\n\n"
            f"n_holes, split_energy = {r.n_holes!r}, {r.split_energy!r}\n"
            "orbital, spin = diff.spectra[mode].calculate_sum_rules(n_holes, split_energy=split_energy)\n"
            "print(f\"{diff.label()}\\nL = {orbital:.3f} μB, S = {spin:.3f} μB\")\n"
            "results.append((diff, orbital, spin))\n\n"
            "fig, axes = plt.subplots(1, 3, figsize=(15, 4))\n"
            "for scans, ax in zip((scans1, scans2), axes):\n"
            "    for scan in scans:\n"
            "        scan.spectra[mode].plot(ax, label=scan.name, lw=0.8)\n"
            "axes[0].set_title(pol1.name)\naxes[1].set_title(pol2.name)\n"
            "pol1.spectra[mode].plot(axes[2], label=diff.spectra1.name)\n"
            "pol2.spectra[mode].plot(axes[2], label=diff.spectra2.name)\n"
            "for ax in axes:\n"
            "    diff.add_edge_lines(ax)\n    ax.set_xlabel('E [eV]')\n    ax.legend()\n"
            "fig, ax = plt.subplots(figsize=(8, 4))\n"
            "diff.spectra[mode].plot_sum_rules(ax, split_energy=split_energy, label=diff.label())\n"
            "ax.set_xlabel('E [eV]')\nax.legend()\n\n"
            "if output_dir:\n"
            "    os.makedirs(output_dir, exist_ok=True)\n"
            "    diff.set_sum_rule_parameters(n_holes, split_energy)\n"
            f"    diff.write_nexus(os.path.join(output_dir, {r.file_name()!r}))"
        )
        sections.append((f"## {n}. {r.label()}\n{len(r.pairs)} pairs, processed with `{chain_code(r.steps)}`", code))
    if len(results) > 1:
        sections.append((
            "## Series\nSum rule values against field and temperature",
            "fig, axes = plt.subplots(1, 2, figsize=(12, 4))\n"
            "for ax, name, key in zip(axes, ('Field (T)', 'Temperature (K)'), ('mag_field', 'temp')):\n"
            "    x = [getattr(diff.metadata, key) for diff, orb, spin in results]\n"
            "    ax.plot(x, [orb for diff, orb, spin in results], 'o-', label='L')\n"
            "    ax.plot(x, [spin for diff, orb, spin in results], 's-', label='S')\n"
            "    ax.set_xlabel(name)\n    ax.legend()"
        ))
    sections.append(('', 'plt.show()'))
    return sections


def to_script(results: list[Result], output_dir: str = '') -> str:
    """Python script that repeats the analysis"""
    parts = []
    for markdown, code in _sections(results, output_dir):
        comment = '\n'.join(f"# {line.lstrip('# ')}" for line in markdown.splitlines() if line)
        parts.append(f"{comment}\n{code}" if comment else code)
    return '\n\n\n'.join(parts) + '\n'


def to_notebook(results: list[Result], output_dir: str = '') -> str:
    """Jupyter notebook (JSON) that repeats the analysis"""
    def cell(kind: str, text: str) -> dict:
        lines = text.splitlines(keepends=True)
        extra = {'execution_count': None, 'outputs': []} if kind == 'code' else {}
        return {'cell_type': kind, 'metadata': {}, 'source': lines, **extra}
    cells = []
    for markdown, code in _sections(results, output_dir):
        if markdown:
            cells.append(cell('markdown', markdown))
        cells.append(cell('code', code.replace('plt.show()', '')) if code != 'plt.show()' else None)
    notebook = {
        'cells': [c for c in cells if c],
        'metadata': {'kernelspec': {'display_name': 'Python 3', 'language': 'python', 'name': 'python3'},
                     'language_info': {'name': 'python'}},
        'nbformat': 4, 'nbformat_minor': 5,
    }
    return json.dumps(notebook, indent=1, ensure_ascii=False)
