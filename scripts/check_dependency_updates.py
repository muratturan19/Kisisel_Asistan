"""Utility to compare pinned requirements with the latest releases.

The script reads ``requirements.txt`` and uses ``pip index versions`` to
retrieve the newest available version for each package. The result is printed
as a table highlighting which pins are outdated. Use it proactively whenever
installations fail on a new Python version (for example 3.13) to verify that
all dependencies expose compatible wheels.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_FILE = ROOT / "requirements.txt"


@dataclass
class RequirementStatus:
    name: str
    current: str
    specifier: SpecifierSet
    latest: Optional[str]
    up_to_date: bool
    error: Optional[str] = None


_VERSION_RE = re.compile(r"^([^(]+)\(([^)]+)\)")


def _run_pip_index(package: str) -> str:
    """Return the stdout produced by ``pip index versions`` for ``package``."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "index", "versions", package],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def _extract_latest(stdout: str) -> Optional[str]:
    """Extract the newest version from ``pip index versions`` output."""
    for line in stdout.splitlines():
        match = _VERSION_RE.search(line.strip())
        if match:
            return match.group(2).strip()
    return None


def parse_requirement(line: str) -> RequirementStatus:
    requirement = Requirement(line)
    specifier = requirement.specifier
    current = next(iter(specifier)).version if specifier else ""

    try:
        stdout = _run_pip_index(requirement.name)
        latest = _extract_latest(stdout)
    except Exception as exc:  # pragma: no cover - defensive logging only
        return RequirementStatus(
            name=requirement.name,
            current=current,
            specifier=specifier,
            latest=None,
            up_to_date=False,
            error=str(exc),
        )

    up_to_date = bool(latest and latest in specifier)
    return RequirementStatus(
        name=requirement.name,
        current=current,
        specifier=specifier,
        latest=latest,
        up_to_date=up_to_date,
    )


def iter_requirements(lines: Iterable[str]) -> Iterable[RequirementStatus]:
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        yield parse_requirement(line)


def format_status(rows: List[RequirementStatus]) -> str:
    name_width = max(len(row.name) for row in rows) + 2
    current_width = max(len(row.current) for row in rows) + 2
    latest_width = max(len(row.latest or "-") for row in rows) + 2

    header = f"{'Package'.ljust(name_width)}{'Pinned'.ljust(current_width)}{'Latest'.ljust(latest_width)}Status"
    separator = "-" * len(header)

    lines = [header, separator]
    for row in rows:
        if row.error:
            status = f"ERROR: {row.error}"
        elif row.up_to_date:
            status = "up to date"
        else:
            status = "update available"
        lines.append(
            f"{row.name.ljust(name_width)}"
            f"{row.current.ljust(current_width)}"
            f"{(row.latest or '-').ljust(latest_width)}"
            f"{status}"
        )
    return "\n".join(lines)


def main() -> int:
    if not REQUIREMENTS_FILE.exists():
        print(f"requirements.txt bulunamadı: {REQUIREMENTS_FILE}")
        return 1

    rows = list(iter_requirements(REQUIREMENTS_FILE.read_text().splitlines()))
    print(format_status(rows))
    print("\nİpucu: Bir satır 'update available' olarak görünüyorsa, sabitlenen sürümü"
          " yeni sürüme güncelleyip tekrar bu betiği çalıştırabilirsiniz.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
