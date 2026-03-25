---
name: mask-video
description: "動画内のファイルパス・ユーザー名・APIキー等を自動検出してぼかしでマスクする。「動画のパスをマスクしたい」「録画を公開したいけど個人情報が映ってる」等で発動。"
argument-hint: <input_video> [output_video]
disable-model-invocation: true
allowed-tools: Bash, Read, Glob
---

# mask-video

動画内の機密テキスト（ファイルパス、ユーザー名、APIキー等）をテンプレートマッチングで検出し、ガウスぼかしで自動マスクする。

## 前提

- `mask_path.py` がこのリポジトリのルートに存在すること
- ffmpeg / ffprobe がインストール済みであること
- Python 3 + OpenCV (`pip install opencv-python-headless`) がインストール済みであること

## ワークフロー

### Phase 1: 入力解析

`$ARGUMENTS` から入力ファイルパスを取得する。

- 第1引数: 入力動画ファイル（必須）
- 第2引数: 出力動画ファイル（省略時は `<入力名>_masked.<拡張子>` を自動生成）

入力ファイルの存在を確認する。存在しない場合はエラーを報告して終了。

### Phase 2: 依存確認

以下を Bash で確認し、不足があればインストール手順を提示して終了:

```bash
ffmpeg -version
python -c "import cv2; print(cv2.__version__)"
```

### Phase 3: サンプルフレーム抽出 & 座標特定

1. 一時ディレクトリを作成し、先頭付近のフレームを3枚抽出:

```bash
mkdir -p /tmp/vpm_sample
ffmpeg -y -i <input> -vframes 3 -vf "fps=0.5" -q:v 2 /tmp/vpm_sample/frame_%03d.jpg
```

Windows の場合は `%TEMP%\vpm_sample` を使用する。

2. Read ツールでフレーム画像を読み込み、以下を特定:
   - ファイルパス（`C:\Users\...`、`/home/...` 等）が映っている箇所
   - ユーザー名が映っている箇所
   - APIキー（`sk-ant-`、`Bearer ` 等）が映っている箇所

3. 検出した各箇所の座標（x, y, w, h）を記録する。
   - ターミナルのフォントは等幅で約7-8px/文字
   - 画像の右半分（x > 50%）がターミナル領域であることが多い

4. パディング方向を判断:
   - パスの右側に続くテキストが多ければ `--pad-right` を大きく（150-300）
   - APIキーは `--pad-right` をさらに大きく（200-400）

### Phase 4: テストマッチング

最初のフレームだけで `--region` を使いテストマッチングを実行:

```bash
python mask_path.py <input> /tmp/vpm_test.mp4 --region <x>,<y>,<w>,<h> --pad-right <N>
```

処理後、出力フレームを Read ツールで確認:
- マスク範囲が適切か
- 取りこぼしがないか
- 誤検出がないか

問題があれば座標やパディングを調整して Phase 3 に戻る。

### Phase 5: 本処理

確定したパラメータで全フレームを処理:

```bash
python mask_path.py <input> <output> --region <x>,<y>,<w>,<h> \
  --threshold 0.65 \
  --pad-left 30 --pad-right <N> \
  --pad-top 2 --pad-bottom 2 \
  --blur-size 31
```

複数箇所をマスクする場合は、1回目の出力を2回目の入力にして連続実行:

```bash
python mask_path.py <input> temp_masked.mp4 --region <region1>
python mask_path.py temp_masked.mp4 <output> --region <region2>
```

### Phase 6: 結果確認

出力動画からサンプルフレームを抽出して Read ツールで目視確認:

```bash
ffmpeg -y -i <output> -vframes 3 -vf "fps=0.5" -q:v 2 /tmp/vpm_check/frame_%03d.jpg
```

確認項目:
- マスク漏れがないか
- 音声が正常にコピーされているか（`ffprobe <output>` で音声ストリームを確認）
- 映像品質が許容範囲か

問題があれば Phase 3 に戻ってパラメータを調整する。

完了したら一時ファイルを削除:

```bash
rm -rf /tmp/vpm_sample /tmp/vpm_check /tmp/vpm_test.mp4
```
