"""Render a clearly labeled replay from sanitized validation facts (requires Pillow)."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def font(size, mono=False):
    choices = (["/System/Library/Fonts/Menlo.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"] if mono else
               ["/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"])
    for name in choices:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def terminal(lines):
    im = Image.new("RGB", (1080, 500), "#101c25")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((18, 18, 1062, 482), 16, fill="#152630", outline="#3a5360", width=2)
    for i, color in enumerate(("#fc716c", "#e9c16a", "#91f4c8")):
        d.ellipse((43+i*24, 40, 56+i*24, 53), fill=color)
    d.text((139, 35), "Muse Bridge · verified test replay", font=font(21), fill="#b7cccf")
    d.line((20, 76, 1060, 76), fill="#3a5360", width=1)
    for i, (text, color) in enumerate(lines):
        d.text((48, 107+i*43), text, font=font(22, True), fill=color)
    d.text((48, 438), "Sanitized replay · paths / IDs replaced · not a raw recording", font=font(18), fill="#8fa7ae")
    return im


def main():
    facts = json.loads((ROOT / "examples/verified-roundtrips.json").read_text())
    frames = []
    for case in facts["cases"]:
        assert case["answer_verified"] and case["result_present_in_muse_history"]
        agent = case["agent"]
        lines = [("$ muse-bridge bridge start --background", "#f3f8f7"),
                 ("  relay running; explicit project scope", "#91f4c8")]
        frames.append(terminal(lines))
        lines += [(f"Muse → local task: {agent} / read", "#f3f8f7"),
                  ("  project: /path/to/disposable-project", "#b7cccf")]
        frames.append(terminal(lines))
        lines += [(f"Local {agent} → {case['expected_answer']}", "#91f4c8")]
        frames.append(terminal(lines))
        lines += [("Result found in Muse chat history ✓", "#91f4c8")]
        frames.append(terminal(lines))
    frames[0].save(ROOT / "assets/roundtrip.gif", save_all=True, append_images=frames[1:], duration=[1300,1300,1400,2200]*2, loop=0, optimize=True)
    im = Image.new("RGB", (1280, 640), "#101c25")
    d=ImageDraw.Draw(im)
    d.text((72, 62), "OPEN SOURCE  /  macOS", font=font(22), fill="#91f4c8")
    d.text((66, 122), "Muse Bridge", font=font(88), fill="#f3f8f7")
    d.text((72, 237), "Muse CLI for Codex & Claude Code", font=font(32), fill="#b7cccf")
    boxes=[(72, 330, 332, 432, "Muse"), (475, 330, 740, 432, "Your Mac"), (875, 330, 1208, 432, "Codex / Claude")]
    for x,y,x2,y2,label in boxes:
        d.rounded_rectangle((x,y,x2,y2),14,fill="#203540",outline="#45616a",width=2)
        d.text((x+25,y+34),label,font=font(29),fill="#f3f8f7")
    d.text((365, 355), "→", font=font(38), fill="#91f4c8")
    d.text((782, 355), "→", font=font(38), fill="#91f4c8")
    d.line((1040,448,1040,485,200,485,200,448),fill="#91f4c8",width=3)
    d.text((410, 505), "Results back in the same Muse chat", font=font(24), fill="#91f4c8")
    d.text((72, 577), "Keychain login · Project scope · MCP · No public ports", font=font(24), fill="#b7cccf")
    im.save(ROOT / "assets/social-preview.png", optimize=True)


if __name__ == "__main__":
    main()
