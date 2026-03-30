[日本語](README_ja.md)

# video-path-mask

Auto-detect and blur sensitive text (file paths, usernames, API keys) in screen recording videos using OpenCV template matching.

## Why

You record your Claude Code or Cursor session to share on social media or your blog. But the terminal shows file paths like `c:\Users\your-name\Documents\...` for the world to see.

Manually editing videos is tedious and error-prone. This tool uses OpenCV template matching to **scan every frame automatically** and blur only the matching regions.

## Quick Start (Claude Code)

As a Claude Code skill, coordinate detection and masking are fully automated.

```bash
git clone https://github.com/Sora-bluesky/video-path-mask.git
cd video-path-mask
pip install -r requirements.txt
```

Launch Claude Code and run the skill:

```
> /mask-video recording.mp4
```

Claude Code extracts frames, identifies sensitive regions via multimodal vision, and runs the masking process.

### Install as a global skill

To use `/mask-video` from any directory:

```bash
cp -r video-path-mask/.claude/skills/mask-video ~/.claude/skills/
```

## Manual Usage (CLI)

### 1. Setup

```bash
pip install opencv-python-headless
# ffmpeg required (brew install ffmpeg / apt install ffmpeg / winget install ffmpeg)

git clone https://github.com/Sora-bluesky/video-path-mask.git
cd video-path-mask
```

### 2. Find the target coordinates

```bash
# Extract the first frame
ffmpeg -i input.mp4 -vframes 1 -q:v 2 first_frame.jpg
```

Open in an image viewer and note the coordinates of the text you want to mask.

### 3. Run

```bash
# By coordinates (x,y,w,h)
python scripts/mask_path.py input.mp4 output.mp4 --region 870,150,120,18

# By template image
python scripts/mask_path.py input.mp4 output.mp4 --template my_template.png
```

### 4. Verify

```bash
# Extract sample frames from the output to check
ffmpeg -i output.mp4 -vf "fps=1" -q:v 2 check_%03d.jpg
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--template` | - | Template image (repeatable: `--template a.png --template b.png`) |
| `--region` | - | Region to crop as template `x,y,w,h` |
| `--threshold` | 0.65 | Matching threshold (0.0-1.0) |
| `--pad-left` | 30 | Blur padding left |
| `--pad-right` | 400 | Blur padding right |
| `--pad-top` | 3 | Blur padding top |
| `--pad-bottom` | 3 | Blur padding bottom |
| `--blur-size` | 41 | Gaussian blur kernel size (applied twice) |
| `--detect-interval` | 5 | Run detection every N frames (reuse between) |
| `--crf` | 14 | Output h264 CRF (lower = better quality) |
| `--keep-temp` | false | Keep temporary files |

## How It Works

```
Input video
  -> VideoCapture reads frames directly (no disk extraction)
  -> OpenCV template matching (every N frames, reuse between)
  -> Double Gaussian blur applied to matched regions
  -> Write to MJPG intermediate file
  -> ffmpeg re-encodes h264 + copies audio from original
Output video
```

## FAQ

**Q: What parts of the video get masked?**
Only regions matching the template. Everything else is untouched.

**Q: How long does it take?**
About 30s–1min for a 30-second video with default frame-skip (`--detect-interval 5`). The bottleneck is template matching.

**Q: What about audio?**
Audio is copied directly from the original without re-encoding.

**Q: I don't know the coordinates.**
Use the Claude Code skill -- it views the frame images and auto-detects the coordinates.

**Q: I need to mask multiple regions.**
Pass `--template` multiple times to handle all patterns in a single pass:
```bash
python scripts/mask_path.py input.mp4 output.mp4 \
  --template path_template.png \
  --template apikey_template.png
```

## License

MIT
