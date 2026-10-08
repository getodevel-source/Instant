"""Compone la grilla comparativa del bake-off: fila QML arriba, fila web abajo,
mismos instantes del replay. Requiere Pillow (dependencia de la app).

Uso: python make_compare.py [--shots 2500,7600,9200] [--out out/compare_grid.png]
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = {"2500": "escuchando", "7600": "procesando", "9200": "aviso"}
TITLES = {"qml": "QML v2 (Qt Quick)", "web": "Web v2 (QtWebEngine + canvas)",
          "qml3": "QML v3 (techo: shader)", "web3": "Web v3 (techo: WebGL2)",
          "qml4": "QML v4 (3D + bloom propio)", "web4": "Web v4 (FBO bloom)"}


def load_font(size):
    for path in (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\arial.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def compose(tags, shots, out_path):
    pad, header = 16, 44
    tiles = {}
    for tag in tags:
        for t in shots:
            path = os.path.join(HERE, "out", f"{tag}_{t}.png")
            if os.path.exists(path):
                tiles[(tag, t)] = Image.open(path).convert("RGBA")
    if not tiles:
        raise SystemExit("no hay capturas para componer")
    width = max(im.width for im in tiles.values())
    height = max(im.height for im in tiles.values())
    cols, rows = len(shots), len(tags)
    grid_w = pad + cols * (width + pad)
    grid_h = pad + rows * (height + header + pad)
    grid = Image.new("RGB", (grid_w, grid_h), (18, 22, 26))
    draw = ImageDraw.Draw(grid)
    font = load_font(15)
    small = load_font(13)

    for row, tag in enumerate(tags):
        for col, t in enumerate(shots):
            x = pad + col * (width + pad)
            y = pad + row * (height + header + pad)
            title = TITLES.get(tag, tag)
            draw.text((x, y), title, fill=(220, 230, 232), font=font)
            draw.text((x, y + 19), f"t={t} ms - {LABELS.get(t, '')}",
                      fill=(140, 155, 160), font=small)
            im = tiles.get((tag, t))
            if im is not None:
                tile = Image.new("RGBA", (width, height), (24, 28, 32, 255))
                tile.alpha_composite(im, ((width - im.width) // 2, (height - im.height) // 2))
                grid.paste(tile.convert("RGB"), (x, y + header))

    grid.save(out_path)
    print(f"grid: {out_path} ({grid_w}x{grid_h})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tags", default="qml,web")
    parser.add_argument("--shots", default="2500,7600,9200")
    parser.add_argument("--out", default=os.path.join(HERE, "out", "compare_grid.png"))
    args = parser.parse_args()
    compose([s.strip() for s in args.tags.split(",") if s.strip()],
            [s.strip() for s in args.shots.split(",") if s.strip()], args.out)


if __name__ == "__main__":
    main()
