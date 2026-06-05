"""Generate the Power Query workbook template from a real Excel file."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'pq_reference.xlsx'
TARGET = ROOT / 'app' / 'static' / 'templates' / 'power_query_workbook_template.xlsx'
PS1 = Path(__file__).resolve().parent / '_make_pq_reference.ps1'


def main() -> None:
    if not SOURCE.is_file():
        subprocess.run(
            ['powershell', '-ExecutionPolicy', 'Bypass', '-File', str(PS1)],
            check=True,
        )
    if not SOURCE.is_file():
        raise SystemExit(f'Reference workbook not found at {SOURCE}')

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SOURCE, TARGET)
    print(f'Wrote template to {TARGET} ({TARGET.stat().st_size} bytes)')


if __name__ == '__main__':
    main()
