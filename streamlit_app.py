import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile

# =============== 基本定義 ===============
cell_offsets = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7}
CELLS_ALL = list(cell_offsets.keys())

# プリセット（画像解像度／座標）
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

# スケール基準値（Andraft基準）
BASE_FRAME_HEIGHT = 49.5
BASE_WIDTH = 3508
BASE_CIRCLE_OFFSET_X = -5
BASE_CIRCLE_OFFSET_Y = -2
BASE_ALPHABET_OFFSET_X = -13
BASE_CROSS_OFFSET_X = -6
BASE_BAR_WIDTH = 1620
BASE_BAR_SHIFT_X = 88
text_offset_y = 4

# 「〜の間」の既定シフト（コマ単位）と微妙なpx調整（あとで scale_w 掛ける）
MID_SHIFT_DEFAULT_KOMA = 0.5     # 中央から右へ 0.5コマ
MID_FINE_DEFAULT_PX     = -3     # さらに左へ 3px
# 個別ペアの上書き（必要ならここに追加）
MID_SHIFT_OVERRIDES_KOMA = {
    ("B", "C"): 0.35,
    ("C", "D"): 0.35,
}
MID_FINE_OVERRIDES_PX = {
    ("B", "C"): -4,
    ("C", "D"): -4,
}

# フォント
font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
base_font_size = int(12 / (1086 / 3508))  # 既存基準

# =============== ユーティリティ ===============
def norm_str(s: object) -> str:
    # 全角→半角、全角スペース→半角、前後スペース除去
    return unicodedata.normalize("NFKC", str(s)).replace("\u3000", " ").strip()

def is_filled(v: object) -> bool:
    s = norm_str(v)
    return s not in ("", "nan", "None")

def clean_frame_column(series):
    series = series.astype(str).str.strip().map(lambda x: unicodedata.normalize("NFKC", x))
    series = pd.to_numeric(series, errors='coerce')
    return series

def read_csv_flexibly(file_bytes):
    try:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding="shift_jis", header=[0, 1], keep_default_na=False)
        # 2段ヘッダーをフラット化（LO配下の列名を第二レベルで採用）
        df.columns = [col[1] if col[1] != '' else col[0] for col in df.columns]
        if 'Unnamed: 0_level_1' in df.columns:
            df = df.rename(columns={'Unnamed: 0_level_1': 'Frame'})
        # 列名を正規化
        df.columns = [norm_str(c) for c in df.columns]
        return df
    except Exception as e:
        st.error(f"CSVの読み込みに失敗しました: {e}")
        return pd.DataFrame()

def preprocess_cells(df_raw, valid_cells):
    """各列の最初の空白にだけ × を入れる（その列が完全空は除外）。"""
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
    """_book列（または book列）の“列順”から挿入位置（before_/between_/after_）を決める。"""
    cols = list(df.columns)
    book_cols = [c for c in cols if re.match(r"^_?book\d+$", str(c), re.IGNORECASE)]
    positions = {}
    for b in book_cols:
        idx = cols.index(b)
        # 左右の近い A〜H を探す
        left_cell = None
        for i in range(idx - 1, -1, -1):
            if cols[i] in valid_cells:
                left_cell = cols[i]
                break
        right_cell = None
        for i in range(idx + 1, len(cols)):
            if cols[i] in valid_cells:
                right_cell = cols[i]
                break
        if left_cell is None and right_cell is None:
            continue
        if left_cell is None:
            positions[b] = f"before_{right_cell}"
        elif right_cell is None:
            positions[b] = f"after_{left_cell}"
        else:
            positions[b] = f"between_{left_cell}_{right_cell}"
    return positions

# =============== book描画（インデント崩れ対策で関数化） ===============
def render_book_markers(
    draw, row, book_positions, cell_x_positions_true, column_offset_x,
    first_frame_top_y_true, frame_height_true, col_block, row_pos,
    true_width, scale_w, scale_h, koma_width, label_font
):
    # この行で出ているbookだけ集計（ポジションごと）
    present = {}
    for book_col, pos in book_positions.items():
        cname = norm_str(book_col)  # "_book2" でも "book2" でもOK
        if (cname in row.index) and is_filled(row[cname]):
            present.setdefault(pos, []).append(cname)

    # 行基準
    row_y_base = first_frame_top_y_true + row_pos * frame_height_true
    col_x_offset = column_offset_x if col_block == 1 else 0

    for pos, books_here in present.items():
        # === 縦線 x（ポジションごとに独立） ===
        book_x = None
        if pos.startswith("before_"):
            tgt = pos.replace("before_", "")
            if tgt in cell_x_positions_true:
                book_x = cell_x_positions_true[tgt] - 10 * scale_w
        elif pos.startswith("between_"):
            _, left, right = pos.split("_")
            if left in cell_x_positions_true and right in cell_x_positions_true:
                mid = (cell_x_positions_true[left] + cell_x_positions_true[right]) / 2
                shift_koma = MID_SHIFT_OVERRIDES_KOMA.get((left, right), MID_SHIFT_DEFAULT_KOMA)
                fine_px    = MID_FINE_OVERRIDES_PX.get((left, right), MID_FINE_DEFAULT_PX)
                book_x = mid + shift_koma * koma_width + fine_px * scale_w
        elif pos.startswith("after_"):
            tgt = pos.replace("after_", "")
            if tgt in cell_x_positions_true:
                book_x = cell_x_positions_true[tgt] + 10 * scale_w
        if book_x is None:
            continue

        # 右カラム補正 + 左に5px
        book_x = book_x + col_x_offset - 5

        # === ラベル配置（このポジション内だけで完結） ===
        # 若番ほど上（book1 → 一番上）
        items = []
        for b in books_here:
            s = norm_str(b).replace("_", "")
            m = re.search(r"(\d+)$", s)
            n = int(m.group(1)) if m else 0
            items.append((n, s))
        items.sort(key=lambda t: t[0])

        # 3コマ上の基準、ベース縦線長
        y_ref = row_y_base - (frame_height_true * 3)
        base_line_top    = y_ref - 4 * scale_h
        base_line_bottom = y_ref + (frame_height_true * 2) + 2 * scale_h

        # グループ一括クランプ（このポジションだけ）
        margin = 12 * scale_w
        line_gap = 2 * scale_h
        sizes, max_w = {}, 0
        for _, label in items:
            bbox = draw.textbbox((0, 0), label, font=label_font)
            lw = bbox[2] - bbox[0]; lh = bbox[3] - bbox[1]
            sizes[label] = (lw, lh)
            max_w = max(max_w, lw)

        group_dx = 0.0
        if book_x - max_w/2 < margin:
            group_dx = margin - (book_x - max_w/2)
        elif book_x + max_w/2 > (true_width - margin):
            group_dx = (true_width - margin) - (book_x + max_w/2)

        # ラベル配置（同ポジション内の重なり回避）
        placed = []
        min_label_y = None
        for idx_item, (_, label) in enumerate(items):
            lw, lh = sizes[label]
            base_y = (base_line_top - lh - 2 * scale_h) - idx_item * (lh + line_gap)
            lx = (book_x + group_dx) - lw/2
            ly = base_y

            def overlap(a, b):
                ax1, ay1, ax2, ay2 = a
                bx1, by1, bx2, by2 = b
                return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)
            cur = (lx, ly, lx+lw, ly+lh)
            while any(overlap(cur, r) for r in placed):
                ly -= (lh + line_gap)
                cur = (lx, ly, lx+lw, ly+lh)

            draw.text((lx, ly), label, fill=(0,0,0,255), font=label_font)
            placed.append(cur)
            if (min_label_y is None) or (ly < min_label_y):
                min_label_y = ly

        # ラベルに合わせてこの縦線だけ上に延長
        line_top = base_line_top
        if min_label_y is not None and (min_label_y - 2*scale_h) < line_top:
            line_top = min_label_y - 2*scale_h
        line_w = max(1, int(2 * scale_w))
        draw.line([(book_x, line_top), (book_x, base_line_bottom)],
                  fill=(0,0,0,255), width=line_w)

# =============== 本体 ===============
def generate_timesheet(file_bytes, preset):
    # プリセット読込
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

    # 1コマ幅（AとBの差）を推定
    try:
        koma_width = cell_x_positions_true['B'] - cell_x_positions_true['A']
    except Exception:
        xs = [cell_x_positions_true[c] for c in sorted(cell_x_positions_true.keys())]
        diffs = [xs[i+1] - xs[i] for i in range(len(xs) - 1)]
        koma_width = sum(diffs) / len(diffs) if diffs else 0

    # フォント
    font_large = ImageFont.truetype(font_path, size=int(base_font_size * scale_h))
    font_small = ImageFont.truetype(font_path, size=int(base_font_size * 0.9 * scale_h))
    label_font  = ImageFont.truetype(font_path, size=int(base_font_size * 0.5 * scale_h))  # book少し小さめ

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

    # _book の列順から挿入位置を決定
    book_positions = get_book_positions(df, valid_cells)

    max_frame = df['Frame'].max()
    frames_per_page = 144
    total_pages = math.ceil(max_frame / frames_per_page)

    result_images = []

    for page in range(total_pages):
        img = Image.new("RGBA", (true_width, true_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        start = page * frames_per_page + 1
        end = (page + 1) * frames_per_page
        df_page = df[(df['Frame'] >= start) & (df['Frame'] <= end)]
        if df_page.empty:
            result_images.append(img)
            continue

        last_frame_in_page = df_page['Frame'].max()

        # ---- 通常セル描画 ----
        for cell in valid_cells:
            x_base = cell_x_positions_true[cell]
            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                timing = str(row[cell]) if not pd.isna(row[cell]) else ""
                idx = (frame - 1) % frames_per_page
                col_block = idx // 72  # 0: 左, 1: 右
                row_pos = idx % 72
                y = first_frame_top_y_true + row_pos * frame_height_true
                x = x_base if col_block == 0 else x_base + column_offset_x
                y_draw = y + text_offset_y

                if timing in ('●', '○'):
                    x += circle_offset_x
                    y_draw += circle_offset_y
                elif timing == '×':
                    x += cross_offset_x
                elif re.match(r"^\d+[a-zA-Z]$", timing) or re.fullmatch(r"\d{2,}", timing):
                    x += alphabet_offset_x

                font = font_small if len(timing) >= 3 else font_large
                draw.text((x, y_draw), timing, fill=(0, 0, 0, 255), font=font)

        # ---- bookマーカー描画（1行に1回呼び出し） ----
        for _, row in df_page.iterrows():
            frame = int(row['Frame'])
            idx = (frame - 1) % frames_per_page
            col_block = idx // 72                 # 0=左, 1=右
            row_pos = idx % 72

            render_book_markers(
                draw, row, book_positions, cell_x_positions_true, column_offset_x,
                first_frame_top_y_true, frame_height_true, col_block, row_pos,
                true_width, scale_w, scale_h, koma_width, label_font
            )

        # ---- 黒バー（ページ末尾） ----
        if last_frame_in_page:
            idx_last = (last_frame_in_page - 1) % frames_per_page
            col_last = idx_last // 72
            row_last = idx_last % 72
            bar_y = first_frame_top_y_true + (row_last + 1) * frame_height_true
            bar_x = 0 if col_last == 0 else column_offset_x
            draw.rectangle(
                [(bar_x + 5 + bar_shift_x, bar_y),
                 (bar_x + 5 + bar_shift_x + bar_width, bar_y + frame_height_true * 2)],
                fill=(0, 0, 0, 128)
            )

        result_images.append(img)

    return result_images, max_frame

# =============== Streamlit UI ===============
st.title("ちゃいむしーと Web版 v1.9.7｜book縦線＆ラベル（ポジション独立・3コマ上・重なり回避）")
selected_preset = st.selectbox("会社プリセットを選択", list(presets.keys()))
preset_cfg = presets[selected_preset]

uploaded_file = st.file_uploader("CSVファイルをアップロード", type=["csv"])

if uploaded_file is not None:
    if st.button("タイムシート生成！"):
        pages, total_frames = generate_timesheet(uploaded_file.read(), preset_cfg)
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
                    b = io.BytesIO()
                    page.save(b, format='PNG')
                    b.seek(0)
                    zipf.writestr(f"timesheet_page_{i+1}.png", b.getvalue())
                    st.download_button(
                        label=f"⬇️ Page {i+1} ダウンロード",
                        data=b.getvalue(),
                        file_name=f"timesheet_page_{i+1}.png",
                        mime="image/png"
                    )
            zip_buffer.seek(0)
            st.download_button(
                label="📦 すべてまとめてダウンロード（ZIP）",
                data=zip_buffer,
                file_name="timesheets_all.zip",
                mime="application/zip"
            )
