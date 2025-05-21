@echo off
TITLE Lemma Cascade Builder
CD /D "%~dp0"
ECHO Running cascade builder at %DATE% %TIME%...
python revoke_and_build.py --config config.json >> cascade_build_log.txt 2>&1
ECHO Completed at %DATE% %TIME%
TIMEOUT /T 5 