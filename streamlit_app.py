import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile

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
        "true_height": 4961
    },
    "動画工房": {
        "first_frame_top_y_true": 468,
        "frame_height_true": 27.25,
        "cell_x_positions_true": {cell: 51.7 + 29 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 870,
        "true_width": 1754,
        "true_height": 2480
    }
}

# 位置調整の基準（Andraft基準）
BASE_FRAME_HEIGHT = 49.5
BASE_WIDTH = 3508
BASE_CIRCLE_OFFSET_X = -5
BASE_CIRCLE_OFFSET_Y = -2
BASE_ALPHABET_OFFSET_X = -13
BASE_CROSS_OFFSET_X = -6
BASE_BAR_WIDTH = 1620
BASE_BAR_SHIFT_X = 88
text_offset_y = 4

# bookラインの旧デフォ（線の下端算出に使用）
BASE_BOOK_OFFSET_KOMA = 3

# ヘッダ（セル名）固定オフセット（px基準）— プリセットに合わせてスケールされる
HEADER_X_NUDGE_PX      = 10   # 右に10px（負で左）
HEADER_BOTTOM_NUDGE_PX = -80  # 下端基準から上に80px（負で上）

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
    """セル名の縦書き専用：横棒っぽい文字を縦棒に統一"""
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
    """各列で最初の空白だけ×を入れる（列が完全空欄なら何もしない）"""
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
    """_book列の左右の A〜H を見て、before/between/after を決める"""
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

# === 縦書き描画（セル名用・下揃え） ===
def draw_vertical_bottom(draw, text, bottom_x, bottom_y, font, spacing=0):
    """
    text を縦書きで、(bottom_x, bottom_y) を“縦列の下端”にして描画。
    spacing は各文字間のpx。
    """
    if not text:
        return
    text = normalize_for_vertical(text)
    boxes = []
    total_h = 0
    for ch in text:
        bbox = draw.textbbox((0, 0), ch, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        boxes.append((ch, w, h))
        total_h += h
    total_h += spacing * (len(boxes) - 1 if boxes else 0)

    # 下端から上へ積み上げ
    y = bottom_y - total_h
    for ch, w, h in boxes:
        draw.text((bottom_x - w / 2.0, y), ch, fill=(0, 0, 0, 255), font=font)
        y += h + spacing

# =============== 本体 ===============
def generate_timesheet(file_bytes, preset, show_books=True, book_offset_koma=6,
                       cell_label_offset_koma=2, cell_labels=None):
    # プリセット
    true_width = preset["true_width"]
    true_height = preset["true_height"]
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

    # 1コマ幅推定（必要になったら使う）
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
    label_font  = ImageFont.truetype(font_path, size=int(base_font_size * 0.6 * scale_h))  # book
    try:
        cell_label_font = ImageFont.truetype(jp_font_path, size=int(base_font_size * 0.9 * scale_h))
    except Exception:
        cell_label_font = ImageFont.truetype(font_path, size=int(base_font_size * 0.9 * scale_h))

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
    result_images = []

    # セル名の辞書（空文字は描画しない）
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

        # ---- セル名ヘッダ（1ページ目だけ・縦書き・左カラムのみ・下揃え）----
        if page == 0:
            # 「数字が始まる位置の n コマ上」を“下端”として使う（スライダーで可変）
            header_bottom_y = (first_frame_top_y_true
                               - cell_label_offset_koma * frame_height_true
                               + (HEADER_BOTTOM_NUDGE_PX * scale_h))
            glyph_spacing = 2 * scale_h
            x_col = 0  # 左カラムのみ
            for cell in valid_cells:
                label = (cell_labels.get(cell) or "").strip()
                if not label:
                    continue
                x_center = x_col + cell_x_positions_true[cell] + (HEADER_X_NUDGE_PX * scale_w)
                draw_vertical_bottom(
                    draw,
                    label,
                    bottom_x=x_center,
                    bottom_y=header_bottom_y,
                    font=cell_label_font,
                    spacing=glyph_spacing
                )

        # ---- 通常セル ----
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

                if timing in ('●','○'):
                    x += circle_offset_x; y_draw += circle_offset_y
                elif timing == '×':
                    x += cross_offset_x
                elif re.match(r"^\d+[a-zA-Z]$", timing) or re.fullmatch(r"\d{2,}", timing):
                    x += alphabet_offset_x

                font = font_small if len(timing)>=3 else font_large
                draw.text((x, y_draw), timing, fill=(0,0,0,255), font=font)

        # ---- book マーカー（重なり回避＆突き抜け防止）----
        if show_books:
            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                idx = (frame-1) % frames_per_page
                col_block = idx // 72
                row_pos = idx % 72

                row_y_base = first_frame_top_y_true + row_pos*frame_height_true
                col_x_offset = column_offset_x if col_block==1 else 0

                present = {}
                for book_col, pos in book_positions.items():
                    cname = norm_str(book_col)
                    if (cname in row.index) and is_filled(row[cname]):
                        present.setdefault(pos, []).append(cname)

                for pos, books_here in present.items():
                    # X座標（Aの前／間／後）
                    book_x = None
                    if pos.startswith("before_"):
                        tgt = pos.replace("before_","")
                        if tgt in cell_x_positions_true:
                            book_x = cell_x_positions_true[tgt] - 12*scale_w
                    elif pos.startswith("between_"):
                        parts = pos.split("_")
                        if len(parts) == 3:
                            _, left, right = parts
                            if left in cell_x_positions_true and right in cell_x_positions_true:
                                # 左セル中心 + 0.8コマ - 3px（全between共通）
                                book_x = cell_x_positions_true[left] + 0.8 * (koma_width) - 3 * scale_w
                    elif pos.startswith("after_"):
                        tgt = pos.replace("after_","")
                        if tgt in cell_x_positions_true:
                            book_x  = cell_x_positions_true[tgt] + 0.8 * (koma_width) - 3 * scale_w
                    if book_x is None:
                        continue

                    book_x = book_x + col_x_offset - 5
                    y_ref = row_y_base - (frame_height_true * book_offset_koma)

                    base_line_top    = y_ref - 4*scale_h
                    base_line_bottom = y_ref + (frame_height_true*2) + 2*scale_h

                    # ラベル順（若い番号→上）
                    items = []
                    for b in books_here:
                        s = norm_str(b).replace("_","")
                        m = re.search(r"(\d+)$", s)
                        n = int(m.group(1)) if m else 0
                        items.append((n, s))
                    items.sort(key=lambda t: t[0])

                    line_gap = 2*scale_h
                    margin   = 12*scale_w

                    # 位置ごとに、ラベルの“最下段の底”を求める
                    placed_boxes = []
                    bottom_label_bottom = None

                    def overlap(a,b):
                        ax1,ay1,ax2,ay2 = a
                        bx1,by1,bx2,by2 = b
                        return not (ax2<=bx1 or bx2<=ax1 or ay2<=by1 or by2<=ay1)

                    for idx_item, (_, label) in enumerate(items):
                        bbox = draw.textbbox((0, 0), label, font=label_font)
                        lw = bbox[2] - bbox[0]
                        lh = bbox[3] - bbox[1]

                        base_y = (base_line_top - lh - 2*scale_h) - idx_item * (lh + line_gap)
                        lx_center = book_x - (lw/2)
                        ly = base_y

                        lx = max(margin, min(true_width - margin - lw, lx_center))

                        cur = (lx, ly, lx+lw, ly+lh)
                        while any(overlap(cur, box) for box in placed_boxes):
                            ly -= (lh + line_gap)
                            cur = (lx, ly, lx+lw, ly+lh)

                        draw.text((lx, ly), label, fill=(0,0,0,255), font=label_font)
                        placed_boxes.append(cur)

                        if (bottom_label_bottom is None) or (ly + lh > bottom_label_bottom):
                            bottom_label_bottom = ly + lh

                    # ラベル直下から線（上端）— 最下段ラベルに追従（突き抜け防止）
                    pad_top = 2 * scale_h
                    line_top = bottom_label_bottom + pad_top if bottom_label_bottom is not None else base_line_top
                    # 下端は book_offset_koma に応じて延長（BASE_BOOK_OFFSET_KOMA との差分で決める）
                    extra_len_by_koma = frame_height_true * max(0, book_offset_koma - BASE_BOOK_OFFSET_KOMA)
                    line_bottom = max(line_top + 1, base_line_bottom + extra_len_by_koma)
                    line_w = max(1, int(2*scale_w))
                    draw.line([(book_x, line_top), (book_x, line_bottom)], fill=(0,0,0,255), width=line_w)

        # ---- 黒バー ----
        if last_frame_in_page:
            idx_last = (last_frame_in_page - 1) % frames_per_page
            col_last = idx_last // 72
            row_last = idx_last % 72
            bar_y = first_frame_top_y_true + (row_last + 1) * frame_height_true
            bar_x = 0 if col_last==0 else column_offset_x
            draw.rectangle(
                [(bar_x + 5 + bar_shift_x, bar_y),
                 (bar_x + 5 + bar_shift_x + bar_width, bar_y + frame_height_true*2)],
                fill=(0,0,0,128)
            )

        result_images.append(img)

    return result_images, max_frame

# =============== デフォルト（プリセット別） ===============
def get_default_offsets(preset_name: str):
    # (book_offset_koma_default, cell_label_offset_koma_default)
    if preset_name == "動画工房":
        return 4, 1
    # Andraft など他は従来どおり
    return 6, 2

# =============== UI ===============
st.title("ちゃいむしーと Web版 v3.0.0｜プリセット別デフォ & セル名“コマ数”スライダー")

c1, c2 = st.columns(2)
with c1:
    selected_preset = st.selectbox("会社プリセット", list(presets.keys()))
with c2:
    show_books = st.checkbox("Bookマーカーを描画する", value=True)

preset_cfg = presets[selected_preset]
# プリセット別デフォを反映
book_default, cell_label_default = get_default_offsets(selected_preset)

book_offset_koma = st.slider("Bookの高さ（何コマ上）",
                             min_value=0, max_value=12, value=book_default, step=1)
cell_label_offset_koma = st.slider("セル名の高さ（何コマ上）",
                                   min_value=0, max_value=12, value=cell_label_default, step=1)

# セル名（縦書き）の入力（1ページ目だけ描画）
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
            cell_label_offset_koma=cell_label_offset_koma,
            cell_labels=cell_labels
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
