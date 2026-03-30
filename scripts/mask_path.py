#!/usr/bin/env python3
"""
video-path-mask v2: Mask file paths in video using template matching + Gaussian blur.

Key improvements over v1:
- VideoCapture direct read (no disk frame extraction)
- Frame-skip detection for speed
- MJPG intermediate codec for quality
- Multi-template single-pass support
- Double Gaussian blur for reliable masking
- Audio copy (no re-encoding)
- Template-proportional NMS

Usage:
  python scripts/mask_path.py input.mp4 output.mp4 --template t1.png
  python scripts/mask_path.py input.mp4 output.mp4 --template t1.png --template t2.png
  python scripts/mask_path.py input.mp4 output.mp4 --region 80,708,90,18
"""

import argparse
import cv2
import numpy as np
import os
import sys
import subprocess
import json


def get_video_info(video_path):
    """Get video FPS, dimensions, and audio presence."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)

    fps = 30.0
    width = 0
    height = 0
    has_audio = False

    for stream in data.get("streams", []):
        if stream["codec_type"] == "video":
            r = stream.get("r_frame_rate", "30/1")
            num, den = map(int, r.split("/"))
            fps = num / den if den else 30.0
            width = int(stream.get("width", 0))
            height = int(stream.get("height", 0))
        if stream["codec_type"] == "audio":
            has_audio = True

    return fps, width, height, has_audio


def nms(matches, tw, th):
    """Non-maximum suppression using template-proportional distance."""
    if not matches:
        return []
    matches.sort(key=lambda m: m[2], reverse=True)
    keep = []
    for x, y, s in matches:
        if not any(abs(x - kx) < tw * 0.7 and abs(y - ky) < th * 0.7
                   for kx, ky, _ in keep):
            keep.append((x, y, s))
    return keep


def detect_regions(gray, templates):
    """Run template matching for all templates and return blur regions."""
    h, w = gray.shape
    regions = []

    for tcfg in templates:
        t = tcfg["template"]
        th, tw = t.shape[:2]

        result = cv2.matchTemplate(gray, t, cv2.TM_CCOEFF_NORMED)
        locs = np.where(result >= tcfg["threshold"])

        matches = [(int(x), int(y), float(result[y, x]))
                    for y, x in zip(locs[0], locs[1])]
        matches = nms(matches, tw, th)

        for mx, my, score in matches:
            bx1 = max(0, mx - tcfg["pad_left"])
            by1 = max(0, my - tcfg["pad_top"])
            bx2 = min(w, mx + tw + tcfg["pad_right"])
            by2 = min(h, my + th + tcfg["pad_bottom"])
            regions.append((bx1, by1, bx2, by2))

    return regions


def apply_blur(frame, regions, blur_size):
    """Apply double Gaussian blur to specified regions."""
    if not regions:
        return frame
    masked = frame.copy()
    for bx1, by1, bx2, by2 in regions:
        roi = masked[by1:by2, bx1:bx2]
        blurred = cv2.GaussianBlur(roi, (blur_size, blur_size), 0)
        blurred = cv2.GaussianBlur(blurred, (blur_size, blur_size), 0)
        masked[by1:by2, bx1:bx2] = blurred
    return masked


def main():
    parser = argparse.ArgumentParser(
        description="Mask file paths in video via template matching + blur"
    )
    parser.add_argument("input", help="Input video file")
    parser.add_argument("output", help="Output video file")
    parser.add_argument("--template", action="append", dest="templates",
                        help="Template image (repeatable for multi-template)")
    parser.add_argument("--region", help="Cut template from first frame: x,y,w,h")
    parser.add_argument("--threshold", type=float, default=0.65,
                        help="Match threshold (default: 0.65)")
    parser.add_argument("--pad-left", type=int, default=30,
                        help="Blur padding left (default: 30)")
    parser.add_argument("--pad-right", type=int, default=400,
                        help="Blur padding right (default: 400)")
    parser.add_argument("--pad-top", type=int, default=3,
                        help="Blur padding top (default: 3)")
    parser.add_argument("--pad-bottom", type=int, default=3,
                        help="Blur padding bottom (default: 3)")
    parser.add_argument("--blur-size", type=int, default=41,
                        help="Gaussian kernel size (default: 41)")
    parser.add_argument("--detect-interval", type=int, default=5,
                        help="Run detection every N frames (default: 5)")
    parser.add_argument("--crf", type=int, default=14,
                        help="Output h264 CRF (default: 14, lower=better)")
    parser.add_argument("--keep-temp", action="store_true",
                        help="Keep intermediate files")

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: input not found: {args.input}")
        sys.exit(1)

    # Get video info
    fps, width, height, has_audio = get_video_info(args.input)
    print(f"Input: {width}x{height}, {fps:.1f}fps, audio={'yes' if has_audio else 'no'}",
          flush=True)

    # Prepare templates
    template_configs = []

    if args.templates:
        for tpath in args.templates:
            t = cv2.imread(tpath, cv2.IMREAD_GRAYSCALE)
            if t is None:
                print(f"Error: cannot read template: {tpath}")
                sys.exit(1)
            template_configs.append({
                "template": t,
                "threshold": args.threshold,
                "pad_left": args.pad_left,
                "pad_right": args.pad_right,
                "pad_top": args.pad_top,
                "pad_bottom": args.pad_bottom,
            })
            print(f"Template: {tpath} ({t.shape[1]}x{t.shape[0]})", flush=True)

    elif args.region:
        # Extract template from first frame
        cap = cv2.VideoCapture(args.input)
        ret, first = cap.read()
        cap.release()
        if not ret:
            print("Error: cannot read first frame")
            sys.exit(1)

        x, y, w, h = map(int, args.region.split(","))
        gray0 = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
        t = gray0[y:y+h, x:x+w]
        template_configs.append({
            "template": t,
            "threshold": args.threshold,
            "pad_left": args.pad_left,
            "pad_right": args.pad_right,
            "pad_top": args.pad_top,
            "pad_bottom": args.pad_bottom,
        })
        print(f"Template from region ({x},{y},{w},{h}): {t.shape[1]}x{t.shape[0]}",
              flush=True)
    else:
        print("Error: specify --template or --region")
        sys.exit(1)

    # Process video: read with VideoCapture, write with MJPG intermediate
    cap = cv2.VideoCapture(args.input)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    temp_dir = os.path.dirname(os.path.abspath(args.output))
    temp_video = os.path.join(temp_dir, "_temp_masked.avi")

    fourcc = cv2.VideoWriter_fourcc(*'MJPG')
    writer = cv2.VideoWriter(temp_video, fourcc, fps, (width, height))

    frame_idx = 0
    current_regions = []
    total_masks = 0

    print(f"Processing {total_frames} frames (detect every {args.detect_interval})...",
          flush=True)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Detect on interval frames
        if frame_idx % args.detect_interval == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            current_regions = detect_regions(gray, template_configs)

        masked = apply_blur(frame, current_regions, args.blur_size)
        writer.write(masked)
        total_masks += len(current_regions)
        frame_idx += 1

        if frame_idx % 1000 == 0:
            pct = frame_idx * 100 // total_frames
            print(f"  {frame_idx}/{total_frames} ({pct}%), "
                  f"regions: {len(current_regions)}", flush=True)

    cap.release()
    writer.release()

    temp_mb = os.path.getsize(temp_video) / (1024 * 1024)
    print(f"Intermediate: {temp_mb:.0f} MB", flush=True)

    # Re-encode with ffmpeg: h264 + copy audio
    print("Re-encoding with ffmpeg...", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", temp_video,
        "-i", args.input,
        "-c:v", "libx264", "-preset", "medium", "-crf", str(args.crf),
        "-pix_fmt", "yuv420p",
        "-map", "0:v:0",
    ]

    if has_audio:
        cmd.extend(["-map", "1:a:0", "-c:a", "copy"])

    cmd.extend(["-movflags", "+faststart", args.output])

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"FFmpeg error: {r.stderr[-500:]}")
        sys.exit(1)

    out_mb = os.path.getsize(args.output) / (1024 * 1024)
    print(f"Output: {args.output} ({out_mb:.1f} MB)", flush=True)
    print(f"Total: {frame_idx} frames, {total_masks} mask operations", flush=True)

    # Cleanup
    if not args.keep_temp:
        os.remove(temp_video)
    else:
        print(f"Temp file kept: {temp_video}")

    print("Done!", flush=True)


if __name__ == "__main__":
    main()
