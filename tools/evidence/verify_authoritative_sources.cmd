@echo off
setlocal EnableExtensions

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "REPO_ROOT=%%~fI"

set /A VERIFIED_COUNT=0
set /A FAILED_COUNT=0

where python >nul 2>nul
if errorlevel 1 (
    echo CONFIGURATION_FAILURE: Python is not available on PATH.
    exit /b 2
)

echo ============================================================
echo AMBA-GOV AUTHORITATIVE SOURCE VERIFIER
echo Repository: repository root resolved by verifier
echo Expected PDFs: 9
echo Checks: file presence, PDF magic header, SHA-256 identity
echo ============================================================
echo.

call :verify_pdf "kb\sources\ethiopia\ETH_ECA_QOS_794_2021.pdf" "3c23ba0cfeca1f0fbdf724da211164fb8bbbec75945f16d9740cb112342ea449"
call :verify_pdf "kb\sources\ethiopia\ETH_ESDP_VI_2021.pdf" "f77622ff64c29d03d1e090f5c401880e3b8cda6015f6379d2afb707a0a9c7678"
call :verify_pdf "kb\sources\ethiopia\ETH_NATIONAL_CYBERSECURITY_POLICY_2024.pdf" "624b0db098bff6cd075e92c2fd44e0a082b892a53bb4ea47952fb0850e12c62e"
call :verify_pdf "kb\sources\ethiopia\ETH_PDPA_1321_2024.pdf" "f4e1eb0c4a6948d34accc3a93dbe32010af851f6cfb7f4b17a66ba94e2df0bf6"
call :verify_pdf "kb\sources\ethiopia\ETH_STME_POLICY_FULL.pdf" "d5a6fb50ecd5b324d5d0eb1e1cb0eabd1744acd0423ff434127b76b4835e0260"
call :verify_pdf "kb\sources\international\ITU_AI_READINESS_REPORT.pdf" "71191768d46b60778c15f8d62b162aff73a319785cfc31ebf76bb944b0c68273"
call :verify_pdf "kb\sources\international\ITU_T_Y3172_2019.pdf" "e42f9a3be3f951d3e19b9007f876f0b389c81b4693f0d8576e18185a1acfe67b"
call :verify_pdf "kb\sources\international\UNESCO_AI_ETHICS_RECOMMENDATION.pdf" "3a93a6006c591bf7600abc55e8beab883b6450b71638fea98148e4b08f005bf7"
call :verify_pdf "kb\sources\international\UNICEF_AI_CHILDREN_V3_2025.pdf" "1d218b79b894402bda57d97527ef7ea015b0642003ba582d6259b050d0a548ea"

echo.
echo ============================================================
echo Verification summary
echo   Verified: %VERIFIED_COUNT%
echo   Failed:   %FAILED_COUNT%
echo ============================================================

if not "%FAILED_COUNT%"=="0" (
    echo AUTHORITATIVE SOURCE VERIFICATION FAILED
    exit /b 1
)

if not "%VERIFIED_COUNT%"=="9" (
    echo CONFIGURATION_FAILURE: Expected 9 verified PDFs but received %VERIFIED_COUNT%.
    exit /b 2
)

echo ALL NINE AUTHORITATIVE SOURCE PDF HASHES AND MAGIC HEADERS VERIFIED
exit /b 0

:verify_pdf
set "RELATIVE_PATH=%~1"
set "EXPECTED_SHA256=%~2"
set "ABSOLUTE_PATH=%REPO_ROOT%\%RELATIVE_PATH%"

if not exist "%ABSOLUTE_PATH%" (
    echo [MISSING] %RELATIVE_PATH%
    set /A FAILED_COUNT+=1
    exit /b 0
)

python -c "from pathlib import Path; import hashlib,sys; p=Path(sys.argv[1]); expected=sys.argv[2].lower(); data=p.read_bytes(); actual=hashlib.sha256(data).hexdigest(); magic=data[:5]; hash_ok=(actual==expected); magic_ok=(magic==bytes.fromhex('255044462d')); print('[VERIFIED] '+sys.argv[3] if hash_ok and magic_ok else '[FAILED] '+sys.argv[3]); print('  expected_sha256: '+expected); print('  actual_sha256:   '+actual); print('  pdf_magic:       '+('VERIFIED' if magic_ok else 'INVALID')); sys.exit(0 if hash_ok and magic_ok else 1)" "%ABSOLUTE_PATH%" "%EXPECTED_SHA256%" "%RELATIVE_PATH%"

if errorlevel 1 (
    set /A FAILED_COUNT+=1
) else (
    set /A VERIFIED_COUNT+=1
)

exit /b 0
