@echo off
echo Installing required packages...
python -m pip install pyinstaller pystray pillow

echo Creating executable...
python -m PyInstaller --noconfirm --onefile --windowed --name "HotelBeacons" admin.py
python -m PyInstaller --noconfirm --onefile --windowed --name "HotelBeaconsStartup" setup_startup.py

echo Creating installer directory...
if not exist installer mkdir installer

echo Done! The executables are in the dist folder.
echo Now compiling the installer with Inno Setup...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss

pause 