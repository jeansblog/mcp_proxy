import os
import asyncio
import uuid
import paho.mqtt.client as mqtt
from mcp.server.fastmcp import FastMCP

# --- 設定 ---
MQTT_BROKER = os.environ.get("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "ubuntu")
MQTT_PW = os.environ.get("MQTT_PW", "ubuntu")

# MCPサーバーの初期化
mcp = FastMCP("MQTT Light Controller")

def send_mqtt_oneshot(topic, payload, qos=0, retain=False):
    """1回だけメッセージを送信するヘルパー"""
    client_id = f"mcp-pub-{uuid.uuid4().hex[:6]}"
    client = mqtt.Client(client_id=client_id)
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PW)
    
    client.connect(MQTT_BROKER, MQTT_PORT)
    client.loop_start()
    info = client.publish(topic, payload=payload, qos=qos, retain=retain)
    info.wait_for_publish()
    client.loop_stop()
    client.disconnect()
    return info.rc == mqtt.MQTT_ERR_SUCCESS

@mcp.tool()
async def control_light(topic: str, action: str) -> str:
    """
    MQTT経由でライトなどのデバイスを操作します。
    
    Args:
        topic: 操作対象のMQTTトピック (例: 'home/light')
        action: 送信するメッセージ。通常は 'ON' または 'OFF'
    """
    success = send_mqtt_oneshot(topic, action)
    if success:
        return f"Successfully sent '{action}' to {topic}"
    else:
        return f"Failed to send message to {topic}"

@mcp.tool()
async def get_light_status(topic: str, timeout: int = 3) -> str:
    """
    指定されたMQTTトピックの最新のメッセージを購読して取得します。
    
    Args:
        topic: 購読するMQTTトピック
        timeout: メッセージを待機する秒数
    """
    received_payload = None
    client_id = f"mcp-sub-{uuid.uuid4().hex[:6]}"
    client = mqtt.Client(client_id=client_id)
    
    if MQTT_USER:
        client.username_pw_set(MQTT_USER, MQTT_PW)

    def on_message(c, u, msg):
        nonlocal received_payload
        received_payload = msg.payload.decode()

    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT)
    client.subscribe(topic)
    
    # メッセージが来るかタイムアウトするまでループ
    client.loop_start()
    for _ in range(timeout * 10):
        if received_payload is not None:
            break
        await asyncio.sleep(0.1)
    client.loop_stop()
    client.disconnect()

    if received_payload is not None:
        return f"Current status of {topic}: {received_payload}"
    else:
        return f"No message received on {topic} within {timeout} seconds."

if __name__ == "__main__":
    # MCPサーバーを標準入出力モードで起動
    mcp.run(transport="stdio")