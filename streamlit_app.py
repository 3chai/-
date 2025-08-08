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

# スケール基準（Andraft基準）
BASE_FRAME_HEIGHT = 49.5
BASE_WIDTH = 3508
BASE_CIRCLE_OFFSET_X = -5
BASE_CIRCLE_OFFSET_Y = -2
BASE_ALPHABET_OFFSET_X = -13
BASE_CROSS_OFFSET_X = -6
BASE_BAR_WIDTH = 1620
BASE_BAR_SHIFT_X = 88
text_offset_y = 4

# フォント
font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
base_font_size = int(12 / (1086 / 3508))

# ========= ユーティリティ =========
def norm_str(s: object) -> str:
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
        df.columns = [col[1] if col[1] != '' else col[0] for col in df.columns]
        if 'Unnamed: 0_level_1' in df.columns:
            df = df.rename(columns={'Unnamed: 0_level_1': 'Frame'})
        df.columns = [norm_str(c) for c in df.columns]
        return df
    except Exception as e:
        st.error(f"CSVの読み込みに失敗しました: {e}")
        return pd.DataFrame()

def preprocess_cells(df_raw, valid_cells):
    """各列の最初の空白にだけ×（列が完全空は除く）"""
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
    """_book列（またはbook列）の列順から before_/between_/after_ を求める"""
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

# ========= 本体 =========
def generate_timesheet(file_bytes, preset):
    # プリセット
    true_width  = preset["true_width"]
    true_height = preset["true_height"]
    frame_h     = preset["frame_height_true"]
    first_y     = preset["first_frame_top_y_true"]
    col_offset  = preset["column_offset_x"]
    cell_x      = preset["cell_x_positions_true"]

    # スケール
    scale_h = frame_h / BASE_FRAME_HEIGHT
    scale_w = true_width / BASE_WIDTH

    circle_dx = BASE_CIRCLE_OFFSET_X * scale_w
    circle_dy = BASE_CIRCLE_OFFSET_Y * scale_h
    alpha_dx  = BASE_ALPHABET_OFFSET_X * scale_w
    cross_dx  = BASE_CROSS_OFFSET_X * scale_w
    bar_w     = BASE_BAR_WIDTH * scale_w
    bar_shift = BASE_BAR_SHIFT_X * scale_w

    # 1コマ幅（AとB差）推定
    try:
        koma_w = cell_x['B'] - cell_x['A']
    except Exception:
        xs = [cell_x[c] for c in sorted(cell_x.keys())]
        diffs = [xs[i+1]-xs[i] for i in range(len(xs)-1)]
        koma_w = sum(diffs)/len(diffs) if diffs else 0

    # フォント
    font_large = ImageFont.truetype(font_path, size=int(base_font_size * scale_h))
    font_small = ImageFont.truetype(font_path, size=int(base_font_size * 0.9 * scale_h))
    label_font = ImageFont.truetype(font_path, size=int(base_font_size * 0.55 * scale_h))  # book少し小さめ

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

    # book位置
    book_pos = get_book_positions(df, valid_cells)

    max_frame = df['Frame'].max()
    frames_per_page = 144
    total_pages = math.ceil(max_frame / frames_per_page)

    result_images = []

    for page in range(total_pages):
        img = Image.new("RGBA", (true_width, true_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        start = page * frames_per_page + 1
        end   = (page + 1) * frames_per_page
        df_p  = df[(df['Frame'] >= start) & (df['Frame'] <= end)]
        if df_p.empty:
            result_images.append(img); continue

        last_in_page = df_p['Frame'].max()

        # ====== 通常セル ======
        for cell in valid_cells:
            x_base = cell_x[cell]
            for _, row in df_p.iterrows():
                f = int(row['Frame'])
                val = str(row[cell]) if not pd.isna(row[cell]) else ""
                idx = (f - 1) % frames_per_page
                col = idx // 72
                r   = idx % 72
                y   = first_y + r * frame_h
                x   = x_base if col == 0 else x_base + col_offset
                ydraw = y + text_offset_y

                if val in ('●', '○'):
                    x += circle_dx; ydraw += circle_dy
                elif val == '×':
                    x += cross_dx
                elif re.match(r"^\d+[a-zA-Z]$", val) or re.fullmatch(r"\d{2,}", val):
                    x += alpha_dx

                font = font_small if len(val) >= 3 else font_large
                draw.text((x, ydraw), val, fill=(0,0,0,255), font=font)

        # ====== bookマーカー（3コマ上・縦線は上に延長） ======
        for _, row in df_p.iterrows():
            f = int(row['Frame'])
            idx = (f - 1) % frames_per_page
            col = idx // 72
            r   = idx % 72

            row_y = first_y + r * frame_h
            col_x = col_offset if col == 1 else 0

            # この行でbook値が入っているもの
            present = {}
            for bcol, pos in book_pos.items():
                cname = norm_str(bcol)
                if (cname in row.index) and is_filled(row[cname]):
                    present.setdefault(pos, []).append(cname)

            for pos, books_here in present.items():
                # x座標
                x_ins = None
                if pos.startswith("before_"):
                    tgt = pos.replace("before_", "")
                    if tgt in cell_x:
                        x_ins = cell_x[tgt] - 10 * scale_w
                elif pos.startswith("between_"):
                    _, left, right = pos.split("_")
                    if left in cell_x and right in cell_x:
                        mid = (cell_x[left] + cell_x[right]) / 2
                        # 「Aの前はそのまま／それ以降（〜の間）は+1コマ右へ」
                        x_ins = mid + koma_w
                elif pos.startswith("after_"):
                    tgt = pos.replace("after_", "")
                    if tgt in cell_x:
                        x_ins = cell_x[tgt] + 10 * scale_w
                if x_ins is None:
                    continue

                x_ins = x_ins + col_x - 5

                # 3コマ上
                y_ref = row_y - (frame_h * 3)

                # ベース縦線（後で上に延長）
                base_top    = y_ref - 4 * scale_h
                base_bottom = y_ref + (frame_h * 2) + 2 * scale_h

                # 若い番号ほど上（book1が最上段）
                items = []
                for b in books_here:
                    s = norm_str(b).replace("_","")
                    m = re.search(r"(\d+)$", s)
                    n = int(m.group(1)) if m else 0
                    items.append((n, s))
                items.sort(key=lambda t: t[0], reverse=True)  # 数字が大きいほど上に来る: book4, book3, …)

                line_gap = 2 * scale_h
                min_label_y = None

                for i_item, (_, label) in enumerate(items):
                    bbox = draw.textbbox((0,0), label, font=label_font)
                    lw = bbox[2]-bbox[0]; lh = bbox[3]-bbox[1]

                    # book1を一番上、その下にbook2...
                    base_y = (base_top - lh - 2*scale_h) - i_item*(lh + line_gap)
                    lx = x_ins - lw/2
                    ly = base_y

                    draw.text((lx, ly), label, fill=(0,0,0,255), font=label_font)

                    if (min_label_y is None) or (ly < min_label_y):
                        min_label_y = ly

                # ラベル最上端に合わせて縦線を上に延長
                line_top = base_top
                if min_label_y is not None and (min_label_y - 2*scale_h) < line_top:
                    line_top = min_label_y - 2*scale_h
                line_w = max(1, int(2 * scale_w))
                draw.line([(x_ins, line_top), (x_ins, base_bottom)], fill=(0,0,0,255), width=line_w)

        # 黒バー
        if last_in_page:
            i_last = (last_in_page - 1) % frames_per_page
            col_l  = i_last // 72
            r_l    = i_last % 72
            bar_y  = first_y + (r_l + 1) * frame_h
            bar_x  = 0 if col_l == 0 else col_offset
            draw.rectangle(
                [(bar_x + 5 + bar_shift, bar_y),
                 (bar_x + 5 + bar_shift + bar_w, bar_y + frame_h * 2)],
                fill=(0,0,0,128)
            )

        result_images.append(img)

    return result_images, max_frame

# =============== Streamlit UI ===============
st.title("ちゃいむしーと Web版 v1.9.5（戻し版：book縦線は上に延長／3コマ上）")
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
