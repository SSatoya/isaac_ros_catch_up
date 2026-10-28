# Isaac ROS FoundationPose セットアップ手順

> **状態**: Quickstart は姿勢推定出力まで動作確認済み（2026-10 / RTX 5080）・自作 launch（ch.13）もノード起動・接続確認済み
> **対象**: Isaac ROS 4.6 / ROS 2 Jazzy / イメージ `isaac-ros-4.6-base`（Ubuntu 24.04）
> **GPU**: RTX 5080（sm_120）。ソースビルド時は ch.4 のとおり CUDA アーキテクチャ指定が必須
> **関連**: 環境・構成の全体像は [ルート README](../README.md)、仕組みの調査記録は [catch-up](../catch-up/pose_estimation.md)

**この文書の読み方**

* 各コマンドブロックに **コンテナ内 / コンテナ外** を明記している。NGC からのアセット・モデル取得は **コンテナ外**、`apt` / `colcon` / 起動は **コンテナ内** で実行する。
* `${ISAAC_ROS_WS}` はホスト側のワークスペースパス。コンテナ内では `/workspaces/isaac_ros-dev` に対応する。
* 章の役割は次のとおり。

| 章 | 内容 |
| --- | --- |
| 1 | 前提（バージョン・使うモデル・入出力トピック） |
| 2〜3 | FoundationPose のアセットと ONNX モデルの取得 |
| 4 | FoundationPose パッケージのインストール（バイナリ / ソースビルド） |
| 5 | TensorRT Engine（`.plan`）の作成 |
| 6〜8 | 前段の RT-DETR と Isaac ROS Examples の準備 |
| 9〜11 | Quickstart の起動・bag 再生・RViz2 での確認 |
| 12 | 実環境に移すときに効く注意点 |
| 13 | 実カメラ入力用の自作 launch（`custom_pose_bringup`） |

## 1. 前提

* Isaac ROS **FoundationPose**
* ROS 2 **Jazzy**
* Isaac ROS **4.6 系**
* FoundationPose の推論モデルとして以下を使用する．

  * `refine_model.onnx`
  * `score_model.onnx`
* TensorRT Engine（`.plan`）を作成して使用する．
* カメラ入力は以下を使用する．

| データ        | Topic                                           |
| ---------- | ----------------------------------------------- |
| RGB画像      | `/head_camera/color/image_raw`                  |
| CameraInfo | `/head_camera/color/camera_info`                |
| Depth画像    | `/head_camera/aligned_depth_to_color/image_raw` |

---

# 2. FoundationPose アセットの取得

## 2.1 コンテナ外で実行

必要なパッケージをインストールする．

```bash
sudo apt update
sudo apt-get install -y curl jq tar
```

---

## 2.2 FoundationPose Quickstart Asset の取得

```bash
NGC_ORG="nvidia"
NGC_TEAM="isaac"
PACKAGE_NAME="isaac_ros_foundationpose"
NGC_RESOURCE="isaac_ros_foundationpose_assets"
NGC_FILENAME="quickstart.tar.gz"

MAJOR_VERSION=4
MINOR_VERSION=6

VERSION_REQ_URL="https://api.ngc.nvidia.com/v2/resources/$NGC_ORG/$NGC_TEAM/$NGC_RESOURCE/versions"

AVAILABLE_VERSIONS=$(curl -s \
    -H "Accept: application/json" "$VERSION_REQ_URL")

LATEST_VERSION_ID=$(echo $AVAILABLE_VERSIONS | jq -r "
    .recipeVersions[]
    | .versionId as \$v
    | \$v | select(test(\"^\\\\d+\\\\.\\\\d+\\\\.\\\\d+$\"))
    | split(\".\") |
      {major: .[0]|tonumber, minor: .[1]|tonumber, patch: .[2]|tonumber}
    | select(.major == $MAJOR_VERSION and .minor <= $MINOR_VERSION)
    | \$v
    " | sort -V | tail -n 1
)

if [ -z "$LATEST_VERSION_ID" ]; then
    echo "No corresponding version found for Isaac ROS $MAJOR_VERSION.$MINOR_VERSION"
    echo "Found versions:"
    echo $AVAILABLE_VERSIONS | jq -r '.recipeVersions[].versionId'
else
    mkdir -p ${ISAAC_ROS_WS}/isaac_ros_assets && \
    FILE_REQ_URL="https://api.ngc.nvidia.com/v2/resources/$NGC_ORG/$NGC_TEAM/$NGC_RESOURCE/\
versions/$LATEST_VERSION_ID/files/$NGC_FILENAME" && \
    curl -LO --request GET "${FILE_REQ_URL}" && \
    tar -xf ${NGC_FILENAME} -C ${ISAAC_ROS_WS}/isaac_ros_assets && \
    rm ${NGC_FILENAME}
fi
```

### 取得される主なファイル

```text
${ISAAC_ROS_WS}/isaac_ros_assets/
└── isaac_ros_foundationpose/
    ├── quickstart_interface_specs.json
    ├── quickstart.bag
    └── Mustard/
        └── textured_simple.obj
```

---

# 3. FoundationPose ONNXモデルの取得

## 3.1 コンテナ外で実行

モデル保存先を作成する．

```bash
mkdir -p ${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose
cd ${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose
```

### Refine Model

```bash
wget \
  'https://api.ngc.nvidia.com/v2/models/nvidia/isaac/foundationpose/versions/1.0.1_onnx/files/refine_model.onnx' \
  -O refine_model.onnx
```

### Score Model

```bash
wget \
  'https://api.ngc.nvidia.com/v2/models/nvidia/isaac/foundationpose/versions/1.0.1_onnx/files/score_model.onnx' \
  -O score_model.onnx
```

最終的に以下の2ファイルが存在する．

```text
${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/
├── refine_model.onnx
└── score_model.onnx
```

---

# 4. FoundationPose ROSパッケージのインストール
<details><summary> Option1: バイナリパッケージ</summary>

## 4.1 コンテナ内で実行

```bash
sudo apt-get update
```

```bash
sudo apt-get install -y ros-jazzy-isaac-ros-foundationpose
```

> `apt` によるインストールのため，環境によっては時間がかかる．

</details>

<details open><summary> Option2: ソースコードからビルド</summary>

## 4.1 コンテナ内で実行
- Git LFSをインストール
```bash
sudo apt-get install -y git-lfs && git lfs install
```

- リポジトリをクローン
```bash
cd ${ISAAC_ROS_WS}/src && \
   git clone -b release-4.6 https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_pose_estimation.git isaac_ros_pose_estimation
```

- Isaac ROS環境をアクティブ化
```bash
isaac-ros activate
```

- rosdepパッケージの依存関係をインストール
```bash
sudo apt-get update
rosdep update && rosdep install --from-paths ${ISAAC_ROS_WS}/src/isaac_ros_pose_estimation/isaac_ros_foundationpose --ignore-src -y
```

- ソースコードからパッケージをビルド

> **重要**: `CMakeLists.txt` が CUDA アーキテクチャを指定していないため、この指定がないとデフォルトの **sm_75** でビルドされる。RTX 5080（sm_120）では sm_75 の SASS は実行できず、`depth_to_xyz_map` で `cudaErrorUnsupportedPtxVersion` に遭遇する（2026-10 実測）。GPU に合わせて `-DCMAKE_CUDA_ARCHITECTURES` を渡すこと。

```bash
cd ${ISAAC_ROS_WS}/ && \
   colcon build --symlink-install --packages-up-to isaac_ros_foundationpose --base-paths ${ISAAC_ROS_WS}/src/isaac_ros_pose_estimation/isaac_ros_foundationpose \
   --cmake-args -DCMAKE_CUDA_ARCHITECTURES=120
```

ビルド後に SASS が埋め込まれている確認できる:

```bash
cuobjdump --list-elf install/isaac_ros_foundationpose/lib/libfoundationpose_pipeline.so
# → libfoundationpose_pipeline.1.sm_120.cubin が並んでいれば OK
```

- ROSワークスペースのソースコード：
```bash
source install/setup.bash
```

</details>

---

# 5. TensorRT Engine の作成

FoundationPose は ONNX モデルを直接使用するのではなく，TensorRT Engine（`.plan`）を使用する．

> **重要: `--fp16` を必ず付ける**
> FP32ビルドだと score の実行コンテキストだけで約2.2 GiBのVRAMを確保し，推論も遅い（RTX 5080実測: score@batch252 FP32 ≈ 252 ms）．
> NVIDIA公式のFoundationPoseエンジンもFP16ビルドが標準であり，精度への実用上の問題は確認されていない．
>
> **shapes と `max_hypothesis` の関係**:
> `config/foundationpose_model_config.yaml` の `max_hypothesis`（既定 126）に対し，
> scoreエンジンのバッチ上限 ≧ `max_hypothesis`，refineエンジンのバッチ上限 ≧ `max_hypothesis / 6`
> （内部で6バッチへ分割されるため）である必要がある．
> 変更時はエンジンの再ビルドとlaunch側の `max_batch_size` を併せて変更すること．
> （`max_hypothesis` は6の倍数にすること．内部で6の倍数へpadされるため）
>
> なお，初期仮説はグリッド総当たり（icosphere頂点数 × 360°/`grid_inplane_step_deg`）で生成され，
> その数が `max_hypothesis` を超えると姿勢推定は全フレーム失敗する（`Sampling produced 0 poses`）．
> 既定は 42view × 60deg step = 252仮説．本設定では 42view × 120deg step = 126仮説へ削減している．
> `grid_n_views` / `grid_inplane_step_deg` は同一yamlで調整可能（ソース改造済み）．

## 5.1 Refine Model

### コンテナ内で実行

```bash
/usr/src/tensorrt/bin/trtexec \
  --onnx=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/refine_model.onnx \
  --saveEngine=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/refine_trt_engine.plan \
  --fp16 \
  --minShapes=input1:1x160x160x6,input2:1x160x160x6 \
  --optShapes=input1:21x160x160x6,input2:21x160x160x6 \
  --maxShapes=input1:21x160x160x6,input2:21x160x160x6
```

RTX 5080実測（trtexec, FP16, batch21）: GPU compute ≈ 6 ms（FP32 batch42で約46 ms）．

## 5.2 Score Model

```bash
/usr/src/tensorrt/bin/trtexec \
  --onnx=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/score_model.onnx \
  --saveEngine=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/score_trt_engine.plan \
  --fp16 \
  --minShapes=input1:1x160x160x6,input2:1x160x160x6 \
  --optShapes=input1:126x160x160x6,input2:126x160x160x6 \
  --maxShapes=input1:126x160x160x6,input2:126x160x160x6
```

RTX 5080実測（trtexec, FP16, batch126）: GPU compute ≈ 29 ms（FP32 batch252で約252 ms）．

### 作成後

```text
${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/
├── refine_model.onnx
├── refine_trt_engine.plan
├── score_model.onnx
└── score_trt_engine.plan
```

## 5.3 仮説グリッド密度のパラメータ化（公式パッケージへのパッチ）

初期仮説の生成数は `makeRotationGrid()` の引数がハードコード（42view × 60° = 252）で，
この数が `max_hypothesis` を超えると sampler が空を返す．仮説数を減らすにはここも連動させる必要がある．
`src/isaac_ros_pose_estimation`（Git管理外）へ以下の小さなパッチを当てる．

1. `include/isaac_ros_foundationpose/foundationpose_impl/pose_sampler.hpp` — `PoseSamplerParams` に追加:

```cpp
unsigned int grid_n_views{40};
double grid_inplane_step_deg{60.0};
```

2. `src/foundationpose_impl/pose_sampler.cpp` — `sample()` 内:

```cpp
auto ob_in_cams = makeRotationGrid(
  all_symmetry_axes, params_.fixed_axis_angles,
  params_.grid_n_views, params_.grid_inplane_step_deg);
```

3. `src/foundationpose_node.cpp` — yaml パース部（`max_hypothesis` の直後）で
   `grid_n_views` / `grid_inplane_step_deg`（任意キー，既定 40 / 60.0）を読み，
   `sampler_params` へ代入する．ノードヘッダにメンバ追加も忘れずに．

設定値（`config/foundationpose_model_config.yaml`）: `grid_n_views: 40`，
`grid_inplane_step_deg: 120.0` → 42 × 3 = 126 仮説（`max_hypothesis: 126` と一致）．

---

# 6. RT-DETR の準備

FoundationPose のQuickstartでは，物体検出にRT-DETRを使用する．

## 6.1 RT-DETR Asset の取得

### コンテナ外で実行

```bash
sudo apt-get install -y curl jq tar
```

```bash
NGC_ORG="nvidia"
NGC_TEAM="isaac"
PACKAGE_NAME="isaac_ros_rtdetr"
NGC_RESOURCE="isaac_ros_rtdetr_assets"
NGC_FILENAME="quickstart.tar.gz"

MAJOR_VERSION=4
MINOR_VERSION=6

VERSION_REQ_URL="https://api.ngc.nvidia.com/v2/resources/$NGC_ORG/$NGC_TEAM/$NGC_RESOURCE/versions"

AVAILABLE_VERSIONS=$(curl -s \
    -H "Accept: application/json" "$VERSION_REQ_URL")

LATEST_VERSION_ID=$(echo $AVAILABLE_VERSIONS | jq -r "
    .recipeVersions[]
    | .versionId as \$v
    | \$v | select(test(\"^\\\\d+\\\\.\\\\d+\\\\.\\\\d+$\"))
    | split(\".\") |
      {major: .[0]|tonumber, minor: .[1]|tonumber, patch: .[2]|tonumber}
    | select(.major == $MAJOR_VERSION and .minor <= $MINOR_VERSION)
    | \$v
    " | sort -V | tail -n 1
)

if [ -z "$LATEST_VERSION_ID" ]; then
    echo "No corresponding version found for Isaac ROS $MAJOR_VERSION.$MINOR_VERSION"
    echo "Found versions:"
    echo $AVAILABLE_VERSIONS | jq -r '.recipeVersions[].versionId'
else
    mkdir -p ${ISAAC_ROS_WS}/isaac_ros_assets && \
    FILE_REQ_URL="https://api.ngc.nvidia.com/v2/resources/$NGC_ORG/$NGC_TEAM/$NGC_RESOURCE/\
versions/$LATEST_VERSION_ID/files/$NGC_FILENAME" && \
    curl -LO --request GET "${FILE_REQ_URL}" && \
    tar -xf ${NGC_FILENAME} -C ${ISAAC_ROS_WS}/isaac_ros_assets && \
    rm ${NGC_FILENAME}
fi
```

---

# 7. RT-DETR パッケージ・モデルのインストール

## 7.1 コンテナ内

まずIsaac ROS環境を有効化する．

```bash
isaac-ros activate
```

### RT-DETRパッケージ

```bash
sudo apt-get update
```

```bash
sudo apt-get install -y ros-jazzy-isaac-ros-rtdetr
```

```bash
sudo apt-get install -y ros-jazzy-isaac-ros-rtdetr-models-install
```

### RT-DETRモデル

```bash
sudo apt-get update
```

```bash
ros2 run isaac_ros_rtdetr_models_install install_rtdetr_models.sh --eula
```

数分待つ．

以下のようにTensorRTのテストが成功すればよい．

```text
PASSED TensorRT.trtexec
```

---

# 8. Isaac ROS Examples のインストール

## 8.1 コンテナ内

```bash
sudo apt-get update
```

```bash
sudo apt-get install -y ros-jazzy-isaac-ros-examples
```

---

# 9. FoundationPose Quickstart の起動

## 9.1 FoundationPoseノードを起動

```bash
ros2 launch isaac_ros_examples isaac_ros_examples.launch.py \
    launch_fragments:=foundationpose \
    interface_specs_file:=${ISAAC_ROS_WS}/isaac_ros_assets/isaac_ros_foundationpose/quickstart_interface_specs.json \
    mesh_file_path:=${ISAAC_ROS_WS}/isaac_ros_assets/isaac_ros_foundationpose/Mustard/textured_simple.obj \
    score_engine_file_path:=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/score_trt_engine.plan \
    refine_engine_file_path:=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/refine_trt_engine.plan \
    rt_detr_engine_file_path:=${ISAAC_ROS_WS}/isaac_ros_assets/models/synthetica_detr/sdetr_grasp.plan
```

このコマンドでは，Quickstart用のMustardモデルとTensorRT Engineを使用する．

---

# 10. ROS Bag の再生

別ターミナルで実行する．

## 10.1 コンテナ内

```bash
isaac-ros activate
```

```bash
ros2 bag play -l \
  ${ISAAC_ROS_WS}/isaac_ros_assets/isaac_ros_foundationpose/quickstart.bag/
```

`-l` はループ再生を意味する．

---

# 11. RViz2で結果を確認

## 11.1 RViz2のインストール

```bash
isaac-ros activate
```

```bash
sudo apt-get install -y ros-jazzy-rviz2 ros-jazzy-vision-msgs-rviz-plugins
```

```bash
source /opt/ros/jazzy/setup.bash
```

## 11.2 FoundationPose用RViz設定で起動

```bash
rviz2 -d \
  $(ros2 pkg prefix isaac_ros_foundationpose --share)/rviz/foundationpose.rviz
```

これでQuickstartのRGB画像，検出結果，FoundationPoseによる6DoF姿勢推定結果などを確認できる．

---

# 12. 重要な注意点

### RGBとDepthの対応

FoundationPoseではRGB画像とDepth画像が同一座標系で対応している必要がある．

今回使用するDepthは，

```text
/head_camera/aligned_depth_to_color/image_raw
```

なので，**DepthがRGB座標系にアライメントされていること**が重要である．

### CameraInfo

```text
/head_camera/color/camera_info
```

の内部パラメータが，実際に入力するRGB画像の解像度・カメラモデルと一致している必要がある．

### TensorRT Engine

`.plan` ファイルはTensorRTの環境に依存するため，別GPU・別TensorRT環境で作成したEngineをそのまま使用できない場合がある．

そのため，実際にFoundationPoseを動かすGPU環境でEngineを生成する．

### CUDAアーキテクチャ（2026-10 / RTX 5080 で再現）

ソースビルド時に `-DCMAKE_CUDA_ARCHITECTURES=120` を忘れると sm_75 の cubin のみが埋め込まれ，実行時に

```text
cudaErrorUnsupportedPtxVersion  (depth_to_xyz_map 内)
```

で落ちる。`cuobjdump --list-elf install/.../libfoundationpose_pipeline.so` で即確認できる（ch.4 参照）。

### 新環境でのセットアップでハマった点（2026-10, RTX 5080）

- ベースイメージ `isaac-ros-4.6-base` には CUDA Toolkit / TensorRT が入っていない。`rosdep install` が `nvidia-cuda-toolkit` 系と TensorRT を apt で入れてくれる（CUDA 13.2 / TensorRT 10.16 が入った）。
- NGC からのアセット取得（ch.2 / ch.6）で EULA 同意プロンプトは `yes |` をパイプして流す（対話 TTY がない exec では止まる）。
- root でクローンした `src/isaac_ros_pose_estimation` はホストユーザーに `chown -R 1001:1001` しておかないと編集不可。
- `custom_pose_bringup` の `CMakeLists.txt` に存在しない `config` ディレクトリの `install(DIRECTORY ...)` があり、ビルドが通らなかった（削除して解消）。
- `docker exec` 越しの `pkill -f "<launch名>"` は **exec 自身の cmdline にもマッチして自爆（exit 143）する**。`pgrep -f "[l]aunch名]"` の bracket 回避か、PID を直接指定して kill する。
- TensorRTNode のトピック名は直感と逆で、`<ns>/tensor_pub` = **リクエスト**（FP → TRT）、`<ns>/tensor_sub` = **結果**（TRT → FP）。
- quickstart の launch は FoundationPose の出力を `/pose_estimation/output` ではなく **`/output`** に remap している。トピック確認時は注意（自作 launch は `/pose_estimation/output` に remap 済み）。
- `/detections_output` が流れていても `detections: []` なら、RT-DETR が物体を見ていない（カメラ前に被写体がない）だけ。姿勢出力が来ないときはまずこれを疑う。
- RTX 5080 上の実測（trtexec）: score @batch252 ≈ 252 ms、refine @batch42 ≈ 46 ms。1 フレーム（252 poses・refine 3 回）で約 1.9 s → 約 0.5 Hz。`Processing timeout, releasing gate`（5 s ウォッチドッグ）は処理がほぼ常時ビジーだと周期に出るが、処理自体は完走している。
- **VRAM 削減・高速化（2026-10-29 実施）**: エンジンを `--fp16` + 実バッチに合わせた shapes で再ビルド（ch.5）、`max_hypothesis` 252 → 126（グリッドも `grid_inplane_step_deg: 120` で連動削減。`grid_n_views` / `grid_inplane_step_deg` は sampler を改造して yaml 化済み）、`refine_iterations` 3 → 2、TensorRTNode の `memory_pool_num_blocks` を実需サイズへ縮小。効果（RTX 5080、Isaac Sim 同居下）: パイプラインプロセス 10338 → **6368 MiB**、姿勢出力 0.52 → **約 2.9 Hz**、TRTコンテキスト 3605 → 827 MiB（score 2215→369、refine 1034→164）。
- `max_hypothesis` を下げても**初期仮説グリッド数は減らない**（既定 42view × 60deg step = 252 固定）。グリッド数 > `max_hypothesis` だと sampler が即 return して全フレーム `Sampling produced 0 poses` になる。必ず `grid_n_views` / `grid_inplane_step_deg` と一緒に調整する（生成数 = 頂点数 × 360/step ≦ `max_hypothesis`）。
- 円筒対称の物体（Mustard 等）は `symmetry_axes` 未指定だと軸周り180°反転の姿勢がフレームごとに切り替わることがある。位置は安定しており、見た目の揺れは物体の対称性が原因。

# 13. 実カメラ入力（custom_pose_bringup）

Quickstart の bag ではなく，実カメラの Topic をそのまま流し込むための自作パッケージが
`isaac_ros-dev/src/custom_pose_bringup/` である．

## 13.1 ビルド（コンテナ内）

```bash
cd ${ISAAC_ROS_WS}
colcon build --symlink-install --packages-select custom_pose_bringup
source install/setup.bash
```

## 13.2 起動（コンテナ内）

```bash
ros2 launch custom_pose_bringup head_camera_foundationpose.launch.py
```

パッケージとして認識されない場合は，パス指定で同じ launch を実行できる．

```bash
ros2 launch src/custom_pose_bringup/launch/head_camera_foundationpose.launch.py
```

## 13.3 Launch Argument

| 引数 | 既定値 | 内容 |
| --- | --- | --- |
| `mesh_file_path` | `.../isaac_ros_assets/isaac_ros_foundationpose/Mustard/textured_simple.obj` | FoundationPose が使う 3D メッシュ．実対象物に差し替える |
| `refine_engine_file_path` | `.../isaac_ros_assets/models/foundationpose/refine_trt_engine.plan` | Refine ネットワークの TensorRT Engine |
| `score_engine_file_path` | `.../isaac_ros_assets/models/foundationpose/score_trt_engine.plan` | Score ネットワークの TensorRT Engine |
| `rt_detr_engine_file_path` | `.../isaac_ros_assets/models/synthetica_detr/sdetr_grasp.plan` | RT-DETR の TensorRT Engine |

指定方法（`:=` で上書き）:

```bash
ros2 launch custom_pose_bringup head_camera_foundationpose.launch.py \
    mesh_file_path:=/workspaces/isaac_ros-dev/isaac_ros_assets/<object>/model.obj
```

## 13.4 入出力 Topic

入力（実カメラ側が publish していること）:

| 役割 | トピック |
| --- | --- |
| RGB | `/head_camera/color/image_raw` |
| CameraInfo | `/head_camera/color/camera_info` |
| Depth（32FC1，color にアライメント済み） | `/head_camera/aligned_depth_to_color/image_raw` |

出力:

| 役割 | トピック |
| --- | --- |
| 6DoF 姿勢 | `/pose_estimation/output` |

全 ComposableNode は `component_container_mt` 1 つの上で動作する．

## 13.5 動作確認（別ターミナル）

```bash
isaac-ros activate
ros2 topic list | grep pose_estimation
ros2 topic echo /pose_estimation/output --once
```

## 13.6 現時点で未整理な点

* TF: RViz の Fixed Frame `tf_camera` と FoundationPose の object frame（既定 `fp_object`）の関係がまだ張られていない
* CameraInfo の解像度と実画像（1280×720）の一致確認が未了
* メッシュは Quickstart の Mustard のまま（実対象物に差し替えていない）

構成・調査の詳細は [catch-up 記録](../catch-up/pose_estimation.md) を参照．
