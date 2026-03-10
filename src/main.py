# src/main.py
import time
from dotenv import load_dotenv

from navamesh.config import load_config
from navamesh.mqtt_client import MqttPublisher
from navamesh.bridge import MeshBridge
from navamesh import topics
from navamesh.processors.soil_text import parse_moisture_raw, make_soil_messages
from navamesh.processors.link import extract_link
from navamesh.processors.position import extract_position
from navamesh.processors.telemetry import extract_battery

def should_bridge(packet: dict, private_channel_index: int) -> bool:
    """
    Private-channel-only when 'channel' exists; allow packets with no channel field
    (common for node info / position packets).
    """
    ch = packet.get("channel", None)
    if ch is None:
        return True
    return ch == private_channel_index


def is_private_channel(packet: dict, private_channel_index: int) -> bool:
    return packet.get("channel") == private_channel_index


def main():
    load_dotenv()  # loads .env if present
    cfg = load_config()

    print(f"Connecting gateway radio on {cfg.serial_port} (private channel index={cfg.private_channel_index})")
    mqtt_pub = MqttPublisher(cfg.mqtt_host, cfg.mqtt_port)

    def on_receive(packet: dict):
        try:
            # General bridge filter
            if not should_bridge(packet, cfg.private_channel_index):
                return

            # Always publish raw RX packet stream (debug)
            mqtt_pub.publish(topics.raw_rx(cfg.root_raw), packet)

            # Publish link metrics when present
            link = extract_link(packet)
            if link:
                from_id = link["fromId"]
                mqtt_pub.publish(topics.node_link(cfg.root_nodes, from_id), link)

            # Publish position/GIS when present
            pos = extract_position(packet)
            if pos:
                from_id = pos["fromId"]
                mqtt_pub.publish(topics.node_position(cfg.root_nodes, from_id), pos)
            
            battery = extract_battery(packet)
            if battery:
                from_id = battery["fromId"]
                mqtt_pub.publish(topics.node_battery(cfg.root_nodes, from_id), battery)

            # Handle text packets here (avoid subscribing to meshtastic.receive.text)
            decoded = packet.get("decoded", {}) or {}
            if decoded.get("portnum") != "TEXT_MESSAGE_APP":
                return

            # Keep text parsing private-only
            if not is_private_channel(packet, cfg.private_channel_index):
                return

            mqtt_pub.publish(topics.raw_text(cfg.root_raw), packet)

            text = decoded.get("text") or ""
            from_id = packet.get("fromId") or "unknown"

            raw_val = parse_moisture_raw(text)
            if raw_val is None:
                return

            raw_msg, pct_msg = make_soil_messages(from_id, raw_val, cfg.adc_dry, cfg.adc_wet)
            mqtt_pub.publish(topics.soil_raw(cfg.root_sensors, from_id), raw_msg)
            mqtt_pub.publish(topics.soil_percent(cfg.root_sensors, from_id), pct_msg)

            print(f"[SENSOR] soil moisture from {from_id}: raw={raw_val}, percent={pct_msg['value']:.2f}")

        except Exception as e:
            print("[ERR] on_receive:", e)

    # IMPORTANT: MeshBridge should subscribe ONLY to "meshtastic.receive"
    # (Update src/navamesh/bridge.py accordingly, removing receive.text subscription.)
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