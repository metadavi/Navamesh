"""
soil_text.py — Parse soil/battery/uptime from Meshtastic text messages.

Two supported message formats:

  FORMAT A (legacy ADC):
      "MOISTURE_RAW=585"
      Yields a raw ADC integer; caller must convert to % using adc_to_percent().

  FORMAT B (device status string from RAK4631 firmware):
      "Soil: 47% | Bat: 82% | Up: 1h 23m"
      "Soil: 0%  | Bat: USB | Up: 0h 3m"
      Yields soil %, battery % (USB → 100), and uptime in seconds directly.
      No ADC calibration needed — the device already computed the percentage.
"""

import re
import time
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# FORMAT A  — legacy: raw ADC integer
# ---------------------------------------------------------------------------

# Matches:  MOISTURE_RAW=585  or  moisture_raw = 585
MOISTURE_RAW_RE = re.compile(r"MOISTURE_RAW\s*=\s*(\d+)", re.IGNORECASE)


def parse_moisture_raw(text: str) -> Optional[int]:
    """Return the raw ADC integer from a FORMAT A message, or None."""
    m = MOISTURE_RAW_RE.search(text or "")
    if not m:
        return None
    return int(m.group(1))


def adc_to_percent(adc: int, adc_dry: int, adc_wet: int) -> float:
    """
    Convert a raw ADC reading to a 0-100 moisture percentage.

    Supports both polarities:
      - Capacitive sensors where dry > wet (higher ADC = drier soil)
      - Resistive sensors where wet > dry (lower ADC = drier soil)
    Result is clamped to [0.0, 100.0].
    """
    if adc_dry == adc_wet:
        return 0.0
    if adc_dry > adc_wet:
        pct = (adc_dry - adc) / (adc_dry - adc_wet) * 100.0
    else:
        pct = (adc - adc_dry) / (adc_wet - adc_dry) * 100.0
    return max(0.0, min(100.0, pct))


def make_soil_messages(
    from_id: str, raw_val: int, adc_dry: int, adc_wet: int
) -> Tuple[dict, dict]:
    """
    Build the two MQTT payloads for FORMAT A messages.

    Returns:
        (raw_msg, percent_msg)  — both include fromId and ts.
    """
    ts = int(time.time())
    pct = adc_to_percent(raw_val, adc_dry, adc_wet)
    raw_msg = {"value": raw_val, "fromId": from_id, "ts": ts}
    pct_msg = {"value": round(pct, 2), "fromId": from_id, "ts": ts}
    return raw_msg, pct_msg


# ---------------------------------------------------------------------------
# FORMAT B  — device status string (RAK4631 firmware)
# ---------------------------------------------------------------------------

# Matches the numeric part of "Soil: 47%" or "Soil: 0%"
_SOIL_RE = re.compile(r"Soil\s*:\s*(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)

# Matches "Bat: 82%" or "Bat: USB"  (USB → treated as 100 %)
_BAT_RE = re.compile(r"Bat\s*:\s*(USB|\d+(?:\.\d+)?)\s*%?", re.IGNORECASE)

# Matches "Up: 1h 23m"  (hours and/or minutes are each optional)
#   "Up: 0h 3m"  →  0 hours, 3 minutes
#   "Up: 2h"     →  2 hours, 0 minutes
#   "Up: 45m"    →  0 hours, 45 minutes
_UP_RE = re.compile(
    r"Up\s*:\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?",
    re.IGNORECASE,
)


def is_status_message(text: str) -> bool:
    """
    Quick check: does this text look like a FORMAT B status string?
    Used by main.py to route the packet to the right parser.
    """
    return bool(_SOIL_RE.search(text or ""))


def parse_status_message(text: str) -> Optional[dict]:
    """
    Parse a FORMAT B status string into a structured dict.

    Returns a dict with keys:
        soil_percent   (float, 0-100)
        battery_level  (float, 0-100;  USB charging → 100.0)
        battery_usb    (bool,  True when the device reported "USB")
        uptime_seconds (int)

    Returns None if the minimum required field (soil %) cannot be parsed.

    Example input:
        "Soil: 47% | Bat: 82% | Up: 1h 23m"
    """
    text = text or ""

    # --- Soil % -----------------------------------------------------------
    soil_match = _SOIL_RE.search(text)
    if not soil_match:
        return None  # not a status message we can use
    soil_pct = float(soil_match.group(1))

    # --- Battery ----------------------------------------------------------
    bat_match = _BAT_RE.search(text)
    battery_usb = False
    battery_level: Optional[float] = None
    if bat_match:
        raw_bat = bat_match.group(1)
        if raw_bat.upper() == "USB":
            battery_usb = True
            battery_level = 100.0   # USB power = treat as full
        else:
            battery_level = float(raw_bat)

    # --- Uptime -----------------------------------------------------------
    up_match = _UP_RE.search(text)
    uptime_seconds = 0
    if up_match:
        hours = int(up_match.group(1) or 0)
        minutes = int(up_match.group(2) or 0)
        uptime_seconds = hours * 3600 + minutes * 60

    return {
        "soil_percent": round(soil_pct, 2),
        "battery_level": battery_level,
        "battery_usb": battery_usb,
        "uptime_seconds": uptime_seconds,
    }


def make_status_mqtt_payloads(
    from_id: str, parsed: dict
) -> Tuple[dict, Optional[dict]]:
    """
    Convert the output of parse_status_message() into MQTT-ready payloads.

    Returns:
        (soil_payload, battery_payload)
        battery_payload is None if no battery data was found in the message.

    soil_payload    → publish to farm/sensors/soil/<fromId>/percent
    battery_payload → publish to farm/nodes/<fromId>/battery
    """
    ts = int(time.time())

    soil_payload = {
        "value": parsed["soil_percent"],
        "fromId": from_id,
        "ts": ts,
    }

    battery_payload = None
    if parsed.get("battery_level") is not None:
        battery_payload = {
            "fromId": from_id,
            "ts": ts,
            "batteryLevel": parsed["battery_level"],
            "batteryUsb": parsed["battery_usb"],
            "uptimeSeconds": parsed["uptime_seconds"],
            # voltage not present in text messages — left absent
        }

    return soil_payload, battery_payload