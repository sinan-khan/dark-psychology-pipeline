"""
Paper/painterly stylization pass, applied to the silent concatenated video
before captions are burned in (so text stays crisp, not painted-over).

Technique: downscaled oil-paint stylization (cv2.xphoto.oilPainting -- a real
offline painterly filter, not a fake grain overlay) + a procedurally-generated
paper texture blend + film-grain + vignette + a slightly desaturated warm
grade. The texture is generated once and cached to disk so every run looks
consistent and no external asset needs to be downloaded.

Runs frame-by-frame via multiprocessing across all available CPU cores --
on a single core a ~40s/30fps clip takes ~6-7 minutes; with GitHub Actions'
usual 4 cores that drops to under 2 minutes.
"""
import json
import multiprocessing
import os
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CONFIG = json.loads((ROOT / "config" / "style.json").read_text())
TEXTURE_PATH = ROOT / "config" / "paper_texture.png"

_VIGNETTE_CACHE = {}


def _generate_paper_texture(width: int, height: int, seed: int = 7) -> np.ndarray:
    """Multi-octave blurred noise -> a mottled paper/canvas-fiber look.
    Grayscale, cached to disk so it's identical across runs."""
    from PIL import Image, ImageFilter

    rng = np.random.default_rng(seed)
    canvas = np.zeros((height, width), dtype=np.float64)
    for weight, blur_radius in [(1.0, 40), (0.5, 15), (0.25, 4)]:
        layer = rng.random((height, width))
        img = Image.fromarray((layer * 255).astype(np.uint8))
        img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        canvas += weight * (np.asarray(img, dtype=np.float64) / 255.0)
    canvas -= canvas.min()
    canvas /= canvas.max()
    return (canvas * 255).astype(np.uint8)


def _get_texture(width: int, height: int) -> np.ndarray:
    if TEXTURE_PATH.exists():
        tex = cv2.imread(str(TEXTURE_PATH), cv2.IMREAD_GRAYSCALE)
        if tex is not None:
            return tex
    tex = _generate_paper_texture(width, height)
    TEXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(TEXTURE_PATH), tex)
    return tex


def _get_vignette_mask(h: int, w: int, strength: float) -> np.ndarray:
    key = (h, w, strength)
    if key not in _VIGNETTE_CACHE:
        y, x = np.ogrid[:h, :w]
        cy, cx = h / 2, w / 2
        dist = np.sqrt(((x - cx) / (w / 2)) ** 2 + ((y - cy) / (h / 2)) ** 2)
        mask = 1 - strength * np.clip(dist - 0.3, 0, 1)
        _VIGNETTE_CACHE[key] = np.clip(mask, 0, 1).astype(np.float32)[..., None]
    return _VIGNETTE_CACHE[key]


def style_frame(frame_bgr: np.ndarray, texture_gray: np.ndarray, cfg: dict) -> np.ndarray:
    h, w = frame_bgr.shape[:2]
    scale = cfg["process_scale"]

    small = cv2.resize(frame_bgr, (max(1, int(w * scale)), max(1, int(h * scale))))
    oil_small = cv2.xphoto.oilPainting(small, cfg["oil_size"], cfg["oil_dyn_ratio"])
    oil = cv2.resize(oil_small, (w, h), interpolation=cv2.INTER_LINEAR)

    hsv = cv2.cvtColor(oil, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:, :, 1] *= cfg["saturation"]
    graded = cv2.cvtColor(np.clip(hsv, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR).astype(np.float32)
    graded[:, :, 2] += cfg["warmth"]
    graded[:, :, 0] -= cfg["warmth"] * 0.5

    tex = cv2.resize(texture_gray, (w, h)).astype(np.float32)[..., None] / 255.0
    op = cfg["texture_opacity"]
    blended = graded * (1 - op * 0.5) + (tex * 255) * (op * 0.5)

    grain_small = np.random.normal(0, cfg["grain_strength"], (max(1, h // 2), max(1, w // 2))).astype(np.float32)
    grain = cv2.resize(grain_small, (w, h))[..., None]
    grained = blended + grain

    vmask = _get_vignette_mask(h, w, cfg["vignette_strength"])
    return np.clip(grained * vmask, 0, 255).astype(np.uint8)


def _process_one_frame(args: tuple) -> None:
    in_path, out_path, texture_path, cfg = args
    frame = cv2.imread(str(in_path))
    texture = cv2.imread(str(texture_path), cv2.IMREAD_GRAYSCALE)
    styled = style_frame(frame, texture, cfg)
    cv2.imwrite(str(out_path), styled, [cv2.IMWRITE_JPEG_QUALITY, 92])


def apply_paper_effect(input_video: Path, output_video: Path) -> None:
    cfg = CONFIG["paper_effect"]
    if not cfg.get("enabled", True):
        shutil.copy(input_video, output_video)
        return

    width, height = CONFIG["resolution"]
    fps = CONFIG["fps"]
    texture = _get_texture(width, height)  # ensures cached texture exists on disk

    work_dir = input_video.parent / "paper_effect_tmp"
    frames_in = work_dir / "in"
    frames_out = work_dir / "out"
    frames_in.mkdir(parents=True, exist_ok=True)
    frames_out.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_video), "-qscale:v", "2",
         str(frames_in / "frame_%06d.jpg")],
        check=True, capture_output=True,
    )

    in_frames = sorted(frames_in.glob("frame_*.jpg"))
    if not in_frames:
        raise RuntimeError(f"No frames extracted from {input_video} -- cannot apply paper effect.")

    jobs = [
        (f, frames_out / f.name, TEXTURE_PATH, cfg)
        for f in in_frames
    ]
    n_workers = max(1, os.cpu_count() or 1)
    with multiprocessing.Pool(processes=n_workers) as pool:
        pool.map(_process_one_frame, jobs)

    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", str(frames_out / "frame_%06d.jpg"),
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         str(output_video)],
        check=True, capture_output=True,
    )

    shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    import sys

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.parent / "styled_video.mp4"
    apply_paper_effect(src, dst)
    print(f"Styled video written to {dst}")
