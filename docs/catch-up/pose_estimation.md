# isaac_ros_pose_estimation キャッチアップ結果

> **時点**: 2026-09-25（本書は調査時点の認識をそのまま残したスナップショットです。再現手順は [setup](../setup/pose_estimation.md) が正）
> **環境**: ホスト Ubuntu 22.04 / RTX 3090 × 2 / Driver 610.57.04，コンテナ Ubuntu 24.04 / ROS 2 Jazzy / Isaac ROS 4.6
> **章の読み方**
> * 1〜3: 環境と Git リポジトリ構成
> * 4〜10: Isaac ROS 4.6 と FoundationPose のアーキテクチャ（Component 構成・GPU メモリ・タイムアウト）
> * 11〜18: FoundationPoseNode・パラメータ・Tracking
> * 19〜28: Launch 構成・アセット・TensorRT・Quickstart bag
> * 29〜34: 実カメラ入力への移植と未整合
> * 35〜40: 到達点・次の TODO・一枚まとめ
>
> 本書中に登場する `docs/pose_estimation.md` は，現在 `docs/setup/pose_estimation.md` へ移動している。

## 1. 全体構成

現在の環境では、Isaac ROS 4.6 をベースに `isaac_ros_pose_estimation` を調査・導入している。

```text
/home/<user>/isaac_ros_ws/
│
├── Dockerfile
├── container.sh
├── .env
├── .env.example
├── dds_cfg/
│   └── fastdds.xml
│
├── docs/
│   └── pose_estimation.md
│
└── isaac_ros-dev/
    │
    ├── src/
    │   └── isaac_ros_pose_estimation/
    │
    ├── isaac_ros_assets/
    │
    ├── build/
    ├── install/
    └── log/
```

### 1.1 ホスト環境

```text
GPU        : RTX 3090 × 2
Driver     : 610.57.04
CUDA UMD   : 13.3
```

Isaac ROSのREADMEに記載されている検証環境はUbuntu 22.04表記である一方，現在のDockerfileではUbuntu 24.04（Noble）を使用している。

---

# 2. Gitリポジトリ構成

Gitリポジトリのルートは，

```text
/home/<user>/isaac_ros_ws/
```

である。

現在の構成：

```text
isaac_ros_ws/
├── Dockerfile
├── container.sh
├── .env
├── .env.example
├── dds_cfg/
├── docs/
│   └── pose_estimation.md
└── isaac_ros-dev/
```

## 2.1 Dockerfile

主な構成：

```text
ubuntu:24.04
    │
    ├── ROS 2 Jazzy
    ├── CUDA repository
    ├── Jetson apt repository（r39.2）
    ├── isaac-ros-cli（release-4.6）
    ├── NVIDIA ROS dependency definitions
    └── RMW = Fast DDS
```

Fast DDS設定：

```text
/workspaces/dds_cfg/fastdds.xml
```

---

## 2.2 container.sh

`isaac-ros-4.6-base` イメージをビルドしてコンテナを起動する。

主な設定：

```text
--gpus all
--network host
--ipc host
```

また，

```text
${ISAAC_ROS_WS}
    ↓
/workspaces/isaac_ros-dev
```

としてワークスペースをコンテナにマウントしている。

DDS設定もマウントする。

---

## 2.3 環境変数

`.env` の主な設定：

```text
IMAGE_NAME=isaac-ros-4.6-base
CONTAINER_NAME=isaac-ros-jazzy-dev
ROS_DOMAIN_ID=0
```

---

# 3. isaac_ros_pose_estimation

対象リポジトリ：

```text
isaac_ros-dev/src/isaac_ros_pose_estimation/
```

現在は **release-4.6** をcloneしている。

このリポジトリには以下の5パッケージが含まれる。

| パッケージ                                     | 役割                     |
| ----------------------------------------- | ---------------------- |
| `isaac_ros_foundationpose`                | 新規物体を含む6DoF姿勢推定・トラッキング |
| `isaac_ros_centerpose`                    | 既知物体の姿勢推定              |
| `isaac_ros_dope`                          | 既知物体向けの高速姿勢推定          |
| `isaac_ros_foundationpose_models_install` | FoundationPose関連モデルの取得 |
| `isaac_ros_pose_proc`                     | 姿勢推定結果の後処理             |

READMEの比較では，FoundationPoseは以下の特徴を持つ。

```text
Novel object : ✓
Speed        : Fast
Quality      : Best quality
Status       : New
```

また，release-4.6の更新日は **2026-08-18** で，Isaac ROS 4.6.0向けの互換性・統合更新が含まれている。

---

# 4. FoundationPoseの位置付け

今回の主目的は，

```text
isaac_ros_foundationpose
```

である。

FoundationPoseの特徴は，対象物ごとに専用の学習を行わなくても，**物体の3Dメッシュを与えることで新規物体の6DoF姿勢を推定できる**点にある。

入力：

```text
RGB画像
Depth画像
CameraInfo
物体マスク
3D Mesh
```

出力：

```text
6DoF Object Pose
```

概念的には，

```text
RGB ───────┐
           │
Depth ─────┤
           ├──→ FoundationPose ──→ 6DoF Pose
CameraInfo ┤
           │
Mask ──────┘
           ↑
       Object Mesh
```

という構成になる。

---

# 5. isaac_ros_foundationpose のビルド構成

`isaac_ros_foundationpose` は `ament_cmake` を使用する。

CUDAも有効化されている。

```text
LANGUAGES C CXX CUDA
```

主な依存：

```text
assimp
Eigen
OpenCV
nvcv_types
cvcuda
cv_bridge
NITROS
tf2
```

また，

```text
rosidl_generate_interfaces
```

によってサービスインターフェースも生成される。

---

# 6. FoundationPose内部ライブラリ

コアライブラリ：

```text
foundationpose_pipeline
```

主な構成要素：

```text
mesh_loader
pose_sampler
pose_renderer
pose_transformer
pose_decoder
```

CUDA kernel：

```text
foundationpose_sampling.cu
foundationpose_render.cu
```

さらに，レンダリング処理に使用する

```text
nvdiffrast
```

のコードもパッケージ内に含まれている。

---

# 7. ROS 2 Component構成

FoundationPoseは，4.6ではGXF/nodeletではなく，**rclcpp component**として実装されている。

主なComponent：

```text
nvidia::isaac_ros::foundationpose::
│
├── FoundationPoseNode
├── FoundationPoseTrackingNode
├── Selector
├── Detection2DArrayFilter
└── Detection2DToMask
```

それぞれの役割は以下の通り。

| Component                    | 役割             |
| ---------------------------- | -------------- |
| `FoundationPoseNode`         | 姿勢推定           |
| `FoundationPoseTrackingNode` | 前フレーム姿勢を利用した追跡 |
| `Selector`                   | 推定と追跡の切り替え     |
| `Detection2DArrayFilter`     | 2D検出結果のフィルタ    |
| `Detection2DToMask`          | 2D検出結果からマスク生成  |

---

# 8. Isaac ROS 4.6 のアーキテクチャ上の特徴

## 8.1 TensorRTをFoundationPose自身が直接実行するわけではない

FoundationPose NodeがTensorRTを直接呼び出す構成ではない。

TensorRT推論は，

```text
isaac_ros_tensor_rt::TensorRTNode
```

が担当する。

FoundationPoseとはNITROS TensorListを介して通信する。

```text
FoundationPoseNode
        │
        │ NITROS TensorList
        ▼
TensorRTNode
        │
        ▼
TensorRT Engine
```

Refine：

```text
refine/tensor_pub
refine/tensor_sub
```

Score：

```text
score/tensor_pub
score/tensor_sub
```

というトピックを利用する。

---

# 9. GPUメモリ管理

FoundationPoseでは，

```text
nitros::CUDAMemoryPool
```

を利用してGPUバッファを再利用する。

主なPool：

```text
refine_pool
score_pool
pose_matrix_pool
```

これにより，画像処理コールバック中に毎回

```text
cudaMalloc
```

を実行することを避ける。

つまり，

```text
毎フレーム cudaMalloc
        ↓
避ける

GPU buffer pool
        ↓
再利用
```

という設計になっている。

---

# 10. タイムアウト・詰まり対策

処理状態を管理する

```text
processing_
```

ゲートと，

```text
watchdog_timer_
```

が実装されている。

デフォルトのタイムアウト：

```text
pose_estimation_timeout_ms = 5000
```

一定時間FoundationPoseの処理が戻らない場合に，詰まりから復帰するための仕組みである。

---

# 11. FoundationPoseNode

## 11.1 入力

FoundationPoseNodeはApproximateTimeによって以下を同期する。

```text
pose_estimation/image
pose_estimation/depth_image
pose_estimation/camera_info
pose_estimation/segmentation
```

---

## 11.2 出力

主な出力：

```text
pose_estimation/output
```

型：

```text
vision_msgs/Detection3DArray
```

Pose Matrix：

```text
pose_estimation/pose_matrix_output
```

さらにTFも発行する。

デフォルトのTF frame：

```text
fp_object
```

---

# 12. 主なパラメータ

主なパラメータ：

```text
configuration_file
mesh_file_path

refine_input_tensor_names
score_input_tensor_names

min_depth
max_depth

pose_estimation_timeout_ms

symmetry_axes
symmetry_planes

fixed_axis_angles
fixed_translations
```

デフォルトのモデル設定：

```text
foundationpose_model_config.yaml
```

---

# 13. FoundationPoseモデル設定

主な設定値：

| パラメータ             |                    値 |
| ----------------- | -------------------: |
| Input size        |            160 × 160 |
| max_hypothesis    |                  252 |
| refine_crop_ratio |                  1.2 |
| score_crop_ratio  |                  1.2 |
| rot_normalizer    |           0.34906585 |
| trans_normalizer  | `[0.02, 0.02, 0.05]` |

特に，

```text
max_hypothesis = 252
```

はScore ModelのTensorRT Engine作成時に設定した最大batch：

```text
252
```

と対応している。

---

# 14. 動的なメッシュ切り替え

FoundationPoseでは実行中に対象物のメッシュを変更できる。

`mesh_file_path` パラメータの変更を検知すると，

```text
mesh_file_path変更
       ↓
selector reset
       ↓
mesh_loader_->tryReload()
       ↓
tracking/switch_mesh
```

という流れでメッシュを再読み込みする。

そのため，対象物を切り替える用途にも利用できる。

---

# 15. Selector

SelectorはFoundationPoseの推定・追跡状態を管理する。

状態：

```text
kPoseEstimation
       ↓
kWaitingRest
       ↓
kTracking
```

という状態遷移を持つ。

---

## 15.1 処理の流れ

```text
RGB
Depth
CameraInfo
Segmentation
   │
   ▼
Selector
   │
   ├── Pose Estimation
   │
   └── Tracking
```

Pose Estimationで初期姿勢を求めた後，Trackingへ移行する。

---

## 15.2 再推定

一定時間ごとに再推定する仕組みもある。

デフォルト：

```text
reset_period = 600000 ms
```

つまり，

```text
600秒
= 10分
```

ごとに再推定が可能である。

---

# 16. TrackingNode

TrackingNodeは前フレームの姿勢を利用して物体を追跡する。

## 16.1 同期

RGB，Depth，CameraInfo：

```text
ExactTime
```

で同期する。

一方，

```text
tracking/pose_input
```

は同期データではなく，**現在の姿勢状態**として扱われる。

---

# 17. TrackingではRefineのみ使用

Tracking時には，

```text
Refine Model
```

のみを使用する。

```text
Score Model
```

による候補姿勢探索は行わない。

そのため，

```text
Pose Estimation
    ↓
Refine + Score

Tracking
    ↓
Refine only
```

という違いがある。

---

# 18. Trackingのドリフト対策

TrackingNodeには，

```text
min_pointcloud_support = 50
```

という条件がある。

点群がメッシュ中心の近傍に十分存在しない場合，

```text
Tracking
   ↓
点群不足
   ↓
Pose publish停止
   ↓
Selector reset
   ↓
Pose Estimation
```

という復帰処理を行う。

また，

```text
enable_auto_reset = true
```

がデフォルトで有効になっている。

---

# 19. FoundationPoseのLaunch構成

主なLaunch：

```text
isaac_ros_foundationpose.launch.py
isaac_ros_foundationpose_core.launch.py
isaac_ros_foundationpose_tracking_core.launch.py
isaac_ros_foundationpose_isaac_sim.launch.py
isaac_ros_foundationpose_isaac_sim_tracking.launch.py
```

---

# 20. 単体Launch

```text
isaac_ros_foundationpose.launch.py
```

は単体構成で，

```text
Refine TensorRT
Score TensorRT
FoundationPoseNode
```

を組み合わせる。

必要に応じて，

```text
launch_bbox_to_mask
```

によって，

```text
Detection2DArrayFilter
Detection2DToMask
```

も追加できる。

RViz起動用の

```text
launch_rviz
```

も存在する。

---

# 21. Core Launch

```text
isaac_ros_foundationpose_core.launch.py
```

は，

```text
isaac_ros_examples
```

経由で利用するIsaac ROS Launch Fragmentである。

概略：

```text
Input Image
     │
     ▼
drop_node
     │
     ▼
resize
     │
     ▼
pad
     │
     ▼
image_to_tensor
     │
     ▼
interleave_to_planar
     │
     ▼
reshape
     │
     ▼
RT-DETR TensorRT
     │
     ▼
detection2_d_array
     │
     ▼
resize_mask
     │
     ▼
FoundationPoseNode
```

---

# 22. drop_node

Core Launchでは，

```text
drop_node
```

による入力フレームの間引きが設定されている。

現在確認した構成では，

```text
30 → 28
```

のdrop設定になっている。

これは入力画像の処理負荷を抑えるための構成である。

---

# 23. Tracking Core Launch

```text
isaac_ros_foundationpose_tracking_core.launch.py
```

では，検出・姿勢推定・追跡を統合する。

追加される主なパラメータ：

```text
reset_period
tracking_timeout_ms = 1000
min_pointcloud_support = 50
```

---

# 24. アセット構成

現在のアセット：

```text
isaac_ros-dev/isaac_ros_assets/
│
├── isaac_ros_foundationpose/
│   ├── quickstart.bag
│   ├── quickstart_interface_specs.json
│   ├── nyokkey_interface_specs.json
│   ├── zed2_/
│   ├── zedx_quickstart_interface_specs.json
│   │
│   ├── Mustard/
│   ├── Mac_and_cheese_0_1/
│   ├── soup_can/
│   └── dock/
│
├── models/
│   ├── foundationpose/
│   │   ├── refine_model.onnx
│   │   ├── score_model.onnx
│   │   ├── refine_trt_engine.plan
│   │   └── score_trt_engine.plan
│   │
│   └── synthetica_detr/
│       ├── sdetr_grasp.onnx
│       ├── sdetr_grasp.plan
│       └── .eula_accepted
│
└── isaac_ros_rtdetr/
```

---

# 25. Interface Spec

標準のQuickstart：

```text
quickstart_interface_specs.json
```

は，

```text
640 × 480
```

である。

一方，今回の実カメラ用に，

```text
nyokkey_interface_specs.json
```

を作成している。

解像度：

```text
1280 × 720
```

作成日は2026-09-23。

現在はroot所有になっているため，編集時には権限に注意する。

---

# 26. TensorRT Engine

FoundationPose用：

```text
models/foundationpose/
├── refine_model.onnx
├── score_model.onnx
├── refine_trt_engine.plan
└── score_trt_engine.plan
```

RT-DETR用：

```text
models/synthetica_detr/
├── sdetr_grasp.onnx
├── sdetr_grasp.plan
└── .eula_accepted
```

すでにTensorRT Engineの生成まで完了している。

---

# 27. FoundationPoseのTensorRT Shape

Refine：

```text
min:
1 × 160 × 160 × 6

opt:
1 × 160 × 160 × 6

max:
42 × 160 × 160 × 6
```

Score：

```text
min:
1 × 160 × 160 × 6

opt:
1 × 160 × 160 × 6

max:
252 × 160 × 160 × 6
```

したがって，

```text
Refine
max batch = 42

Score
max batch = 252
```

となっている。

---

# 28. Quickstart Bag

```text
quickstart.bag
```

に含まれる主なTopic：

```text
image_rect
camera_info_rect
depth
```

Interface spec：

```text
640 × 480
```

つまりQuickstartでは，

```text
image_rect
camera_info_rect
depth
```

をFoundationPose側の入力として使用する。

---

# 29. 現在の自作ドキュメント

```text
docs/pose_estimation.md
```

に今回のセットアップ手順を整理している。

現在は12節構成。

主な内容：

```text
1. 前提
2. Quickstart Asset取得
3. ONNXモデル取得
4. FoundationPoseパッケージ導入
5. TensorRT Engine生成
6. RT-DETR Asset取得
7. RT-DETR導入
8. Isaac ROS Examples導入
9. FoundationPose起動
10. ROS Bag再生
11. RViz2
12. 注意事項
```

---

# 30. FoundationPoseの実カメラ入力

今回使用する実カメラTopic：

| データ        | Topic                                           |
| ---------- | ----------------------------------------------- |
| RGB        | `/head_camera/color/image_raw`                  |
| CameraInfo | `/head_camera/color/camera_info`                |
| Depth      | `/head_camera/aligned_depth_to_color/image_raw` |

QuickstartとはTopic名が異なる。

```text
Quickstart
────────────────────────────
image_rect
camera_info_rect
depth


実カメラ
────────────────────────────
/head_camera/color/image_raw
/head_camera/color/camera_info
/head_camera/aligned_depth_to_color/image_raw
```

---

# 31. 現在確認されている未整合

## 31.1 TF Frame

RViz側のFixed Frame：

```text
tf_camera
```

FoundationPoseNodeのデフォルト：

```text
fp_object
```

となっている。

そのため，TFを表示する場合は，

```text
Camera Frame
    ↓
Object Frame
```

のTF関係が正しく構築されているか確認する必要がある。

---

# 32. 実カメラTopicのRemap

現在のCore LaunchはQuickstartを前提としており，

```text
image_rect
camera_info_rect
depth
```

を入力としている。

そのため，

```text
/head_camera/color/image_raw
/head_camera/color/camera_info
/head_camera/aligned_depth_to_color/image_raw
```

をそのまま接続できるとは限らない。

実カメラを使う場合は，

```text
専用remap
```

または

```text
専用Launch
```

を用意する必要がある。

---

# 33. RTX 3090について

現在のGPU：

```text
RTX 3090 × 2
```

は，Isaac ROS 4.6の公式検証対象から外れている可能性がある。

そのため，FoundationPoseのTensorRT Engineについては，

```text
既製Engineをそのまま使用
```

するのではなく，

```text
現在のGPU環境でONNX
      ↓
TensorRT
      ↓
.plan生成
```

としている。

これは現在の環境では重要なポイントである。

---

# 34. 未ビルドのパッケージ

現在build/installされているのは，

```text
isaac_ros_foundationpose
```

が中心である。

以下はまだビルドされていない。

```text
isaac_ros_centerpose
isaac_ros_dope
isaac_ros_pose_proc
```

今回の目的がFoundationPoseによる6DoF姿勢推定であるため，現時点では問題ない。

---

# 35. 現在の処理構成

現時点で想定している実環境の処理フロー：

```text
                   Head Camera
                       │
          ┌────────────┴────────────┐
          │                         │
         RGB                       Depth
          │                         │
          ▼                         ▼
/head_camera/color/image_raw   /head_camera/aligned_depth_to_color/image_raw
          │                         │
          └────────────┬────────────┘
                       │
                       ▼
                CameraInfo
                       │
                       ▼
                  RT-DETR
                       │
                       ▼
                2D Detection
                       │
                       ▼
                  Mask生成
                       │
                       ▼
              FoundationPose
                       │
              ┌────────┴────────┐
              │                 │
           Refine              Score
              │                 │
              └────────┬────────┘
                       ▼
                  6DoF Pose
                       │
                       ▼
                  TF / RViz
```

---

# 36. Pose EstimationとTracking

FoundationPoseは大きく2段階で考えると分かりやすい。

## 初期推定

```text
RGB
Depth
Mask
Mesh
   │
   ▼
FoundationPose
   │
   ├── Score
   └── Refine
   │
   ▼
初期6DoF Pose
```

## 継続追跡

```text
前フレームPose
      │
      ▼
   Tracking
      │
      ▼
    Refine
      │
      ▼
現在のPose
```

したがって，毎フレーム重い初期姿勢探索を行うのではなく，

```text
初期推定
   ↓
Tracking
   ↓
必要に応じて再推定
```

という構成になっている。

---

# 37. 今後確認すべきポイント

現在の環境では，次の順番で確認するとよい。

### ① Quickstartが正常動作することを確認

```text
quickstart.bag
    ↓
FoundationPose
    ↓
RViz
```

まず標準構成を完成させる。

---

### ② 実カメラTopicの確認

```bash
ros2 topic list | grep head_camera
```

以下が存在することを確認する。

```text
/head_camera/color/image_raw
/head_camera/color/camera_info
/head_camera/aligned_depth_to_color/image_raw
```

---

### ③ RGB / Depth同期・アライメント確認

特に，

```text
RGB
Depth
```

が同じ時刻・同じ画素位置で対応していることを確認する。

---

### ④ CameraInfo確認

```text
/head_camera/color/camera_info
```

の

```text
fx
fy
cx
cy
width
height
```

が実際のRGB画像と一致していることを確認する。

---

### ⑤ 実カメラ用Launchを作成

Quickstartの

```text
image_rect
camera_info_rect
depth
```

を，

```text
/head_camera/color/image_raw
/head_camera/color/camera_info
/head_camera/aligned_depth_to_color/image_raw
```

へ接続する。

---

### ⑥ Meshを実対象物へ変更

Quickstartの，

```text
Mustard/textured_simple.obj
```

から，実際に推定したい対象物のmeshへ変更する。

---

### ⑦ TFを整理

少なくとも，

```text
Camera Frame
    ↓
FoundationPose Object Frame
```

が正しく接続されるようにする。

---

# 38. 現在の到達点

現時点では，以下まで完了している。

```text
[完了]
✓ Isaac ROS 4.6環境構築
✓ ROS 2 Jazzy
✓ isaac_ros_pose_estimation release-4.6取得
✓ FoundationPose package導入
✓ FoundationPoseソース調査
✓ NGC Asset取得
✓ FoundationPose ONNX取得
✓ TensorRT Engine生成
✓ RT-DETR導入
✓ RT-DETR TensorRT Engine生成
✓ Quickstart用interface spec確認
✓ 実カメラ用1280×720 interface spec作成
✓ FoundationPoseセットアップ手順をdocsに整理
```

一方，実環境で残っている主要項目は，

```text
[未確認 / 未実装]
△ Quickstartの最終動作確認
△ 実カメラTopicへの接続
△ RGB/Depth同期確認
△ CameraInfo確認
△ 実対象物Meshへの変更
△ TF構成
△ 実カメラでの6DoF Pose確認
```

である。

---

# 39. 現在の構成を一枚でまとめると

```text
┌─────────────────────────────────────────────────────────────┐
│                    Host / RTX 3090 × 2                      │
│                                                             │
│  /home/<user>/isaac_ros_ws/                                 │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Docker: isaac-ros-4.6-base                            │  │
│  │                                                       │  │
│  │ ROS 2 Jazzy                                           │  │
│  │ Isaac ROS 4.6                                        │  │
│  │                                                       │  │
│  │ /workspaces/isaac_ros-dev                            │  │
│  │                                                       │  │
│  │  ├── isaac_ros_pose_estimation                       │  │
│  │  │      └── isaac_ros_foundationpose                 │  │
│  │  │                                                   │  │
│  │  ├── isaac_ros_assets                                │  │
│  │  │      ├── FoundationPose models                    │  │
│  │  │      ├── RT-DETR model                            │  │
│  │  │      └── Object meshes                            │  │
│  │  │                                                   │  │
│  │  └── build / install / log                           │  │
│  │                                                       │  │
│  │          RGB ──────────────┐                          │  │
│  │          Depth ────────────┤                          │  │
│  │          CameraInfo ───────┤                          │  │
│  │                            ▼                          │  │
│  │                         RT-DETR                       │  │
│  │                            │                          │  │
│  │                            ▼                          │  │
│  │                       Mask生成                       │  │
│  │                            │                          │  │
│  │                            ▼                          │  │
│  │                     FoundationPose                    │  │
│  │                       │          │                    │  │
│  │                    Refine       Score                 │  │
│  │                       └────┬─────┘                    │  │
│  │                            ▼                          │  │
│  │                         6DoF Pose                     │  │
│  │                            │                          │  │
│  │                            ▼                          │  │
│  │                       TF / RViz2                      │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 40. 重要な認識

今回の調査で特に重要なのは，FoundationPose単体がすべてを行っているわけではない点である。

実際には，

```text
                  ┌── RT-DETR
                  │
Camera ───────────┼── Mask生成
                  │
                  └── FoundationPose
                         │
                         ├── Score TensorRT
                         └── Refine TensorRT
                                  │
                                  ▼
                              6DoF Pose
```

という複数のIsaac ROS Componentを組み合わせたパイプラインになっている。

そのため，現在の実環境への移植では，**FoundationPose本体だけでなく，RT-DETR，入力Topic，CameraInfo，RGB-Depthアライメント，TFの5点を合わせて確認する必要がある**。

---

## 付録（2026-10-29）: RTX 5080 環境での再キャッチアップ

本書本文は RTX 3090 環境（`/home/<user>/...`）時点のスナップショットだが，2026-10-29 にホスト更改新後（RTX 5080 / Driver 580.126.09 / CUDA 13.2 / TensorRT 10.16.1）にキャッチアップした結果を付記する。再現手順は [setup](../setup/pose_estimation.md) 側へ反映済み。

### 実施内容

- `src/isaac_ros_pose_estimation` を release-4.6 で再クローンし、ソースビルド（混合構成: RT-DETR と Isaac ROS コアは apt バイナリ）。
- NGC アセット・ONNX を再取得し、trtexec で `.plan` を再生成（score max batch 252 / refine max batch 42、いずれも PASSED）。
- quickstart bag でパイプライン全体を再検証。

### ハマった点（本文の認識に上書きするもの）

1. **CUDA アーキテクチャ不整合でクラッシュ**
   - `colcon build` に `-DCMAKE_CUDA_ARCHITECTURES=120` を渡さない限り、FoundationPose の CUDA カーネルは sm_75 でビルドされる（CMakeLists は arch 未指定）。
   - RTX 5080（sm_120）では `depth_to_xyz_map` で `cudaErrorUnsupportedPtxVersion` が発生。`cuobjdump --list-elf libfoundationpose_pipeline.so` に `sm_120.cubin` が出れば解決。
2. **推論速度はボトルネックではなかった**
   - 5080 実測: score @252 ≈ 252 ms, refine @42 ≈ 46 ms。1 フレーム（252 poses, refine 3 iter）≈ 1.9 s → 出力 ≈ 0.5 Hz。
   - 本文 7 章あたりの「GPU 負荷が重い」という懸念は、5080 では成立しない。
3. **quickstart の出力トピックは `/output`**
   - launch フラグメントが FoundationPoseNode の出力を `/output` に remap している。`/pose_estimation/output` を期待して探すと「出ていない」と誤認する。
4. **`tensor_pub` / `tensor_sub` の向き**
   - `<ns>/tensor_pub` = FP → TRT のリクエスト、`<ns>/tensor_sub` = TRT → FP の結果。命名とデータフローが逆に見える罠。
5. **`Processing timeout, releasing gate` は常時ビジーの副産物**
   - processFrame が syncCallback ごとに起動し duty cycle ほぼ 100% だと、5 s ウォッチドッグが周期性に警告を出す。処理自体は完走しており、この警告だけで停止はしない。
6. **運用メモ**
   - `docker exec` 経由の `pkill -f <launch名>` は exec 自身にマッチして自爆する（exit 143）。PID 指定 kill または `[b]racket` 回避を使う。
   - gdb attach はホストの `ptrace_scope=1` で不可。切り分けはソースへの一時ログ挿入が現実的。

### 到達点（2026-10-29 時点）

- quickstart: `/output` に Detection3DArray が 0.5 Hz、Mustard の姿勢（例: xyz ≈ [-0.45, 0.12, 0.80]）が確認できた。
- 自作 launch `head_camera_foundationpose.launch.py`: 全 15 ComposableNode が起動し、`/head_camera/color/image_raw` 38 Hz・`aligned_depth` 35 Hz で接続確認済み。`/detections_output` は流れるが `detections: []`（カメラ前に被写体がないため）。被写体を置いた状態での最終検証は未実施。
