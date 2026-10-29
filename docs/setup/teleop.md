# Isaac ROS Teleop セットアップ手順

> **状態**: 動作確認済み（2026-10-29、Quest 3 実機。
> コントローラモードとハンドトラッキングモード（`hand_teleop`）の両方）
> **対象**: Isaac ROS 4.6 / ROS 2 Jazzy / Ubuntu 24.04 ベースイメージ / isaacteleop 1.3.131
> **所要時間目安**: 30〜60 分（クローン・ビルドを含む。Vulkan 修正が要らなければ短縮）

## 0. この文書の読み方

- 各コマンドブロックの直前に **コンテナ内 / コンテナ外** を書く。
- `${ISAAC_ROS_WS}` はホスト側ワークスペース（コンテナ内では `/workspaces/isaac_ros-dev`）。
- 途中で失敗したら「[つまずいたとき](#9-つまずいたとき)」を先に見る。
- 仕組み・切り分けの詳細は [調査記録](../catch-up/teleop.md)。

## 1. 前提

* **目的**: XR クライアント（Quest 3 実機。コントローラ / 素手トラッキング）の
  姿勢・関節データを ROS 2 トピックとして受け取る。
* **パッケージ**: `isaac_ros_teleop`（ROS 2 層）と `isaac_teleop_core`（OpenXR / CloudXR 層）。
  本リポジトリでは **ソースビルド**（apt バイナリではない）。
* **ランタイム**: isaacteleop 1.3.131 が同梱する CloudXR 6.2.0 ランタイムが、
  XR 配信サーバーとしてノード起動時に自動起動する。

### 通信ポート（コンテナが host network のためホスト全体で一意にする）

| プロトコル | ポート | 用途 | 備考 |
| --- | --- | --- | --- |
| TCP | 49100 | CloudXR シグナリング（sign_in / WebRTC ネゴシエーション） | `NV_CXR_SERVER_PORT` で変更可 |
| TCP | 48322 | WSS プロキシ（TLS 終端 → 49100 へ中継、自己署名証明書） | `PROXY_PORT` で変更可 |
| UDP | **47998** | WebRTC 音声・映像メディア | **この実装では固定。環境変数 `NV_CXR_MEDIA_PORT` は効かない** |

> 共有ホストで他のユーザーの CloudXR サーバー（Isaac Lab / Isaac Sim の teleop 機能を含む）と
> **49100 と 47998 が衝突するとセッションが確立できない**。起動前・接続前に必ず空きを確認する（5 章・9 章）。

### 出力トピック（クライアント接続後）

出力はノードパラメータ `mode`（既定 `controller_teleop`）で変わる。
ハンドトラッキングモード（`hand_teleop`）は [8 章](#8-ハンドトラッキングモード-hand_teleop)。

| データ | トピック | 型 | 備考 |
| --- | --- | --- | --- |
| 両手首の姿勢（左→右の 2 要素） | `/xr_teleop/ee_poses` | `geometry_msgs/PoseArray` | frame `world`、既定 60 Hz。hand_teleop ではハンドトラッキングの手首 |
| 頭の姿勢 | `/xr_teleop/head_pose` | `geometry_msgs/PoseStamped` | |
| 移動コマンド | `/xr_teleop/root_twist` | `geometry_msgs/TwistStamped` | controller: スティック / hand_teleop: フットペダル |
| コントローラ生データ | `/xr_teleop/controller_data` | `ByteMultiArray` | msgpack |
| 指関節の姿勢（hand_teleop） | `/xr_teleop/hand` | `geometry_msgs/PoseArray` | XR_EXT_hand_tracking 25 関節×左右=50 pose |
| 指関節角度 | `/xr_teleop/finger_joints` | `sensor_msgs/JointState` | controller(trihand): 6×2 / hand_teleop: Sharpa Wave 22×2 |
| TF | `/tf` | — | `world → head / left_wrist / right_wrist`。**セッション確立中のみ配信** |

## 2. パッケージのインストール（コンテナ内）

```bash
cd /workspaces/isaac_ros-dev/src
git clone -b release-4.6 --recursive \
  https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_teleop.git

isaac-ros activate   # ROS 2 + ワークスペース + isaac-ros venv の環境設定

rosdep install --from-paths isaac_ros_teleop --ignore-src -r -y
```

> rosdep により `python3-isaacteleop-pip-shim`（isaacteleop 1.3.131）と msgpack 系パッケージが入る。
> `isaacteleop` は isaac-ros venv（`/var/lib/isaac-ros-cli/isaac-ros`）に入るため、
> **`isaac-ros activate`（または venv の activate）をしないと CloudXR が起動しない**。

## 3. ビルド（コンテナ内）

RTX 50 シリーズ（sm_120）では CUDA アーキテクチャの明示が必須（既定の sm_75 だと実行時エラー）。

```bash
cd /workspaces/isaac_ros-dev
colcon build --symlink-install --packages-up-to isaac_ros_teleop \
  --cmake-args -DCMAKE_CUDA_ARCHITECTURES=120
source install/setup.bash
```

確認:

```bash
python3 -c "import isaacteleop; print(isaacteleop.__file__)"
# → /var/lib/isaac-ros-cli/isaac-ros/lib/python3.12/site-packages/isaacteleop/...
```

## 4. 前提条件の確認: コンテナ内の Vulkan（コンテナ内）

CloudXR ランタイムは **Vulkan + NVENC** で映像を作るため、コンテナ内で Vulkan が効いていないと
接続前に落ちる。必ず確認する:

```bash
vulkaninfo --summary   # "NVIDIA GeForce RTX 5080" と apiVersion が出るはず
```

<details><summary> 出なかった場合の原因と直し方</summary>

原因は、コンテナ起動が `--gpus all` になっていること（症状は
`WARNING: [Loader Message] Code 0 : terminator created an empty icd` 等）。
**runc では nvidia-container-toolkit の createContainer フックが実行されず、
Vulkan ICD・graphics モジュールが注入されない**
（詳細な再現ファイルリストは [調査記録 6 章](../catch-up/teleop.md)）。

対処は 2 通り:

1. **恒久対策（次回のコンテナ作成から有効）**: `container.sh` の `docker run` で
   `--gpus all` をやめ、`--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all` に変える。
   ※ 既存コンテナの作り直しになるので、他の実行中ジョブに影響がないか確認してから行う。
2. **ホットパッチ（作り直さず今すぐ直したい場合）**: ホストのドライバーと同じバージョンの
   グラフィクスマウント一式（`libnvidia-vksc-core.so.*`, ICD json `nvidia_icd.json`,
   `10_nvidia.json`, `nvidia_layers.json` 等）をコンテナへ展開して `ldconfig` する。
   コンテナの書き込みレイヤーに載るだけなので**作り直すと消える**。

</details>

## 5. 起動（コンテナ内）

```bash
cd /workspaces/isaac_ros-dev
source install/setup.bash
isaac-ros activate
export FASTRTPS_DEFAULT_PROFILES_FILE=/workspaces/dds_cfg/fastdds.xml

# 起動前にポート確認（他ユーザーと衝突していたら接続できない）
ss -tln | grep -E ':49100|:48322' && echo "BUSY!: 49100/48322 が使用中"
ss -uln | grep ':47998'           && echo "BUSY!: 47998/udp が使用中"

ros2 launch isaac_ros_teleop isaac_ros_teleop.launch.py cloudxr_accept_eula:=true
```

正常な起動ログ（この状態 = クライアント待ち。`-35` の WARN はループしていて正常）:

```text
[teleop_ros2_node]: Mode: controller_teleop
[INFO] CloudXR runtime and WSS proxy started (WSS log: .../isaac_ros-dev/.cloudxr/logs/wss....log)
Created OpenXR instance
[WARN] No XR client connected (Failed to get OpenXR system: -35), retrying in 2s...
```

ログの場所:

| ログ | パス |
| --- | --- |
| launch 全体 | `~/.ros/log/` またはリダイレクト先（例 `/tmp/teleop_launch*.log`） |
| WSS プロキシ / CloudXR ランタイム / streamsdk | `${ISAAC_ROS_WS}/.cloudxr/logs/`（host network の `.cloudxr` は Git 管理外） |

## 6. XR クライアントでの接続（Quest 3 実機）

バージョン一致のクライアントを推奨（isaacteleop 1.3.131 なら）。
最新版で良いなら `.../client/stable/`。URL の仕組みは [調査記録 9 章](../catch-up/teleop.md)。

```text
https://nvidia.github.io/IsaacTeleop/client/release-1.3.x/
```

1. Quest ブラウザで上のクライアントを開き、サーバー IP に **サーバーの LAN IP**
   （本ホスト例: `192.168.128.80`）を入れる
2. 証明書未通過の場合は、クライアントページ内に出る
   **「Click https://<ip>:48322/ to accept cert」** リンクから新しいタブを開き、
   「Your connection is not private」→ 詳細表示 → ** Proceed to <ip>（ unsafe）** を選択。
   **"Certificate Accepted"** が出たらクライアントのタブに戻る
   （リンクを出したいときは Connect を一度押せばよい。同一 LAN であれば ufw の変更は
   不要だった。公式ドキュメントは `47998/udp`, `49100/tcp`, `48322/tcp` の開放を挙げており、
   ufw が有効な環境では必要になる可能性あり）
3. **Connect**。ハンドトラッキングを使う場合は許可を聞かれたら OK（素手で接続、8 章）
4. 成功するとクライアントに映像が出て、ノードログに:

```text
Left: 'Quest Touch Plus Left'
Created OpenXR system
Created OpenXR session (headless mode)
[INFO] TeleopSession started successfully
```

<details><summary> ヘッドセットが無い場合の代替（デスクトップブラウザ）</summary>

ブラウザ単体では VR デバイスを emulate できないため、WebXR エミュレータ拡張が必須。
拡張を有効化して VR デバイスを emulate した状態で、手順は Quest と同じ
（クライアント URL → 証明書をページ内リンクで通過 → Connect）。2026-10-29 のトピック検証はこの経路でも行った。

</details>

## 7. 動作確認（コンテナ内）

```bash
isaac-ros activate
export FASTRTPS_DEFAULT_PROFILES_FILE=/workspaces/dds_cfg/fastdds.xml

ros2 topic hz /xr_teleop/ee_poses     # 期待: ~56〜60 Hz
timeout 5 ros2 topic echo /tf | grep child_frame_id | sort | uniq -c
# 期待: head / left_wrist / right_wrist の 3 フレーム

ros2 topic echo /xr_teleop/ee_poses --once
# 期待: frame_id: world、poses が 2 個（1 番目=左手 y>0、2 番目=右手 y<0、z≈1.4）
```

2026-10-29 の実測: ee_poses 56.3〜56.4 Hz（std dev 0.2 ms）、head_pose 57 Hz、TF 3 フレームすべて確認。

## 8. ハンドトラッキングモード: hand_teleop

Quest 3 の素手トラッキング（コントローラ不使用）で、手首姿勢・指関節を受け取る。
**動作確認済み（2026-10-29、Quest 3 実機）**。

### 8.1 Sharpa Wave URDF の準備（初回のみ、コンテナ内）

`hand_teleop` の既定リターゲット（DexPilot）は Sharpa Wave ハンドモデルを必要とし、
ソースビルドでは未取得（`examples/teleop_ros2/assets/urdf/sharpa_standalone/` に README のみ）。

```bash
cd /workspaces/isaac_ros-dev/src/isaac_ros_teleop/isaac_teleop_core/IsaacTeleop
python3 examples/teleop_ros2/scripts/fetch_sharpa_wave_urdfs.py
```

> 起動ログに `Unable to resolve filename: package://...STL`（mesh 未取得）が出るが、
> リターゲットは関節キネマティクスのみで動作するため**実害ない**。

### 8.2 起動（コンテナ内）

ノードパラメータ `mode` は launch ファイルが引数として公開していないため、
ノードを直接起動して渡す（ノード自体が CloudXR / WSS プロキシも起動する。
ポート確認は 5 章と同じものを使う）:

```bash
cd /workspaces/isaac_ros-dev
isaac-ros activate
export FASTRTPS_DEFAULT_PROFILES_FILE=/workspaces/dds_cfg/fastdds.xml

ros2 run isaac_teleop_core teleop_ros2_node --ros-args \
  -p cloudxr_accept_eula:=true -p mode:=hand_teleop
```

起動ログで `Mode: hand_teleop` / `Hand retargeter: dexpilot` を確認。

### 8.3 接続と検証

Quest 3 で接続手順は 6 章と同じ。ハンドトラッキングの許可を聞かれたら OK
（設定で有効化済みならそのまま）。**コントローラは持たずに素手**でConnectする。
ログに `Right: '<none>'`（コントローラ不在）と出るのは正常。

```bash
ros2 topic hz /xr_teleop/hand       # 期待 ~56 Hz（PoseArray 50 pose = 25 関節×左右）
ros2 topic hz /xr_teleop/ee_poses   # 手首姿勢。期待 ~56 Hz
ros2 topic echo /xr_teleop/finger_joints --once   # 44 関節名（Sharpa Wave 22×左右）
```

実測（2026-10-29）: hand 56.0 Hz、ee_poses 55.6 Hz、TF 配信あり、finger_joints 44 名称。

### 8.4 注意事項

- 移動（`root_twist`）は **3 軸フットペダル**（`pedal_collection_id` パラメータ）前提。
  ペダルが無い環境ではゼロのまま（位置・指の計測は可能）
- コントローラ移動を残して**指だけ**ハンドトラッキングにする中間解
  `-p mode:=controller_teleop -p hand_retargeter:=dexpilot` は**未検証**
- `hand_retargeter:=pink_ik` は追加で `isaacteleop[grounding]` と Sharpa MJCF が必要（不使用）

## 9. つまずいたとき

<details><summary> 症状 → 原因 → 対処 一覧</summary>

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| 起動時に `ERROR_STREAMSDK_PORT_UNAVAILABLE` | 49100 を他のプロセス（他ユーザーの CloudXR サーバー等）が使用中 | `ss -tln \| grep :49100` で確認 → 所有者を特定して停止してもらう（下表） |
| ブラウザ側で `0xC0F2230F (The server ended the streaming session)` | サーバーがセッションを確立・維持できなかった。最頻原因是ポート衝突（49100/47998 を他サーバーと共有している） | ①ポート確認 ②クライアント URL をバージョン一致（release-1.3.x）で再試行 ③それでもダメなら `.cloudxr/logs` の wss / streamsdk ログへ |
| `sign_in` だけ WSS ログに残り 6〜30 秒で切れる（streamsdk に ICE/SDP の行が無い） | 上記と同じ。セッション作成がメディアポート（47998/udp）まで到達しない | ポート衝突を解消してノード再起動 → 再接続 |
| `No XR client connected ... -35` がずっと続く | クライアント未接続（これは正常待ち）。ただし Connect したのに出続けるならセッション不成功 | 上記 0xC0F2230F 側を見る |
| `xrCreateInstance` 失敗 / Vulkan 系エラー | コンテナに Vulkan が通っていない（`--gpus all` 問題） | 4 章の恒久対策またはホットパッチ |
| `(W) The GPU with device ID 11266 is not white-listed` | CloudXR 6.2.0 が RTX 5080（Blackwell, 0x2C02）をホワイトリストに持たないことの警告 | 実測で映像配信・セッションとも正常に動作。**無視してよい** |
| `Failed to read the Av1Disable regkey` | レジストリキー読み取りの警告 | 无害。無視してよい |
| ブラウザが証明書を弾いて WS が張れない | 自己署名証明書を未許可 | クライアントページ内の「Click https://<ip>:48322/ to accept cert」リンク（なければ 48322 を直接開く）→ 詳細表示 → 続行 → "Certificate Accepted" を確認して戻る |
| rviz2 で TF/トピックが「みえるとき・みえないとき」がある | ①XR クライアント切断（TF も `xr_teleop/*` もセッション確立中のみ配信。Quest ブラウザタブのフォアグラウンド喪失やスリープで切れる）②rviz2 の環境変数不一致 ③Fixed Frame 未設定 | ①`ros2 topic hz /tf` で生存確認（接続中は 50〜60 Hz、切れると 0）→ Quest 再接続 ②rviz2 側でも `ROS_DOMAIN_ID=30` と `FASTRTPS_DEFAULT_PROFILES_FILE=/workspaces/dds_cfg/fastdds.xml` を export ③Fixed Frame を `world` に |

</details>

<details><summary> 所有者の見えないポート衝突の特定方法（host network・マルチユーザー環境）</summary>

`ss -tlnp` で `users:(...)` が空 = 他コンテナ／他ユーザーのプロセス。次の手順で犯人を特定した:

```bash
# 例: 49100 (16 進 BFCC) の socket inode を取る
awk '$4=="0A" && $2 ~ /:BFCC$/' /proc/net/tcp    # 9 列目 = inode
# 各コンテナ内でその socket を持つプロセスを探す
docker exec <container> bash -c \
  'for p in /proc/[0-9]*; do ls -l $p/fd 2>/dev/null | grep -q "socket:\[<inode>\]" && echo $p && tr "\0" " " < $p/cmdline; done'
```

</details>

## 10. 参照

* IsaacTeleop 公式 Quickstart（サブツリー内）: `isaac_ros-dev/src/isaac_ros_teleop/isaac_teleop_core/IsaacTeleop/docs/source/getting_started/quick_start.rst`
* トラブルシューティング（エラーコード一覧）: 同 `docs/source/references/oob_teleop_control.rst`
* Web クライアント: `https://nvidia.github.io/IsaacTeleop/client/`
* 公式接続ガイド（クライアント UI・証明書通過の流れの図解）:
  <https://nvidia.github.io/IsaacCapture/main/teleop/quick_start.html#connect-an-xr-headset>
* 調査記録（仕組み・はまりどころ・今後の TODO）: [../catch-up/teleop.md](../catch-up/teleop.md)
