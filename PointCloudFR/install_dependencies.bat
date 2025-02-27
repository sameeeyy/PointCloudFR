@echo off
call "C:\Program Files\QGIS 3.34.6\bin\o4w_env.bat"
call "py3-env.bat"
"C:\Program Files\QGIS 3.34.6\bin\qgis-ltr-bin.exe" -m pip install --upgrade pip
"C:\Program Files\QGIS 3.34.6\bin\qgis-ltr-bin.exe" -m pip install -r "C:\Users\k2sam\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\PointCloudFR\requirements.txt"
@echo on
