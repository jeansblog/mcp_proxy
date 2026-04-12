"""
簡易MQTTライト切替スクリプト
使い方例:
  ライトをONにする:
    python3 mqtt_light_switch.py --broker localhost --topic home/light --action ON

  状態を購読して表示する:
    python3 mqtt_light_switch.py --broker localhost --topic home/light --listen

環境変数でもブローカー情報を与えられます: MQTT_BROKER, MQTT_PORT
"""
import os
import argparse
import time
import sys
import uuid
import paho.mqtt.client as mqtt


def build_args():
    p = argparse.ArgumentParser(description="MQTTでライトをON/OFFする簡易クライアント")
    p.add_argument("--broker", default=os.getenv("MQTT_BROKER", "localhost"), help="MQTTブローカーのホスト")
    p.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")), help="MQTTブローカーのポート")
    p.add_argument("--topic", required=True, help="ライトのトピック（例: home/light）")
    p.add_argument("--action", choices=["ON","OFF"], help="ライトを切り替える（ON または OFF）")
    p.add_argument("--message", help="送信するメッセージ（省略時は action を利用）")
    p.add_argument("--qos", type=int, choices=[0,1,2], default=0, help="QoS")
    p.add_argument("--retain", action="store_true", help="retainフラグを付ける")
    p.add_argument("--client-id", default=f"mqtt-light-{uuid.uuid4().hex[:6]}", help="MQTTクライアントID")
    p.add_argument("--username", help="MQTTユーザー名（任意）")
    p.add_argument("--password", help="MQTTパスワード（任意）")
    p.add_argument("--listen", action="store_true", help="指定トピックを購読してメッセージを表示する")
    return p.parse_args()


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("接続成功")
    else:
        print("接続失敗: rc=", rc)


def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode('utf-8')
    except Exception:
        payload = msg.payload
    print(f"受信: topic={msg.topic} payload={payload} qos={msg.qos} retain={msg.retain}")


def main():
    args = build_args()

    client = mqtt.Client(client_id=args.client_id)
    if args.username:
        client.username_pw_set(args.username, args.password)

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.broker, args.port, keepalive=60)
    except Exception as e:
        print("ブローカーへの接続に失敗しました:", e)
        sys.exit(1)

    # リッスンモード
    if args.listen:
        client.subscribe(args.topic, qos=args.qos)
        client.loop_forever()
        return

    # アクション送信
    if not args.action and not args.message:
        print("--action または --message を指定してください。例: --action ON")
        sys.exit(2)

    payload = args.message if args.message is not None else args.action

    client.loop_start()
    info = client.publish(args.topic, payload=payload, qos=args.qos, retain=args.retain)
    info.wait_for_publish()
    if info.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"送信完了: topic={args.topic} payload={payload} qos={args.qos} retain={args.retain}")
    else:
        print("送信失敗 rc=", info.rc)

    # 少し待ってから終了（必要に応じて調整）
    time.sleep(0.5)
    client.loop_stop()
    client.disconnect()


if __name__ == "__main__":
    main()
