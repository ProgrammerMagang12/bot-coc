"""Interactive ROI tool: select a template region on a screenshot and save it.

Usage:
    py tools/make_template.py --image work/.../screen.png --name attack
    py tools/make_template.py --image shot.png --name next --assets assets

Select the region with the mouse, press ENTER to confirm (c to cancel).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2


def crop_and_save(
    image_path: str | Path, box_xywh: tuple[int, int, int, int], out_path: str | Path
) -> None:
    """Crop box (x, y, w, h) from image_path and save it as a PNG template."""
    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"cannot read image: {image_path}")
    x, y, w, h = (int(v) for v in box_xywh)
    crop = image[y : y + h, x : x + w]
    if crop.size == 0:
        raise ValueError(f"empty selection: {(x, y, w, h)}")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(out), crop):
        raise OSError(f"failed to write template: {out}")


def region_percent(
    box_xywh: tuple[int, int, int, int], image_size: tuple[int, int]
) -> tuple[float, float, float, float]:
    """Convert (x, y, w, h) pixels to (x1, y1, x2, y2) percentages."""
    x, y, w, h = (int(v) for v in box_xywh)
    width, height = image_size
    return (x / width, y / height, (x + w) / width, (y + h) / height)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_template")
    parser.add_argument("--image", required=True, help="screenshot png")
    parser.add_argument("--name", required=True, help="template name (without .png)")
    parser.add_argument("--assets", default="assets", help="template output directory")
    args = parser.parse_args(argv)

    image = cv2.imread(args.image, cv2.IMREAD_COLOR)
    if image is None:
        print(f"cannot read image: {args.image}")
        return 1

    roi = cv2.selectROI(
        "select template - ENTER confirm / c cancel", image, showCrosshair=True
    )
    cv2.destroyAllWindows()
    x, y, w, h = (int(v) for v in roi)
    if w == 0 or h == 0:
        print("selection cancelled")
        return 2

    out = Path(args.assets) / f"{args.name}.png"
    crop_and_save(args.image, (x, y, w, h), out)
    x1, y1, x2, y2 = region_percent((x, y, w, h), (image.shape[1], image.shape[0]))
    print(f"saved {out} ({w}x{h})  region=({x1:.3f}, {y1:.3f}, {x2:.3f}, {y2:.3f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
