from typing import Callable, Optional
from meshtastic.serial_interface import SerialInterface
from pubsub import pub

class MeshBridge:
    """
    Subscribes to Meshtastic pubsub receive events and forwards packets via a single callback.
    """
    def __init__(self, serial_port: str, on_receive: Callable[[dict], None]):
        self._iface: Optional[SerialInterface] = None
        self._serial_port = serial_port
        self._on_receive = on_receive

    def start(self) -> None:
        self._iface = SerialInterface(self._serial_port)
        pub.subscribe(self._on_receive, "meshtastic.receive")  # <-- only this

    def stop(self) -> None:
        if self._iface is None:
            return
        try:
            self._iface.close()
        except Exception as e:
            print("[WARN] iface.close() interrupted or failed:", e)
        self._iface = None