from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "assets" / "papereading-master.ico"


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    size = 256
    image = Image.new("RGBA", (size, size), "#173f3d")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((28, 24, 228, 232), radius=20, fill="#f6f8f7")
    draw.rectangle((54, 54, 202, 68), fill="#1b6f68")
    draw.rectangle((54, 88, 178, 99), fill="#b6c7c4")
    draw.rectangle((54, 113, 190, 124), fill="#b6c7c4")
    draw.rectangle((54, 138, 165, 149), fill="#b6c7c4")
    draw.line((54, 184, 104, 158, 139, 177, 199, 134), fill="#d06b47", width=10)
    draw.ellipse((190, 125, 208, 143), fill="#d06b47")
    try:
        font = ImageFont.truetype("segoeuib.ttf", 42)
    except OSError:
        font = ImageFont.load_default()
    draw.text((55, 174), "PM", font=font, fill="#173f3d")
    image.save(
        OUTPUT,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    main()
