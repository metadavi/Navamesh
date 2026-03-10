import re
import time
from typing import Optional, Tuple

MOISTURE_RE = re.compile(r"MOISTURE_RAW\s*=\s*(\d+)", re.IGNORECASE)

def parse_moisture_raw(text: str) -> Optional[int]:
    m = MOISTURE_RE.search(text or "")
    if not m:
        return None
    return int(m.group(1))

def adc_to_percent(adc: int, adc_dry: int, adc_wet: int) -> float:
    if adc_dry == adc_wet:
        return 0.0

    if adc_dry > adc_wet:
        pct = (adc_dry - adc) / (adc_dry - adc_wet) * 100.0
    else:
        pct = (adc - adc_dry) / (adc_wet - adc_dry) * 100.0

    return max(0.0, min(100.0, pct))

def make_soil_messages(from_id: str, raw_val: int, adc_dry: int, adc_wet: int) -> Tuple[dict, dict]:
    ts = int(time.time())
    pct = adc_to_percent(raw_val, adc_dry, adc_wet)
    raw_msg = {"value": raw_val, "fromId": from_id, "ts": ts}
    pct_msg = {"value": round(pct, 2), "fromId": from_id, "ts": ts}
    return raw_msg, pct_msg