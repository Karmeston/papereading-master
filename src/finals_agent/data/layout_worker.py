from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, nargs="+")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--confidence", type=float, default=0.2)
    args = parser.parse_args()

    from doclayout_yolo import YOLOv10

    model_path = Path(args.model)
    if not model_path.exists():
        from huggingface_hub import hf_hub_download

        downloaded = hf_hub_download(
            repo_id="juliozhao/DocLayout-YOLO-DocStructBench",
            filename="doclayout_yolo_docstructbench_imgsz1024.pt",
            local_dir=model_path.parent,
        )
        model_path = Path(downloaded)

    model = YOLOv10(str(model_path))
    results = model.predict(
        [str(Path(item)) for item in args.image],
        imgsz=1024,
        conf=args.confidence,
        device=args.device,
        verbose=False,
    )
    pages = []
    for image_path, result in zip(args.image, results):
        height, width = result.orig_shape
        detections = []
        for box in result.boxes:
            x0, y0, x1, y1 = (float(value) for value in box.xyxy[0].tolist())
            detections.append(
                {
                    "label": result.names[int(box.cls.item())],
                    "confidence": round(float(box.conf.item()), 6),
                    "bbox": [
                        _clamp(x0 / width),
                        _clamp(y0 / height),
                        _clamp(x1 / width),
                        _clamp(y1 / height),
                    ],
                }
            )
        pages.append({"image": Path(image_path).name, "detections": detections})
    Path(args.output).write_text(
        json.dumps({"pages": pages}, ensure_ascii=False),
        encoding="utf-8",
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


if __name__ == "__main__":
    main()
