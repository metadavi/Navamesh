# main.py  (project root)
#
# Layout:
#   Navamesh MQTT/
#   ├── main.py              ← this file
#   └── src/
#       └── navamesh/
#           ├── config.py
#           ├── bridge.py
#           ├── mqtt_client.py
#           ├── topics.py
#           └── processors/
#               ├── soil_text.py
#               ├── link.py
#               ├── position.py
#               └── telemetry.py
#
# Run from anywhere:
#   python main.py
#   python "C:\...\Navamesh MQTT\main.py"

import sys
import time
from pathlib import Path

# ── Make sure src/ is on the path so `navamesh` package is importable ────────
# This works whether you run from the project root, from src/, or with a full
# path — Path(__file__).parent always resolves to the folder containing main.py
_SRC = Path(__file__).parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from dotenv import load_dotenv

from navamesh.config import load_config
from navamesh.mqtt_client import MqttPublisher
from navamesh.bridge import MeshBridge
from navamesh import topics

# FORMAT A (legacy):  MOISTURE_RAW=585
from navamesh.processors.soil_text import parse_moisture_raw, make_soil_messages
# FORMAT B (RAK4631): "Soil: 47% | Bat: 82% | Up: 1h 23m"
from navamesh.processors.soil_text import (
    is_status_message,
    parse_status_message,
    make_status_mqtt_payloads,
)
from navamesh.processors.link import extract_link
from navamesh.processors.position import extract_position
from navamesh.processors.telemetry import extract_battery


def should_bridge(packet: dict, private_channel_index: int) -> bool:
    """
    Pass packets on the private channel through.
    Also pass packets with no channel field (node-info / position broadcasts).
    """
    ch = packet.get("channel", None)
    if ch is None:
        return True
    return ch == private_channel_index


def is_private_channel(packet: dict, private_channel_index: int) -> bool:
    return packet.get("channel") == private_channel_index


def main():
    load_dotenv()
    cfg = load_config()

    print(f"Connecting gateway radio on {cfg.serial_port} "
          f"(private channel index={cfg.private_channel_index})")
    mqtt_pub = MqttPublisher(cfg.mqtt_host, cfg.mqtt_port)

    def on_receive(packet: dict):
        try:
            # ── channel gate ──────────────────────────────────────────────
            if not should_bridge(packet, cfg.private_channel_index):
                return

            # ── raw debug stream ──────────────────────────────────────────
            mqtt_pub.publish(topics.raw_rx(cfg.root_raw), packet)

            # ── link quality (RSSI / SNR / hops) ─────────────────────────
            link = extract_link(packet)
            if link:
                mqtt_pub.publish(topics.node_link(cfg.root_nodes, link["fromId"]), link)

            # ── GIS position ──────────────────────────────────────────────
            pos = extract_position(packet)
            if pos:
                mqtt_pub.publish(topics.node_position(cfg.root_nodes, pos["fromId"]), pos)

            # ── TELEMETRY_APP battery (device metrics packet) ─────────────
            battery = extract_battery(packet)
            if battery:
                mqtt_pub.publish(topics.node_battery(cfg.root_nodes, battery["fromId"]), battery)

            # ── TEXT_MESSAGE_APP ──────────────────────────────────────────
            decoded = packet.get("decoded", {}) or {}
            if decoded.get("portnum") != "TEXT_MESSAGE_APP":
                return

            # Text messages are private-channel only
            if not is_private_channel(packet, cfg.private_channel_index):
                return

            mqtt_pub.publish(topics.raw_text(cfg.root_raw), packet)

            text    = decoded.get("text") or ""
            from_id = packet.get("fromId") or "unknown"

            # ── FORMAT B: "Soil: 47% | Bat: 82% | Up: 1h 23m" ───────────
            if is_status_message(text):
                parsed = parse_status_message(text)
                if parsed is None:
                    return

                soil_pl, bat_pl = make_status_mqtt_payloads(from_id, parsed)
                mqtt_pub.publish(topics.soil_percent(cfg.root_sensors, from_id), soil_pl)
                if bat_pl is not None:
                    mqtt_pub.publish(topics.node_battery(cfg.root_nodes, from_id), bat_pl)

                bat_str = "USB" if parsed["battery_usb"] else f"{parsed['battery_level']}%"
                print(f"[SENSOR] {from_id} | soil={parsed['soil_percent']}% | "
                      f"bat={bat_str} | up={parsed['uptime_seconds']}s")
                return

            # ── FORMAT A: MOISTURE_RAW=585 (legacy ADC value) ────────────
            raw_val = parse_moisture_raw(text)
            if raw_val is None:
                return  # unknown text format — ignore silently

            raw_msg, pct_msg = make_soil_messages(from_id, raw_val, cfg.adc_dry, cfg.adc_wet)
            mqtt_pub.publish(topics.soil_raw(cfg.root_sensors, from_id), raw_msg)
            mqtt_pub.publish(topics.soil_percent(cfg.root_sensors, from_id), pct_msg)

            print(f"[SENSOR] {from_id} | soil raw={raw_val} → {pct_msg['value']:.2f}%")

        except Exception as e:
            print("[ERR] on_receive:", e)

    bridge = MeshBridge(cfg.serial_port, on_receive=on_receive)
    bridge.start()

    print("Navamesh bridge running. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()
        mqtt_pub.close()
        print("Stopped.")


if __name__ == "__main__":
    main()