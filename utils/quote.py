from io import BytesIO
import os
import json
import tempfile
import hashlib
import math
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter, ImageSequence
import numpy as np
import imageio

from .fonts import (
    font_manager,
    BOLD_FONT_CANDIDATES,
    REGULAR_FONT_CANDIDATES,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
background_path = os.path.join(BASE_DIR, "background.png")
background_anim_path = os.path.join(BASE_DIR, "background_anim.mp4")
settings_path = os.path.join(BASE_DIR, "settings.json")

DEFAULT_BLUR_PERCENT = 25


width, height = 1280, 720
card_margin = 30
card_radius = 42
padding = 58
inner_v_padding = 34

avatar_size = 440
avatar_border = 3

attachment_w, attachment_h = 240, 360
attachment_radius = 18

font_size_username = 30
font_size_name = 52
font_size_date = 22
font_size_quote = 44
font_size_quote_mark = 72

quote_text_offset = 34

accent_color = (227, 179, 65)
text_color = (255, 255, 255)
muted_color = (175, 175, 175)

avatar_palette = [
    (255, 122, 92),
    (255, 165, 82),
    (255, 200, 87),
    (135, 211, 124),
    (94, 199, 194),
    (94, 168, 222),
    (129, 140, 248),
    (198, 120, 221),
    (240, 98, 146),
]

bold_font_candidates = BOLD_FONT_CANDIDATES
regular_font_candidates = REGULAR_FONT_CANDIDATES


@lru_cache(maxsize=None)
def _resolve_font(candidates, size):
    for path, variation in candidates:
        if not os.path.isfile(path):
            continue
        try:
            font = ImageFont.truetype(path, size)
        except Exception:
            continue
        if variation:
            try:
                font.set_variation_by_name(variation)
            except Exception:
                pass
        return font
    return ImageFont.load_default()


def _load_font(candidates, size):
    return _resolve_font(tuple(candidates), size)


@lru_cache(maxsize=16)
def _get_circle_mask(size):
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask


@lru_cache(maxsize=16)
def _get_rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def _wrap_text(draw, text, font, max_width):
    lines = []
    for raw_line in text.splitlines() or [""]:
        words = raw_line.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    return lines


def _fit_quote_font(draw, text, max_width, max_height):
    font_size, lines, line_h = font_manager.fit_quote_font(
        draw, text, max_width, max_height, initial_size=font_size_quote, min_size=22
    )
    font = _load_font(bold_font_candidates, font_size)
    return font, lines, line_h


def _initials(name):
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _seed_color(seed):
    digest = hashlib.sha256(str(seed).encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(avatar_palette)
    return avatar_palette[index]


def _make_fallback_avatar(size, name, seed=None):
    color = _seed_color(seed if seed is not None else name)
    canvas = Image.new("RGB", (size, size), color)
    draw = ImageDraw.Draw(canvas)
    letters = _initials(name)
    font_size = int(size * 0.4)

    w = font_manager.measure_text_width(draw, letters, font_size, is_bold=True)
    h = font_size
    font_manager.draw_text(
        draw,
        ((size - w) / 2.0, (size - h) / 2.0 - 6),
        letters,
        font_size,
        fill=(255, 255, 255),
        is_bold=True,
    )
    return canvas


def _make_avatar(avatar_bytes, size, fallback_name="?", fallback_seed=None):
    if avatar_bytes:
        try:
            avatar = Image.open(BytesIO(avatar_bytes)).convert("RGB")
        except Exception:
            avatar = _make_fallback_avatar(size, fallback_name, fallback_seed)
    else:
        avatar = _make_fallback_avatar(size, fallback_name, fallback_seed)

    avatar = ImageOps.fit(avatar, (size, size), method=Image.BILINEAR)
    mask = _get_circle_mask(size)

    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(avatar, (0, 0), mask)
    return result


def _make_rounded_image(img, size, radius):
    img = ImageOps.fit(img, size, method=Image.BILINEAR)
    mask = _get_rounded_mask(size, radius)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)
    return result


def _load_raw_background(source):
    try:
        if isinstance(source, (bytes, bytearray)):
            bg = Image.open(BytesIO(source)).convert("RGB")
        else:
            bg = Image.open(source).convert("RGB")
        return ImageOps.fit(bg, (width, height), method=Image.BILINEAR)
    except Exception:
        return None


def _base_scene(raw_bg):
    if raw_bg is None:
        return Image.new("RGBA", (width, height), (15, 15, 15, 255))
    dimmed = raw_bg.filter(ImageFilter.GaussianBlur(5))
    dark = Image.new("RGB", dimmed.size, (0, 0, 0))
    return Image.blend(dimmed, dark, 0.52).convert("RGBA")


@lru_cache(maxsize=4)
def _vertical_fade(size, top_alpha, bottom_alpha):
    w, h = size
    fade = Image.new("L", (1, h))
    for i in range(h):
        t = i / max(h - 1, 1)
        fade.putpixel((0, i), int(top_alpha + (bottom_alpha - top_alpha) * t))
    return fade.resize((w, h))


def get_blur_percent() -> int:
    """Get the current blur percentage (0-150%). Default is 25% (10px)."""
    try:
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return int(data.get("blur_percent", DEFAULT_BLUR_PERCENT))
    except Exception:
        pass
    return DEFAULT_BLUR_PERCENT


def get_blur_radius() -> int:
    """Get blur radius in pixels (25% -> 10px, 50% -> 20px, 100% -> 40px)."""
    p = get_blur_percent()
    return int(round(p * 0.4))


def set_blur_percent(percent: int) -> tuple[int, int]:
    """Set blur percentage, save to settings.json, and reload background cache.
    Returns (percent, radius_px).
    """
    percent = max(0, min(150, percent))
    data = {}
    try:
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception:
        data = {}
    data["blur_percent"] = percent
    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[ERROR saving settings]: {e}")
    reload_background()
    return percent, int(round(percent * 0.4))


def reset_blur_percent() -> tuple[int, int]:
    """Reset blur to default value (25% / 10px)."""
    return set_blur_percent(DEFAULT_BLUR_PERCENT)


def _glass_card(img, raw_bg, box, radius):
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0

    mask = _get_rounded_mask((w, h), radius)

    if raw_bg is not None:
        crop = raw_bg.crop(box)
        blur_r = get_blur_radius()
        if blur_r > 0:
            blurred = crop.filter(ImageFilter.GaussianBlur(blur_r))
        else:
            blurred = crop
    else:
        blurred = Image.new("RGB", (w, h), (22, 22, 22))

    dark_tint = Image.new("RGB", (w, h), (14, 14, 14))
    blurred = Image.blend(blurred, dark_tint, 0.45)

    glass_rgba = blurred.convert("RGBA")
    glass_rgba.putalpha(mask)

    glass_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    glass_layer.paste(glass_rgba, (x0, y0), glass_rgba)
    img = Image.alpha_composite(img, glass_layer)

    fade = _vertical_fade((w, h), 35, 0)
    shine = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    shine.putalpha(Image.composite(fade, Image.new("L", (w, h), 0), mask))
    shine_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shine_layer.paste(shine, (x0, y0), shine)
    img = Image.alpha_composite(img, shine_layer)

    border_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(border_layer).rounded_rectangle(
        box, radius=radius, outline=(255, 255, 255, 75), width=2
    )
    img = Image.alpha_composite(img, border_layer)

    return img


_CACHED_DEFAULT_CARD = None


BACKGROUNDS_DIR = os.path.join(BASE_DIR, "backgrounds")
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)

_USER_CARDS_CACHE: dict[int, Image.Image] = {}


def reload_background():
    """Clear cached background card so changes apply immediately."""
    global _CACHED_DEFAULT_CARD, _USER_CARDS_CACHE
    _CACHED_DEFAULT_CARD = None
    _USER_CARDS_CACHE.clear()


def clear_user_background_cache(user_id: int):
    global _USER_CARDS_CACHE
    _USER_CARDS_CACHE.pop(user_id, None)


def get_user_background_path(user_id: int | None) -> str | None:
    if not user_id:
        return None
    p = os.path.join(BACKGROUNDS_DIR, f"{user_id}.png")
    return p if os.path.isfile(p) else None


def save_user_background(user_id: int, image: Image.Image) -> str:
    os.makedirs(BACKGROUNDS_DIR, exist_ok=True)
    p = os.path.join(BACKGROUNDS_DIR, f"{user_id}.png")
    image.save(p, format="PNG")
    clear_user_background_cache(user_id)
    return p


def reset_user_background(user_id: int) -> bool:
    p = os.path.join(BACKGROUNDS_DIR, f"{user_id}.png")
    if os.path.isfile(p):
        try:
            os.remove(p)
            clear_user_background_cache(user_id)
            return True
        except Exception:
            pass
    return False


def _get_default_card():
    global _CACHED_DEFAULT_CARD
    if _CACHED_DEFAULT_CARD is None:
        raw_bg = _load_raw_background(background_path)
        base = _base_scene(raw_bg)
        card_box = (card_margin, card_margin, width - card_margin, height - card_margin)
        _CACHED_DEFAULT_CARD = _glass_card(base, raw_bg, card_box, card_radius)
    return _CACHED_DEFAULT_CARD.copy()


def _get_card_for_user(user_id: int | None = None) -> Image.Image:
    if user_id and user_id in _USER_CARDS_CACHE:
        return _USER_CARDS_CACHE[user_id].copy()

    user_bg = get_user_background_path(user_id)
    if user_bg:
        try:
            raw_bg = _load_raw_background(user_bg)
            base = _base_scene(raw_bg)
            card_box = (card_margin, card_margin, width - card_margin, height - card_margin)
            card = _glass_card(base, raw_bg, card_box, card_radius)
            if user_id:
                _USER_CARDS_CACHE[user_id] = card
            return card.copy()
        except Exception as e:
            print(f"[WARN] Error loading user {user_id} background: {e}")

    return _get_default_card()


def _prepare_quote_base(
    quote,
    author,
    username=None,
    avatar_bytes=None,
    background_bytes=None,
    has_attachment=False,
    timestamp=None,
    avatar_seed=None,
    user_id=None,
):
    if background_bytes:
        raw_bg = _load_raw_background(background_bytes)
        img = _base_scene(raw_bg)
        card_box = (card_margin, card_margin, width - card_margin, height - card_margin)
        img = _glass_card(img, raw_bg, card_box, card_radius)
    else:
        img = _get_card_for_user(user_id)

    draw = ImageDraw.Draw(img)
    avatar_x = card_margin + padding
    left_column_center = avatar_x + avatar_size // 2
    avatar_y = card_margin + 28

    border_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(border_layer).ellipse(
        (
            avatar_x - avatar_border,
            avatar_y - avatar_border,
            avatar_x + avatar_size + avatar_border,
            avatar_y + avatar_size + avatar_border,
        ),
        outline=(255, 255, 255, 255),
        width=avatar_border,
    )
    img = Image.alpha_composite(img, border_layer)

    avatar = _make_avatar(avatar_bytes, avatar_size, fallback_name=author, fallback_seed=avatar_seed or username or author)
    img.paste(avatar, (avatar_x, avatar_y), avatar)
    draw = ImageDraw.Draw(img)

    y = avatar_y + avatar_size + 36

    if username:
        uw = font_manager.measure_text_width(draw, username, font_size_username, is_bold=True)
        ux = left_column_center - uw / 2.0
        font_manager.draw_text(
            draw,
            (0, y),
            username,
            font_size_username,
            fill=accent_color,
            is_bold=True,
            center_x=left_column_center,
        )
        underline_y = y + 36
        draw.line((ux - 4, underline_y, ux + uw + 4, underline_y), fill=accent_color, width=3)
        y = underline_y + 14

    curr_name_size = font_size_name
    while curr_name_size > 26:
        name_w = font_manager.measure_text_width(draw, author, curr_name_size, is_bold=True)
        if name_w <= avatar_size + 60:
            break
        curr_name_size -= 2

    font_manager.draw_text(
        draw,
        (0, y),
        author,
        curr_name_size,
        fill=text_color,
        is_bold=True,
        center_x=left_column_center,
    )

    quote_mark_x = avatar_x + avatar_size + 82
    quote_x = quote_mark_x + quote_text_offset
    quote_right = width - card_margin - padding
    if has_attachment:
        quote_right = width - card_margin - padding + 22 - attachment_w - 28
    quote_max_w = quote_right - quote_x
    quote_max_h = height - 2 * (card_margin + 40)

    font_quote_size, lines, line_h = font_manager.fit_quote_font(
        draw, quote, quote_max_w, quote_max_h, initial_size=font_size_quote, min_size=22
    )
    total_h = len(lines) * line_h
    text_y = (height - total_h) // 2 - 10

    for line in lines:
        font_manager.draw_text(
            draw,
            (quote_x, text_y),
            line,
            font_quote_size,
            fill=text_color,
            is_bold=True,
        )
        text_y += line_h

    if timestamp:
        ts_w = font_manager.measure_text_width(draw, timestamp, font_size_date, is_bold=False)
        _, _, _, ts_h = font_manager.measure_text_bbox(draw, timestamp, font_size_date, is_bold=False)
        ts_x = width - card_margin - padding - ts_w
        ts_y = height - card_margin - padding - ts_h
        font_manager.draw_text(
            draw,
            (ts_x, ts_y),
            timestamp,
            font_size_date,
            fill=muted_color,
            is_bold=False,
        )

    return img, quote_mark_x, (height - total_h) // 2 - 10


def generate_quote_image(
    quote,
    author,
    username=None,
    avatar_bytes=None,
    background_bytes=None,
    attachment_bytes=None,
    timestamp=None,
    avatar_seed=None,
    user_id=None,
):
    has_attachment = False
    att_img = None
    if attachment_bytes:
        try:
            att = Image.open(BytesIO(attachment_bytes)).convert("RGB")
            att_img = _make_rounded_image(att, (attachment_w, attachment_h), attachment_radius)
            has_attachment = True
        except Exception:
            has_attachment = False

    img, quote_mark_x, text_y = _prepare_quote_base(
        quote=quote,
        author=author,
        username=username,
        avatar_bytes=avatar_bytes,
        background_bytes=background_bytes,
        has_attachment=has_attachment,
        timestamp=timestamp,
        avatar_seed=avatar_seed,
        user_id=user_id,
    )

    draw = ImageDraw.Draw(img)
    font_quote_mark = _load_font(bold_font_candidates, font_size_quote_mark)
    draw.text((quote_mark_x, text_y - 68), "\u201c", font=font_quote_mark, fill=accent_color)

    if has_attachment and att_img:
        att_x = width - card_margin - padding + 22 - attachment_w
        att_y = (height - attachment_h) // 2 - 65
        img.paste(att_img, (att_x, att_y), att_img)

    buffer = BytesIO()
    img.convert("RGB").save(buffer, format="PNG", compress_level=1)
    buffer.seek(0)
    buffer.name = "quote.png"
    return buffer


def _extract_attachment_frames(attachment_bytes, is_animated=True, max_frames=30):
    """Extract frames from an attachment (GIF or MP4/video or static image)."""
    if not attachment_bytes:
        return []

    if is_animated:
        try:
            im = Image.open(BytesIO(attachment_bytes))
            if getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1:
                n = getattr(im, "n_frames", 1)
                step = max(1, n // max_frames)
                frames = []
                for i, frame in enumerate(ImageSequence.Iterator(im)):
                    if i % step == 0:
                        frames.append(frame.convert("RGB"))
                        if len(frames) >= max_frames:
                            break
                if frames:
                    return frames
        except Exception:
            pass

        tmp_path = None
        try:
            suffix = ".mp4"
            if attachment_bytes.startswith((b"GIF87a", b"GIF89a")):
                suffix = ".gif"
            elif attachment_bytes.startswith(b"\x1a\x45\xdf\xa3"):
                suffix = ".webm"

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(attachment_bytes)
                tmp_path = f.name
            reader = imageio.get_reader(tmp_path)
            try:
                total_frames = reader.count_frames()
            except Exception:
                total_frames = 0
            step = max(1, total_frames // max_frames) if total_frames > max_frames else 1

            frames = []
            for i, frame in enumerate(reader):
                if i % step == 0:
                    frames.append(Image.fromarray(frame).convert("RGB"))
                    if len(frames) >= max_frames:
                        break
            reader.close()
            if frames:
                return frames
        except Exception:
            pass
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    try:
        static_img = Image.open(BytesIO(attachment_bytes)).convert("RGB")
        return [static_img]
    except Exception:
        return []


def generate_quote_animation(
    quote,
    author,
    username=None,
    avatar_bytes=None,
    background_bytes=None,
    attachment_bytes=None,
    is_attachment_animated=False,
    timestamp=None,
    avatar_seed=None,
    fps=15,
    max_frames=30,
    user_id=None,
) -> BytesIO:
    """Generate an animated looping GIF/MP4 quote."""
    raw_frames = []
    has_attachment = False

    if attachment_bytes:
        raw_frames = _extract_attachment_frames(
            attachment_bytes,
            is_animated=is_attachment_animated,
            max_frames=max_frames,
        )
        if raw_frames:
            has_attachment = True

    img, quote_mark_x, text_y = _prepare_quote_base(
        quote=quote,
        author=author,
        username=username,
        avatar_bytes=avatar_bytes,
        background_bytes=background_bytes,
        has_attachment=has_attachment,
        timestamp=timestamp,
        avatar_seed=avatar_seed,
        user_id=user_id,
    )

    font_quote_mark = _load_font(bold_font_candidates, font_size_quote_mark)
    att_x = width - card_margin - padding + 22 - attachment_w
    att_y = (height - attachment_h) // 2 - 65

    output_frames = []

    if has_attachment and len(raw_frames) > 1:
        while len(raw_frames) < 15:
            raw_frames = raw_frames + raw_frames
        if len(raw_frames) > max_frames:
            raw_frames = raw_frames[:max_frames]

        for frame in raw_frames:
            canvas = img.copy()
            draw = ImageDraw.Draw(canvas)
            draw.text((quote_mark_x, text_y - 68), "\u201c", font=font_quote_mark, fill=accent_color)
            att_rounded = _make_rounded_image(frame, (attachment_w, attachment_h), attachment_radius)
            canvas.paste(att_rounded, (att_x, att_y), att_rounded)
            output_frames.append(canvas.convert("RGB"))
    else:
        num_frames = 15
        att_rounded = None
        if has_attachment and raw_frames:
            att_rounded = _make_rounded_image(raw_frames[0], (attachment_w, attachment_h), attachment_radius)

        for i in range(num_frames):
            canvas = img.copy()
            draw = ImageDraw.Draw(canvas)
            factor = 0.70 + 0.30 * math.sin(i / num_frames * 2 * math.pi)
            r = int(accent_color[0] * factor)
            g = int(accent_color[1] * factor)
            b = int(accent_color[2] * factor)
            draw.text((quote_mark_x, text_y - 68), "\u201c", font=font_quote_mark, fill=(r, g, b))
            if att_rounded:
                canvas.paste(att_rounded, (att_x, att_y), att_rounded)
            output_frames.append(canvas.convert("RGB"))

    out_buf = BytesIO()
    with imageio.get_writer(
        out_buf,
        format="mp4",
        fps=fps,
        codec="libx264",
        pixelformat="yuv420p",
        output_params=["-movflags", "+faststart"],
    ) as writer:
        for f in output_frames:
            writer.append_data(np.array(f))

    thumb_buf = BytesIO()
    thumb_img = img.resize((320, 180), Image.BILINEAR).convert("RGB")
    thumb_img.save(thumb_buf, format="JPEG", quality=80)
    thumb_buf.seek(0)
    thumb_buf.name = "thumb.jpg"

    out_buf.seek(0)
    out_buf.name = "quote.mp4"
    out_buf.thumb = thumb_buf
    out_buf.duration = max(1, round(len(output_frames) / fps))
    return out_buf


