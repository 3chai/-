# ちゃいむしーと v1.9.3 with book列描画対応

import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile

# 列オフセット
cell_offsets = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7}
cell_list = list(cell_offsets.keys())

# プリセット辞書
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

# オフセット基準
BASE_FRAME_HEIGHT = 49.5
BASE_WIDTH = 3508
BASE_CROSS_OFFSET_X = -6
BASE_ALPHABET_OFFSET_X = -13
BASE_CIRCLE_OFFSET_X = -5
BASE_CIRCLE_OFFSET_Y = -2
BASE_BAR_WIDTH = 1620
BASE_BAR_SHIFT_X = 88
text_offset_y = 4

font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
font_size_true = int(12 / (1086 / 3508))

def draw_vertical_text(draw, text, x, y, font, fill):
    for i, char in enumerate(text):
        draw.text((x, y + i * font.size), char, font=font, fill=fill)

def clean_frame_column(series):
    series = series.astype(str).str.strip().map(lambda x: unicodedata.normalize("NFKC", x))
    series = pd.to_numeric(series, errors='coerce')
    return series

def read_csv_flexibly(file_bytes):
    df = pd.read_csv(io.BytesIO(file_bytes), encoding="shift_jis", header=[0, 1], keep_default_na=False)
    df.columns = [col[1] if col[1] != '' else col[0] for col in df.columns]
    if 'Unnamed: 0_level_1' in df.columns:
        df = df.rename(columns={'Unnamed: 0_level_1': 'Frame'})
    return df

def get_book_positions(df):
    book_cols = [col for col in df.columns if col.startswith('_book')]
    positions = {}
    for col in book_cols:
        idx = df.columns.get_loc(col)
        if idx == 0:
            insert_pos = 'before_A'
        else:
            prev_col = df.columns[idx - 1]
            insert_pos = f"between_{prev_col}_{df.columns[idx + 1]}"
        positions[col] = insert_pos
    return positions

def preprocess_cells(df_raw, valid_cells):
    for cell in valid_cells:
        if df_raw[cell].astype(str).str.strip().replace("nan", "").eq("").all():
            continue
        seen = False
        for idx, row in df_raw.iterrows():
            val = str(row[cell]).strip()
            if val == "" or pd.isna(row[cell]):
                if not seen:
                    df_raw.at[idx, cell] = "×"
                    seen = True
            else:
                seen = True
    return df_raw

def generate_timesheet(file_bytes, preset):
    ff_top = preset["first_frame_top_y_true"]
    fh = preset["frame_height_true"]
    cx = preset["cell_x_positions_true"]
    offset_x = preset["column_offset_x"]
    true_width = preset["true_width"]
    true_height = preset["true_height"]

    scale_h = fh / BASE_FRAME_HEIGHT
    scale_w = true_width / BASE_WIDTH

    cross_offset_x = BASE_CROSS_OFFSET_X * scale_w
    alphabet_offset_x = BASE_ALPHABET_OFFSET_X * scale_w
    circle_offset_x = BASE_CIRCLE_OFFSET_X * scale_w
    circle_offset_y = BASE_CIRCLE_OFFSET_Y * scale_h
    bar_width = BASE_BAR_WIDTH * scale_w
    bar_shift_x = BASE_BAR_SHIFT_X * scale_w

    font_large = ImageFont.truetype(font_path, size=int(font_size_true * scale_h))
    font_small = ImageFont.truetype(font_path, size=int(font_size_true * 0.9 * scale_h))

    df = read_csv_flexibly(file_bytes)
    if df.empty or 'Frame' not in df.columns:
        return [], 0

    df['Frame'] = clean_frame_column(df['Frame'])
    df = df.dropna(subset=['Frame'])
    df['Frame'] = df['Frame'].astype(int)
    df = df[df['Frame'] > 0]

    valid_cells = [c for c in cell_list if c in df.columns]
    df = preprocess_cells(df, valid_cells)

    book_positions = get_book_positions(df)

    max_frame = df['Frame'].max()
    pages = math.ceil(max_frame / 144)
    results = []

    for page in range(pages):
        img = Image.new("RGBA", (true_width, true_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        start = page * 144 + 1
        end = (page + 1) * 144
        df_page = df[(df['Frame'] >= start) & (df['Frame'] <= end)]

        for cell in valid_cells:
            x_base = cx[cell]
            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                timing = str(row[cell]) if not pd.isna(row[cell]) else ""
                idx = (frame - 1) % 144
                col = idx // 72
                row_pos = idx % 72
                y = ff_top + row_pos * fh
                x = x_base if col == 0 else x_base + offset_x
                y += text_offset_y
                if timing == '●' or timing == '○':
                    x += circle_offset_x
                    y += circle_offset_y
                elif timing == '×':
                    x += cross_offset_x
                elif re.match(r"^\d+[a-zA-Z]$", timing) or re.fullmatch(r"\d{2,}", timing):
                    x += alphabet_offset_x
                font = font_small if len(timing) >= 3 else font_large
                draw.text((x, y), timing, font=font, fill=(0, 0, 0, 255))

        # Book文字挿入
        for bcol, pos in book_positions.items():
            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                val = str(row[bcol]).strip()
                if val == "" or pd.isna(row[bcol]): continue
                idx = (frame - 1) % 144
                col = idx // 72
                row_pos = idx % 72
                y = ff_top + row_pos * fh
                if pos == 'before_A':
                    x = cx['A'] - 30 * scale_w
                elif "between_" in pos:
                    parts = pos.replace("between_", "").split("_")
                    if all(p in cx for p in parts):
                        x = (cx[parts[0]] + cx[parts[1]]) / 2
                    else:
                        continue
                else:
                    continue
                x += offset_x * col
                draw_vertical_text(draw, val, x, y, font_large, (0, 0, 0, 255))

        results.append(img)

    return results, max_frame

# Streamlit UI
st.title("ちゃいむしーと v1.9.3 book列対応版")
selected_preset_name = st.selectbox("会社プリセットを選んでね", list(presets.keys()))
preset_cfg = presets[selected_preset_name]

uploaded_file = st.file_uploader("CSVファイルをアップロードしてね", type=["csv"])

if uploaded_file is not None and st.button("タイムシート生成！"):
    pages, total = generate_timesheet(uploaded_file.read(), preset_cfg)
    if not pages:
        st.warning("Frameデータがなかったよ")
    else:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zipf:
            for i, page in enumerate(pages):
                st.image(page, caption=f"Page {i+1}", use_container_width=True)
                b = io.BytesIO()
                page.save(b, format="PNG")
                zipf.writestr(f"timesheet_page_{i+1}.png", b.getvalue())
                st.download_button(f"⬇️ Page {i+1} ダウンロード", b.getvalue(), file_name=f"timesheet_page_{i+1}.png")

        zip_buf.seek(0)
        st.download_button("📦 ZIPで全部ダウンロード", zip_buf, file_name="timesheets_all.zip")
