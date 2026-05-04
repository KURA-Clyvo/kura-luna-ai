"""Download YOLOv8n weights to src/ai/models/."""
from pathlib import Path

from ultralytics import YOLO


def main() -> None:
    dest = Path("src/ai/models/yolov8n.pt")
    dest.parent.mkdir(parents=True, exist_ok=True)
    model = YOLO("yolov8n.pt")
    model.save(str(dest))
    print(f"Weights saved to {dest}")


if __name__ == "__main__":
    main()
