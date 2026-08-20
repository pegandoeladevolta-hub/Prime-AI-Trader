from pathlib import Path

from PIL import Image, ImageDraw


root = Path(__file__).parents[1]
size = 512
image = Image.new("RGBA", (size, size), "#070b12")
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8, 8, 504, 504), radius=105, fill="#0d1b2e", outline="#2e7dff", width=10)
draw.rounded_rectangle((125, 105, 205, 407), radius=18, fill="#2e7dff")
draw.rounded_rectangle((170, 105, 390, 285), radius=70, fill="#2e7dff")
draw.rounded_rectangle((203, 168, 315, 225), radius=20, fill="#0d1b2e")
points = [(92, 360), (170, 305), (235, 330), (303, 250), (355, 278), (430, 180)]
draw.line(points, fill="#29d391", width=18, joint="curve")
for x, y in points:
    draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill="#29d391")
image.save(root / "assets" / "icon.png")
image.save(root / "assets" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

