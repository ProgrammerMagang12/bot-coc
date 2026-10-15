"""Strategy calibration tool: click drop points on a scouting screenshot.

Usage:
    py tools/make_strategy.py --image work/.../scout.png [--name Scenario1] [--out AttackStrategies.json]

Controls in the window:
    left click : add point to the current group
    d / b / w  : switch group (dragon / balloon / wall_wrecker)
    u          : undo last point of current group
    s          : save strategy (appends to the file) and quit
    q / ESC    : quit without saving
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

COLORS = {"dragon": (0, 0, 255), "balloon": (0, 220, 0), "wall_wrecker": (255, 128, 0)}


def points_to_percent(
    points: list[tuple[int, int]], image_size: tuple[int, int]
) -> list[tuple[float, float]]:
    width, height = image_size
    return [(x / width, y / height) for x, y in points]


def save_strategy(
    name: str,
    dragon: list[tuple[float, float]],
    balloon: list[tuple[float, float]],
    wrecker: tuple[float, float] | None,
    out_path: str | Path,
) -> None:
    """Append one strategy to the JSON file (creates it when missing)."""
    out = Path(out_path)
    data: dict = {"strategies": []}
    if out.is_file():
        data = json.loads(out.read_text(encoding="utf-8"))
        data.setdefault("strategies", [])
    data["strategies"].append(
        {
            "name": name,
            "dragon_drops": [list(p) for p in dragon],
            "balloon_drops": [list(p) for p in balloon],
            "wall_wrecker_drop": list(wrecker) if wrecker is not None else None,
        }
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_strategy")
    parser.add_argument("--image", required=True, help="scouting screenshot png")
    parser.add_argument("--name", default="Scenario1", help="strategy name")
    parser.add_argument("--out", default="AttackStrategies.json")
    args = parser.parse_args(argv)

    image = cv2.imread(args.image, cv2.IMREAD_COLOR)
    if image is None:
        print(f"cannot read image: {args.image}")
        return 1
    height, width = image.shape[:2]

    points: dict[str, list[tuple[int, int]]] = {
        "dragon": [],
        "balloon": [],
        "wall_wrecker": [],
    }
    group = "dragon"

    def render():
        canvas = image.copy()
        for group_name, group_points in points.items():
            for x, y in group_points:
                cv2.circle(canvas, (x, y), 8, COLORS[group_name], -1)
                cv2.circle(canvas, (x, y), 8, (255, 255, 255), 2)
        cv2.putText(
            canvas,
            f"group={group} dragon={len(points['dragon'])} balloon={len(points['balloon'])} ws={len(points['wall_wrecker'])}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2,
        )
        cv2.putText(
            canvas,
            "click=add | d/b/w=group | u=undo | s=save | q=quit",
            (20, 80),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (200, 255, 200),
            2,
        )
        return canvas

    def on_mouse(event, x, y, _flags, _param):
        if event == cv2.EVENT_LBUTTONDOWN:
            points[group].append((x, y))

    cv2.namedWindow("make_strategy", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("make_strategy", on_mouse)
    while True:
        cv2.imshow("make_strategy", render())
        key = cv2.waitKey(30) & 0xFF
        if key in (ord("q"), 27):
            cv2.destroyAllWindows()
            print("cancelled")
            return 2
        if key == ord("d"):
            group = "dragon"
        elif key == ord("b"):
            group = "balloon"
        elif key == ord("w"):
            group = "wall_wrecker"
        elif key == ord("u"):
            if points[group]:
                points[group].pop()
        elif key == ord("s"):
            dragon = points_to_percent(points["dragon"], (width, height))
            balloon = points_to_percent(points["balloon"], (width, height))
            wrecker_pct = points_to_percent(points["wall_wrecker"][:1], (width, height))
            save_strategy(
                args.name,
                dragon,
                balloon,
                wrecker_pct[0] if wrecker_pct else None,
                args.out,
            )
            cv2.destroyAllWindows()
            print(f"saved strategy '{args.name}' to {args.out}")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
