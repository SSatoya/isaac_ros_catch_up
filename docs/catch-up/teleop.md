# Isaac ROS キャッチアップ記録 — teleop

> **時点**: 2026-10-29（この文書は書いた時点の認識のスナップショットです）
> **環境**: ホスト Ubuntu 22.04.5 / RTX 5080 / Driver 580.126.09（CUDA 13.0）、
> コンテナ Ubuntu 24.04 / ROS 2 Jazzy / Isaac ROS 4.6（isaac-ros-4.6-base、**ホットパッチ済み**）
> **手順書**: [setup](../setup/teleop.md)

## 1. 目的と結論（先に結論を書く）

- 目的: `isaac_ros_teleop`（ソースビルド）で XR テレオペの全パイプライン
  （XR クライアント → CloudXR → OpenXR → ROS トピック）を Quest 3 なしで検証する
  （→ 結果として Quest 3 実機・ハンドトラッキングまで到達）。
- **結論（2026-10-29 到達）**
  - デスクトップブラウザ + WebXR エミュレータで接続成功。`ee_poses` 約 56 Hz、
    TF `world → head / left_wrist / right_wrist` 配信確認済み。
  - **Quest 3 実機接続も成功**（同一 LAN、ufw 変更不要だった）。さらに
    **`hand_teleop` モード（素手のハンドトラッキング）も実機で動作確認**。
    `/xr_teleop/hand` 56.0 Hz、`ee_poses` 55.6 Hz、`finger_joints` 44 関節。
  - 接続失敗（`0xC0F2230F`）の直接原因は、**他のユーザーの CloudXR サーバーとの
    ポート衝突**（49100/tcp、47998/udp）。共有ホスト（host network）では構造的な問題。
  - **47998/udp はこの実装では固定**（`NV_CXR_MEDIA_PORT` は無視された）。ポート移動で
    衝突を回避できるのは TCP 側だけ。
  - コンテナで Vulkan が効かなかった根本原因は `--gpus all`（runc だと nvidia-container-toolkit
    の createContainer フックが走らず graphics 系マウントが注入されない）。恒久対策は
    `--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all`。
  - CloudXR 6.2.0 の「GPU device ID 11266 (RTX 5080) is not white-listed」警告は、
    実運用で無害であることが実測で確認できた。

## 2. 参照した情報

* 公式サブツリー docs: `isaac_ros-dev/src/isaac_ros_teleop/isaac_teleop_core/IsaacTeleop/docs/`
  （`getting_started/quick_start.rst`、`references/oob_teleop_control.rst`、`references/mcap_record_replay.rst`）
* Web クライアントのデプロイ仕様: 同 `docs/source/conf.py` と `.github/workflows/docs.yaml`
  （`/client/<slug>/`、slug = `main` / `release-1.3.x` / `v1.3.131` / `stable`）
* isaacteleop パッケージ本体: `/var/lib/isaac-ros-cli/isaac-ros/lib/python3.12/site-packages/isaacteleop/cloudxr/`
  （`launcher.py`, `runtime.py`, `wss.py`, `env_config.py`, `oob_teleop_env.py`）
* サブモジュール IsaacTeleop のピン: tag `v1.3.131` + 1 commit（`465ce637`）

## 3. 環境と構成

<details><summary> ディレクトリ構成（コンテナ内 / .cloudxr の中身）</summary>

```text
isaac_ros-dev/
├── src/isaac_ros_teleop/            ← clone（release-4.6, --recursive）。Git 管理外
│   ├── isaac_ros_teleop/            ← ROS 2 パッケージ（launch / メッセージ）
│   └── isaac_teleop_core/           ← C++/Python ノード + IsaacTeleop サブモジュール
└── .cloudxr/                        ← ランタイムの状態（Git 管理外・.gitignore 追加済み）
    ├── certs/server.crt|key         ← WSS プロキシの自己署名証明書（自動生成）
    ├── run/cloudxr.env              ← OpenXR 設定の受け渡し
    ├── openxr_cloudxr.json          ← OpenXR ロードマニフェスト（XR_RUNTIME を指す）
    ├── libopenxr_cloudxr.so         ← OpenXR API レイヤー／ランタイムスタブ
    └── logs/                        ← wss.*.log / cxr_server.*.log / cxr_streamsdk.*.log
```

</details>

## 4. パッケージ・ノードの役割

| パッケージ / プロセス | 役割 | 入力 | 出力 |
| --- | --- | --- | --- |
| `teleop_ros2_node`（Python/rclpy） | OpenXR アプリ + **WSS プロキシを同プロセス内に持つ**（48322） | OpenXR アクション | ROS トピック + TF |
| CloudXR ランタイム（`isaacteleop.cloudxr.runtime.run` を実行する python） | XR 配信サーバー。WebRTC セッション・NVENC 映像・シグナリング（49100） | WS sign_in / SDP / ICE | OpenXR 空間・姿勢 → IPC pipe 経由でノードへ |
| `wss-proxy`（node プロセス内スレッド） | TLS 終端 + WS 中継（48322 → ws://localhost:49100）、証明書通過ページ、静的クライアント配信（`--host-client` 時のみ） | ブラウザの WSS | 49100 への WS |
| Web クライアント（CloudXR.js） | ブラウザ側の WebXR クライアント。WebRTC 受信・描画・入力送信 | — | — |

ノードとランタイムは `.cloudxr/run/` の UNIX ソケット（"pipe"）で IPC 接続される。
`cxr_server` ログの `Client 139 connected to pipe` は XR アプリ側の接続であり、
ブラウザの接続とは別物（混同しやすい）。

## 5. データフロー

```text
[ブラウザ + WebXR emulator]                        [コンテナ（host network）]
 CloudXR.js client ── WSS 48322 ──▶ wss-proxy ── ws 49100 ──▶ CloudXR ランタイム
        ▲  (TLS, 自己署名)                │                        │
        │                                 └─ /client 静的配信は    │ cxr_server 内の
        │                                    --host-client のみ     │ streamsdk(ICE/SDP)
        │                                                          │
        └──── WebRTC メディア UDP 47998（H.264/AV1 + 音声）◀── NVENC (Vulkan)
                                                                   │
                                            OpenXR 姿勢（pipe IPC）│
                                                                   ▼
                                                     teleop_ros2_node ──▶ /xr_teleop/* + /tf
```

## 6. 検証した内容与結果

<details><summary> 検証項目一覧（13 項目）</summary>

| # | 確認したこと | 結果 | 備考 |
| --- | --- | --- | --- |
| 1 | ソースビルド（release-4.6 + CUDA arch 120） | 成功 | `isaacteleop 1.3.131` が venv に入る |
| 2 | コンテナ内 Vulkan | `vulkaninfo --summary` に RTX 5080 / API 1.4.312 | ホットパッチ後。原因は `--gpus all` |
| 3 | `NV_CXR_SERVER_PORT` | **有効**（49100 変更 OK） | |
| 4 | `NV_CXR_MEDIA_PORT` | **無効**（47998/udp に固定バインド） | このランタイム（CloudXR 6.2.0）の実測挙動 |
| 5 | ノード起動 → 49100/48322 待受、WSS 証明書自動生成 | 成功 | `.cloudxr/certs/` |
| 6 | ブラウザ接続（初回、他ユーザーの CloudXR サーバー生存時） | 失敗 `0xC0F2230F` | sign_in は届くが 6〜30 s でサーバー側が切断。streamsdk に ICE/SDP 記録なし |
| 7 | 同一ブラウザ IP のクライアントが先に**他ユーザーのサーバー**に接続していた事実 | 確認 | 競合サーバー除去後、同一手順で成功 |
| 8 | ポート解放後の再接続（release-1.3.x クライアント） | **成功**、一度も失敗せず | `TeleopSession started successfully` |
| 9 | トピック / TF | ee_poses 56.3〜56.4 Hz（左→右 2 pose）、head_pose 57 Hz、TF 3 フレーム | 60 Hz 目標に対しエミュレータ要因でやや下回る |
| 10 | 他ユーザー `at-factory-jazzy` の `run_nyokkey_head.py` が 49100 を再取得 | 特定済み（`/proc/net/tcp` inode → 各コンテナ fd 検索） | 自動リトライで空きポートを拾う模様 |
| 11 | GPU ホワイトリスト警告（device 11266 = RTX 5080） | セッション成功と両立 | CloudXR 6.2.0 の既知の警告、実害なし |
| 12 | Quest 3 実機接続（controller_teleop） | **成功**。ufw は変更せず同一 LAN で接続できた | 証明書通過 → release-1.3.x クライアント → Connect |
| 13 | **`hand_teleop` モード（Quest 3 素手）** | **成功**。hand 56.0 Hz・ee_poses 55.6 Hz・TF 配信・finger_joints 44 名称（Sharpa Wave 22×左右） | `ros2 run` で `-p mode:=hand_teleop`。要 URDF fetch。ログの `Unable to resolve filename: ...STL`（mesh 欠落）と `Right: '<none>'`（コントローラ無し）は実害なし |

</details>

## 7. 主要パラメータ・環境変数

| 名前 | 意味 | 今回採用した値 | 根拠 |
| --- | --- | --- | --- |
| launch 引数 `cloudxr_accept_eula` | CloudXR EULA 同意 | `true` | 未指定だと起動拒否 |
| launch 引数 `rate_hz` | 出力周期 | 既定 60 | |
| launch 引数 `transform_rotation` | OpenXR(RUB)→ROS(FLU) 回転 `[0.5,-0.5,-0.5,0.5]` | 既定 | |
| launch 引数 `cloudxr_setup_oob` / `cloudxr_usb_local` | adb 経由でヘッドセットへ自動接続（coturn / adb reverse 含む） | 未使用 | LAN 接続で実機接続できたため未使用 |
| ノードパラメータ `mode` | テレオペモード（`controller_teleop` 既定 / `hand_teleop` / `controller_raw` / `full_body`）。**launch は公開していない** | `hand_teleop`（実機検証） | `ros2 run ... --ros-args -p mode:=hand_teleop` で渡す |
| ノードパラメータ `hand_retargeter` | 指のリターゲット方式（`mode_default` / `trihand` / `dexpilot` / `pink_ik`）。hand_teleop の既定は dexpilot | 既定（dexpilot） | dexpilot は Sharpa Wave URDF が必要（fetch スクリプトあり）。pink_ik は `isaacteleop[grounding]` + MJCF が必要 |
| ノードパラメータ `pedal_collection_id` | hand_teleop の移動（root_twist）に使う 3 軸フットペダルの tensor collection ID | 既定（ペダル無し → root_twist はゼロ） | ペダル装置は未所持 |
| `NV_CXR_ENABLE_PUSH_DEVICES` | CloudXR の hand tracking push（overseer） | 既定 `true` | これにより XR_EXT_hand_tracking のデータがサーバーへ入る |
| `NV_CXR_SERVER_PORT` | シグナリングポート | 既定 49100 | 変更は有効だが UDP は固定なので根本回避にならない |
| `PROXY_PORT` | WSS プロキシポート | 既定 48322 | |
| `NV_CXR_SERVER_LOG` | ランタイムログレベル（trace/debug/info/warn/error） | `debug`（診断中） | 既定は error で情報不足。**本来は既定に戻す** |
| `WSS_PROXY_DEBUG` | isaacteleop の wss.py に追加した独自デバッグフラグ（WS メッセージ全文ログ） | `1`（診断中） | 診断用ローカルパッチ。**恒久的なものではなく復元対象**（8 章 TODO#1） |

## 8. 未確認・次の TODO

<details><summary> TODO 一覧（12 項目）</summary>

| # | 項目 | 状態 | メモ |
| --- | --- | --- | --- |
| 1 | **wss.py 診断パッチの復元** | **未実施（接続検証中のため意図的に残し）** | `wss.py` を `/tmp/wss.py.orig`（コンテナ内）から復元して `NV_CXR_SERVER_LOG` / `WSS_PROXY_DEBUG` を外し、ノードを一回再起動する。手順: `cp /tmp/wss.py.orig /var/lib/isaac-ros-cli/isaac-ros/lib/python3.12/site-packages/isaacteleop/cloudxr/wss.py && rm -rf .../__pycache__/wss*.pyc`。**バックアップはコンテナの書き込みレイヤーにあるので、コンテナを作り直すと消える**（その場合は再インストールで戻る） |
| 2 | `container.sh` の `--gpus all` → `--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all` | 未実施 | 次回のコンテナ作成時に反映。現コンテナはホットパッチで生存中（作り直すとパッチも消える）。FoundationPose 等の実行中ジョブを殺さないこと |
| 3 | ホストの ufw 確認・開放 | **実質不要だった** | ufw を一切変更せずに Quest 3 実機が同一 LAN で接続できた（2026-10-29）。ufw の状態自体は未確認のまま |
| 4 | Quest 3 実機接続 | **完了（2026-10-29）** | 同一 LAN で接続成功。IWER 不要（Quest 側が WebXR を持つ）。controller / hand 両モードで確認 |
| 5 | ドライバー 595+ 要件 | 未検証 | CloudXR 公式は 595+ を要求するが、580.126.09 で動作実績あり。**ホスト Driver の更新はユーザーの明示許可なしには行わない** |
| 6 | `cloudxr_setup_oob:=true` / `--usb-local`（adb 直結）モード | 未検証 | USB 直結なら ufw 不要。coturn が必要（`apt install coturn`） |
| 7 | MCAP レコード / リプレイ（ヘッドセット無し代替） | 未検証 | `IsaacTeleop/docs/source/references/mcap_record_replay.rst`。XR 抜きで teleop 下流を検証する手段 |
| 8 | 共有ホストでの 47998/udp 運用ルール | 要調整 | UDP が固定なので「CloudXR を同時に 1 系統しか動かせない」。at-factory ユーザー（`run_nyokkey_head.py` は自動リトライでポートを拾う）と運用の*time 住み分け*を決める |
| 9 | ルート README の環境表（RTX 3090×2 表記） | 今回更新済み | RTX 5080 / 580.126.09 / CUDA 13.0 に更新 |
| 10 | **ハンドトラッキング（hand_teleop モード）** | **完了（2026-10-29 実機検証）** | `ros2 run ... --ros-args -p cloudxr_accept_eula:=true -p mode:=hand_teleop`。URDF は `fetch_sharpa_wave_urdfs.py` で取得済み（`examples/teleop_ros2/assets/urdf/sharpa_standalone/`）。実測は 6 章 #13。手順は setup 8 章 |
| 11 | `mode:=controller_teleop hand_retargeter:=dexpilot`（移動はコントローラ、指だけハンドトラッキング） | 未検証 | ペダル不要の中間解。同 URDF でいけるはず |
| 12 | フットペダル（`pedal_collection_id`）による hand_teleop の移動 | 未検証（装置未所持） | `Generic3AxisPedalSource` の tensor collection。push device 経由で供給される想定 |

</details>

## 9. 重要な認識

- **`0xC0F2230F` は「サーバーがセッションを終わらせた」という意味のクライアント側コード**。
  原因はサーバー側ログ（`.cloudxr/logs/`）に出るので、クライアントの再試行だけでは解決しない。
  （対になる `0xC0F2220F` は ICE のローカル候補待ちタイムアウトで、意味が全く違う。）
- **ポート競合の見え方**: WSS ログには `sign_in` が Proxy されるのに、`cxr_streamsdk.*.log` に
  ICE/SDP/Peer の行が一切無い = WebRTC セッション生成自体がメディアポート（47998/udp）まで
  到達していない合図。既定ログレベル（error）では理由が残らないため、切り分け時は
  `NV_CXR_SERVER_LOG=debug` が有効。
- **UDP 47998 固定**のため、host network の共有ホストでは CloudXR サーバーは 1 系統限定になる。
  TCP 側だけ逃げても無意味。
- クライアント URL の slug は docs のブランチ名由来（`/client/release-1.3.x/` 等）。
  ルート `/client/` は `stable`（最高タグ）へリダイレクトされ、ランタイム（1.3.131）より
  新しいクライアントになる。今回の失敗時はこの取り違えも疑ったが、実際の原因はポート競合だった。
- ブラウザからの接続は「48322 への TLS 通過」が前提。WSS プロキシは同一パスで
  静的クライアント配信（`--host-client`）や OOB ハブ API も担う。
  通過ページへはクライアント UI 内の「Click https://<ip>:48322/ to accept cert」
  リンクから行けるため、48322 を先に直接開く手順は不要（公式图解:
  IsaacCapture Quick Start「Connect an XR headset」）。
- `teleop_ros2_node` は **Python ノード**（`install/isaac_teleop_core/lib/isaac_teleop_core/teleop_ros2_node` は python3 スクリプト）。
  WSS プロキシはこのプロセス内にあり、CloudXR ランタイムは別プロセス（python が `runtime.run()` を実行）。
- **TF も `/xr_teleop/*` も「XR セッション確立中にしか」出ない**。クライアントが切れる
  （Quest ブラウザタブのフォアグラウンド喪失、スリープ等）と `-35` ループに戻り、
  `/tf` は完全に停止する。rviz2 で「みえるとき/みえないとき」があるなら、まず
  `ros2 topic hz /tf` でセッション生存を確認し、次に rviz2 側の
  `ROS_DOMAIN_ID=30` / `FASTRTPS_DEFAULT_PROFILES_FILE` と Fixed Frame=`world` を確認する。
- ハンドトラッキングは**モードが要求する OpenXR 拡張で on/off が決まる**。
  `controller_teleop`+`trihand`（既定）は HandTracker をパイプラインに持たないため
  `XR_EXT_hand_tracking` を要求しない（接続ログで `ext_hand_tracking_enabled: false`）。
  `hand_teleop` や `hand_retargeter:=dexpilot/pink_ik` では要求され、Quest 3 の素手データが
  流れてくる（クライアント側は常に `handTracking: true` でセッション要求、サーバー側の
  push overseer `NV_CXR_ENABLE_PUSH_DEVICES` は既定 true）。
