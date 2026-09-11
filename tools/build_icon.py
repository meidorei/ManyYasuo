"""Build an ICO whose native sizes are preserved by Tk on Windows."""

from pathlib import Path

from PIL import Image


def main():
    assets = Path(__file__).resolve().parents[1] / "assets"
    sizes = [(size, size) for size in (16, 20, 24, 32, 40, 48, 64, 128, 256)]
    with Image.open(assets / "app-icon.png") as source:
        # Tk loads PNG ICO entries at the system default size, then picks
        # the first matching entry (a rescaled 16px image). DIB entries keep
        # their dimensions, so title bars and taskbars get the correct image.
        source.convert("RGBA").save(
            assets / "app-icon.ico", format="ICO", bitmap_format="bmp", sizes=sizes
        )


if __name__ == "__main__":
    main()
