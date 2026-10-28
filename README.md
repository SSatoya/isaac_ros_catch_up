# Isaac ROS ワークスペース（isaac_ros_ws）

NVIDIA GPU 上で Isaac ROS を Docker コンテナとして動かし、機能ごとに **手順書（setup）** と **調査記録（catch-up）** を積み上げていくリポジトリです。

現在扱っているテーマは **Pose Estimation（FoundationPose による 6DoF 姿勢推定）** の 1 つです。今後 Isaac ROS の他テーマ（物体検出、SLAM、NI-TROS など）を同じ型で追加できる構成にしています。

```text
RGB + Depth + CameraInfo
        │
        ▼
     RT-DETR（物体検出）
        │
        ▼
  セグメンテーションマスク生成
        │
        ▼
 FoundationPose（Score / Refine）
        │
        ▼
     6DoF 姿勢推定結果
```

## 目次

1. [何ができるか](#1-何ができるか)
2. [動作確認している環境](#2-動作確認している環境)
3. [ディレクトリ構成](#3-ディレクトリ構成)
4. [立ち上げ手順](#4-立ち上げ手順)
5. [知っておきたい決まり事](#5-知っておきたい決まり事)
6. [ドキュメントの読み方](#6-ドキュメントの読み方)
7. [テーマを追加するとき](#7-テーマを追加するとき)
8. [つまずきやすいポイント](#8-つまずきやすいポイント)
9. [用語の最低限の知識](#9-用語の最低限の知識)

---

## 1. 何ができるか

| できること | 場所 |
| --- | --- |
| Isaac ROS 4.6 + ROS 2 Jazzy の開発コンテナをビルド・起動する | `Dockerfile`, `container.sh` |
| FoundationPose の Quickstart（サンプル bag）を RViz2 で確認する | [docs/setup/pose_estimation.md](./docs/setup/pose_estimation.md) |
| 実カメラのトピック（`/head_camera/*`）を FoundationPose に流す launch を持つ | `isaac_ros-dev/src/custom_pose_bringup/` |
| TensorRT Engine（`.plan`）の生成手順が残っている | 手順書 5 章 |
| 仕組み・はまりどころの調査記録が残っている | [docs/catch-up/pose_estimation.md](./docs/catch-up/pose_estimation.md) |

**まだできていないこと**（2026-10 時点）

* 実カメラ入力での安定動作（TF・CameraInfo・同期の調整が未完）
* 実対象物の 3D メッシュでの推定
* Pose Estimation 以外のテーマ

---

## 2. 動作確認している環境

| 項目 | 値 |
| --- | --- |
| ホスト OS | Ubuntu 22.04.5 LTS |
| GPU | NVIDIA GeForce RTX 3090 × 2（24 GB） |
| NVIDIA Driver (KMD) | 610.57.04 |
| CUDA UMD | 13.3 |
| Docker | 28.x（NVIDIA Container Toolkit 必須） |
| コンテナイメージ | `isaac-ros-4.6-base`（Ubuntu 24.04 / ROS 2 Jazzy / Isaac ROS CLI 4.6） |

> **注意**: Isaac ROS 公式の検証環境表記は Ubuntu 22.04 ですが、本リポジトリのイメージは **Ubuntu 24.04 (Noble) + Jazzy** です。パッケージ名（`ros-jazzy-...`）やリポジトリ URL が公式例と異なる場合があります。

---

## 3. ディレクトリ構成

```text
isaac_ros_ws/                     ← Git リポジトリのルート（ホスト）
├── README.md                     ← この文書
├── Dockerfile                    ← 開発イメージ（Ubuntu 24.04 / Jazzy / Isaac ROS 4.6）
├── container.sh                  ← イメージビルド + コンテナ起動のスクリプト
├── .env.example                  ← .env の雛形（.env は Git 管理外）
├── dds_cfg/
│   └── fastdds.xml               ← Fast-RTPS の UDP 設定（コンテナへ /workspaces/dds_cfg として共有）
├── docs/                         ← キャッチアップ文書（テーマ × 種別で拡張）
│   ├── README.md                 ← 文書索引・追加ルール
│   ├── _templates/               ← 新テーマ用の雛形（setup / catch-up）
│   ├── setup/                    ← 手順書
│   └── catch-up/                 ← 調査記録
└── isaac_ros-dev/                ← ROS ワークスペース（コンテナの /workspaces/isaac_ros-dev）
    ├── src/
    │   ├── isaac_ros_*           ← クローンした公式リポジトリ（Git 管理外）
    │   └── custom_pose_bringup/  ← 自作の bringup パッケージ（Git 管理）
    ├── isaac_ros_assets/         ← NGC から取得するアセット・モデル（Git 管理外）
    ├── build/ install/ log/      ← colcon の成果物（Git 管理外）
```

Git の管理範囲は [.gitignore](./.gitignore) で決めています。目安は次の 3 分類です。

| 分類 | 例 | 管理 |
| --- | --- | --- |
| 再現に必要な設定・手順・自作コード | `Dockerfile`, `container.sh`, `docs/`, `src/custom_*` | する |
| 大容量のダウンロード物・成果物 | `isaac_ros_assets/`, `build/`, `install/`, `log/`, `src/isaac_ros*` | しない |
| 個人固有の情報 | `.env` | しない（`.env.example` を共有） |

---

## 4. 立ち上げ手順

### 4.0 前提（ホスト側）

* NVIDIA ドライバが入っていて `nvidia-smi` が効くこと
* Docker と NVIDIA Container Toolkit が入っていること
* X11 表示（RViz2）を使う場合は `xhost +local:` 等の設定が必要

### 4.1 ホスト側（1 回だけ）

```bash
cd $HOME
git clone https://github.com/SSatoya/isaac_ros_catch_up isaac_ros_ws


# (1) ワークスペースの位置を環境変数で教える（container.sh が使用する）
export ISAAC_ROS_WS="$HOME/isaac_ros_ws/isaac_ros-dev"
echo 'export ISAAC_ROS_WS="$HOME/isaac_ros_ws/isaac_ros-dev"' >> ~/.bashrc

# (2) 個人設定を雛形から作る（IMAGE_NAME / CONTAINER_NAME / ROS_DOMAIN_ID）
#     .env が既にある場合はスキップしてよい
cd isaac_ros_ws
cp .env.example .env
```

> 設定済みかの確認: `echo $ISAAC_ROS_WS` が `/home/<user>/isaac_ros_ws/isaac_ros-dev` を返すなら (1) は不要。

### 4.2 コンテナのビルド・起動

```bash
cd ~/isaac_ros_ws
./container.sh
```

`container.sh` は次の処理だけをしています。

1. `.env` を読み込む（無ければ既定値）
2. `ISAAC_ROS_WS` が未設定ならエラーで終了
3. イメージが無ければ `docker build -t ${IMAGE_NAME} .`
4. `docker run`（GPU 全部 / host network / host IPC / X11 マウント / ワークスペースマウント）

### 4.3 コンテナ内（初回だけ）

```bash
sudo isaac-ros init venv    # Isaac ROS CLI を venv モードで初期化
newgrp isaac-ros-cli        # init で追加されたグループを現在のシェルに反映
isaac-ros status            # 設定の確認
```

### 4.4 コンテナ内（ターミナルを開くたびに）

```bash
isaac-ros activate          # ROS 2 とワークスペースの setup を source する
```

### 4.5 ビルドと起動（Pose Estimation の例）

```bash
cd /workspaces/isaac_ros-dev
colcon build --symlink-install --packages-up-to isaac_ros_foundationpose custom_pose_bringup
source install/setup.bash

# Quickstart（サンプル bag）での確認は、手順書の 9〜11 章に完全なコマンドを書いてある

# 実カメラ Topic を流し込む自作 launch
ros2 launch custom_pose_bringup head_camera_foundationpose.launch.py
```

細かい引数・アセット取得・TensorRT Engine 作成までは [docs/setup/pose_estimation.md](./docs/setup/pose_estimation.md) に書いています。

---

## 5. 知っておきたい決まり事

このリポジトリの文書・スクリプトは、すべて次の前提で書かれています。

| 決まり事 | 内容 |
| --- | --- |
| **コンテナ内 / 外の区別** | 文書中のすべてのコマンドブロックに実行場所を書いてある。NGC からのアセット取得は **コンテナ外**、`apt` や `colcon` は **コンテナ内** |
| **ワークスペースのパス** | ホスト `${ISAAC_ROS_WS}`（= `~/isaac_ros_ws/isaac_ros-dev`）⇄ コンテナ `/workspaces/isaac_ros-dev`。文書・launch はコンテナ内パスで統一 |
| **`isaac-ros activate`** | ターミナルを開くたびに実行する（ROS 2 と `install/setup.bash` を source する）。忘れると `ros2: command not found` やパッケージが見つからないエラーになる |
| **アセットは都度取得** | `isaac_ros_assets/` は Git 管理外。クローン後には手順書の 2〜3 章・6 章を取得から実行する |
| **TensorRT Engine は環境依存** | `.plan` は使った GPU / TensorRT のバージョンでしか読めない。GPU を変えたら **同じ環境で作り直す** |
| **公式リポジトリは触らない** | `src/isaac_ros*` は Git 管理外。自作コードは `src/custom_<theme>*/` に入れて分離する |
| **個人設定は `.env`** | `IMAGE_NAME` / `CONTAINER_NAME` / `ROS_DOMAIN_ID` を管理。Git には `.env.example` だけを入れる |

---

## 6. ドキュメントの読み方

`docs/` は **「テーマ × 種別」** の 2 軸で整理しています（詳細は [docs/README.md](./docs/README.md)）。

| 知りたいこと | 読む文書 |
| --- | --- |
| 環境をもう一度作る / 直したい | `docs/setup/<theme>.md`（手順書） |
| なぜその構成なのか、仕組み・はまりどころ | `docs/catch-up/<theme>.md`（調査記録） |
| 文書の追加・命名ルール | [docs/README.md](./docs/README.md) |

### テーマ一覧（2026-10 時点）

| テーマ | 手順書 | 調査記録 | 状態 |
| --- | --- | --- | --- |
| Pose Estimation（FoundationPose） | [setup](./docs/setup/pose_estimation.md) | [catch-up](./docs/catch-up/pose_estimation.md) | Quickstart 動作確認済み／実カメラ入力は調整中 |

<!-- 新しいテーマを足したらここへ 1 行追加する -->

---

## 7. テーマを追加するとき

Isaac ROS の別機能（例: `visual_slam`, `rtdetr`, `body_pose`）を足す場合は、次の型に沿ってください。詳しいルールは [docs/README.md](./docs/README.md) にあります。

```bash
# 1. 文書を雛形から作る
cp docs/_templates/setup.md    docs/setup/<theme>.md
cp docs/_templates/catch-up.md docs/catch-up/<theme>.md

# 2. 自作コードはテーマごとに分ける
mkdir -p isaac_ros-dev/src/custom_<theme>_bringup/launch

# 3. 索引に 1 行追加する（docs/README.md のテーマ一覧 / この README の 6 章）
```

追加時に決めていること:

* 公式リポジトリは `isaac_ros-dev/src/isaac_ros_*`（Git 管理外）、自作は `custom_*`（Git 管理）で混ざらないようにする
* 手順書には **確認した日付と環境** を書く（TensorRT Engine の作り直しが必要になるため）
* `.env` の `ROS_DOMAIN_ID` をテーマで分けると、別テーマと同時に動かしたときの混線を避けられる

---

## 8. つまずきやすいポイント

| 症状 | 原因 | 対処 |
| --- | --- | --- |
| `ros2: command not found`、パッケージが見つからない | `isaac-ros activate` / `source install/setup.bash` をそのターミナルで実行していない | ターミナルを開くたびに `isaac-ros activate` |
| TensorRT Engine が読み込まれない、`.plan` がエラー | `.plan` は生成した GPU・TensorRT 環境に依存する | 同じ GPU 環境で `trtexec` から作り直す |
| FoundationPose が姿勢を返さない、処理が 5 秒で復帰する | RGB / Depth / CameraInfo の同期・アライメント不一致、または `pose_estimation_timeout_ms`（既定 5000 ms）のタイムアウト | タイムスタンプ一致、`aligned_depth_to_color` を使っているか、CameraInfo の解像度を実画像と一致させる |
| RViz2 に姿勢（TF）が表示されない | RViz の Fixed Frame（`tf_camera`）と FoundationPose の object frame（既定 `fp_object`）の TF 関係が構築されていない | TF を張るか、表示は `/pose_estimation/output` を直接見る |
| 実カメラの画像が Quickstart の launch に繋がらない | 公式 launch は `image_rect` / `camera_info_rect` / `depth` 入力前提 | remap か、自作の `custom_pose_bringup` の専用 launch を使う |
| 他マシン・他ユーザと混線する、ノードが見えない | `ROS_DOMAIN_ID` と RMW の不一致 | `.env` の `ROS_DOMAIN_ID` を揃える。イメージは `rmw_fastrtps_cpp` + `dds_cfg/fastdds.xml`（UDP）で統一している |
| Depth が効かない・姿勢が暴れる | Depth が 32FC1 で RGB 座標系にアライメントされていない | RealSense 等では aligned depth トピックを使い、Depth の単位（m）を確認 |
| `apt` でパッケージが入らない | 公式例は Ubuntu 22.04 / Humble 前提の記載が多い | `ros-jazzy-...` と `release-4.6`、noble 向けリポジトリに置き換える |
| FoundationPose 起動直後に `cudaErrorUnsupportedPtxVersion` でクラッシュ | ソースビルドが既定の sm_75 で行われ、新しめの GPU（例: RTX 5080 / sm_120）で SASS が実行できない | `colcon build --cmake-args -DCMAKE_CUDA_ARCHITECTURES=120` で再ビルド。`cuobjdump --list-elf` で sm_120 cubin を確認 |
| 出力トピックが見つからない | quickstart の launch は FoundationPose 出力を `/output` に remap する。TRT 往復は `tensor_pub`=リクエスト / `tensor_sub`=結果 | `ros2 node info` で実際の解決後トピック名を確認する（詳細は setup 12 章） |

---

## 9. 用語の最低限の知識

| 用語 | 意味 |
| --- | --- |
| **Isaac ROS** | NVIDIA が GPU 前提で提供する ROS 2 パッケージ群。画像処理・検出・姿勢推定など |
| **Isaac ROS CLI** | `isaac-ros init / activate / status` を提供する管理ツール。`activate` が ROS 2 とワークスペースの環境設定の読み込み |
| **NI-TROS (NITROS)** | Isaac ROS 内部の型適応の仕組み。ROS 2 標準メッセージと GPU 上のテンソル表現をノード間で自動変換し、コピーを減らす |
| **TensorRT Engine（`.plan`）** | ONNX モデルをその GPU 向けに最適化した実行ファイル。GPU / TensorRT のバージョンが変わると再生成が必要 |
| **NGC / quickstart asset** | NVIDIA NGC からダウンロードするサンプルデータ・モデル・メッシュのまとまり |
| **RT-DETR** | 物体検出モデル。FoundationPose の入力マスクを作る前段として使われる |
| **FoundationPose** | テンプレート（3D メッシュ）付き 6DoF 姿勢推定。Score（候補評価）と Refine（姿勢改善）の 2 ネットワークで構成される |
| **bringup パッケージ** | 既存ノードを特定のハード（ここではヘッドカメラ）で動かすための launch / config をまとめた自作パッケージ |
| **ComposableNode / `component_container_mt`** | 複数のノードを 1 プロセスに載せ、マルチスレッドで並列実行する ROS 2 の仕組み。`custom_pose_bringup` は全ノードを 1 コンテナにまとめている |
| **Quickstart** | 実ハードの代わりに収録済み bag（`quickstart.bag`）で動作確認する公式の入口 |

---

## 参考

* Isaac ROS 公式ドキュメント: <https://nvidia-isaac-ros.github.io/>
* Isaac ROS CLI: <https://github.com/NVIDIA-ISAAC-ROS/isaac-ros-cli>
* Pose Estimation（FoundationPose）: <https://nvidia-isaac-ros.github.io/repositories_and_packages/isaac_ros_pose_estimation/index.html>

