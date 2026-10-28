# AGENT.md

このリポジトリで AI エージェントが作業するための前提・規約メモ。
人間向けの全体像は `README.md`、詳細手順は `docs/setup/pose_estimation.md`、調査記録は `docs/catch-up/pose_estimation.md`。

## プロジェクト概要

Isaac ROS 4.6（ROS 2 Jazzy）上の FoundationPose + RT-DETR による姿勢推定ワークスペース。
実カメラトピック（`/head_camera/*`）を FoundationPose に流す自作 launch が最終成果物。

- 最終対象 launch: `isaac_ros-dev/src/custom_pose_bringup/launch/head_camera_foundationpose.launch.py`
- 出力: `/pose_estimation/output`（`vision_msgs/Detection3DArray`、約 2.9 Hz）

## 実行環境（重要: ホストで直接やらない）

- 作業は Docker コンテナ **内**で行う。イメージ名・コンテナ名は `.env`（`IMAGE_NAME` / `CONTAINER_NAME`）
- ホスト `${ISAAC_ROS_WS}` = リポジトリ内の `isaac_ros-dev/` ⇄ コンテナ内 `/workspaces/isaac_ros-dev`（バインドマウント。コンテナ内パスで統一すること）
- `docker exec` の非対話 shell では ROS 環境が引継ぎされないため、毎回:

```bash
source /opt/ros/jazzy/setup.bash
source /workspaces/isaac_ros-dev/install/setup.bash
export ROS_DOMAIN_ID=<.envの値>
export FASTRTPS_DEFAULT_PROFILES_FILE=/workspaces/dds_cfg/fastdds.xml
```

## ビルド規約

- ソースビルドは **必ず** `--cmake-args -DCMAKE_CUDA_ARCHITECTURES=120` を付ける（RTX 5080 / sm_120。既定の sm_75 だと `cudaErrorUnsupportedPtxVersion` でクラッシュ）
- 確認: `cuobjdump --list-elf install/isaac_ros_foundationpose/lib/libfoundationpose_pipeline.so` に `sm_120.cubin`
- 再ビルド対象は通常 `isaac_ros_foundationpose` と `custom_pose_bringup` のみ

```bash
cd /workspaces/isaac_ros-dev
colcon build --packages-select isaac_ros_foundationpose custom_pose_bringup \
  --cmake-args -DCMAKE_CUDA_ARCHITECTURES=120
```

## Git 管理ポリシー（公開リポジトリ）

- **個人固有の情報をコミットしない**（ユーザ名入り絶対パス、メール等。履歴ごと scrub 済みなので復活させない）
- 管理しないもの: `src/isaac_ros*`（公式クローン）、`isaac_ros_assets/`、`build/ install/ log/`、`.env`
- **公式パッケージ (`src/isaac_ros_pose_estimation` など) への変更は Git に入らない。** 変更を加えたら必ず `docs/setup/pose_estimation.md` にパッチ手順として記載すること（例: 5.3 仮説グリッドのパラメータ化）
- コミットメッセージは日本語

## 重要な結合関係（壊しやすい）

FoundationPose の「仮説数」は以下の 4 箇所が連動している。1 箇所変えたら他も全部合わせること。

| 場所 | 現値 | 関係式 |
| --- | --- | --- |
| `foundationpose_model_config.yaml` `grid_n_views` × `grid_inplane_step_deg` | 40 × 120° | グリッド生成数 = icosphere頂点(40view→42) × 360/step = 126 |
| 同 `max_hypothesis` | 126 | ≧ グリッド生成数（超えると全フレーム `Sampling produced 0 poses`） |
| launch `score_trt` `max_batch_size` / score engine maxShapes | 126 | ≧ `max_hypothesis` |
| launch `refine_trt` `max_batch_size` / refine engine maxShapes | 21 | ≧ `max_hypothesis / 6`（内部で 6 バッチ分割。`max_hypothesis` は 6 の倍数にすること） |

- TensorRT エンジンは **FP16 + 実バッチ shapes** でビルド（手順は setup 5 章）。FP32 に戻すと VRAM +4 GiB・速度 1/5
- `enable_fp16=True`（TensorRTNode）は FP32 ビルドエンジンでは無効。fp16 はエンジンビルド側で効かせる

## はまりどころ（実測済み・省略禁止事項）

- `docker exec` 越しの `pkill -f "<launch名>"` は exec 自身にマッチして自爆（exit 143）。`pgrep -f "[l]aunch名]"` の bracket 回避か PID 直接指定
- TensorRTNode のトピックは `tensor_pub` = リクエスト（FP→TRT）、`tensor_sub` = 結果（TRT→FP）。命名と逆
- quickstart 公式 launch は出力を `/output` に remap する（自作 launch は `/pose_estimation/output`）
- `Processing timeout, releasing gate` は処理がほぼ常時ビジーなだけ。処理自体は完走している
- 検出があっても姿勢が出ない → mask・depth の妥当性、`Sampling produced 0 poses` のグリッド結合を疑う

## 検証コマンド（コンテナ内）

```bash
# 姿勢出力レートと内容
ros2 topic hz /pose_estimation/output
ros2 topic echo /pose_estimation/output --once --field detections

# 入力・検出
ros2 topic hz /head_camera/color/image_raw
ros2 topic echo /detections_output --once --field detections   # detections: [] なら被写体がないだけ

# VRAM（プロセス別。GPUには他プロセス（Isaac Sim等）も同居する点に注意）
nvidia-smi --query-compute-apps=pid,used_memory --format=csv
```

VRAM 内訳の切り分けは、FoundationPose ノードが起動時・初フレーム後に `cudaMemGetInfo` プローブを 2 行ログ出力する（`[FoundationPoseNode][VRAM]`）。
