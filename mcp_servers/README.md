MQTT ライト切替スクリプト

ファイル:
- mqtt_light_switch.py — ライトへON/OFFメッセージを送る/購読する簡易クライアント
- requirements.txt — 必要な依存

セットアップ:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

使い方例:
ライトをONにする:
```bash
python3 mqtt_light_switch.py --broker localhost --topic home/light --action ON
```
ライトをOFFにする:
```bash
python3 mqtt_light_switch.py --broker localhost --topic home/light --action OFF
```
トピックを購読して状態を表示する:
```bash
python3 mqtt_light_switch.py --broker localhost --topic home/light --listen
```

環境変数でブローカー設定を与える例:
```bash
export MQTT_BROKER=broker.example.com
export MQTT_PORT=1883
python3 mqtt_light_switch.py --topic home/light --action ON
```

備考:
- トピック名とメッセージは実際のライト（ブローカー→デバイス）の仕様に合わせてください。
- 保持（retain）フラグやQoSはオプションで指定できます。
