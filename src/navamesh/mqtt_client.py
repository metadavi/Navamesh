import json
import paho.mqtt.client as mqtt

class MqttPublisher:
    def __init__(self, host: str, port: int):
        self._client = mqtt.Client()
        self._client.connect(host, port, 60)
        self._client.loop_start()

    def publish(self, topic: str, obj, qos: int = 0, retain: bool = False) -> None:
        payload = json.dumps(obj, default=str, ensure_ascii=False)
        info = self._client.publish(topic, payload, qos=qos, retain=retain)
        print(f"[MQTT] published rc={info.rc} topic={topic}")

    def close(self) -> None:
        try:
            self._client.loop_stop()
        except Exception:
            pass