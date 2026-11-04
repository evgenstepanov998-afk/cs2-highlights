@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name CS2Highlights ^
  --add-data "site\index.html;site" ^
  --collect-all demoparser2 --collect-all polars --collect-all polars_runtime_32 ^
  --hidden-import pyarrow --hidden-import pyarrow.lib --collect-binaries pyarrow ^
  --hidden-import pycaw.pycaw --hidden-import comtypes.stream --hidden-import zstandard ^
  --distpath dist --workpath build cs2highlights.py
