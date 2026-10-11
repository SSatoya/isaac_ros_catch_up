# Isaac ROS <テーマ名> セットアップ手順

> **状態**: 未検証 / 動作確認済み（YYYY-MM-DD）
> **対象**: Isaac ROS 4.6 / ROS 2 Jazzy / Ubuntu 24.04 ベースイメージ
> **所要時間目安**: XX 分（モデル取得・Engine 作成を含む）

## 0. この文書の読み方

- 各コマンドブロックの直前に **コンテナ内 / コンテナ外** を書く。
- `${ISAAC_ROS_WS}` はホスト側ワークスペース（コンテナ内では `/workspaces/isaac_ros-dev`）。
- 途中で失敗したら「[つまずいたとき](#つまずいたとき)」を先に見る。

## 1. 前提

* 対象機能・バージョン
* 使用するモデル / アセット
* 入出力トピック（表にすると後で読みやすい）

| データ | トピック |
| --- | --- |
| RGB画像 | `/...` |
| CameraInfo | `/...` |
| Depth画像 | `/...` |

## 2. アセット・モデルの取得（コンテナ外）

```bash
# NGC から取得する例
```

### 取得される主なファイル

```text
${ISAAC_ROS_WS}/isaac_ros_assets/
└── ...
```

## 3. パッケージのインストール（コンテナ内）

<details><summary> Option1: バイナリパッケージ</summary>

```bash
sudo apt-get update
sudo apt-get install -y ros-jazzy-<package-name>
```

</details>

<details open><summary> Option2: ソースコードからビルド</summary>

```bash
cd ${ISAAC_ROS_WS}/src && \
   git clone -b release-4.6 https://github.com/NVIDIA-ISAAC-ROS/<repo>.git
isaac-ros activate
rosdep update && rosdep install --from-paths <path> --ignore-src -y
cd ${ISAAC_ROS_WS} && colcon build --symlink-install --packages-up-to <package-name>
source install/setup.bash
```

</details>

## 4. TensorRT Engine の作成（コンテナ内）

`.plan` は **その GPU・TensorRT 環境で生成したもの**を使う（作り直し前提）。

```bash
/usr/src/tensorrt/bin/trtexec \
  --onnx=... --saveEngine=... \
  --minShapes=... --optShapes=... --maxShapes=...
```

## 5. 起動

```bash
isaac-ros activate
ros2 launch <package> <launch>.launch.py ...
```

## 6. 動作確認

確認コマンドと、期待される出力（ログ・RViz2・`ros2 topic echo` など）を貼る。

```bash
ros2 topic list
ros2 topic echo /... --once
```

## 7. つまずいたとき

| 症状 | 原因 | 対処 |
| --- | --- | --- |
|  |  |  |

## 8. 参照

* 公式: <URL>
* 本リポジトリ内の関連: [調査記録](../catch-up/<theme>.md)
