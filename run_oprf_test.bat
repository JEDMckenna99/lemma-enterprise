@echo off
REM Run the OPRF-Cascaded Bloom Filter test script
echo Running OPRF-Cascaded Bloom Filter test...
python test_oprf_revocation.py %*
echo Test completed.
pause 