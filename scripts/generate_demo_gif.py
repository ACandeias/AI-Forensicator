#!/usr/bin/env python3
"""Generate a demo GIF for README using Pillow with mock terminal output.

Renders several 'screens' of the AIFT tool with realistic mock data,
styled to look like a macOS terminal.
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------
WIDTH = 860
LINE_HEIGHT = 20
FONT_SIZE = 14
PADDING_X = 18
PADDING_TOP = 48  # space for title bar
PADDING_BOTTOM = 14
TITLE_BAR_H = 36

BG_COLOR = (30, 30, 30)
TITLE_BAR_COLOR = (50, 50, 50)
TEXT_COLOR = (204, 204, 204)

# Semantic colors (terminal palette)
C = {
    "white": (204, 204, 204),
    "bold_white": (255, 255, 255),
    "dim": (128, 128, 128),
    "cyan": (0, 200, 200),
    "bright_cyan": (80, 220, 255),
    "green": (0, 180, 0),
    "bright_green": (80, 255, 80),
    "yellow": (220, 200, 0),
    "bright_yellow": (255, 255, 80),
    "magenta": (200, 80, 200),
    "bright_magenta": (255, 110, 255),
    "red": (220, 60, 60),
    "bright_red": (255, 90, 90),
    "blue": (80, 120, 255),
    "bright_blue": (100, 150, 255),
    "orange": (220, 140, 40),
}

FONT_PATH = "/System/Library/Fonts/Menlo.ttc"

try:
    FONT = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    FONT_BOLD = ImageFont.truetype(FONT_PATH, FONT_SIZE, index=1)
except Exception:
    FONT = ImageFont.truetype(FONT_PATH, FONT_SIZE)
    FONT_BOLD = FONT


def _text_width(text, font=None):
    """Approximate text width."""
    f = font or FONT
    bbox = f.getbbox(text)
    return bbox[2] - bbox[0]


def _calc_height(lines):
    """Calculate image height for N lines of text."""
    return PADDING_TOP + len(lines) * LINE_HEIGHT + PADDING_BOTTOM


def _draw_title_bar(draw, w, title="anthony@mac: ~/ai_forensics"):
    """Draw the macOS-style terminal title bar."""
    draw.rectangle([(0, 0), (w, TITLE_BAR_H)], fill=TITLE_BAR_COLOR)
    # Traffic light buttons
    r = 7
    y = TITLE_BAR_H // 2
    draw.ellipse([(14 - r, y - r), (14 + r, y + r)], fill=(255, 95, 87))
    draw.ellipse([(36 - r, y - r), (36 + r, y + r)], fill=(255, 189, 46))
    draw.ellipse([(58 - r, y - r), (58 + r, y + r)], fill=(39, 201, 63))
    # Title text
    tw = _text_width(title)
    tx = (w - tw) // 2
    draw.text((tx, (TITLE_BAR_H - FONT_SIZE) // 2), title, fill=C["dim"], font=FONT)


def _draw_line(draw, y, segments):
    """Draw a line of text as a list of (text, color, bold?) segments."""
    x = PADDING_X
    for seg in segments:
        if len(seg) == 2:
            text, color = seg
            bold = False
        else:
            text, color, bold = seg
        font = FONT_BOLD if bold else FONT
        draw.text((x, y), text, fill=color, font=font)
        x += _text_width(text, font)


def render_frame(lines_spec, title="anthony@mac: ~/ai_forensics"):
    """Render a frame from a list of line specifications.

    Each line is a list of (text, color) or (text, color, bold) tuples.
    A line can also be None for an empty line.
    """
    # Filter Nones for empty lines
    processed = []
    for line in lines_spec:
        if line is None:
            processed.append([])
        else:
            processed.append(line)

    h = _calc_height(processed)
    img = Image.new("RGB", (WIDTH, h), BG_COLOR)
    draw = ImageDraw.Draw(img)
    _draw_title_bar(draw, WIDTH, title)

    for i, segments in enumerate(processed):
        y = PADDING_TOP + i * LINE_HEIGHT
        if segments:
            _draw_line(draw, y, segments)

    return img


# ===============================================================
# Frame 1: Dry-run detection
# ===============================================================

def frame_dryrun():
    lines = [
        [("$ ", C["bright_green"]), ("python3 main.py collect --dry-run", C["bold_white"], True)],
        [("Detecting available collectors...", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] Claude Code", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] Claude Desktop", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] ChatGPT", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] Cursor", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] chrome", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] safari", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] OpenAI Atlas", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] LM Studio", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] cagent", C["white"])],
        [("  [", C["dim"]), ("detected", C["bright_green"]), ("] generic_logs", C["white"])],
        [("  [", C["dim"]), ("not found", C["dim"]), ("] brave", C["dim"])],
        [("  [", C["dim"]), ("not found", C["dim"]), ("] edge", C["dim"])],
        [("  [", C["dim"]), ("not found", C["dim"]), ("] ollama", C["dim"])],
        [("  [", C["dim"]), ("not found", C["dim"]), ("] windsurf", C["dim"])],
        [("  [", C["dim"]), ("not found", C["dim"]), ("] cline", C["dim"])],
        [("  ... (", C["dim"]), ("26 more not found", C["dim"]), (")", C["dim"])],
        None,
    ]
    return render_frame(lines)


# ===============================================================
# Frame 2: Collection run
# ===============================================================

def frame_collect():
    lines = [
        [("$ ", C["bright_green"]), ("python3 main.py collect", C["bold_white"], True)],
        [("Running 10 collector(s)...", C["white"])],
        [("  Claude Code       - ", C["white"]), ("49,138 artifacts", C["bright_green"])],
        [("  Claude Desktop    - ", C["white"]), ("7 artifacts", C["bright_green"])],
        [("  ChatGPT           - ", C["white"]), ("92 artifacts", C["bright_green"])],
        [("  Cursor            - ", C["white"]), ("54 artifacts", C["bright_green"])],
        [("  chrome            - ", C["white"]), ("130 artifacts", C["bright_green"])],
        [("  safari            - ", C["white"]), ("1 artifacts", C["bright_green"])],
        [("  OpenAI Atlas      - ", C["white"]), ("207 artifacts", C["bright_green"])],
        [("  LM Studio         - ", C["white"]), ("6 artifacts", C["bright_green"])],
        [("  cagent            - ", C["white"]), ("13 artifacts", C["bright_green"])],
        [("  generic_logs      - ", C["white"]), ("24 artifacts", C["bright_green"])],
        [("Inserted ", C["bright_green"], True), ("49,672 artifacts", C["bold_white"], True), (" into the database.", C["bright_green"], True)],
        None,
    ]
    return render_frame(lines)


# ===============================================================
# Frame 3: Statistics dashboard
# ===============================================================

def frame_stats():
    bc = C["bright_cyan"]
    w = C["white"]
    bw = C["bold_white"]
    g = C["bright_green"]
    y = C["yellow"]
    m = C["bright_magenta"]
    d = C["dim"]

    lines = [
        [("$ ", C["bright_green"]), ("python3 main.py stats", bw, True)],
        [("=== ", bc), ("AIFT - AI Forensics Tool", bc, True), (" Statistics ===", bc)],
        [("Total artifacts:  ", w), ("49,672", bw, True)],
        [("Collection runs:  ", w), ("3", bw, True)],
        [("Token estimate:   ", w), ("163,333,836", bw, True)],
        [("Date range:       ", w), ("2025-12-03 to 2026-02-28", bw, True)],
        None,
        [("Source distribution:", w, True)],
        [("  Claude Code                    ", g), ("49,138", bw)],
        [("  chrome                            ", g), ("130", bw)],
        [("  OpenAI Atlas                      ", g), ("207", bw)],
        [("  ChatGPT                            ", g), ("92", bw)],
        [("  Cursor                            ", g), ("54", bw)],
        [("  generic_logs                       ", g), ("24", bw)],
        [("  cagent                             ", g), ("13", bw)],
        [("  Claude Desktop                     ", g), ("7", bw)],
        [("  LM Studio                          ", g), ("6", bw)],
        [("  safari                              ", g), ("1", bw)],
        None,
        [("Model usage:", w, True)],
        [("  claude-opus-4-6                ", y), ("55,446", bw)],
        [("  claude-haiku-4-5               ", y), ("16,996", bw)],
        [("  claude-opus-4-5                ", y), ("7,584", bw)],
        [("  claude-sonnet-4-6              ", y), ("471", bw)],
        [("  gpt-4                          ", y), ("6", bw)],
        [("  Qwen3-4B                       ", y), ("3", bw)],
        [("  Mistral-7B-Instruct            ", y), ("3", bw)],
        None,
    ]
    return render_frame(lines)


# ===============================================================
# Frame 4: Browse view (table-like)
# ===============================================================

def frame_browse():
    bc = C["bright_cyan"]
    w = C["white"]
    g = C["green"]
    y = C["yellow"]
    m = C["magenta"]
    d = C["dim"]
    bw = C["bold_white"]

    lines = [
        [("$ ", C["bright_green"]), ("python3 main.py browse --limit 8", bw, True)],
        None,
        [("Timestamp           ", bc), ("Source          ", g), ("Type            ", m), ("Model             ", y), ("Preview", w)],
        [("-" * 100, d)],
        [("2026-02-28T15:42  ", bc), ("Claude Code     ", g), ("conversation    ", m), ("claude-opus-4-6   ", y), ("Implement the following plan...", w)],
        [("2026-02-28T15:41  ", bc), ("Claude Code     ", g), ("conversation    ", m), ("claude-opus-4-6   ", y), ("Create collectors/mixins.py...", w)],
        [("2026-02-28T14:30  ", bc), ("chrome          ", g), ("browser_history ", m), ("                  ", y), ("claude.ai - Claude", w)],
        [("2026-02-28T14:28  ", bc), ("chrome          ", g), ("browser_history ", m), ("                  ", y), ("chatgpt.com - ChatGPT", w)],
        [("2026-02-28T13:15  ", bc), ("OpenAI Atlas    ", g), ("encrypted_conv  ", m), ("                  ", y), ("91 encrypted .data files...", w)],
        [("2026-02-28T12:00  ", bc), ("Cursor          ", g), ("conversation    ", m), ("claude-opus-4-6   ", y), ("[Refactor] Updated browser...", w)],
        [("2026-02-27T22:10  ", bc), ("LM Studio       ", g), ("config          ", m), ("                  ", y), ("settings.json - 12 keys", w)],
        [("2026-02-27T21:45  ", bc), ("cagent          ", g), ("manifest        ", m), ("                  ", y), ("OCI manifest: 3 layers...", w)],
        None,
    ]
    return render_frame(lines)


# ===============================================================
# Frame 5: Search results
# ===============================================================

def frame_search():
    bc = C["bright_cyan"]
    w = C["white"]
    g = C["green"]
    y = C["yellow"]
    m = C["magenta"]
    d = C["dim"]
    bw = C["bold_white"]
    r = C["bright_red"]

    lines = [
        [("$ ", C["bright_green"]), ("python3 main.py search \"claude-opus\"", bw, True)],
        [("Found ", w), ("1,247", bw, True), (" result(s):", w)],
        None,
        [("Timestamp           ", bc), ("Source          ", g), ("Type            ", m), ("Preview", w)],
        [("-" * 90, d)],
        [("2026-02-28T15:42  ", bc), ("Claude Code     ", g), ("conversation    ", m), ("model: ", w), ("claude-opus", r, True), ("-4-6", w)],
        [("2026-02-28T15:41  ", bc), ("Claude Code     ", g), ("prompt_history  ", m), ("Using ", w), ("claude-opus", r, True), ("-4-6 for task", w)],
        [("2026-02-28T14:30  ", bc), ("Cursor          ", g), ("conversation    ", m), ("model: ", w), ("claude-opus", r, True), ("-4-6", w)],
        [("2026-02-27T22:10  ", bc), ("Claude Code     ", g), ("analytics       ", m), ("", w), ("claude-opus", r, True), ("-4-6: 55,446 uses", w)],
        [("2026-02-27T19:55  ", bc), ("Claude Code     ", g), ("conversation    ", m), ("Switched to ", w), ("claude-opus", r, True), ("-4-5", w)],
        None,
    ]
    return render_frame(lines)


# ===============================================================
# Frame 6: TUI main menu
# ===============================================================

def frame_tui_menu():
    bc = C["bright_cyan"]
    w = C["white"]
    bw = C["bold_white"]
    d = C["dim"]

    lines = [
        [("$ ", C["bright_green"]), ("python3 main.py", bw, True)],
        None,
        [("  \u250c", bc), ("\u2500" * 46, bc), ("\u2510", bc)],
        [("  \u2502 ", bc), ("AIFT - AI Forensics Tool", bc, True), ("  v0.2.0", d), ("         \u2502", bc)],
        [("  \u2514", bc), ("\u2500" * 46, bc), ("\u2518", bc)],
        None,
        [("  \u250c", bc), ("\u2500 Main Menu ", bc), ("\u2500" * 34, bc), ("\u2510", bc)],
        [("  \u2502 ", bc), ("1", bc, True), (" Run Collection                          \u2502", w)],
        [("  \u2502 ", bc), ("2", bc, True), (" Browse Artifacts                        \u2502", w)],
        [("  \u2502 ", bc), ("3", bc, True), (" Timeline View                           \u2502", w)],
        [("  \u2502 ", bc), ("4", bc, True), (" Statistics                               \u2502", w)],
        [("  \u2502 ", bc), ("5", bc, True), (" Search                                   \u2502", w)],
        [("  \u2502 ", bc), ("6", bc, True), (" Export                                   \u2502", w)],
        [("  \u2502 ", bc), ("7", bc, True), (" Collection History                      \u2502", w)],
        [("  \u2502 ", bc), ("0", bc, True), (" Exit                                     \u2502", w)],
        [("  \u2514", bc), ("\u2500" * 46, bc), ("\u2518", bc)],
        None,
        [("  Select an option", bw, True), (" [0/1/2/3/4/5/6/7]: ", d), ("\u2588", C["bright_cyan"])],
        None,
    ]
    return render_frame(lines)


# ===============================================================
# Compose GIF
# ===============================================================

def main():
    out_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_path = os.path.join(out_dir, "assets", "demo.gif")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    frames = [
        (frame_tui_menu(), 3000),      # Main menu - 3s
        (frame_dryrun(), 4000),        # Detection - 4s
        (frame_collect(), 4000),       # Collection - 4s
        (frame_stats(), 5000),         # Statistics - 5s
        (frame_browse(), 4000),        # Browse - 4s
        (frame_search(), 4000),        # Search - 4s
    ]

    # Normalize all frames to the same height (max height)
    max_h = max(f.size[1] for f, _ in frames)
    normalized = []
    for img, duration in frames:
        if img.size[1] < max_h:
            new_img = Image.new("RGB", (WIDTH, max_h), BG_COLOR)
            new_img.paste(img, (0, 0))
            normalized.append((new_img, duration))
        else:
            normalized.append((img, duration))

    # Save as animated GIF
    first = normalized[0][0]
    rest_imgs = [f for f, _ in normalized[1:]]
    durations = [d for _, d in normalized]

    first.save(
        out_path,
        save_all=True,
        append_images=rest_imgs,
        duration=durations,
        loop=0,
        optimize=True,
    )

    size_kb = os.path.getsize(out_path) / 1024
    print("Generated demo GIF: {} ({:.0f} KB)".format(out_path, size_kb))
    print("Frames: {}".format(len(frames)))
    print("Dimensions: {}x{}".format(WIDTH, max_h))


if __name__ == "__main__":
    main()
