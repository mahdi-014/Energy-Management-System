@echo off
echo ========================================================
echo  DCEMS: Enabling Mosquitto LAN Access and Firewall Rule
echo ========================================================
echo.

:: Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] This script MUST be run as Administrator!
    echo Please right-click enable_lan_mosquitto.bat and select "Run as administrator".
    pause
    exit /b 1
)

echo Configuring C:\Program Files\Mosquitto\mosquitto.conf ...
echo.>> "C:\Program Files\Mosquitto\mosquitto.conf"
echo listener 1883 0.0.0.0>> "C:\Program Files\Mosquitto\mosquitto.conf"
echo allow_anonymous true>> "C:\Program Files\Mosquitto\mosquitto.conf"

echo Adding Windows Firewall Rule for Port 1883 ...
netsh advfirewall firewall add rule name="Mosquitto_1883" dir=in action=allow protocol=TCP localport=1883

echo Restarting Mosquitto Service ...
net stop mosquitto
net start mosquitto

echo.
echo ========================================================
echo [SUCCESS] Mosquitto is now listening on LAN (0.0.0.0:1883)!
echo NodeMCU can now connect freely to your PC!
echo ========================================================
pause
