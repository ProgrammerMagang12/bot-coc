@echo off
REM ============================================================
REM  Build GARUDA.exe (Windows) — jalankan dari folder coc-lab:
REM      build_exe.bat
REM  Profil akun & config.json milikmu di dist\GARUDA AMAN:
REM  otomatis di-backup sebelum build dan dipulihkan setelahnya.
REM ============================================================
cd /d "%~dp0"

REM --- tutup GARUDA.exe bila sedang jalan (file-nya terkunci saat build) ---
tasklist /FI "IMAGENAME eq GARUDA.exe" 2>nul | find /I "GARUDA.exe" >nul
if not errorlevel 1 (
  echo GARUDA.exe sedang berjalan - menutup dulu...
  taskkill /IM GARUDA.exe /F >nul
  timeout /t 2 /nobreak >nul
)

echo [1/4] Backup data user (profiles + config.json) dari dist\GARUDA...
if exist dist\GARUDA\profiles (
  if not exist dist\_userdata\profiles mkdir dist\_userdata\profiles
  xcopy /E /I /Y dist\GARUDA\profiles dist\_userdata\profiles >nul
)
if exist dist\GARUDA\config.json copy /Y dist\GARUDA\config.json dist\_userdata\config.json >nul

echo [2/4] Membangun EXE dengan PyInstaller...
py -m PyInstaller --noconfirm --clean --windowed --name GARUDA ^
  --collect-all rapidocr_onnxruntime --collect-all onnxruntime ^
  gui.py
if errorlevel 1 (
  echo GAGAL membangun EXE.
  pause
  exit /b 1
)

echo.
echo [3/4] Menyalin file data default...
copy /Y config.example.json dist\GARUDA\ >nul
copy /Y AttackStrategies.json dist\GARUDA\ >nul
xcopy /E /I /Y assets dist\GARUDA\assets >nul

echo.
echo [4/4] Memulihkan data user (profiles + config.json)...
if exist dist\_userdata\profiles xcopy /E /I /Y dist\_userdata\profiles dist\GARUDA\profiles >nul
if exist dist\_userdata\config.json copy /Y dist\_userdata\config.json dist\GARUDA\config.json >nul

echo.
echo Selesai!  Jalankan:  dist\GARUDA\GARUDA.exe
pause
