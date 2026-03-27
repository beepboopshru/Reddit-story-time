"""
reddit_card.py — Renders a Reddit-style post card image using Pillow.
Used as the intro overlay for Part 1 of generated reels.
"""

from __future__ import annotations
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from utils import TEMP_DIR


# ─── Constants ────────────────────────────────────────────────────────────────
VIDEO_W = 1080
VIDEO_H = 1920
CARD_W = 940          # card width in pixels
CARD_PADDING = 40     # inner horizontal padding
CARD_RADIUS = 32      # corner rounding
CARD_Y_CENTER = 0.40  # fraction down the screen to vertically center the card

# Colors
CARD_BG = (255, 255, 255, 255)         # white
CARD_SHADOW = (0, 0, 0, 60)            # semi-transparent shadow
REDDIT_ORANGE = (255, 85, 0)           # Reddit orange
SNOO_BG = (255, 85, 0)
META_GRAY = (120, 120, 120)
VOTE_ORANGE = (220, 73, 0)
TITLE_BLACK = (20, 20, 20)
DIVIDER = (230, 230, 230)

# Fonts — fall back to PIL default if system fonts unavailable
def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try to load a nice system font, fall back to PIL default."""
    candidates_bold = [
        "arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf",
        "NotoSans-Bold.ttf", "segoeui-bold.ttf", "segoeuib.ttf",
    ]
    candidates_regular = [
        "arial.ttf", "Arial.ttf", "DejaVuSans.ttf",
        "NotoSans-Regular.ttf", "segoeui.ttf",
    ]
    for name in (candidates_bold if bold else candidates_regular):
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default()


# ─── Helper: rounded rectangle ────────────────────────────────────────────────
def _rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill, shadow_offset: int = 0):
    x0, y0, x1, y1 = xy
    if shadow_offset:
        sx0, sy0, sx1, sy1 = x0 + shadow_offset, y0 + shadow_offset, x1 + shadow_offset, y1 + shadow_offset
        draw.rounded_rectangle((sx0, sy0, sx1, sy1), radius=radius, fill=CARD_SHADOW)
    draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill)


# ─── Helper: wrap text ────────────────────────────────────────────────────────
def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines, current = [], ""
    dummy = Image.new("RGBA", (1, 1))
    d = ImageDraw.Draw(dummy)
    for word in words:
        test = f"{current} {word}".strip()
        w = d.textlength(test, font=font)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


# ─── Reddit Snoo icon ─────────────────────────────────────────────────────────
def _draw_snoo(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int = 28):
    """Draw a simple Reddit-style circle icon."""
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=REDDIT_ORANGE)
    # White alien head
    hr = int(r * 0.55)
    draw.ellipse((cx - hr, cy - hr - 4, cx + hr, cy + hr - 4), fill=(255, 255, 255))
    # Eyes
    er = max(3, int(r * 0.12))
    draw.ellipse((cx - hr // 2 - er, cy - hr // 2 - 4, cx - hr // 2 + er, cy - hr // 2 + er - 4), fill=REDDIT_ORANGE)
    draw.ellipse((cx + hr // 2 - er, cy - hr // 2 - 4, cx + hr // 2 + er, cy - hr // 2 + er - 4), fill=REDDIT_ORANGE)
    # Smile arc
    smile_r = int(hr * 0.55)
    draw.arc(
        (cx - smile_r, cy - 4, cx + smile_r, cy + smile_r - 4),
        start=10, end=170, fill=REDDIT_ORANGE, width=max(2, int(r * 0.07))
    )
    # Antenna
    draw.line((cx, cy - hr - 4, cx, cy - hr - int(r * 0.4) - 4), fill=(255, 255, 255), width=max(2, int(r * 0.07)))
    draw.ellipse((cx - int(r * 0.1), cy - hr - int(r * 0.55) - 4,
                  cx + int(r * 0.1), cy - hr - int(r * 0.3) - 4), fill=(255, 255, 255))


# ─── Main renderer ────────────────────────────────────────────────────────────
class RedditCardRenderer:
    """
    Renders a Reddit-style post card PNG overlay.

    Usage:
        renderer = RedditCardRenderer(
            title="What are signs that a person genuinely is unintelligent?",
            subreddit="AskReddit",
            username="leathur_records",
            score=11700,
            num_comments=10000,
        )
        path = renderer.render()
    """

    def __init__(
        self,
        title: str,
        subreddit: str = "AskReddit",
        username: str = "u/user",
        score: int = 0,
        num_comments: int = 0,
        age: str = "2d",
    ):
        self.title = title
        self.subreddit = subreddit.lstrip("r/")
        self.username = username.lstrip("u/")
        self.score = score
        self.num_comments = num_comments
        self.age = age

    @staticmethod
    def _fmt_number(n: int) -> str:
        if n >= 1_000_000:
            return f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.1f}k"
        return str(n)

    def render(self, output_path: Path | None = None) -> Path:
        """Render the card and return path to the PNG."""
        if output_path is None:
            output_path = TEMP_DIR / "reddit_card.png"

        # ── Fonts ──────────────────────────────────────────────────────────────
        font_sub  = _load_font(34, bold=True)
        font_meta = _load_font(30)
        font_title = _load_font(46, bold=True)
        font_stats = _load_font(30)

        # ── Measure title text ─────────────────────────────────────────────────
        inner_w = CARD_W - 2 * CARD_PADDING
        title_lines = _wrap_text(self.title, font_title, inner_w)

        # ── Compute card height ────────────────────────────────────────────────
        snoo_row_h = 70      # row with icon + sub + meta
        title_line_h = 58    # px per title line
        stats_row_h = 60     # upvote/comment row
        sep_h = 1            # thin divider line
        card_h = (
            CARD_PADDING
            + snoo_row_h
            + 12                              # gap
            + len(title_lines) * title_line_h
            + 20                              # gap before stats
            + sep_h + 8
            + stats_row_h
            + CARD_PADDING
        )

        # ── Card position on 1080×1920 canvas ─────────────────────────────────
        card_x = (VIDEO_W - CARD_W) // 2
        card_y = int(VIDEO_H * CARD_Y_CENTER - card_h // 2)

        # ── Create RGBA canvas ─────────────────────────────────────────────────
        img = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # ── Drop shadow ────────────────────────────────────────────────────────
        shadow_img = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_img)
        for offset in range(12, 0, -1):
            alpha = int(80 * (1 - offset / 12))
            sd.rounded_rectangle(
                (card_x - offset, card_y - offset // 2,
                 card_x + CARD_W + offset, card_y + card_h + offset // 2),
                radius=CARD_RADIUS + 4,
                fill=(0, 0, 0, alpha)
            )
        img = Image.alpha_composite(img, shadow_img)
        draw = ImageDraw.Draw(img)

        # ── Card background ────────────────────────────────────────────────────
        draw.rounded_rectangle(
            (card_x, card_y, card_x + CARD_W, card_y + card_h),
            radius=CARD_RADIUS,
            fill=CARD_BG,
        )

        # ── Layout cursor ──────────────────────────────────────────────────────
        cy = card_y + CARD_PADDING

        # ── Row 1: Snoo + subreddit + meta ────────────────────────────────────
        snoo_cx = card_x + CARD_PADDING + 28
        snoo_cy = cy + snoo_row_h // 2
        _draw_snoo(draw, snoo_cx, snoo_cy, r=28)

        text_x = snoo_cx + 40
        draw.text((text_x, cy + 4), f"r/{self.subreddit}", font=font_sub, fill=(20, 20, 20))
        sub_w = int(draw.textlength(f"r/{self.subreddit}", font=font_sub))
        draw.text((text_x, cy + 4 + 36), f"u/{self.username} · {self.age}", font=font_meta, fill=META_GRAY)

        cy += snoo_row_h + 12

        # ── Row 2: Title ──────────────────────────────────────────────────────
        for line in title_lines:
            draw.text((card_x + CARD_PADDING, cy), line, font=font_title, fill=TITLE_BLACK)
            cy += title_line_h

        cy += 20

        # ── Thin divider ──────────────────────────────────────────────────────
        draw.line(
            (card_x + CARD_PADDING, cy, card_x + CARD_W - CARD_PADDING, cy),
            fill=DIVIDER, width=1
        )
        cy += 8

        # ── Row 3: Stats (upvotes · comments) ────────────────────────────────
        upvote_str  = self.score and self._fmt_number(self.score) or "–"
        comment_str = self.num_comments and self._fmt_number(self.num_comments) or "–"

        # Arrow-up icon (simple triangle)
        arr_x, arr_y = card_x + CARD_PADDING, cy + 15
        draw.polygon(
            [(arr_x + 10, arr_y), (arr_x, arr_y + 18), (arr_x + 20, arr_y + 18)],
            fill=VOTE_ORANGE
        )
        draw.text((arr_x + 28, cy + 12), upvote_str, font=font_stats, fill=VOTE_ORANGE)
        vote_w = int(draw.textlength(upvote_str, font=font_stats))

        # Comment bubble (circle)
        bubble_x = arr_x + 28 + vote_w + 30
        br = 11
        draw.ellipse((bubble_x - br, cy + 15 - br + 9, bubble_x + br, cy + 15 + br + 9), outline=META_GRAY, width=2)
        draw.text((bubble_x + 18, cy + 12), comment_str, font=font_stats, fill=META_GRAY)

        # ── Save ──────────────────────────────────────────────────────────────
        output_path = Path(output_path)
        img.save(str(output_path), format="PNG")
        print(f"✅ Reddit card rendered → {output_path}  ({img.size[0]}×{img.size[1]})")
        return output_path


# ─── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    r = RedditCardRenderer(
        title="What are signs that a person genuinely is unintelligent?",
        subreddit="AskReddit",
        username="leathur_records",
        score=11700,
        num_comments=10000,
        age="2d",
    )
    path = r.render()
    print(f"Saved to {path}")
    img = Image.open(path)
    img.show()
