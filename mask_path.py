#!/usr/bin/env python3
"""
video-path-mask: 動画内のファイルパスをテンプレートマッチングで検出し、ぼかしでマスクする。

使い方:
  python mask_path.py <input_video> <output_video> [options]

例:
  python mask_path.py input.mp4 output.mp4
  python mask_path.py input.mp4 output.mp4 --pattern "Users\\\\komei"
  python mask_path.py input.mp4 output.mp4 --template template.png
  python mask_path.py input.mp4 output.mp4 --auto-detect
"""

import argparse
import cv2
import numpy as np
import os
import sys
import subprocess
import glob
import shutil
import tempfile


def extract_frames(video_path, output_dir):
    """動画から全フレームをJPEGで抽出"""
    os.makedirs(output_dir, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-q:v", "2",
        os.path.join(output_dir, "frame_%05d.jpg")
    ]
    subprocess.run(cmd, capture_output=True)
    frames = sorted(glob.glob(os.path.join(output_dir, "frame_*.jpg")))
    return frames


def get_video_info(video_path):
    """動画のFPSと音声有無を取得"""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", video_path
    ]
    import json
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)

    fps = 30
    has_audio = False
    for stream in data.get("streams", []):
        if stream["codec_type"] == "video":
            r = stream.get("r_frame_rate", "30/1")
            num, den = map(int, r.split("/"))
            fps = num / den if den else 30
        if stream["codec_type"] == "audio":
            has_audio = True

    return fps, has_audio


def auto_detect_template(frames, scan_count=5):
    """
    先頭のフレームをスキャンし、filePath: 行からパステンプレートを自動検出。
    ターミナル上の filePath: "c:\\Users\\<username>\\... パターンを探す。
    """
    # filePath: の直後にあるパス文字列を含む行を探す
    # 画面右半分（x > 50%）のターミナル領域で filePath 行を検出
    for frame_path in frames[:scan_count]:
        img = cv2.imread(frame_path)
        if img is None:
            continue
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # "filePath:" テキストをテンプレートマッチで探すのは難しいので、
        # ヒューリスティック: 右半分で明るいテキスト行（ターミナル背景は暗い）を走査
        # パスの特徴: "Users" や "Documents" が含まれる行

        # 別アプローチ: ユーザーに最初のフレームを見せて領域を指定してもらう
        # ここでは右半分の全行をスキャンして、パス文字列っぽい領域を返す
        pass

    return None


def create_template_from_region(frame_path, x, y, w, h):
    """指定座標からテンプレートを切り出す"""
    img = cv2.imread(frame_path, cv2.IMREAD_GRAYSCALE)
    template = img[y:y+h, x:x+w]
    return template


def find_and_mask(frames, template, output_dir, threshold=0.65,
                  pad_left=30, pad_right=150, pad_top=2, pad_bottom=2,
                  blur_ksize=31, blur_sigma=15):
    """
    全フレームでテンプレートマッチングを行い、ヒット箇所にぼかしを適用。
    """
    os.makedirs(output_dir, exist_ok=True)
    th, tw = template.shape[:2]
    total_masks = 0

    for i, fpath in enumerate(frames):
        img = cv2.imread(fpath)
        if img is None:
            continue

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        # 近接マッチの重複除去
        matched = []
        for pt in zip(*locations[::-1]):
            x, y = pt
            is_dup = any(abs(x - mx) < 20 and abs(y - my) < 10
                         for mx, my in matched)
            if not is_dup:
                matched.append((x, y))

        for x, y in matched:
            x1 = max(0, x - pad_left)
            y1 = max(0, y - pad_top)
            x2 = min(img.shape[1], x + tw + pad_right)
            y2 = min(img.shape[0], y + th + pad_bottom)

            roi = img[y1:y2, x1:x2]
            blurred = cv2.GaussianBlur(roi, (blur_ksize, blur_ksize), blur_sigma)
            img[y1:y2, x1:x2] = blurred
            total_masks += 1

        outpath = os.path.join(output_dir, os.path.basename(fpath))
        cv2.imwrite(outpath, img, [cv2.IMWRITE_JPEG_QUALITY, 95])

        if (i + 1) % 200 == 0:
            print(f"  処理中: {i+1}/{len(frames)} フレーム ({total_masks} 箇所マスク済み)")

    print(f"  完了: {len(frames)} フレーム処理、{total_masks} 箇所をマスク")
    return total_masks


def reassemble_video(frames_dir, original_video, output_path, fps):
    """マスク済みフレームを動画に再結合"""
    _, has_audio = get_video_info(original_video)

    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", os.path.join(frames_dir, "frame_%05d.jpg"),
    ]

    if has_audio:
        cmd.extend(["-i", original_video, "-map", "0:v", "-map", "1:a", "-c:a", "copy"])
    else:
        cmd.extend(["-map", "0:v"])

    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p", "-shortest", output_path
    ])

    subprocess.run(cmd, capture_output=True)


def interactive_template_setup(frames):
    """
    最初のフレームからテンプレートを対話的に設定。
    座標を指定してもらうか、自動検出を試みる。
    """
    print("\n=== テンプレート設定 ===")
    print(f"最初のフレーム: {frames[0]}")
    print("このフレームを確認して、マスクしたい領域の座標を指定してください。")
    print("例: パスが映る行の x,y,w,h を指定")
    print("    x=870, y=150, w=120, h=18")

    x = int(input("x (左端): "))
    y = int(input("y (上端): "))
    w = int(input("w (幅): "))
    h = int(input("h (高さ): "))

    return create_template_from_region(frames[0], x, y, w, h)


def main():
    parser = argparse.ArgumentParser(
        description="動画内のファイルパスをテンプレートマッチングで検出し、ぼかしでマスクする"
    )
    parser.add_argument("input", help="入力動画ファイル")
    parser.add_argument("output", help="出力動画ファイル")
    parser.add_argument("--template", help="テンプレート画像 (PNG/JPG)")
    parser.add_argument("--region", help="テンプレート切り出し領域 x,y,w,h (例: 870,150,120,18)")
    parser.add_argument("--threshold", type=float, default=0.65,
                        help="マッチング閾値 (0.0-1.0, デフォルト: 0.65)")
    parser.add_argument("--pad-left", type=int, default=30,
                        help="ぼかし領域の左パディング (デフォルト: 30)")
    parser.add_argument("--pad-right", type=int, default=150,
                        help="ぼかし領域の右パディング (デフォルト: 150)")
    parser.add_argument("--pad-top", type=int, default=2,
                        help="ぼかし領域の上パディング (デフォルト: 2)")
    parser.add_argument("--pad-bottom", type=int, default=2,
                        help="ぼかし領域の下パディング (デフォルト: 2)")
    parser.add_argument("--blur-size", type=int, default=31,
                        help="ぼかしカーネルサイズ (デフォルト: 31)")
    parser.add_argument("--keep-temp", action="store_true",
                        help="一時ファイルを削除しない")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"エラー: 入力ファイルが見つかりません: {args.input}")
        sys.exit(1)

    # 一時ディレクトリ
    tmpdir = tempfile.mkdtemp(prefix="vpm_")
    frames_dir = os.path.join(tmpdir, "frames")
    masked_dir = os.path.join(tmpdir, "masked")

    try:
        # 1. 動画情報取得
        fps, has_audio = get_video_info(args.input)
        print(f"入力動画: {fps:.1f}fps, 音声{'あり' if has_audio else 'なし'}")

        # 2. フレーム抽出
        print("フレーム抽出中...")
        frames = extract_frames(args.input, frames_dir)
        print(f"  {len(frames)} フレーム抽出完了")

        # 3. テンプレート準備
        if args.template:
            template = cv2.imread(args.template, cv2.IMREAD_GRAYSCALE)
            if template is None:
                print(f"エラー: テンプレート画像を読み込めません: {args.template}")
                sys.exit(1)
        elif args.region:
            x, y, w, h = map(int, args.region.split(","))
            template = create_template_from_region(frames[0], x, y, w, h)
        else:
            print("エラー: --template または --region を指定してください")
            print("  手順: まず最初のフレームでマスク対象の座標を確認し、--region で指定")
            sys.exit(1)

        print(f"テンプレート: {template.shape[1]}x{template.shape[0]}px")

        # 4. マッチング & マスク
        print("マスク処理中...")
        total = find_and_mask(
            frames, template, masked_dir,
            threshold=args.threshold,
            pad_left=args.pad_left,
            pad_right=args.pad_right,
            pad_top=args.pad_top,
            pad_bottom=args.pad_bottom,
            blur_ksize=args.blur_size,
            blur_sigma=args.blur_size // 2,
        )

        # 5. 動画再結合
        print("動画再結合中...")
        reassemble_video(masked_dir, args.input, args.output, fps)
        print(f"出力: {args.output}")
        print(f"合計 {total} 箇所をマスクしました")

    finally:
        if not args.keep_temp:
            shutil.rmtree(tmpdir, ignore_errors=True)
        else:
            print(f"一時ファイル: {tmpdir}")


if __name__ == "__main__":
    main()
