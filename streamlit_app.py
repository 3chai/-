import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile

# 列オフセット
cell_offsets = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7}

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

font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")


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
        return df
    except Exception as e:
        st.error(f"CSVの読み込みに失敗しました: {e}")
        return pd.DataFrame()


def get_book_positions(df):
    positions = []
    for col in df.columns:
        if col.startswith("_book"):
            idx = df.columns.get_loc(col)
            if idx == 0:
                insert_pos = f"before_{df.columns[idx+1]}"
            else:
                prev_col = df.columns[idx-1]
                next_col = df.columns[idx+1] if idx + 1 < len(df.columns) else ""
                insert_pos = f"between_{prev_col}_{next_col}"
            positions.append((col, insert_pos))
    return positions


def generate_timesheet(file_bytes, preset):
    # プリセット読み込み
    true_width = preset["true_width"]
    true_height = preset["true_height"]
    frame_height_true = preset["frame_height_true"]
    first_frame_top_y_true = preset["first_frame_top_y_true"]
    column_offset_x = preset["column_offset_x"]
    cell_x_positions_true = preset["cell_x_positions_true"]

    scale_factor = true_height / 4961
    font = ImageFont.truetype(font_path, size=int(90 * scale_factor))
    book_font = ImageFont.truetype(font_path, size=int(75 * scale_factor))

    df = read_csv_flexibly(file_bytes)
    if df.empty or 'Frame' not in df.columns:
        return [], 0

    df['Frame'] = clean_frame_column(df['Frame'])
    df = df.dropna(subset=['Frame'])
    df['Frame'] = df['Frame'].astype(int)
    max_frame = df['Frame'].max()
    pages = []
    per_page = 144

    book_positions = get_book_positions(df)

    for p in range(math.ceil(max_frame / per_page)):
        img = Image.new("RGBA", (true_width, true_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        start = p * per_page + 1
        end = start + per_page - 1
        df_page = df[(df['Frame'] >= start) & (df['Frame'] <= end)]

        for _, row in df_page.iterrows():
            f = row['Frame']
            y = first_frame_top_y_true + ((f - 1) % per_page) % 72 * frame_height_true
            col_block = ((f - 1) % per_page) // 72
            offset_x = 0 if col_block == 0 else column_offset_x

            for cell, x_base in cell_x_positions_true.items():
                val = str(row.get(cell, "")).strip()
                if val:
                    draw.text((x_base + offset_x, y), val, fill=(0,0,0,255), font=font)

            for book_col, position in book_positions:
                book_val = str(row.get(book_col, "")).strip()
                if not book_val:
                    continue
                text = book_col.replace("_", "")

                if position.startswith("before_"):
                    target = position.replace("before_", "")
                    x = cell_x_positions_true.get(target, 0) + offset_x - 40
                elif position.startswith("between_"):
                    parts = position.replace("between_", "").split("_")
                    if len(parts) == 2:
                        left, right = parts
                        lx = cell_x_positions_true.get(left, 0)
                        rx = cell_x_positions_true.get(right, 0)
                        x = (lx + rx) / 2 + offset_x - 20
                    else:
                        continue
                else:
                    continue

                draw.text((x, y), text, fill=(0,0,0,255), font=book_font)

        pages.append(img)
    return pages, max_frame


# UI
st.title("ちゃいむしーと Web v1.9.2 + book対応")
selected_preset_name = st.selectbox("会社プリセット", list(presets.keys()))
preset_cfg = presets[selected_preset_name]
uploaded_file = st.file_uploader("CSVアップロード", type=["csv"])

if uploaded_file is not None and st.button("生成"):
    pages, total = generate_timesheet(uploaded_file.read(), preset_cfg)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for i, p in enumerate(pages):
            img_io = io.BytesIO()
            p.save(img_io, format="PNG")
            img_io.seek(0)
            zipf.writestr(f"timesheet_page_{i+1}.png", img_io.read())
            st.image(p, caption=f"Page {i+1}")

    zip_buffer.seek(0)
    st.download_button(
        label="まとめてダウンロード (ZIP)",
        data=zip_buffer,
        file_name="timesheets_all.zip",
        mime="application/zip"
    )
