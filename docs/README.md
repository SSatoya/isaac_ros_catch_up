# docs — キャッチアップ文書の索引

このディレクトリには、Isaac ROS のキャッチアップで得た **手順（setup）** と **調査結果（catch-up）** を保存します。

初めて読む場合は、まずルートの [README.md](../README.md) を読んで全体像（環境・構成・起動方法）を掴み、その後に関心のあるテーマの文書に入るのがおすすめです。

---

## 1. 文書の種別

| 種別 | 書く内容 | 場所 | 雛形 |
| --- | --- | --- | --- |
| **setup（手順書）** | コピペすれば同じ環境を再構築・再実行できる手順 | `docs/setup/<theme>.md` | [`_templates/setup.md`](./_templates/setup.md) |
| **catch-up（調査記録）** | 構成・仕組み・はまった箇所など「なぜそうなるか」の記録（書いた時点のスナップショット） | `docs/catch-up/<theme>.md` | [`_templates/catch-up.md`](./_templates/catch-up.md) |

- **setup** は「壊れたら直す」運用文書です。コマンドが変わったら本文も更新します。
- **catch-up** は「調べた時点の認識を残す」文書です。後から書き換えず、冒頭の時点情報を更新します。
- 1 テーマにつき基本 2 文書（setup + catch-up）。補足は同じテーマ名で `docs/catch-up/<theme>_<topic>.md` のように増やします。
- **必ず読まなくてもよい部分**（エラー対処表・診断手順・完了済み項目・ディレクトリツリーなど）は
  `<details><summary> ... </summary> ... </details>` で折り畳む。手順の本体（フォアパス）は開いたままにする。

---

## 2. テーマ一覧

| テーマ | 対象パッケージ | 手順書 | 調査記録 | 状態（2026-10 時点） |
| --- | --- | --- | --- | --- |
| `pose_estimation` | `isaac_ros_foundationpose`<br>`isaac_ros_rtdetr` | [setup](./setup/pose_estimation.md) | [catch-up](./catch-up/pose_estimation.md) | Quickstart は動作確認済み。実カメラ（`/head_camera/*`）入力の bringup は調整中 |
| `teleop` | `isaac_ros_teleop`<br>`isaac_teleop_core` | [setup](./setup/teleop.md) | [catch-up](./catch-up/teleop.md) | Quest 3 実機（コントローラ / ハンドトラッキング両モード）で動作確認済み |

<!-- 新しいテーマを追加したらこの表に 1 行足す -->

---

## 3. テーマを追加するとき

1. **テーマ名を決める**：`snake_case`。公式リポジトリ／パッケージ名に寄せる（例：`visual_slam`, `nitros`, `rtdetr`, `body_pose`）。
2. **雛形をコピーする**
   ```bash
   cp docs/_templates/setup.md   docs/setup/<theme>.md
   cp docs/_templates/catch-up.md docs/catch-up/<theme>.md
   ```
3. **このページの「テーマ一覧」に 1 行追加**し、ルート [README.md](../README.md) のドキュメント表にも反映する。
4. **コードを書く場所**：テーマごとに `isaac_ros-dev/src/custom_<theme>_bringup/` のように分け、`isaac_ros*`（公式）と同じ並びにならないようにする（`.gitignore` 参照）。
5. 手順書には **必ず「いつ・どの環境で確認したか」** を書く。TensorRT Engine（`.plan`）は GPU 環境依存のため、再現性の担保に必須です。

---

## 4. 書き方のルール

- **コンテナ内 / コンテナ外** のどちらで実行するかを、すべてのコマンドブロックに明記する。
- ワークスペースは常に `${ISAAC_ROS_WS}`（ホスト）= `/workspaces/isaac_ros-dev`（コンテナ）で書く。絶対パスの直書きは避ける。
- 図は **ASCII の text コードブロック** で統一する（GitHub 側で Mermaid が効かない環境でも読めるため）。
- 文書間のリンクは **相対リンク**（`./setup/xxx.md`, `../README.md`）を使う。
- 未確認・仮説の箇所は「未確認」「要検証」と明示する（catch-up の `## 未確認・次の TODO` 節に集約）。
