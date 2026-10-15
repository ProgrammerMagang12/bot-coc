@echo off
REM ============================================================
REM  Build GARUDA.exe (Windows) — jalankan dari folder coc-lab:
REM      build_exe.bat
REM  Hasil: dist\GARUDA\GARUDA.exe (+ file data di sampingnya)
REM ============================================================
cd /d "%~dp0"

echo [1/3] Membangun EXE dengan PyInstaller...
py -m PyInstaller --noconfirm --clean --windowed --name GARUDA ^
  --collect-all rapidocr_onnxruntime --collect-all onnxruntime ^
  gui.py
if errorlevel 1 (
  echo GAGAL membangun EXE.
  pause
  exit /b 1
)

echo.
echo [2/3] Menyalin file data (config, assets, strategi)...
if exist config.json copy /Y config.json dist\GARUDA\ >nul
copy /Y config.example.json dist\GARUDA\ >nul
copy /Y AttackStrategies.json dist\GARUDA\ >nul
xcopy /E /I /Y assets dist\GARUDA\assets >nul

echo.
echo [3/3] Selesai!
echo.
echo  Jalankan:  dist\GARUDA\GARUDA.exe
echo  Catatan: file data (assets/ config.json AttackStrategies.json) tetap
echo  di samping exe — kalibrasi template tetap bisa tanpa rebuild.
pause
