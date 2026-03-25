# video-path-mask

動画内に映り込んだファイルパス・ユーザー名・APIキーなどの機密テキストを、テンプレートマッチングで自動検出してぼかしでマスクするツール。

## なぜ必要か

Claude CodeやCursorの操作を画面録画してSNSやブログで共有したい。でもターミナルにはファイルパスが映る。`c:\Users\あなたの名前\Documents\...` が全世界に公開される。

手作業で動画を編集するのは面倒だし、見落としが怖い。このツールはOpenCVのテンプレートマッチングで **全フレームを自動スキャン** して、該当箇所だけにぼかしをかける。

## クイックスタート（Claude Code）

Claude Code のスキルとして使うと、座標の特定から処理まで全自動で行える。

```bash
git clone https://github.com/Sora-bluesky/video-path-mask.git
cd video-path-mask
pip install -r requirements.txt
```

Claude Code を起動してスキルを実行:

```
> /mask-video recording.mp4
```

Claude Code がフレームを抽出し、画像を見てマスク対象の座標を自動特定し、処理を実行する。

### グローバルスキルとして使う

任意のディレクトリから `/mask-video` を使いたい場合:

```bash
cp -r video-path-mask/.claude/skills/mask-video ~/.claude/skills/
```

## 手動で使う（CLI）

### 1. セットアップ

```bash
pip install opencv-python-headless
# ffmpeg が必要（brew install ffmpeg / apt install ffmpeg / winget install ffmpeg）

git clone https://github.com/Sora-bluesky/video-path-mask.git
cd video-path-mask
```

### 2. マスク対象の座標を確認

```bash
# 最初のフレームを抽出
ffmpeg -i input.mp4 -vframes 1 -q:v 2 first_frame.jpg
```

画像ビューアで開いて、マスクしたいテキスト（パス、ユーザー名など）の座標を確認する。

### 3. 実行

```bash
# 座標指定（x,y,w,h）
python mask_path.py input.mp4 output.mp4 --region 870,150,120,18

# テンプレート画像を指定
python mask_path.py input.mp4 output.mp4 --template my_template.png
```

### 4. 確認

```bash
# マスク済み動画からサンプルフレームを抽出して目視
ffmpeg -i output.mp4 -vf "fps=1" -q:v 2 check_%03d.jpg
```

## オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--template` | - | テンプレート画像（PNG/JPG） |
| `--region` | - | テンプレート切り出し座標 `x,y,w,h` |
| `--threshold` | 0.65 | マッチング閾値（0.0-1.0） |
| `--pad-left` | 30 | ぼかしの左余白 |
| `--pad-right` | 150 | ぼかしの右余白 |
| `--pad-top` | 2 | ぼかしの上余白 |
| `--pad-bottom` | 2 | ぼかしの下余白 |
| `--blur-size` | 31 | ぼかし強度 |
| `--keep-temp` | false | 一時ファイルを残す |

## 仕組み

```
入力動画
  ↓ ffmpeg でフレーム抽出（30fps → JPEGファイル群）
  ↓ OpenCV テンプレートマッチング（全フレーム × テンプレート）
  ↓ ヒット箇所にガウスぼかし適用
  ↓ ffmpeg でフレーム再結合（音声も元動画からコピー）
出力動画
```

## よくある質問

**Q: 動画のどの部分がマスクされるの？**
テンプレートと一致する箇所だけ。テンプレートに含まれない文字列は一切触らない。

**Q: 処理時間は？**
30秒の動画（900フレーム）で1-2分程度。ボトルネックはフレーム単位のマッチング。

**Q: 音声はどうなる？**
元動画の音声をそのままコピーする。再エンコードしない。

**Q: テンプレートの座標がわからない**
Claude Code のスキルとして使えば、フレーム画像を見て座標を自動特定する。

**Q: 複数箇所をマスクしたい**
スクリプトを連続実行する。1回目の出力を2回目の入力にする:
```bash
python mask_path.py input.mp4 temp.mp4 --region 870,150,120,18
python mask_path.py temp.mp4 output.mp4 --template apikey_template.png
```

## ライセンス

MIT
