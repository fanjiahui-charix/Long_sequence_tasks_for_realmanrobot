"""Regenerate a synthetic A/B schematic. Optional development dependency: Pillow.
This is a task-input illustration, not an observed physical environment.
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    image = Image.new("RGB", (1000, 560), (246, 248, 251))
    d = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 25)
        small = ImageFont.truetype("arial.ttf", 21)
        title = ImageFont.truetype("arialbd.ttf", 30)
    except OSError:
        font = ImageFont.load_default(size=25)
        small = ImageFont.load_default(size=21)
        title = ImageFont.load_default(size=30)
    d.text(
        (40, 25),
        "Synthetic task scene: retrieve and return",
        fill=(25, 40, 60),
        font=title,
    )
    d.rectangle((35, 95, 965, 485), outline=(160, 173, 190), width=3)
    d.ellipse((90, 230, 210, 350), fill=(199, 224, 250), outline=(36, 95, 160), width=4)
    d.text((138, 268), "A", fill=(20, 55, 95), font=title)
    d.text((75, 370), "START / RETURN", fill=(20, 55, 95), font=small)
    d.line((245, 285, 650, 285), fill=(80, 113, 150), width=5)
    d.polygon([(650, 285), (628, 272), (628, 298)], fill=(80, 113, 150))
    d.text((320, 240), "navigate to B", fill=(50, 75, 105), font=font)
    d.line((650, 330, 245, 330), fill=(80, 113, 150), width=5)
    d.polygon([(245, 330), (267, 317), (267, 343)], fill=(80, 113, 150))
    d.text((305, 350), "return while holding", fill=(50, 75, 105), font=small)
    d.rounded_rectangle(
        (690, 180, 915, 400),
        radius=12,
        fill=(231, 215, 190),
        outline=(120, 98, 70),
        width=3,
    )
    d.text((710, 195), "B: TABLE", fill=(80, 57, 30), font=title)
    d.rounded_rectangle(
        (742, 260, 866, 308), radius=18, fill=(28, 30, 33), outline=(0, 0, 0), width=2
    )
    d.text((699, 335), "black glasses case", fill=(40, 40, 45), font=small)
    d.text(
        (40, 510),
        "Goal: robot at A AND glasses case held. No release/place action.",
        fill=(55, 75, 95),
        font=small,
    )
    output = Path(__file__).with_name("scene_ab.png")
    image.save(output)
    print(output)


if __name__ == "__main__":
    main()
