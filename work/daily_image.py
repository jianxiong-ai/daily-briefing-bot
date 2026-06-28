#!/usr/bin/env python3
import html
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
import uuid

from PIL import Image, ImageDraw, ImageFont


DEFAULT_WIDTH = 1080
OUTER_X = 56
CARD_X = 58
CARD_GAP = 54
PANEL_GAP = 28
PANEL_PAD_X = 42
PANEL_PAD_Y = 34
LINE_GAP = 18
PARAGRAPH_GAP = 26
BLOCK_TITLE_GAP = 24
PARAGRAPH_MIN_CHARS = 72
PARAGRAPH_SOFT_MAX_CHARS = 132

CARD_BG = "#eaf4ff"
PANEL_BG = "#fafdff"
BLUE = "#1788ff"
CYAN = "#21d4d6"
TEXT = "#21304a"
MUTED = "#6a7894"
RULE = "#c8ddf4"


def _first_existing(candidates):
    for path in candidates:
        if os.path.exists(path):
            return path
    return ""


# Regular weight: prefer macOS system fonts (launchd host), fall back to the
# Noto CJK font installed in the Docker image so containers render CJK too.
REGULAR_FONT_PATH = _first_existing(
    [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-VF.otf",
    ]
)
# Bold weight: macOS uses a heavier face inside PingFang.ttc (index 2); on Linux
# we ship a dedicated bold file when available, else fall back to regular.
BOLD_FONT_PATH = (
    _first_existing(
        [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        ]
    )
    or REGULAR_FONT_PATH
)
FONT_PATH = REGULAR_FONT_PATH


def _font(size, bold=False):
    path = BOLD_FONT_PATH if bold else REGULAR_FONT_PATH
    if path:
        try:
            index = 2 if bold and path.endswith("PingFang.ttc") else 0
            return ImageFont.truetype(path, size=size, index=index)
        except Exception:
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _font_with_index(size, index):
    # PingFang.ttc exposes a distinct body weight at this index on macOS; other
    # platforms have no equivalent collection layout, so use the regular face.
    if REGULAR_FONT_PATH.endswith("PingFang.ttc"):
        try:
            return ImageFont.truetype(REGULAR_FONT_PATH, size=size, index=index)
        except Exception:
            pass
    return _font(size, False)


TITLE_FONT = _font(58, True)
SUBTITLE_FONT = _font(27, True)
CHIP_FONT = _font(32, True)
SECTION_FONT = _font(33, True)
BODY_FONT = _font_with_index(32, 1)
BOLD_FONT = _font(32, True)
SMALL_FONT = _font(26, False)


def compact_text(value):
    value = html.unescape(str(value or ""))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def sanitize_display_text(value):
    value = str(value or "")
    value = value.replace("大户助理-囚", "大户助理-可")
    value = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufe0e\ufe0f]", "", value)
    value = re.sub(r"[\ue000-\uf8ff]", "", value)
    normalized = []
    for char in value:
        if "LATIN" not in unicodedata.name(char, ""):
            normalized.append(char)
            continue
        normalized.extend(
            item
            for item in unicodedata.normalize("NFKD", char)
            if not unicodedata.combining(item)
        )
    return "".join(normalized)


def strip_markdown(value):
    value = str(value or "")
    value = re.sub(r"</?font\b[^>]*>", "", value)
    value = value.replace("**", "")
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    return sanitize_display_text(html.unescape(value))


def parse_line_spans(line):
    line = str(line or "")
    plain_line = strip_markdown(line).strip()
    prefix_match = re.match(r"^([\u4e00-\u9fffA-Za-z0-9 /+·&（）()《》-]{2,18})([：:])(.+)$", plain_line)
    if prefix_match and not plain_line.startswith(("范围：", "重点：", "作者：", "博主：")):
        return [
            (prefix_match.group(1), BOLD_FONT, BLUE),
            (prefix_match.group(2), BODY_FONT, TEXT),
            (prefix_match.group(3), BODY_FONT, TEXT),
        ]
    spans = []
    pos = 0
    pattern = re.compile(
        r"<font\s+color=\"?blue\"?>(?:\*\*)?(.+?)(?:\*\*)?</font>|\[([^\]]+)\]\([^)]+\)|(\*\*([^*]+)\*\*)",
        re.I,
    )
    for match in pattern.finditer(line):
        if match.start() > pos:
            spans.append((strip_markdown(line[pos : match.start()]), BODY_FONT, TEXT))
        if match.group(1) is not None:
            spans.append((strip_markdown(match.group(1)), BODY_FONT, BLUE))
        elif match.group(2) is not None:
            spans.append((strip_markdown(match.group(2)), BODY_FONT, BLUE))
        elif match.group(4) is not None:
            spans.append((strip_markdown(match.group(4)), BODY_FONT, TEXT))
        pos = match.end()
    if pos < len(line):
        spans.append((strip_markdown(line[pos:]), BODY_FONT, TEXT))
    clean = []
    for text, font, color in spans:
        text = html.unescape(text)
        if text:
            clean.append((text, font, color))
    return clean or [("", BODY_FONT, TEXT)]


def is_section_heading(line):
    value = str(line or "").strip()
    return value.startswith("**") and value.endswith("**") and len(strip_markdown(value)) <= 24


def wrap_spans(draw, spans, max_width):
    lines = []
    current = []
    current_width = 0

    def flush():
        nonlocal current, current_width
        lines.append(current or [("", BODY_FONT, TEXT)])
        current = []
        current_width = 0

    for text, font, color in spans:
        buffer = ""
        for char in text:
            tentative = buffer + char
            width = draw.textlength(tentative, font=font)
            if current_width + width <= max_width:
                buffer = tentative
                continue
            if buffer:
                current.append((buffer, font, color))
                current_width += draw.textlength(buffer, font=font)
                buffer = char
            if current_width + draw.textlength(buffer, font=font) > max_width and current:
                flush()
        if buffer:
            current.append((buffer, font, color))
            current_width += draw.textlength(buffer, font=font)
    if current:
        flush()
    return lines or [[("", BODY_FONT, TEXT)]]


def split_spans_into_paragraphs(spans):
    paragraphs = []
    current = []
    visible_chars = 0

    def append_char(char, font, color):
        if current and current[-1][1] == font and current[-1][2] == color:
            text, old_font, old_color = current[-1]
            current[-1] = (text + char, old_font, old_color)
        else:
            current.append((char, font, color))

    def flush():
        nonlocal current, visible_chars
        if current:
            paragraphs.append(current)
        current = []
        visible_chars = 0

    for text, font, color in spans:
        for char in text:
            append_char(char, font, color)
            if not char.isspace():
                visible_chars += 1
            if char in "。！？；!?" and visible_chars >= PARAGRAPH_MIN_CHARS:
                flush()
            elif char in "，、," and visible_chars >= PARAGRAPH_SOFT_MAX_CHARS:
                flush()
    flush()
    return paragraphs or [spans]


def line_height(spans):
    sizes = []
    for _text, font, _color in spans:
        bbox = font.getbbox("国")
        sizes.append(bbox[3] - bbox[1])
    return max(sizes or [28])


def text_width(draw, text, font):
    return draw.textlength(str(text or ""), font=font)


def draw_centered_text(draw, x1, x2, y, text, font, fill):
    width = text_width(draw, text, font)
    draw.text((x1 + (x2 - x1 - width) / 2, y), text, font=font, fill=fill)


def split_title(title):
    title = compact_text(title)
    title = re.sub(r"^(知识星球日报)\s+知识星球(\s+\d{4}-\d{2}-\d{2})$", r"\1\2", title)
    if len(title) <= 12:
        return [title]
    parts = title.split()
    if len(parts) >= 2:
        first = parts[0]
        rest = " ".join(parts[1:])
        if len(first) <= 12:
            return [first, rest]
    midpoint = len(title) // 2
    return [title[:midpoint], title[midpoint:]]


def section_heading_text(section, fallback):
    first = ""
    for line in section:
        if is_section_heading(line):
            text = strip_markdown(line)
            if not first:
                first = text
            if text != "昨夜补遗":
                return text
    return first or fallback


def whole_blue_heading(line):
    value = str(line or "").strip()
    match = re.fullmatch(r"<font\s+color=\"?blue\"?>(?:\*\*)?(.+?)(?:\*\*)?</font>", value, flags=re.I)
    if match:
        return strip_markdown(match.group(1))
    return ""


def split_section_blocks(section):
    heading_seen = False
    section_heading = ""
    blocks = []
    current_title = ""
    current_lines = []

    def flush():
        nonlocal current_title, current_lines
        if current_title or current_lines:
            blocks.append({"title": current_title, "lines": current_lines})
        current_title = ""
        current_lines = []

    for raw_line in section:
        line = str(raw_line or "").rstrip()
        plain_line = strip_markdown(line).strip()
        if plain_line.startswith(("原文：", "原文入口", "完整版：", "分条新闻：")):
            continue
        if not heading_seen and is_section_heading(line):
            heading_seen = True
            section_heading = strip_markdown(line)
            if section_heading == "昨夜补遗":
                current_title = section_heading
            continue
        if not line:
            if current_title and not current_lines:
                continue
            flush()
            continue
        if current_title == "昨夜补遗" and re.match(r"^范围[：:]", strip_markdown(line)):
            continue
        blue_title = whole_blue_heading(line)
        if is_section_heading(line):
            flush()
            current_title = strip_markdown(line)
            continue
        if blue_title:
            flush()
            current_title = blue_title
            continue
        current_lines.append(line)
    flush()
    return blocks


def measure_rich_lines(draw, lines, max_width):
    measured = []
    height = 0
    for raw_line in lines:
        is_list_item = bool(re.match(r"^\s*\d+[.、]", strip_markdown(raw_line)))
        spans = parse_line_spans(raw_line)
        if str(raw_line).startswith("原文"):
            spans = [(strip_markdown(raw_line), SMALL_FONT, MUTED)]
        paragraphs = split_spans_into_paragraphs(spans)
        for paragraph_index, paragraph_spans in enumerate(paragraphs):
            wrapped = wrap_spans(draw, paragraph_spans, max_width)
            paragraph_break = paragraph_index < len(paragraphs) - 1
            measured.append(
                {
                    "wrapped": wrapped,
                    "is_list_item": is_list_item and paragraph_index == 0,
                    "paragraph_break": paragraph_break,
                }
            )
            for wrapped_spans in wrapped:
                height += line_height(wrapped_spans) + LINE_GAP
            if paragraph_break:
                height += PARAGRAPH_GAP
            else:
                height += 16 if is_list_item else 8
    return measured, max(0, height - 8)


def measure_block(draw, block, panel_width):
    content_width = panel_width - PANEL_PAD_X * 2 - 18
    height = PANEL_PAD_Y * 2
    title = block.get("title", "")
    title_lines = []
    if title:
        title_lines = wrap_spans(draw, [(title, BOLD_FONT, BLUE)], content_width)
        for wrapped in title_lines:
            height += line_height(wrapped) + 8
        height += BLOCK_TITLE_GAP
    measured, lines_height = measure_rich_lines(draw, block.get("lines") or [], content_width)
    height += lines_height
    return {"block": block, "title_lines": title_lines, "lines": measured, "height": max(112, height)}


def layout_sections(title, sections, width=DEFAULT_WIDTH):
    measure = Image.new("RGB", (width, 100), CARD_BG)
    draw = ImageDraw.Draw(measure)
    card_width = width - CARD_X * 2
    panel_width = card_width - 58 * 2
    ops = []
    header_height = 410
    y = header_height + 24
    for section_index, section in enumerate(sections):
        heading = section_heading_text(section, f"Section {section_index + 1}")
        section_blocks = split_section_blocks(section)
        if not section_blocks:
            continue
        blocks = [measure_block(draw, block, panel_width) for block in section_blocks]
        panels_height = sum(item["height"] for item in blocks) + PANEL_GAP * max(0, len(blocks) - 1)
        card_top = y + 24
        card_height = panels_height + 104
        ops.append(("card", card_top, heading, blocks, card_height))
        y = card_top + card_height + CARD_GAP
    total_height = max(y + 160, header_height + 520)
    return ops, total_height, header_height


def lerp(a, b, t):
    return int(a + (b - a) * t)


def hex_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))


def make_background(width, height):
    top = hex_rgb("#1bb7f4")
    bottom = hex_rgb("#1452cc")
    image = Image.new("RGB", (width, height), bottom)
    pixels = image.load()
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(lerp(top[i], bottom[i], t) for i in range(3))
        for x in range(width):
            pixels[x, y] = color
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for radius in range(360, 1600, 92):
        box = (width // 2 - radius, -radius // 2, width // 2 + radius, radius * 2)
        draw.arc(box, 198, 345, fill=(255, 255, 255, 22), width=3)
    for offset in range(0, width, 110):
        draw.line((offset - 220, height - 280, offset + 120, height - 120), fill=(0, 235, 255, 32), width=4)
    draw.ellipse((-170, height - 520, 260, height - 90), outline=(30, 240, 255, 76), width=5)
    for index, x in enumerate(range(70, width - 80, 160)):
        h = 115 + (index % 3) * 70
        draw.polygon(
            [(x, height - 70), (x, height - 70 - h), (x + 88, height - 118 - h), (x + 88, height - 70)],
            fill=(35, 143, 245, 72),
        )
    image = Image.alpha_composite(image.convert("RGBA"), overlay)
    return image.convert("RGB")


def draw_shadowed_round(draw, xy, radius, fill, outline=None, width=1, shadow=True):
    x1, y1, x2, y2 = xy
    if shadow:
        draw.rounded_rectangle((x1 + 3, y1 + 5, x2 + 3, y2 + 5), radius=radius, fill=(25, 96, 170, 14))
        draw.rounded_rectangle((x1 + 6, y1 + 9, x2 + 6, y2 + 9), radius=radius + 2, fill=(25, 96, 170, 7))
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def draw_gradient_chip(image, xy, radius, text, font):
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    mask = Image.new("L", image.size, 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle(xy, radius=radius, fill=255)
    x1, y1, x2, y2 = [int(value) for value in xy]
    grad = Image.new("RGBA", image.size, (0, 0, 0, 0))
    pixels = grad.load()
    left = hex_rgb("#148dff")
    right = hex_rgb("#25d6d3")
    for x in range(x1, x2):
        t = (x - x1) / max(1, x2 - x1)
        color = tuple(lerp(left[i], right[i], t) for i in range(3)) + (255,)
        for y in range(y1, y2):
            pixels[x, y] = color
    overlay = Image.composite(grad, overlay, mask)
    image.alpha_composite(overlay)
    draw = ImageDraw.Draw(image)
    draw_centered_text(draw, x1, x2, y1 + (y2 - y1 - line_height([("", font, "#fff")])) / 2 - 2, text, font, "#ffffff")


def render_daily_image(title, sections, output_path=None, width=DEFAULT_WIDTH):
    ops, height, header_height = layout_sections(title, sections, width=width)
    image = make_background(width, int(height)).convert("RGBA")
    draw = ImageDraw.Draw(image)

    title_lines = split_title(title)
    title_top = 182 if len(title_lines) == 1 else 154
    for index, line in enumerate(title_lines[:2]):
        draw_centered_text(draw, 0, width, title_top + index * 70, line, TITLE_FONT, "#ffffff")

    section_titles = [section_heading_text(section, "") for section in sections]
    section_titles = [item for item in section_titles if item and item != "原文入口"]
    subtitle = " · ".join(section_titles[:4]) or "Daily Report"
    if len(subtitle) > 32:
        subtitle = subtitle[:31] + "..."
    chip_width = min(width - 220, max(360, int(text_width(draw, subtitle, SUBTITLE_FONT) + 96)))
    chip_x = (width - chip_width) // 2
    draw_gradient_chip(image, (chip_x, 312, chip_x + chip_width, 376), 32, subtitle, SUBTITLE_FONT)

    for op in ops:
        kind = op[0]
        if kind != "card":
            continue
        _kind, card_top, heading, blocks, card_height = op
        card_left = CARD_X
        card_right = width - CARD_X
        card_bottom = card_top + card_height
        draw_shadowed_round(
            draw,
            (card_left, card_top, card_right, card_bottom),
            20,
            fill=(235, 246, 255, 238),
            outline=(205, 230, 255, 255),
            width=3,
            shadow=True,
        )
        chip_w = min(420, max(260, int(text_width(draw, heading, CHIP_FONT) + 116)))
        chip_left = (width - chip_w) // 2
        draw_gradient_chip(image, (chip_left, card_top - 38, chip_left + chip_w, card_top + 42), 36, heading, CHIP_FONT)

        y = card_top + 84
        panel_left = card_left + 58
        panel_right = card_right - 58
        for measured in blocks:
            panel_height = measured["height"]
            panel_bottom = y + panel_height
            draw.rounded_rectangle((panel_left, y, panel_right, panel_bottom), radius=0, fill=PANEL_BG)
            draw.rectangle((panel_left, y, panel_left + 8, panel_bottom), fill="#27c7ff")
            text_x = panel_left + PANEL_PAD_X
            text_y = y + PANEL_PAD_Y
            block_title = measured["block"].get("title", "")
            if block_title:
                for wrapped in measured.get("title_lines") or [[(block_title, BOLD_FONT, BLUE)]]:
                    x = text_x
                    for text, font, color in wrapped:
                        draw.text((x, text_y), text, font=font, fill=color)
                        x += draw.textlength(text, font=font)
                    text_y += line_height(wrapped) + 8
                text_y += BLOCK_TITLE_GAP
            for line_group in measured["lines"]:
                for wrapped in line_group["wrapped"]:
                    x = text_x
                    for text, font, color in wrapped:
                        draw.text((x, text_y), text, font=font, fill=color)
                        x += draw.textlength(text, font=font)
                    text_y += line_height(wrapped) + LINE_GAP
                if line_group.get("paragraph_break"):
                    text_y += PARAGRAPH_GAP
                else:
                    text_y += 16 if line_group["is_list_item"] else 8
            y = panel_bottom + PANEL_GAP

    if not output_path:
        output_path = os.path.join(tempfile.gettempdir(), f"daily_report_{int(time.time())}_{uuid.uuid4().hex[:8]}.png")
    image.convert("RGB").save(output_path, "PNG", optimize=True)
    return output_path


def _json_post(url, payload, headers=None, timeout=20):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def feishu_tenant_access_token(app_id, app_secret):
    body = _json_post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    token = body.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"feishu token response missing tenant_access_token: {body}")
    return token


def _multipart_form(fields, files):
    boundary = "----CodexDailyImage" + uuid.uuid4().hex
    chunks = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    for name, file_path in files.items():
        filename = os.path.basename(file_path)
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            (
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                "Content-Type: image/png\r\n\r\n"
            ).encode("utf-8")
        )
        with open(file_path, "rb") as image_file:
            chunks.append(image_file.read())
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return boundary, b"".join(chunks)


def upload_feishu_image(image_path, app_id, app_secret):
    token = feishu_tenant_access_token(app_id, app_secret)
    boundary, data = _multipart_form({"image_type": "message"}, {"image": image_path})
    req = urllib.request.Request(
        "https://open.feishu.cn/open-apis/im/v1/images",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"feishu image upload failed http={exc.code} body={detail[:1200]}") from exc
    image_key = (body.get("data") or {}).get("image_key")
    if not image_key:
        raise RuntimeError(f"feishu image upload response missing image_key: {body}")
    return image_key


def send_feishu_image(webhook, image_key):
    payload = {"msg_type": "image", "content": {"image_key": image_key}}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        sys.stdout.write(resp.read().decode("utf-8"))


def send_feishu_daily_image(webhook, title, sections, app_id, app_secret, output_dir=None):
    if not app_id or not app_secret:
        raise RuntimeError("FEISHU_APP_ID/FEISHU_APP_SECRET missing")
    output_dir = output_dir or tempfile.gettempdir()
    os.makedirs(output_dir, exist_ok=True)
    safe_title = re.sub(r"[^0-9A-Za-z._-]+", "_", title).strip("_") or "daily_report"
    image_path = os.path.join(output_dir, f"{safe_title}_{int(time.time())}.png")
    render_daily_image(title, sections, image_path)
    image_key = upload_feishu_image(image_path, app_id, app_secret)
    send_feishu_image(webhook, image_key)
    return image_path
