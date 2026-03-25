# video-path-mask

動画内に映り込んだファイルパス・ユーザー名・APIキーなどの機密テキストを、テンプレートマッチングで自動検出してぼかしでマスクするツール。

## なぜ必要か

Claude CodeやCursorの操作を画面録画してSNSやブログで共有したい。でもターミナルにはファイルパスが映る。`c:\Users\あなたの名前\Documents\...` が全世界に公開される。

手作業で動画を編集するのは面倒だし、見落としが怖い。このツールはOpenCVのテンプレートマッチングで **全フレームを自動スキャン** して、該当箇所だけにぼかしをかける。

## セットアップ

```bash
# 依存
pip install opencv-python-headless
# ffmpeg が必要（brew install ffmpeg / apt install ffmpeg / winget install ffmpeg）

# リポジトリ取得
git clone https://github.com/Sora-bluesky/video-path-mask.git
cd video-path-mask
```

## 使い方

### 1. マスク対象の座標を確認

```bash
# 最初のフレームを抽出
ffmpeg -i input.mp4 -vframes 1 -q:v 2 first_frame.jpg
```

画像ビューアで開いて、マスクしたいテキスト（パス、ユーザー名など）の座標を確認する。

### 2. 実行

```bash
# 座標指定（x,y,w,h）
python scripts/mask_path.py input.mp4 output.mp4 --region 870,150,120,18

# テンプレート画像を指定
python scripts/mask_path.py input.mp4 output.mp4 --template my_template.png
```

### 3. 確認

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
Claude Codeのスキルとして使う場合、viewツールでフレームを確認して座標を自動特定する。

## Claude Code スキルとして使う

`SKILL.md` をClaude Codeのスキルディレクトリにコピーすると、「動画のパスをマスクしたい」等の指示で自動的にワークフローが起動する。

```bash
cp -r video-path-mask ~/.claude/skills/
```

## ライセンス

MIT
