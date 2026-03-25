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

1. 一時ディレクトリを作成し、最初の1フレームをネイティブ品質で抽出:

```bash
mkdir -p /tmp/vpm_sample
ffmpeg -y -i <input> -vframes 1 -q:v 2 /tmp/vpm_sample/frame_001.jpg
```

Windows の場合は `%TEMP%\vpm_sample` を使用する。

**重要: `-vframes 1` を使うこと。`-vf "fps=1"` でリサンプルするとJPEG圧縮品質が `mask_path.py` の内部抽出と異なり、マッチングスコアが0.52まで低下して検出できなくなる。**

2. Read ツールでフレーム画像を読み込み、以下を特定:
   - ファイルパス（`C:\Users\...`、`/home/...` 等）が映っている箇所
   - ユーザー名が映っている箇所
   - APIキー（`sk-ant-`、`Bearer ` 等）が映っている箇所

3. 座標の特定方法:
   - フレーム全体が大きい場合は、右半分を上下4分割して Read で確認すると効率的
   - ターミナルのフォントは等幅で約7-8px/文字
   - 画像の右半分（x > 50%）がターミナル領域であることが多い

4. テンプレートの切り出し（Python で実行）:

```python
import cv2
gray = cv2.imread('/tmp/vpm_sample/frame_001.jpg', cv2.IMREAD_GRAYSCALE)
template = gray[y:y+h, x:x+w]
cv2.imwrite('/tmp/vpm_sample/template.png', template)
```

テンプレートは短い固有文字列（`Users\\komei` 等）にする。長すぎると部分一致しにくくなる。

5. パディング方向を判断:
   - パスの右側に続くテキストが多ければ `--pad-right` を大きく（150-350）
   - APIキーは `--pad-right` をさらに大きく（200-400）
   - テンプレートの左側もカバーする場合は `--pad-left` を調整

### Phase 4: テストマッチング

Phase 3 で保存したテンプレート PNG を使い、まずスコアを確認:

```python
import cv2, numpy as np
gray = cv2.imread('/tmp/vpm_sample/frame_001.jpg', cv2.IMREAD_GRAYSCALE)
template = cv2.imread('/tmp/vpm_sample/template.png', cv2.IMREAD_GRAYSCALE)
result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
print(f"Best match: {max_val:.4f} at {max_loc}")
locations = np.where(result >= 0.65)
print(f"Matches (>=0.65): {len(locations[0])}")
```

- ベストスコアが 0.95 以上であることを確認（同一フレームなので 1.0 に近いはず）
- 0.65 以上のマッチ数が妥当か確認（1フレームに同パターンが複数ある場合は2以上）

次に短い動画テスト:

```bash
python mask_path.py <input> /tmp/vpm_test.mp4 --template /tmp/vpm_sample/template.png --pad-right <N>
```

処理後、出力フレームを Read ツールで確認:
- マスク範囲が適切か（テンプレート直前の `filePath:` 等は見えてOK）
- 取りこぼしがないか
- 誤検出がないか

問題があれば座標やパディングを調整して Phase 3 に戻る。

### Phase 5: 本処理

確定したパラメータで全フレームを処理:

```bash
python mask_path.py <input> <output> \
  --template /tmp/vpm_sample/template.png \
  --threshold 0.65 \
  --pad-left 10 --pad-right <N> \
  --pad-top 2 --pad-bottom 2 \
  --blur-size 31
```

複数箇所をマスクする場合は、1回目の出力を2回目の入力にして連続実行:

```bash
python mask_path.py <input> temp_masked.mp4 --template /tmp/vpm_sample/template1.png
python mask_path.py temp_masked.mp4 <output> --template /tmp/vpm_sample/template2.png
```

### Phase 6: 結果確認

出力動画からサンプルフレームを抽出して Read ツールで目視確認:

```bash
mkdir -p /tmp/vpm_check
ffmpeg -y -i <output> -vframes 3 -vf "select='eq(n\,0)+eq(n\,500)+eq(n\,1000)'" -vsync vfr -q:v 2 /tmp/vpm_check/frame_%03d.jpg
```

フレーム番号は動画の長さに応じて調整する（先頭・中間・終盤の3箇所を確認）。

確認項目:
- マスク漏れがないか
- 音声が正常にコピーされているか（`ffprobe <output>` で音声ストリームを確認）
- 映像品質が許容範囲か

問題があれば Phase 3 に戻ってパラメータを調整する。

完了したら一時ファイルを削除:

```bash
rm -rf /tmp/vpm_sample /tmp/vpm_check /tmp/vpm_test.mp4
```
