#ifndef SECRETS_EXAMPLE_H
#define SECRETS_EXAMPLE_H

// Copy this file to firmware/include/secrets.h and enter physical Wi-Fi & MQTT credentials.
// NEVER commit secrets.h to version control.

#define WIFI_SSID       "Your_Office_WiFi_SSID"
#define WIFI_PASSWORD   "Your_Office_WiFi_Password"

#define MQTT_BROKER_HOST "192.168.1.100"  // Static IP or local hostname of the Mosquitto broker
#define MQTT_BROKER_PORT 1883
#define MQTT_USERNAME    "dcems_esp8266"
#define MQTT_PASSWORD    "dcems_device_password_here"

#define ROOM_IDENTIFIER  "room1"

#endif // SECRETS_EXAMPLE_H

