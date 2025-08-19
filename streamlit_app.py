import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile, xml.etree.ElementTree as ET

# =============== 基本定義 ===============
cell_offsets = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7}
CELLS_ALL = list(cell_offsets.keys())

presets = {
    "Andraft": {
        "first_frame_top_y_true": 1278.67,
        "frame_height_true": 49.5,
        "cell_x_positions_true": {cell: 110 + 55 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 1690,
        "true_width": 3508,
        "true_height": 4961,
        "default_book_koma": 6,
        "default_celllabel_koma": 2,
        # --- カメラ欄（初期値。UIで微調整可能） ---
        "camera_x_true": 70,     # 左カラムのカメラ欄X（px）
        "camera_label": "CAM",   # 見出し用（使わない場合は空でOK）
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
        "camera_x_true": 35,
        "camera_label": "CAM",
    },
    "ぴえろ": {
        "first_frame_top_y_true": 800,      # 最初のフレームの上端Y
        "frame_height_true": 27.5,          # 1コマの高さ
        "cell_x_positions_true": {cell: 86 + 30.8 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 950.5,           # 右カラムまでのXオフセット
        "true_width": 2026,
        "true_height": 2866,
        "default_book_koma": 4,
        "default_celllabel_koma": 1,
        "camera_x_true": 55,
        "camera_label": "CAM",
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

# セル名オフセット（px基準 → スケール）
HEADER_X_NUDGE_PX      = 10   # 右に10px（負で左）
HEADER_BOTTOM_NUDGE_PX = -80  # 下端基準から上に80px（負で上）

# ○/●/〇 の専用縮小＆位置補正
CIRCLE_SCALE   = 0.5   # 1.0=等倍。小さくしたいなら 0.5〜0.8 くらい
CIRCLE_NUDGE_X = 8     # px（正=右, 負=左）
CIRCLE_NUDGE_Y = 14    # px（正=下,  負=上）

# フォント
font_path    = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
jp_font_path = os.path.join(os.path.dirname(__file__), "NotoSansJP-Regular.otf")
base_font_size = int(12 / (1086 / 3508))

# =============== ユーティリティ ===============
def clean_frame_column(series):
    series = series.astype(str).str.strip().map(lambda x: unicodedata.normalize("NFKC", x))
    series = pd.to_numeric(series, errors='coerce')
    return series

def normalize_for_vertical(text: str) -> str:
    # セル名の縦書き用：横棒を縦棒に
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
    # 各列の最初の空白だけ × を入れる（列が完全空欄なら何もしない）
    for cell in valid_cells:
        if cell not in df_raw.columns:
            continue
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
    # _book列の左右の A〜H を見て、before/between/after を決める
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

# 縦書き（セル名・下揃え）
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
                # 左セル中心 + 0.8コマ + 3px相当
                book_x = cell_x_positions_true[left] + 0.8 * koma_width + 3 * scale_w
    elif pos.startswith("after_"):
        tgt = pos.replace("after_", "")
        if tgt in cell_x_positions_true:
            book_x = cell_x_positions_true[tgt] + 0.8 * koma_width + 3 * scale_w
    return book_x

# =============== XDTS（カメラ） ===============
def read_xdts_camera(file_bytes):
    """
    XDTS（XML）から Cameraトラック/フォルダっぽい要素を拾って、
    Frame & Label を返す。構造差異を吸収するためルーズに探索。
    """
    frames = []
    try:
        tree = ET.parse(io.BytesIO(file_bytes))
        root = tree.getroot()

        # Track/Layer/Folder…名前に 'camera' を含むノード配下の key を探索
        camera_like = root.findall(".//*[@name]")
        for node in camera_like:
            name = (node.get("name") or "").lower()
            if "camera" not in name:
                continue
            # キー候補：<key frame="123" label="PAN"> or value/text
            for key in node.findall(".//key"):
                f = key.get("frame") or key.get("Frame") or "0"
                try:
                    frame = int(float(f))
                except:
                    continue
                if frame <= 0:
                    continue
                label = key.get("label") or key.get("value") or ""
                label = norm_str(label)
                if not label:
                    # テキストノードに文字が入るケースにも対応
                    if key.text and norm_str(key.text):
                        label = norm_str(key.text)
                if label:
                    frames.append({"Frame": frame, "Camera": label})

        # 予備：<event>などに入る場合
        if not frames:
            for ev in root.findall(".//event"):
                cname = (ev.get("name") or "").lower()
                if "camera" in cname:
                    f = ev.get("frame") or "0"
                    try:
                        frame = int(float(f))
                    except:
                        continue
                    txt = ev.get("label") or ev.get("value") or ev.text or ""
                    txt = norm_str(txt)
                    if frame > 0 and txt:
                        frames.append({"Frame": frame, "Camera": txt})

    except Exception as e:
        st.error(f"XDTSの読み込みに失敗しました: {e}")
        return pd.DataFrame()

    if not frames:
        return pd.DataFrame()
    return pd.DataFrame(frames).drop_duplicates(subset=["Frame"]).sort_values("Frame")


# =============== 本体 ===============
def generate_timesheet(df_base, preset, show_books=True, book_offset_koma=6, cell_labels=None, celllabel_koma=2,
                       camera_x_px=None, camera_y_nudge_px=0, camera_font_scale=1.0):
    """
    df_base: 既に DataFrame 化されたデータ（CSV + もしあれば Camera列をマージ済み）
    camera_x_px: カメラ欄のX（左カラム基準px）。Noneならプリセットの camera_x_true を使う。
    """
    # プリセット
    true_width = preset["true_width"]; true_height = preset["true_height"]
    frame_height_true = preset["frame_height_true"]
    first_frame_top_y_true = preset["first_frame_top_y_true"]
    column_offset_x = preset["column_offset_x"]
    cell_x_positions_true = preset["cell_x_positions_true"]
    preset_camera_x = preset.get("camera_x_true", 60)

    # スケール
    scale_h = frame_height_true / BASE_FRAME_HEIGHT
    scale_w = true_width / BASE_WIDTH

    circle_offset_x = BASE_CIRCLE_OFFSET_X * scale_w
    circle_offset_y = BASE_CIRCLE_OFFSET_Y * scale_h
    alphabet_offset_x = BASE_ALPHABET_OFFSET_X * scale_w
    cross_offset_x = BASE_CROSS_OFFSET_X * scale_w

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

    # === データ整形 ===
    if df_base.empty or 'Frame' not in df_base.columns:
        return [], 0
    df = df_base.copy()
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

    # カメラ欄X
    cam_x_left = preset_camera_x if (camera_x_px is None) else camera_x_px

    # カメラフォント
    camera_font = ImageFont.truetype(
        font_path,
        size=max(1, int(base_font_size * 0.9 * scale_h * camera_font_scale))
    )

    cell_labels = cell_labels or {}

    for page in range(total_pages):
        img = Image.new("RGBA", (true_width, true_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        start = page*frames_per_page + 1
        end = (page+1)*frames_per_page
        df_page = df[(df['Frame']>=start) & (df['Frame']<=end)]
        if df_page.empty:
            result_images.append(img); continue

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

        # ---- 通常セル（A〜H）----
        for cell in valid_cells:
            x_base = cell_x_positions_true[cell]
            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                timing = str(row[cell]) if (cell in row and not pd.isna(row[cell])) else ""
                idx = (frame-1) % frames_per_page
                col_block = idx // 72
                row_pos = idx % 72
                y = first_frame_top_y_true + row_pos*frame_height_true
                x = x_base if col_block==0 else x_base + column_offset_x
                y_draw = y + text_offset_y

                # 記号の位置＆フォント
                if timing in ('●','○','〇'):
                    x += circle_offset_x + (CIRCLE_NUDGE_X * scale_w)
                    y_draw += circle_offset_y + (CIRCLE_NUDGE_Y * scale_h)
                    font = font_circle
                elif timing == '×':
                    x += BASE_CROSS_OFFSET_X * scale_w
                    font = font_large
                elif re.match(r"^\d+[a-zA-Z]$", timing) or re.fullmatch(r"\d{2,}", timing):
                    x += BASE_ALPHABET_OFFSET_X * scale_w
                    font = font_large if len(timing) < 3 else font_small
                else:
                    font = font_small if len(timing) >= 3 else font_large

                draw.text((x, y_draw), timing, fill=(0,0,0,255), font=font)

        # ---- カメラ欄（左カラム側のみ。CSVやXDTSから来た 'Camera' 列を描画）----
        if 'Camera' in df.columns:
            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                cam = str(row['Camera']) if not pd.isna(row['Camera']) else ""
                if not cam or cam.lower() in ("nan", "none"):
                    continue
                idx = (frame-1) % frames_per_page
                col_block = idx // 72         # カメラ欄は左カラム側にのみ描画
                row_pos = idx % 72
                y = first_frame_top_y_true + row_pos * frame_height_true
                x = cam_x_left
                y_draw = y + text_offset_y + (camera_y_nudge_px * scale_h)
                # ○/●も小さく出したいニーズに合わせて同じ扱い
                if cam in ('●','○','〇'):
                    x_draw = x + circle_offset_x + (CIRCLE_NUDGE_X * scale_w)
                    y_draw2 = y_draw + circle_offset_y + (CIRCLE_NUDGE_Y * scale_h)
                    draw.text((x_draw, y_draw2), cam, fill=(0,0,0,255), font=font_circle)
                else:
                    draw.text((x, y_draw), cam, fill=(0,0,0,255), font=camera_font)

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

                # その行でbook値が入っている列を位置ごとに集約
                present = {}
                for book_col, pos in book_positions.items():
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
                                       outline=(0,0,0,255), width=BOX_OUTLINE_W)

                        placed_boxes_row.append(cur_padded)
                        bottom_label_bottom = max(bottom_label_bottom or cur_padded[3], cur_padded[3])

                    pad_top = 2 * scale_h
                    line_top = (bottom_label_bottom + pad_top) if bottom_label_bottom is not None else base_line_top
                    extra_len = frame_height_true * max(0, book_offset_koma - BASE_BOOK_OFFSET_KOMA)
                    line_bottom = max(line_top + 1, base_line_bottom + extra_len)
                    line_w = max(1, int(2*scale_w))
                    draw.line([(book_x, line_top), (book_x, line_bottom)], fill=(0,0,0,255), width=line_w)

        # ---- 黒バー（全体の最後のフレーム位置にのみ描画）----
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
    /* タイトルを小さく＆はみ出し防止 */
    .stApp h1 {
        font-size: 1.35rem !important;
        line-height: 1.3 !important;
        margin-bottom: 0.4rem !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    /* 入力をコンパクトに（セル名用） */
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

st.title("ちゃいむしーと Web版 v3.2.0｜CAM欄対応（CSV＋任意でXDTSマージ）")

# プリセット選択
selected_preset = st.selectbox("会社プリセット", list(presets.keys()))
preset_cfg = presets[selected_preset]

# デフォルト値（プリセットごと）
default_book_koma = preset_cfg.get("default_book_koma", 6)
default_celllabel_koma = preset_cfg.get("default_celllabel_koma", 2)

# ==== 左ペイン（設定） ====
with st.sidebar:
    st.subheader("描画設定")
    show_books = st.checkbox("Bookマーカーを描画", value=True)
    book_offset_koma = st.slider("Bookの高さ（何コマ上）", 0, 12, int(default_book_koma), 1)
    celllabel_koma = st.slider("セル名の高さ（何コマ上）", 0, 6, int(default_celllabel_koma), 1)

    st.markdown("---")
    st.subheader("カメラ欄（見た目調整）")
    cam_x_default = float(preset_cfg.get("camera_x_true", 60))
    camera_x_px = st.number_input("CAM X（px, 左カラム）", value=float(cam_x_default), step=1.0)
    camera_y_nudge_px = st.number_input("CAM 縦補正（px）", value=0.0, step=1.0)
    camera_font_scale = st.slider("CAM 文字サイズ倍率", 0.5, 2.0, 1.0, 0.05)

# セル名入力（1ページ目・縦書き）
with st.expander("セル名（A〜H）を入力（縦書き・1ページ目のみ / 日本語OK）", expanded=False):
    default_labels = {c: "" for c in CELLS_ALL}
    cols = st.columns(4)
    cell_labels = {}
    for i, cell in enumerate(CELLS_ALL):
        with cols[i % 4]:
            cell_labels[cell] = st.text_input(f"{cell} セルのラベル", value=default_labels[cell], key=f"label_{cell}")

# ファイル入力：CSV（必須）＋ XDTS（任意）
c_up1, c_up2 = st.columns(2)
with c_up1:
    csv_file = st.file_uploader("CSVファイルをアップロード", type=["csv"])
with c_up2:
    xdts_file = st.file_uploader("XDTS（任意, CAMラベル抽出用）", type=["xdts"])

df_main = pd.DataFrame()
if csv_file is not None:
    df_main = read_csv_flexibly(csv_file.read())

# XDTS → カメラDF
df_cam = pd.DataFrame()
if xdts_file is not None:
    df_cam = read_xdts_camera(xdts_file.read())
    if df_cam.empty:
        st.info("XDTSからカメラ情報は見つかりませんでした。")

# マージ（CSVがなくても、XDTSだけで描画可能：Frame＋Camera）
df_for_draw = None
if not df_main.empty and not df_cam.empty:
    df_for_draw = pd.merge(df_main, df_cam, on="Frame", how="outer").sort_values("Frame").reset_index(drop=True)
elif not df_main.empty:
    df_for_draw = df_main
elif not df_cam.empty:
    df_for_draw = df_cam
else:
    df_for_draw = pd.DataFrame()

# =============== 実行 ===============
if (csv_file is not None) or (xdts_file is not None):
    if st.button("タイムシート生成！"):
        pages, total_frames = generate_timesheet(
            df_for_draw,
            preset_cfg,
            show_books=show_books,
            book_offset_koma=book_offset_koma,
            cell_labels=cell_labels,
            celllabel_koma=celllabel_koma,
            camera_x_px=camera_x_px,
            camera_y_nudge_px=camera_y_nudge_px,
            camera_font_scale=camera_font_scale
        )
        if not pages:
            st.warning("有効なFrameデータが見つかりませんでした。")
        else:
            seconds = total_frames // 24
            remainder = total_frames % 24
            st.text_input("TIME", value=f"{seconds} + {remainder}")

            # 出力＆ZIP
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
