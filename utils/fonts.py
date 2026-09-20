import os
import struct
import unicodedata
from functools import lru_cache
from PIL import ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
WINDOWS_FONTS_DIR = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")

BOLD_FONT_CANDIDATES = [
    (os.path.join(FONTS_DIR, "Inter-Bold.ttf"), None),
    (os.path.join(FONTS_DIR, "Onest[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "GolosText[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "Unbounded[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "Roboto[wdth,wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "Montserrat[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "OpenSans[wdth,wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "PT_Sans-Web-Bold.ttf"), None),
    (os.path.join(FONTS_DIR, "RussoOne-Regular.ttf"), None),
    (os.path.join(FONTS_DIR, "Rubik[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "Manrope[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "Nunito[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "Mulish[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "Lato-Bold.ttf"), None),
    (os.path.join(FONTS_DIR, "Poppins-Bold.ttf"), None),
    (os.path.join(FONTS_DIR, "FiraCode[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "Comfortaa[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "Oswald[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "PlayfairDisplay[wght].ttf"), "Bold"),
    (os.path.join(FONTS_DIR, "BebasNeue-Regular.ttf"), None),
    (os.path.join(FONTS_DIR, "NotoSans[wdth,wght].ttf"), "Bold"),
    (os.path.join(WINDOWS_FONTS_DIR, "arialbd.ttf"), None),
    (os.path.join(WINDOWS_FONTS_DIR, "segoeuib.ttf"), None),
]

REGULAR_FONT_CANDIDATES = [
    (os.path.join(FONTS_DIR, "Inter-Regular.ttf"), None),
    (os.path.join(FONTS_DIR, "Onest[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "GolosText[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "Roboto[wdth,wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "Montserrat[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "OpenSans[wdth,wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "PT_Sans-Web-Regular.ttf"), None),
    (os.path.join(FONTS_DIR, "Rubik[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "Manrope[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "Nunito[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "Mulish[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "Lato-Regular.ttf"), None),
    (os.path.join(FONTS_DIR, "Poppins-Regular.ttf"), None),
    (os.path.join(FONTS_DIR, "FiraCode[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "Comfortaa[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "Caveat[wght].ttf"), "Regular"),
    (os.path.join(FONTS_DIR, "NotoSans[wdth,wght].ttf"), "Regular"),
    (os.path.join(WINDOWS_FONTS_DIR, "arial.ttf"), None),
    (os.path.join(WINDOWS_FONTS_DIR, "segoeui.ttf"), None),
]

FALLBACK_FONT_CANDIDATES = [
    (os.path.join(FONTS_DIR, "NotoSansMath-Regular.ttf"), None),
    (os.path.join(FONTS_DIR, "NotoSansSymbols[wght].ttf"), None),
    (os.path.join(FONTS_DIR, "NotoSansSymbols2-Regular.ttf"), None),
    (os.path.join(WINDOWS_FONTS_DIR, "seguisym.ttf"), None),
    (os.path.join(WINDOWS_FONTS_DIR, "seguiemj.ttf"), None),
    (os.path.join(WINDOWS_FONTS_DIR, "malgun.ttf"), None),
    (os.path.join(WINDOWS_FONTS_DIR, "msyh.ttc"), None),
    (os.path.join(WINDOWS_FONTS_DIR, "arial.ttf"), None),
    (os.path.join(FONTS_DIR, "NotoSans[wdth,wght].ttf"), "Regular"),
]


def _read_ttf_cmap(font_path: str) -> set[int]:
    """Parse TTF/OTF cmap table to extract set of supported character code points."""
    try:
        with open(font_path, "rb") as f:
            data = f.read()
        if len(data) < 12:
            return set()
        num_tables, = struct.unpack(">H", data[4:6])
        cmap_offset = None
        for i in range(num_tables):
            offset = 12 + i * 16
            if offset + 12 > len(data):
                break
            tag = data[offset : offset + 4]
            if tag == b"cmap":
                cmap_offset, = struct.unpack(">I", data[offset + 8 : offset + 12])
                break
        if not cmap_offset or cmap_offset + 4 > len(data):
            return set()

        num_subtables, = struct.unpack(">H", data[cmap_offset + 2 : cmap_offset + 4])
        chars: set[int] = set()
        subtables = []
        for i in range(num_subtables):
            rec_off = cmap_offset + 4 + i * 8
            if rec_off + 8 > len(data):
                break
            p_id, e_id, sub_off = struct.unpack(">HHI", data[rec_off : rec_off + 8])
            subtables.append((p_id, e_id, cmap_offset + sub_off))

        for _, _, sub_off in subtables:
            if sub_off + 16 > len(data):
                continue
            fmt, = struct.unpack(">H", data[sub_off : sub_off + 2])
            if fmt == 12:
                n_groups, = struct.unpack(">I", data[sub_off + 12 : sub_off + 16])
                for g in range(n_groups):
                    grp_off = sub_off + 16 + g * 12
                    if grp_off + 12 > len(data):
                        break
                    start, end, _ = struct.unpack(">III", data[grp_off : grp_off + 12])
                    chars.update(range(start, end + 1))
                return chars

        for _, _, sub_off in subtables:
            if sub_off + 16 > len(data):
                continue
            fmt, = struct.unpack(">H", data[sub_off : sub_off + 2])
            if fmt == 4:
                seg_count, = struct.unpack(">H", data[sub_off + 6 : sub_off + 8])
                seg_count //= 2
                end_off = sub_off + 14
                end_size = seg_count * 2
                start_off = end_off + end_size + 2
                if start_off + end_size > len(data):
                    continue
                end_codes = struct.unpack(f">{seg_count}H", data[end_off : end_off + end_size])
                start_codes = struct.unpack(f">{seg_count}H", data[start_off : start_off + end_size])
                for start, end in zip(start_codes, end_codes):
                    if end != 0xFFFF:
                        chars.update(range(start, end + 1))
                return chars

        return chars
    except Exception:
        return set()


@lru_cache(maxsize=128)
def get_cached_cmap(font_path: str) -> set[int]:
    return _read_ttf_cmap(font_path)


@lru_cache(maxsize=256)
def get_cached_font(path: str, size: int, variation: str | None = None) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(path, size)
    if variation:
        try:
            font.set_variation_by_name(variation)
        except Exception:
            pass
    return font


class FontManager:
    """Multi-font typography engine with seamless fallback for Russian, English,

    Mathematical Alphanumeric Symbols (Gothic, Fraktur, Script, Double-Struck),
    special characters, symbols, and emojis.
    """

    def __init__(self):
        self._valid_bold = [(p, v) for p, v in BOLD_FONT_CANDIDATES if os.path.isfile(p)]
        self._valid_regular = [(p, v) for p, v in REGULAR_FONT_CANDIDATES if os.path.isfile(p)]
        self._valid_fallbacks = [(p, v) for p, v in FALLBACK_FONT_CANDIDATES if os.path.isfile(p)]

    @lru_cache(maxsize=64)
    def get_font_chain(self, size: int, is_bold: bool = True) -> list[tuple[ImageFont.FreeTypeFont, set[int], str]]:
        primaries = self._valid_bold if is_bold else self._valid_regular
        chain = []
        seen_paths = set()
        for path, var in primaries + self._valid_fallbacks:
            if path in seen_paths:
                continue
            seen_paths.add(path)
            try:
                font = get_cached_font(path, size, var)
                cmap = get_cached_cmap(path)
                chain.append((font, cmap, path))
            except Exception:
                continue
        if not chain:
            default_font = ImageFont.load_default()
            chain.append((default_font, set(), "default"))
        return chain

    def get_runs(self, text: str, size: int, is_bold: bool = True) -> list[tuple[ImageFont.FreeTypeFont, str]]:
        """Split text into continuous runs of characters matching their best font."""
        if not text:
            return []

        chain = self.get_font_chain(size, is_bold)
        primary_font = chain[0][0]
        runs: list[tuple[ImageFont.FreeTypeFont, str]] = []

        for ch in text:
            code = ord(ch)

            if 0xFE00 <= code <= 0xFE0F or code in (0x200D, 0x200B, 0x200C, 0x200E, 0x200F, 0xFEFF):
                continue

            chosen_font: ImageFont.FreeTypeFont | None = None
            resolved_ch = ch

            for font, cmap, _ in chain:
                if code in cmap:
                    chosen_font = font
                    break

            if not chosen_font:
                norm = unicodedata.normalize("NFKC", ch)
                if norm and norm != ch:
                    for font, cmap, _ in chain:
                        if ord(norm[0]) in cmap:
                            chosen_font = font
                            resolved_ch = norm
                            break

            if not chosen_font:
                for font, cmap, _ in chain[1:]:
                    if ord("?") in cmap:
                        chosen_font = font
                        break
                if not chosen_font:
                    chosen_font = primary_font

            if runs and runs[-1][0] is chosen_font:
                runs[-1] = (chosen_font, runs[-1][1] + resolved_ch)
            else:
                runs.append((chosen_font, resolved_ch))

        return runs

    def measure_text_width(self, draw: ImageDraw.Draw, text: str, size: int, is_bold: bool = True) -> float:
        runs = self.get_runs(text, size, is_bold)
        return sum(draw.textlength(run_text, font=f) for f, run_text in runs)

    def measure_text_bbox(self, draw: ImageDraw.Draw, text: str, size: int, is_bold: bool = True) -> tuple[int, int, int, int]:
        runs = self.get_runs(text, size, is_bold)
        if not runs:
            return (0, 0, 0, 0)
        total_w = 0.0
        max_h = 0
        min_top = 0
        for f, run_text in runs:
            total_w += draw.textlength(run_text, font=f)
            bbox = draw.textbbox((0, 0), run_text, font=f)
            min_top = min(min_top, bbox[1])
            max_h = max(max_h, bbox[3] - bbox[1])
        return (0, int(min_top), int(total_w), int(max_h))

    def draw_text(
        self,
        draw: ImageDraw.Draw,
        xy: tuple[float, float],
        text: str,
        size: int,
        fill: tuple,
        is_bold: bool = True,
        center_x: float | None = None,
    ) -> float:
        """Render multi-font text aligned along a shared typographic baseline."""
        runs = self.get_runs(text, size, is_bold)
        if not runs:
            return 0.0

        total_w = sum(draw.textlength(run_text, font=f) for f, run_text in runs)
        cur_x, cur_y = xy
        if center_x is not None:
            cur_x = center_x - total_w / 2.0

        primary_font = self.get_font_chain(size, is_bold)[0][0]
        baseline_y = cur_y + getattr(primary_font.font, "ascent", size)

        for font, run_text in runs:
            draw.text((cur_x, baseline_y), run_text, font=font, fill=fill, anchor="ls")
            cur_x += draw.textlength(run_text, font=font)

        return total_w

    def wrap_text(self, draw: ImageDraw.Draw, text: str, size: int, max_width: float, is_bold: bool = True) -> list[str]:
        """Wrap text into multiple lines respecting fallback width measurements."""
        lines = []
        for raw_line in text.splitlines() or [""]:
            words = raw_line.split()
            if not words:
                lines.append("")
                continue
            current = ""
            for word in words:
                test = f"{current} {word}".strip()
                if self.measure_text_width(draw, test, size, is_bold) <= max_width:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = word
            if current:
                lines.append(current)
        return lines

    def fit_quote_font(
        self,
        draw: ImageDraw.Draw,
        text: str,
        max_width: float,
        max_height: float,
        initial_size: int = 44,
        min_size: int = 22,
    ) -> tuple[int, list[str], int]:
        """Dynamically fit text within dimensions by adjusting font size."""
        size = initial_size
        while size > min_size:
            lines = self.wrap_text(draw, text, size, max_width, is_bold=True)
            line_h = size + 12
            if len(lines) * line_h <= max_height:
                return size, lines, line_h
            size -= 2
        lines = self.wrap_text(draw, text, min_size, max_width, is_bold=True)
        return min_size, lines, min_size + 12


font_manager = FontManager()
