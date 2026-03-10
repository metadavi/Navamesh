# Navamesh — Private Meshtastic → MQTT Gateway (Offline-First)

Navamesh is an **offline-first telemetry pipeline** that bridges a **private Meshtastic LoRa mesh channel** into a **local MQTT broker (Mosquitto)** running on a MiniPC (house/gateway node). It publishes both **raw mesh packets** and **clean, structured topics** for soil moisture, link quality (RSSI/SNR), and GIS position.

This repo contains the Python bridge that:
- Reads packets from a **USB-connected Meshtastic gateway radio** (RAK4631 / Heltec / etc.)
- Filters traffic to a **private channel** (e.g., `navamesh`, channel index `1`)
- Publishes into Mosquitto on `127.0.0.1:1883`
- Outputs clean MQTT topics for downstream storage and dashboards

---

## Architecture

**Field node(s)** (sensor radios)  
→ **Meshtastic LoRa mesh (private channel + PSK)**  
→ **Gateway radio (USB serial to MiniPC)**  
→ **Python bridge (`mesh_to_mqtt.py`)**  
→ **Mosquitto (MQTT broker, local)**  
→ **Subscribers** (CLI, DB writer, dashboard, alerts)

---

## What You Get (MQTT Topic Schema)

### Clean sensor topics
- `farm/sensors/soil/<fromId>/raw`  
  Example payload:
  ```json
  {"value":324,"fromId":"!86b0c98d","ts":1772843516}

- `farm/sensors/soil/<fromId>/percent`
  Example payload:
   ```json
   {"value":100.0,"fromId":"!86b0c98d","ts":1772843516}

### Link Quality (strength/Mesh Path)
- `farm/nodes/<fromId>/link`
  Example Payload:
  `{
  "ts":1772843634,
  "fromId":"!86b0c98d",
  "rxRssi":-36,
  "rxSnr":5.75,
  "hopLimit":3,
  "hopStart":3,
  "relayNode":141,
  "transportMechanism":"TRANSPORT_LORA"
}`   

### GIS pOSTION (FIXED POSITION OR position_app packets)
- `farm/nodes/<fromId>/link`
  Example Payload:
  `{"ts":1772844000,"fromId":"!86b0c98d","lat":26.3979008,"lon":-80.084992,"alt":4}`

### Raw/Debug topic (filtered by the private channel)
-`farm/raw/rx (all packets that pass filtering, JSON)`
-`farm/raw/text (text packets that pass filtering, JSON)`


## Requirements

### Software
- Mosquitto MQTT broker installed and running on the MiniPC
- python 3.x
  
### Dependencies:
-meshtastic
-paho-mqtt
-pypubsub

## Hardware
At least two meshtastic nodes:
- Gateway Node connected via USB to the MiniPC
- Sensor/Field nodes on the same private mesh channel


## Private Channel Set Up (Meshtastic)

This Pipeline assumes sensor traffic is sent on a private channel, for example: 

-Channel name: navamesh:
-Channel Index: 1
-Shared PSK: must match across nodes

## Mosquitto (broker) Setup
Check if mosquitto is listening on 1883:
`netstat -an | findstr 1883`

Local Test:
`mosquitto_sub -h 127.0.0.1 -p 1883 -t "farm/test" -v
mosquitto_pub -h 127.0.0.1 -p 1883 -t "farm/test" -m "hello"`

## Run the bridge

Moisture Calibration (ADC_DRY / ADC_WET)

The soil sensor reports a raw ADC value (e.g. `MOISTURE_RAW=324`). To convert raw readings into a moisture percentage, the bridge uses two calibration points:

- `ADC_DRY`: average raw reading when the sensor is completely dry (air / dry soil)
- `ADC_WET`: average raw reading when the sensor is fully wet (water / saturated soil)

### 1) Configure the script
open the src/mesh_to_mqtt.py and set: 
-SERIAL_PORT to your gatways COM port
-PRIVATE_CHANNEL_INDEX = 1

Moisture Calibration (ADC_DRY / ADC_WET)
The soil sensor reports a raw ADC value (e.g. `MOISTURE_RAW=324`). To convert raw readings into a moisture percentage, the bridge uses two calibration points:

- `ADC_DRY`: average raw reading when the sensor is completely dry (air / dry soil)
- `ADC_WET`: average raw reading when the sensor is fully wet (water / saturated soil)

  
### 2) Start the bridge
-`python .\src\mesh_to_mqtt.py`
or
-`.\scripts\run_bridge.ps1`

### Subscribe Commands

# Clean Sensor Data:
-`mosquitto_sub -h 127.0.0.1 -p 1883 -t "farm/sensors/#" -v`

# Link Quality (RSSI/SNR)
-`mosquitto_sub -h 127.0.0.1 -p 1883 -t "farm/nodes/+/link" -v`

# Position/GIS
-`mosquitto_sub -h 127.0.0.1 -p 1883 -t "farm/nodes/+/position" -v`

# RAW debug streams
-`mosquitto_sub -h 127.0.0.1 -p 1883 -t "farm/raw/#" -v`

# EVERYTHING
-`mosquitto_sub -h 127.0.0.1 -p 1883 -t "#" -v`

## Debugging/Troubleshooting

# Verify that mesh packets are being heard (no mqtt)
-`meshtastic --port COM3 --listen`

# If no messages are being delivered (verify mosquitto is running/listening) 
1) `netstat -an | findstr 1883`
2) Verify that local publish/subscribe work (farm/test example above)
3) Verify that the bridge prints [MQTT] pubslished ... lines


## Notes on positions (no GPS module)

If your node has no GPS module:
- Use fixed position 
- The device can broadcast POSITION_APP packets (LOC_MANUAL)
  




