"""Draws ui/watermark.png: the Killcam crosshair + name + site, white with a soft shadow.
Shipped inside the app and laid over exported clips by ffmpeg (highlights/export.py)."""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT = r"C:\Windows\Fonts\bahnschrift.ttf"
SCALE = 2  # drawn large, ffmpeg scales it down to the video

logo = Image.open(os.path.join(ROOT, "assets", "killcam.png")).convert("RGBA").resize((96 * SCALE, 96 * SCALE), Image.LANCZOS)
title = ImageFont.truetype(FONT, 58 * SCALE)
title.set_variation_by_name("Bold")
small = ImageFont.truetype(FONT, 22 * SCALE)
small.set_variation_by_name("SemiBold")

W, H = 470 * SCALE, 112 * SCALE
art = Image.new("RGBA", (W, H), (0, 0, 0, 0))
art.alpha_composite(logo, (8 * SCALE, 8 * SCALE))
d = ImageDraw.Draw(art)
d.text((118 * SCALE, 6 * SCALE), "KILLCAM", font=title, fill=(255, 255, 255, 255))
d.text((121 * SCALE, 74 * SCALE), "killcam-app.github.io/killcam", font=small, fill=(255, 210, 180, 235))

# soft dark shadow so it reads on bright maps (Dust2 sky) and dark corners alike
shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
shadow.putalpha(art.getchannel("A").point(lambda a: int(a * 0.65)))
shadow = shadow.filter(ImageFilter.GaussianBlur(5 * SCALE))
out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
out.alpha_composite(shadow, (0, 2 * SCALE))
out.alpha_composite(art)
out.save(os.path.join(ROOT, "ui", "watermark.png"))
print("ui/watermark.png", out.size)
