@echo off
cd /d "%~dp0"
python build_cascade.py --config config.json >> cascade_build.log 2>&1 