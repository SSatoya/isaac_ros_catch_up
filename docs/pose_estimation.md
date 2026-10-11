# Isaac ROS FoundationPose セットアップ手順

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
```bash
cd ${ISAAC_ROS_WS}/ && \
   colcon build --symlink-install --packages-up-to isaac_ros_foundationpose --base-paths ${ISAAC_ROS_WS}/src/isaac_ros_pose_estimation/isaac_ros_foundationpose
```

- ROSワークスペースのソースコード：
```bash
source install/setup.bash
```

</details>

---

# 5. TensorRT Engine の作成

FoundationPose は ONNX モデルを直接使用するのではなく，TensorRT Engine（`.plan`）を使用する．

## 5.1 Refine Model

### コンテナ内で実行

```bash
/usr/src/tensorrt/bin/trtexec \
  --onnx=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/refine_model.onnx \
  --saveEngine=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/refine_trt_engine.plan \
  --minShapes=input1:1x160x160x6,input2:1x160x160x6 \
  --optShapes=input1:1x160x160x6,input2:1x160x160x6 \
  --maxShapes=input1:42x160x160x6,input2:42x160x160x6
```

## 5.2 Score Model

```bash
/usr/src/tensorrt/bin/trtexec \
  --onnx=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/score_model.onnx \
  --saveEngine=${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/score_trt_engine.plan \
  --minShapes=input1:1x160x160x6,input2:1x160x160x6 \
  --optShapes=input1:1x160x160x6,input2:1x160x160x6 \
  --maxShapes=input1:252x160x160x6,input2:252x160x160x6
```

### 作成後

```text
${ISAAC_ROS_WS}/isaac_ros_assets/models/foundationpose/
├── refine_model.onnx
├── refine_trt_engine.plan
├── score_model.onnx
└── score_trt_engine.plan
```

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

# 13. カスタム
```bash
cd /workspaces/isaac_ros-dev
source install/setup.bash
ros2 launch src/custom_pose_bringup/launch/head_camera_foundationpose.launch.py
```