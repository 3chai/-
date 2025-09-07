import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile

# =============== 基本定義 ===============
cell_offsets = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7}
CELLS_ALL = list(cell_offsets.keys())

presets = {
    "Andraft": {
        "first_frame_top_y_true": 1279,
        "frame_height_true": 49.6,
        "cell_x_positions_true": {cell: 108 + 55.8 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 1688,
        "true_width": 3508,
        "true_height": 4961,
        "default_book_koma": 6,
        "default_celllabel_koma": 2,
    },
    "動画工房": {
        "first_frame_top_y_true": 468,
        "frame_height_true": 27.25,
        "cell_x_positions_true": {cell: 51.7 + 29 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 870,
        "true_width": 1754,
        "true_height": 2480,
        "default_book_koma": 5,
        "default_celllabel_koma": 0,
    },
    "ぴえろ（マイルさん用）": {
        "first_frame_top_y_true": 800,
        "frame_height_true": 27.5,
        "cell_x_positions_true": {cell: 86 + 30.8 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 950.5,
        "true_width": 2026,
        "true_height": 2866,
        "default_book_koma": 4,
        "default_celllabel_koma": 1
    },
    "CygamesPictures": {
        "first_frame_top_y_true": 780,
        "frame_height_true": 33.98,
        "cell_x_positions_true": {cell: 112 + 37.3 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 1168,
        "true_width": 2340,
        "true_height": 3307,
        "default_book_koma": 5,
        "default_celllabel_koma": 2
    }
}

# =============== 位置調整の基準（Andraft基準） ===============
BASE_FRAME_HEIGHT = 49.5
BASE_WIDTH = 3508
BASE_CIRCLE_OFFSET_X = -5
BASE_CIRCLE_OFFSET_Y = -2
BASE_ALPHABET_OFFSET_X = -13
BASE_CROSS_OFFSET_X = -6
BASE_BAR_WIDTH = 1620
BASE_BAR_SHIFT_X = 88
text_offset_y = 4

BASE_BOOK_OFFSET_KOMA = 3

# 数字の段階的縮小
TWO_DIGIT_SCALE    = 0.85  # 例: 12
THREE_PLUS_SCALE   = 0.7  # 例: 100, 240

# ===== 数字の桁数別 位置補正（px相当；負=上/左, 正=下/右）=====
NUM1_NUDGE_X = 0
NUM1_NUDGE_Y = 0

NUM2_NUDGE_X = 0
NUM2_NUDGE_Y = 2

NUM3PLUS_NUDGE_X = -5
NUM3PLUS_NUDGE_Y = 5


# ====== 英字付き(例: 1a/12a/108a)の桁数別スケール＆位置補正 ======
ALPHA1_SCALE = 0.8   # 1a の基準スケール
ALPHA2_SCALE = 0.7   # 12a の基準スケール
ALPHA3PLUS_SCALE = 0.6  # 100a など

# 負=上/左, 正=下/右（px相当をスケールに掛ける）
ALPHA1_NUDGE_X = 5
ALPHA1_NUDGE_Y = 6.5

ALPHA2_NUDGE_X = 1.8
ALPHA2_NUDGE_Y = 9

ALPHA3PLUS_NUDGE_X = -1.8
ALPHA3PLUS_NUDGE_Y = 10


# --- 囲み描画の見た目（UIで上書き可） ---
ENC_PAD_W = 10   # テキスト左右余白(px相当)
ENC_PAD_H = 6    # テキスト上下余白(px相当)
ENC_STROKE = 4   # 線の太さ(px相当)

# セル名オフセット（px基準 → スケール）
HEADER_X_NUDGE_PX      = 10
HEADER_BOTTOM_NUDGE_PX = -80

# ○/●/〇 の専用縮小＆位置補正
CIRCLE_SCALE   = 0.5   # 1.0=等倍
CIRCLE_NUDGE_X = 8     # px（正=右, 負=左）
CIRCLE_NUDGE_Y = 14    # px（正=下,  負=上）

# フォント
font_path    = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
jp_font_path = os.path.join(os.path.dirname(__file__), "NotoSansJP-Regular.otf")
base_font_size = int(12 / (1086 / 3508))

# =============== まとめ入力パーサー ===============
def parse_triangle_spec(s: str):
    """
    'A1, A10a, C24, 3, 5-7, 10a' などを一括で解釈。
    戻り値: (triangle_cell_refs, triangle_alpha_tokens, triangle_numbers)
      - triangle_cell_refs: {'A1', 'A10a', 'C24', ...}  ※セル優先
      - triangle_alpha_tokens: {'10a', '7b', ...}       ※全セルで英字付き
      - triangle_numbers: {3,5,6,7,...}                 ※全セルで数字のみ
    """
    cell_refs = set()
    alpha_tokens = set()
    numbers = set()

    s = (s or "").strip()
    if not s:
        return cell_refs, alpha_tokens, numbers

    for part in re.split(r"[,\u3001\s]+", s):
        part = part.strip()
        if not part:
            continue

        # セル指定（A-H + 数字 + 英字0/1）
        m_cell = re.fullmatch(r"([A-Ha-h])\s*(\d+)\s*([a-zA-Z]?)", part)
        if m_cell:
            c = m_cell.group(1).upper()
            n = m_cell.group(2)
            suf = m_cell.group(3).lower()
            cell_refs.add(f"{c}{n}{suf}")
            continue

        # 数字レンジ 5-12 / 12-5
        m_rng = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m_rng:
            a, b = int(m_rng.group(1)), int(m_rng.group(2))
            if a <= b:
                numbers.update(range(a, b+1))
            else:
                numbers.update(range(b, a+1))
            continue

        # 英字付き token (10a など)
        m_alpha = re.fullmatch(r"(\d+)([a-zA-Z])", part)
        if m_alpha:
            n = m_alpha.group(1)
            suf = m_alpha.group(2).lower()
            alpha_tokens.add(f"{n}{suf}")
            continue

        # 純数字
        if part.isdigit():
            numbers.add(int(part))
            continue

    return cell_refs, alpha_tokens, numbers

# =============== ユーティリティ ===============
def parse_mixed_triangle_targets(s: str):
    """
    例:
      "1, 4-6, 24, 10a,7b，12C"
      -> ( {1,4,5,6,24}, {"10a","7b","12C"} )
    ・数字は範囲対応 (a-b)
    ・英字付き(10aなど)はトークン単位。範囲は非対応
    """
    nums = set()
    alnum = set()
    s = (s or "").strip()
    if not s:
        return nums, alnum

    for part in re.split(r"[,\u3001]", s):
        part = part.strip()
        if not part:
            continue

        m_rng = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m_rng:
            a, b = int(m_rng.group(1)), int(m_rng.group(2))
            if a <= b:
                nums.update(range(a, b+1))
            else:
                nums.update(range(b, a+1))
            continue

        m_num      = re.fullmatch(r"\d+", part)
        m_numalpha = re.fullmatch(r"\d+[a-zA-Z]", part)
        if m_num:
            nums.add(int(part))
        elif m_numalpha:
            alnum.add(part)

    return nums, alnum

def clean_frame_column(series):
    series = series.astype(str).str.strip().map(lambda x: unicodedata.normalize("NFKC", x))
    series = pd.to_numeric(series, errors='coerce')
    return series

def normalize_for_vertical(text: str) -> str:
    return (text
            .replace("ー", "｜").replace("ｰ", "｜")
            .replace("－", "｜").replace("―", "｜")
            .replace("—", "｜").replace("–", "｜"))

def read_csv_flexibly(file_bytes):
    try:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding="shift_jis", header=[0, 1], keep_default_na=False)
        df.columns = [col[1] if col[1] != '' else col[0] for col in df.columns]
        if 'Unnamed: 0_level_1' in df.columns:
            df = df.rename(columns={'Unnamed: 0_level_1': 'Frame'})
        df.columns = [unicodedata.normalize("NFKC", str(c)).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"CSVの読み込みに失敗しました: {e}")
        return pd.DataFrame()

def preprocess_cells(df_raw, valid_cells):
    for cell in valid_cells:
        if df_raw[cell].astype(str).str.strip().replace("nan", "").eq("").all():
            continue
        seen_content = False
        for idx, row in df_raw.iterrows():
            val = str(row[cell]).strip()
            if val == "" or pd.isna(row[cell]):
                if not seen_content:
                    df_raw.at[idx, cell] = "×"
                    seen_content = True
            else:
                seen_content = True
    return df_raw

def get_book_positions(df, valid_cells):
    cols = list(df.columns)
    book_cols = [c for c in cols if re.match(r"^_?book\d+$", str(c), re.IGNORECASE)]
    positions = {}
    for b in book_cols:
        idx = cols.index(b)
        left_cell = None
        for i in range(idx - 1, -1, -1):
            if cols[i] in valid_cells:
                left_cell = cols[i]; break
        right_cell = None
        for i in range(idx + 1, len(cols)):
            if cols[i] in valid_cells:
                right_cell = cols[i]; break
        if left_cell is None and right_cell is None:
            continue
        if left_cell is None:
            positions[b] = f"before_{right_cell}"
        elif right_cell is None:
            positions[b] = f"after_{left_cell}"
        else:
            positions[b] = f"between_{left_cell}_{right_cell}"
    return positions

def norm_str(s):
    return unicodedata.normalize("NFKC", str(s)).replace("\u3000", " ").strip()

def is_filled(v):
    s = norm_str(v)
    return s not in ("", "nan", "None")

def draw_vertical_bottom(draw, text, bottom_x, bottom_y, font, spacing=0):
    if not text:
        return
    text = normalize_for_vertical(text)
    boxes, total_h = [], 0
    for ch in text:
        bbox = draw.textbbox((0, 0), ch, font=font)
        w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]
        boxes.append((ch, w, h)); total_h += h
    total_h += spacing * (len(boxes) - 1 if boxes else 0)
    y = bottom_y - total_h
    for ch, w, h in boxes:
        draw.text((bottom_x - w/2.0, y), ch, fill=(0,0,0,255), font=font)
        y += h + spacing

# book X座標（before/between/after）
def calc_book_x(pos, cell_x_positions_true, koma_width, scale_w):
    book_x = None
    if pos.startswith("before_"):
        tgt = pos.replace("before_", "")
        if tgt in cell_x_positions_true:
            book_x = cell_x_positions_true[tgt] - 9 * scale_w
    elif pos.startswith("between_"):
        parts = pos.split("_")
        if len(parts) == 3:
            _, left, right = parts
            if left in cell_x_positions_true and right in cell_x_positions_true:
                book_x = cell_x_positions_true[left] + 0.8 * koma_width + 3 * scale_w
    elif pos.startswith("after_"):
        tgt = pos.replace("after_", "")
        if tgt in cell_x_positions_true:
            book_x = cell_x_positions_true[tgt] + 0.8 * koma_width + 3 * scale_w
    return book_x

# 三角の見た目調整
TRIANGLE_NUDGE_Y = -0.9  # 負=上、正=下（px）
TRIANGLE_BASE_W_SCALE = 1.2
TRIANGLE_HEIGHT_SCALE = 1
TRIANGLE_USE_FIXED = True  # Trueで三角の大きさを一定にする
TRIANGLE_FIXED_SIZE = 40   # 基準ピクセル（Andraft基準）。テンプレートに合わせ scale_h で拡大縮小
TRIANGLE_FILL_ALPHA = 0       # 三角の塗りの不透明度（0% = 0）
TRIANGLE_OUTLINE_ALPHA = 77  # 三角枠の不透明度（約50%）

# 丸の固定サイズ設定（三角と揃える）
CIRCLE_USE_FIXED  = True
CIRCLE_FIXED_SIZE = 48
CIRCLE_FILL_ALPHA = 0
CIRCLE_OUTLINE_ALPHA = 128 # 円の不透明度（塗りはデフォルト0%、枠はデフォルト50%）

# 囲み描画（数字の周りに丸/三角）
ENC_PAD_BASE    = 0    # 文字と円の基本余白(px)
ENC_GROWTH      = 0.53 # 横が縦より大きい時の増量係数
ENC_MAX_EXTRA   = 30   # 増量の上限(px)

def draw_enclosure(draw, bbox, shape="circle", stroke=2,
                   tri_outline_alpha=TRIANGLE_OUTLINE_ALPHA,
                   circ_outline_alpha=CIRCLE_OUTLINE_ALPHA,
                   tri_fill_alpha=TRIANGLE_FILL_ALPHA,
                   circ_fill_alpha=CIRCLE_FILL_ALPHA,
                   scale_w=1.0, scale_h=1.0):
    """
    bbox: テキストの描画境界 (x1,y1,x2,y2)
    shape: "circle" or "triangle"
    """
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1

    if shape == "triangle":
        # 二等辺三角形（上向き）
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        if TRIANGLE_USE_FIXED:
            # 一定サイズ（三角の見た目を安定させる）。高さと底辺は固定サイズを基準に scale_h を掛ける。
            height = TRIANGLE_FIXED_SIZE * scale_h * TRIANGLE_HEIGHT_SCALE
            base_half = (TRIANGLE_FIXED_SIZE * TRIANGLE_BASE_W_SCALE * scale_h) / 2.0
            top_y = cy - height / 2.0
            bottom_y = cy + height / 2.0
        else:
            # 従来：テキストbboxに追従（数値が長いと横に広がる）
            w = x2 - x1
            h = y2 - y1
            base_half = (w / 2.0) * TRIANGLE_BASE_W_SCALE
            top_y = y2 - h * TRIANGLE_HEIGHT_SCALE
            bottom_y = y2

        pts = [(cx, top_y), (cx - base_half, bottom_y), (cx + base_half, bottom_y)]
        # polygon による塗り（既定は透明）
        draw.polygon(pts, fill=(0, 0, 0, tri_fill_alpha))
        # 枠線（不透明度指定）
        draw.line(pts + [pts[0]], fill=(0, 0, 0, tri_outline_alpha), width=stroke, joint="curve")
        return

    # 真円（数字が横長でも半径に少し加算してキレイに収める）
    # --- circle（固定サイズ or 従来の自動） ---
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    if CIRCLE_USE_FIXED:
        # 一定半径（三角に合わせて scale_h で拡縮）
        r = (CIRCLE_FIXED_SIZE * scale_h) / 2.0
    else:
        extra = max(0, w - h) * ENC_GROWTH
        extra = min(extra, ENC_MAX_EXTRA)
        r = (h / 2.0) + ENC_PAD_BASE + (extra / 2.0)

    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=(0, 0, 0, circ_fill_alpha),
        outline=(0, 0, 0, circle_outline_alpha),
        width=stroke
    )

# --- ドリフトしないY計算（保険用） ---
def y_for_frame(top_y: int, n_frame: int, frame_h: float, fps: int = 24) -> int:
    sec, sub = divmod(n_frame, fps)
    y_sec = int(round(top_y + sec * fps * frame_h))
    return int(round(y_sec + sub * frame_h))

# =============== 本体 ===============
def generate_timesheet(
    file_bytes,
    preset,
    show_books=True,
    book_offset_koma=6,
    cell_labels=None,
    celllabel_koma=2,
    target_cell_for_enclose="A",
    mixed_triangle_str="",
    enc_pad_w=ENC_PAD_W,
    enc_pad_h=ENC_PAD_H,
    enc_stroke=ENC_STROKE,
    triangle_outline_alpha=TRIANGLE_OUTLINE_ALPHA,
    circle_outline_alpha=CIRCLE_OUTLINE_ALPHA,
    alpha_all_triangle=False,
):
    # 入力一発 → セル参照・英字付きトークン・数字セットに分解
    triangle_cell_refs, triangle_alpha_tokens, triangle_numbers = parse_triangle_spec(mixed_triangle_str)

    # プリセット
    true_width = preset["true_width"]; true_height = preset["true_height"]
    frame_height_true = preset["frame_height_true"]
    first_frame_top_y_true = preset["first_frame_top_y_true"]
    column_offset_x = preset["column_offset_x"]
    cell_x_positions_true = preset["cell_x_positions_true"]

    # スケール
    scale_h = frame_height_true / BASE_FRAME_HEIGHT
    scale_w = true_width / BASE_WIDTH

    circle_offset_x = BASE_CIRCLE_OFFSET_X * scale_w
    circle_offset_y = BASE_CIRCLE_OFFSET_Y * scale_h
    alphabet_offset_x = BASE_ALPHABET_OFFSET_X * scale_w
    cross_offset_x = BASE_CROSS_OFFSET_X * scale_w
    bar_width = BASE_BAR_WIDTH * scale_w
    bar_shift_x = BASE_BAR_SHIFT_X * scale_w

    # 1コマ幅推定
    try:
        koma_width = cell_x_positions_true['B'] - cell_x_positions_true['A']
    except Exception:
        items = sorted(cell_x_positions_true.items(), key=lambda kv: kv[1])
        coords = [v for _, v in items]
        diffs = [coords[i+1] - coords[i] for i in range(len(coords)-1)]
        diffs.sort()
        koma_width = diffs[len(diffs)//2] if diffs else 0.0

    # フォント
    font_large = ImageFont.truetype(font_path, size=int(base_font_size * scale_h))
    font_small = ImageFont.truetype(font_path, size=int(base_font_size * 0.9 * scale_h))
    font_circle = ImageFont.truetype(font_path, size=int(base_font_size * scale_h * CIRCLE_SCALE))
    label_font  = ImageFont.truetype(font_path, size=int(base_font_size * 0.6 * scale_h))
    try:
        cell_label_font = ImageFont.truetype(jp_font_path, size=int(base_font_size * 0.6 * scale_h))
    except Exception:
        cell_label_font = ImageFont.truetype(font_path, size=int(base_font_size * 0.6 * scale_h))

    # CSV
    df = read_csv_flexibly(file_bytes)
    if df.empty or 'Frame' not in df.columns:
        return [], 0

    df['Frame'] = clean_frame_column(df['Frame'])
    df = df.dropna(subset=['Frame'])
    df['Frame'] = df['Frame'].astype(int)
    df = df[df['Frame'] > 0]
    if df.empty:
        return [], 0

    valid_cells = [c for c in CELLS_ALL if c in df.columns]
    df = preprocess_cells(df, valid_cells)
    book_positions = get_book_positions(df, valid_cells)

    max_frame = df['Frame'].max()
    frames_per_page = 144
    total_pages = math.ceil(max_frame / frames_per_page)
    last_frame_global = max_frame
    result_images = []
    cell_labels = cell_labels or {}

    for page in range(total_pages):
        img = Image.new("RGBA", (true_width, true_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        start = page*frames_per_page + 1
        end = (page+1)*frames_per_page
        df_page = df[(df['Frame']>=start) & (df['Frame']<=end)]
        if df_page.empty:
            result_images.append(img); continue

        last_frame_in_page = df_page['Frame'].max()

        # ---- セル名（1ページ目のみ・左カラム・縦書き下揃え）----
        if page == 0:
            header_bottom_y = (first_frame_top_y_true
                               - celllabel_koma * frame_height_true
                               + (HEADER_BOTTOM_NUDGE_PX * scale_h))
            glyph_spacing = 2 * scale_h
            for cell in valid_cells:
                label = (cell_labels.get(cell) or "").strip()
                if not label:
                    continue
                x_center = cell_x_positions_true[cell] + (HEADER_X_NUDGE_PX * scale_w)
                draw_vertical_bottom(
                    draw, label,
                    bottom_x=x_center,
                    bottom_y=header_bottom_y,
                    font=cell_label_font,
                    spacing=glyph_spacing
                )

        # ---- 通常セル（丸/三角 囲み対応）----
        for cell in valid_cells:
            x_base = cell_x_positions_true[cell]
            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                timing = str(row[cell]) if not pd.isna(row[cell]) else ""
                idx = (frame-1) % frames_per_page
                col_block = idx // 72
                row_pos = idx % 72
                y = first_frame_top_y_true + row_pos*frame_height_true
                x = x_base if col_block==0 else x_base + column_offset_x
                y_draw = y + text_offset_y

                # 記号の扱い
                if timing in ('●','○','〇'):
                    x += circle_offset_x + (CIRCLE_NUDGE_X * scale_w)
                    y_draw += circle_offset_y + (CIRCLE_NUDGE_Y * scale_h)
                    font = font_circle
                elif timing == '×':
                    x += cross_offset_x
                    font = font_large
                else:
                    # 文字種別でフォントとスケールを決定し、桁数別の補正を適用
                    m_num_alpha = re.fullmatch(r"(\d+)([a-zA-Z])", timing)  # 10a
                    m_digits    = re.fullmatch(r"\d+", timing)              # 12, 108 など

                    if m_num_alpha:
                        # 英字付き（例：10a）。数字部分の桁数で細かく最適化
                        digit_part = m_num_alpha.group(1)   # "10"
                        nlen = len(digit_part)

                        if nlen == 1:
                            scale = ALPHA1_SCALE
                            nx, ny = ALPHA1_NUDGE_X, ALPHA1_NUDGE_Y
                        elif nlen == 2:
                            scale = ALPHA2_SCALE
                            nx, ny = ALPHA2_NUDGE_X, ALPHA2_NUDGE_Y
                        else:
                            scale = ALPHA3PLUS_SCALE
                            nx, ny = ALPHA3PLUS_NUDGE_X, ALPHA3PLUS_NUDGE_Y

                        font = ImageFont.truetype(font_path, size=int(base_font_size * scale_h * scale))

                        # 既存の横位置微調整は活かす（文字詰まり防止）
                        x += alphabet_offset_x
                        # 桁数別の最終補正
                        x += nx * scale_w
                        y_draw += ny * scale_h

                    elif m_digits:
                        nlen = len(timing)
                        if nlen == 1:
                            font = font_large
                            nx, ny = NUM1_NUDGE_X, NUM1_NUDGE_Y
                        elif nlen == 2:
                            scale = TWO_DIGIT_SCALE
                            font = ImageFont.truetype(font_path, size=int(base_font_size * scale_h * scale))
                            x += alphabet_offset_x * 0.6
                            nx, ny = NUM2_NUDGE_X, NUM2_NUDGE_Y
                        else:
                            scale = THREE_PLUS_SCALE
                            font = ImageFont.truetype(font_path, size=int(base_font_size * scale_h * scale))
                            x += alphabet_offset_x * 0.6
                            nx, ny = NUM3PLUS_NUDGE_X, NUM3PLUS_NUDGE_Y
                        x += nx * scale_w
                        y_draw += ny * scale_h
                    else:
                        font = font_small if len(timing) >= 3 else font_large

                # ===== 囲み（全セル対象：セル指定 > 英字付きtoken > 数字のみ の優先順）=====
                m_lead = re.match(r"\s*(\d+)([a-zA-Z]?)", timing)  # 先頭の「数字(+任意の英字1文字)」
                if m_lead:
                    num_text = m_lead.group(1)           # '12'
                    suffix   = m_lead.group(2).lower()   # 'a' or ''
                    token    = f"{num_text}{suffix}"     # '12a' or '12'
                    cell_tok = f"{cell}{token}"          # 例: 'A12a'

                    # --- 三角の判定（優先度：セル指定 > 英字付きtoken > 数字のみ） ---
                    is_triangle = (
                        (cell_tok in triangle_cell_refs) or
                        (suffix and (alpha_all_triangle or (token in triangle_alpha_tokens))) or
                        ((not suffix) and (int(num_text) in triangle_numbers))
                    )

                    # トークン全体（数字 + 任意の英字1文字）の bbox を取得
                    # suffix が空でも token は num_text と同じなのでそのまま使える
                    token_bbox = draw.textbbox((x, y_draw), token, font=font)

                    pad_w = enc_pad_w * scale_w
                    pad_h = enc_pad_h * scale_h
                    dy = (TRIANGLE_NUDGE_Y * scale_h) if is_triangle else 0

                    ebbox = (
                        token_bbox[0] - pad_w,
                        token_bbox[1] - pad_h + dy,
                        token_bbox[2] + pad_w,
                        token_bbox[3] + pad_h + dy
                    )
                    stroke_px = max(1, int(enc_stroke * scale_w))
                    draw_enclosure(
                        draw, ebbox,
                        shape=('triangle' if is_triangle else 'circle'),
                        stroke=stroke_px,
                        tri_outline_alpha=triangle_outline_alpha,
                        circ_outline_alpha=circle_outline_alpha,
                        tri_fill_alpha=TRIANGLE_FILL_ALPHA,
                        circ_fill_alpha=CIRCLE_FILL_ALPHA,
                        scale_w=scale_w, scale_h=scale_h
                    )

                # テキストを最後に描画
                draw.text((x, y_draw), timing, fill=(0,0,0,255), font=font)

        # ---- book マーカー（行内共有の重なり回避／枠は飾り）----
        if show_books:
            BOX_PAD_X = 1 * scale_w
            BOX_PAD_Y = 1 * scale_h
            BOX_OUTLINE_W = max(1, int(1.5 * scale_w))

            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                idx = (frame-1) % frames_per_page
                col_block = idx // 72
                row_pos = idx % 72

                row_y_base = first_frame_top_y_true + row_pos*frame_height_true
                col_x_offset = column_offset_x if col_block==1 else 0

                present = {}
                for book_col, pos in get_book_positions(df, valid_cells).items():
                    cname = norm_str(book_col)
                    if (cname in row.index) and is_filled(row[cname]):
                        present.setdefault(pos, []).append(cname)

                placed_boxes_row = []

                entries = []
                for pos, books_here in present.items():
                    bx = calc_book_x(pos, cell_x_positions_true, koma_width, scale_w)
                    if bx is not None:
                        entries.append((bx + col_x_offset - 5, pos, books_here))

                for book_x, pos, books_here in sorted(entries, key=lambda t: t[0]):
                    y_ref = row_y_base - (frame_height_true * book_offset_koma)
                    base_line_top    = y_ref - 4*scale_h
                    base_line_bottom = y_ref + (frame_height_true*2) + 2*scale_h

                    items = []
                    for b in books_here:
                        s = norm_str(b).replace("_","")
                        m = re.search(r"(\d+)$", s)
                        n = int(m.group(1)) if m else 0
                        items.append((n, s))
                    items.sort(key=lambda t: t[0])

                    line_gap    = 2*scale_h
                    extra_shift = 3*scale_h
                    margin      = 12*scale_w

                    bottom_label_bottom = None

                    def overlap(a,b):
                        ax1,ay1,ax2,ay2 = a
                        bx1,by1,bx2,by2 = b
                        return not (ax2<=bx1 or bx2<=ax1 or ay2<=by1 or by2<=ay1)

                    for idx_item, (_, label) in enumerate(items):
                        bbox0 = draw.textbbox((0, 0), label, font=label_font)
                        lw = bbox0[2] - bbox0[0]
                        lh = bbox0[3] - bbox0[1]

                        base_y = (base_line_top - lh - 2*scale_h) - idx_item * (lh + line_gap)
                        lx_center = book_x - (lw / 2)
                        ly = base_y
                        lx = max(margin, min(true_width - margin - lw, lx_center))

                        while True:
                            bbox_at = draw.textbbox((lx, ly), label, font=label_font)
                            cur_padded = (
                                bbox_at[0] - BOX_PAD_X,
                                bbox_at[1] - BOX_PAD_Y,
                                bbox_at[2] + BOX_PAD_X,
                                bbox_at[3] + BOX_PAD_Y
                            )
                            hit = any(overlap(cur_padded, box) for box in placed_boxes_row)
                            if not hit:
                                break
                            ly -= (lh + line_gap + extra_shift)

                        draw.text((lx, ly), label, fill=(0,0,0,255), font=label_font)
                        draw.rectangle([cur_padded[0], cur_padded[1], cur_padded[2], cur_padded[3]],
                                       outline=(0,0,0,255), width=max(1, int(1.5*scale_w)))
                        placed_boxes_row.append(cur_padded)
                        bottom_label_bottom = max(bottom_label_bottom or cur_padded[3], cur_padded[3])

                    pad_top = 2 * scale_h
                    line_top = (bottom_label_bottom + pad_top) if bottom_label_bottom is not None else base_line_top
                    extra_len = frame_height_true * max(0, book_offset_koma - BASE_BOOK_OFFSET_KOMA)
                    line_bottom = max(line_top + 1, base_line_bottom + extra_len)
                    line_w = max(1, int(2*scale_w))
                    draw.line([(book_x, line_top), (book_x, line_bottom)], fill=(0,0,0,255), width=line_w)

        # ---- 黒バー（全体の最後のフレーム位置のみ）----
        if page == total_pages - 1:
            idx_last = (last_frame_global - 1) % frames_per_page
            col_last = idx_last // 72
            row_last = idx_last % 72

            bar_y = first_frame_top_y_true + (row_last + 1) * frame_height_true
            bar_x = 0 if col_last == 0 else column_offset_x

            draw.rectangle(
                [
                    (bar_x + 5 + BASE_BAR_SHIFT_X * (true_width / BASE_WIDTH), bar_y),
                    (bar_x + 5 + BASE_BAR_SHIFT_X * (true_width / BASE_WIDTH) + BASE_BAR_WIDTH * (true_width / BASE_WIDTH),
                     bar_y + frame_height_true * 2)
                ],
                fill=(0, 0, 0, 128)
            )

        result_images.append(img)

    return result_images, max_frame

# =============== UI（CSSでサイズ調整） ===============
st.markdown("""
    <style>
    .stApp h1 {
        font-size: 1.35rem !important;
        line-height: 1.3 !important;
        margin-bottom: 0.4rem !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    input[type="text"] {
        font-size: 0.8rem !important;
        height: 1.8rem !important;
        padding: 0 6px !important;
    }
    .stMarkdown h3, .stMarkdown h2 {
        font-size: 1rem !important;
        margin: 0.4rem 0 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("ちゃいむしーと Web版 v4")

# プリセット選択
selected_preset = st.selectbox("会社プリセット", list(presets.keys()))
preset_cfg = presets[selected_preset]

# デフォルト値（プリセットごと）
default_book_koma = preset_cfg.get("default_book_koma", 6)
default_celllabel_koma = preset_cfg.get("default_celllabel_koma", 2)

c1, c2, c3 = st.columns(3)
with c1:
    show_books = st.checkbox("Bookマーカーを描画する", value=True)
with c2:
    book_offset_koma = st.slider("Bookの高さ（何コマ上）", 0, 12, int(default_book_koma), 1)
with c3:
    celllabel_koma = st.slider("セル名の高さ（何コマ上）", 0, 6, int(default_celllabel_koma), 1)

# 丸/三角設定（入力はひとつだけ）
with st.expander("原画番号の丸/参考設定", expanded=True):
    # 例: A1, A10a, C24, 3, 5-7, 10a
    triangle_spec_str = st.text_input(
        "参考にする指定（A1,A6,A10a,コンマで区切る）",
        value=""
    )

    # 英字付き（例: 10a, 7b）は全て参考にする
    alpha_all_triangle = st.checkbox("英字付き(例: 10a, 7b)はすべて参考にする", value=True)

    # 不透明度（％）スライダー → 0〜255 に変換（枠のみ）
    tri_alpha_pct  = st.slider("三角の枠の不透明度(%)", 0, 100, int(round(TRIANGLE_OUTLINE_ALPHA * 100 / 255)))
    circ_alpha_pct = st.slider("丸の枠の不透明度(%)", 0, 100, int(round(CIRCLE_OUTLINE_ALPHA   * 100 / 255)))
    triangle_outline_alpha = int(round(tri_alpha_pct  * 255 / 100))
    circle_outline_alpha   = int(round(circ_alpha_pct * 255 / 100))

# セル名入力（1ページ目・縦書き）
with st.expander("セル名（A〜H）を入力（縦書き・1ページ目のみ / 日本語OK）", expanded=True):
    default_labels = {c: "" for c in CELLS_ALL}
    cols = st.columns(4)
    cell_labels = {}
    for i, cell in enumerate(CELLS_ALL):
        with cols[i % 4]:
            cell_labels[cell] = st.text_input(f"{cell} セルのラベル", value=default_labels[cell], key=f"label_{cell}")

uploaded_file = st.file_uploader("CSVファイルをアップロード", type=["csv"])

if uploaded_file is not None:
    if st.button("タイムシート生成！"):
        pages, total_frames = generate_timesheet(
            uploaded_file.read(),
            preset_cfg,
            show_books=show_books,
            book_offset_koma=book_offset_koma,
            cell_labels=cell_labels,
            celllabel_koma=celllabel_koma,
            mixed_triangle_str=triangle_spec_str,   # ← 入力ひとつを渡す（UIのテキストボックス値）
            triangle_outline_alpha=triangle_outline_alpha,
            circle_outline_alpha=circle_outline_alpha,
            alpha_all_triangle=alpha_all_triangle,
        )
        if not pages:
            st.warning("有効なFrameデータが見つかりませんでした。")
        else:
            seconds = total_frames // 24
            remainder = total_frames % 24
            st.text_input("TIME", value=f"{seconds} + {remainder}")

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for i, page in enumerate(pages):
                    st.image(page, caption=f"Page {i+1}", use_container_width=True)
                    b = io.BytesIO(); page.save(b, format='PNG'); b.seek(0)
                    content = b.getvalue()
                    zipf.writestr(f"timesheet_page_{i+1}.png", content)
                    st.download_button(
                        label=f"⬇️ Page {i+1} ダウンロード",
                        data=content,
                        file_name=f"timesheet_page_{i+1}.png",
                        mime="image/png"
                    )
            zip_buffer.seek(0)
            st.download_button(
                label="📦 すべてまとめてダウンロード（ZIP）",
                data=zip_buffer.getvalue(),
                file_name="timesheets_all.zip",
                mime="application/zip"
            )
