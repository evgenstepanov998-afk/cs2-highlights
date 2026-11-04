"""Draws the Killcam icon (crosshair on a dark rounded tile, orange gradient) → assets/killcam.ico."""
import os
from PIL import Image, ImageDraw

S = 1024


def gradient(size):
    g = Image.new("RGBA", (size, size))
    px = g.load()
    stops = [(0.0, (255, 77, 46)), (0.6, (255, 122, 47)), (1.0, (255, 179, 71))]
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            for (a, ca), (b, cb) in zip(stops, stops[1:]):
                if a <= t <= b:
                    k = (t - a) / (b - a)
                    px[x, y] = tuple(int(ca[i] + (cb[i] - ca[i]) * k) for i in range(3)) + (255,)
                    break
    return g


def main():
    os.makedirs("assets", exist_ok=True)
    tile = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(tile)
    d.rounded_rectangle((32, 32, S - 32, S - 32), radius=230, fill=(21, 22, 29, 255))

    mask = Image.new("L", (S, S), 0)
    m = ImageDraw.Draw(mask)
    c, r, w = S // 2, 250, 64
    m.ellipse((c - r, c - r, c + r, c + r), outline=255, width=w)
    arm = 64
    for x0, y0, x1, y1 in ((c, 150, c, 330), (c, S - 330, c, S - 150), (150, c, 330, c), (S - 330, c, S - 150, c)):
        m.line((x0, y0, x1, y1), fill=255, width=arm)
        for px, py in ((x0, y0), (x1, y1)):
            m.ellipse((px - arm // 2, py - arm // 2, px + arm // 2, py + arm // 2), fill=255)
    m.ellipse((c - 62, c - 62, c + 62, c + 62), fill=255)
    m.rounded_rectangle((40, 40, S - 40, S - 40), radius=225, outline=110, width=10)

    small = gradient(256).resize((S, S))
    tile.paste(small, (0, 0), mask)
    tile.save("assets/killcam.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    tile.resize((512, 512), Image.LANCZOS).save("assets/killcam.png")
    print("ok")


main()
