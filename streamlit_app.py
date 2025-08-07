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

BASE_FRAME_HEIGHT = 49.5
BASE_WIDTH = 3508
BASE_CIRCLE_OFFSET_X = -5
BASE_CIRCLE_OFFSET_Y = -2
BASE_ALPHABET_OFFSET_X = -13
BASE_CROSS_OFFSET_X = -6
BASE_BAR_WIDTH = 1620
BASE_BAR_SHIFT_X = 88

text_offset_y = 4
font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
font_size_true = int(12 / (1086 / 3508))

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

def get_book_positions(df):
    book_positions = {}
    cols = df.columns.tolist()
    for idx, col in enumerate(cols):
        if col.startswith("_book"):
            if idx == 0:
                insert_pos = "before_" + cols[idx + 1]
            elif idx == len(cols) - 1:
                insert_pos = "after_" + cols[idx - 1]
            else:
                insert_pos = f"between_{cols[idx - 1]}_{cols[idx + 1]}"
            book_positions.setdefault(insert_pos, []).append(col)
    return book_positions

def generate_timesheet(file_bytes, preset):
    first_frame_top_y_true = preset["first_frame_top_y_true"]
    frame_height_true = preset["frame_height_true"]
    cell_x_positions_true = preset["cell_x_positions_true"]
    column_offset_x = preset["column_offset_x"]
    true_width = preset["true_width"]
    true_height = preset["true_height"]

    scale_factor_h = frame_height_true / BASE_FRAME_HEIGHT
    scale_factor_w = true_width / BASE_WIDTH

    circle_offset_x_true = BASE_CIRCLE_OFFSET_X * scale_factor_w
    circle_offset_y_true = BASE_CIRCLE_OFFSET_Y * scale_factor_h
    alphabet_offset_x_true = BASE_ALPHABET_OFFSET_X * scale_factor_w
    cross_offset_x_true = BASE_CROSS_OFFSET_X * scale_factor_w

    bar_width = BASE_BAR_WIDTH * scale_factor_w
    bar_shift_x = BASE_BAR_SHIFT_X * scale_factor_w

    font_large_scaled = ImageFont.truetype(font_path, size=int(font_size_true * scale_factor_h))
    font_small_scaled = ImageFont.truetype(font_path, size=int(font_size_true * 0.9 * scale_factor_h))

    df = read_csv_flexibly(file_bytes)
    if df.empty or 'Frame' not in df.columns:
        return [], 0

    df['Frame'] = clean_frame_column(df['Frame'])
    df = df.dropna(subset=['Frame'])
    df['Frame'] = df['Frame'].astype(int)
    df = df[df['Frame'] > 0]

    if df.empty:
        return [], 0

    valid_cells = [c for c in cell_offsets if c in df.columns]
    df = preprocess_cells(df, valid_cells)
    book_positions = get_book_positions(df)

    max_frame_num = df['Frame'].max()
    frames_per_page = 144
    total_pages = math.ceil(max_frame_num / frames_per_page)
    result_images = []

    for page in range(total_pages):
        img = Image.new("RGBA", (true_width, true_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)
        start = page * frames_per_page + 1
        end = (page + 1) * frames_per_page
        df_page = df[(df['Frame'] >= start) & (df['Frame'] <= end)]
        last_frame = df_page['Frame'].max() if not df_page.empty else None

        for col in valid_cells:
            x_base = cell_x_positions_true[col]
            for _, row in df_page.iterrows():
                frame = row['Frame']
                val = str(row[col]) if not pd.isna(row[col]) else ""
                idx_in_col = (frame - 1) % frames_per_page
                col_num = idx_in_col // 72
                row_num = idx_in_col % 72
                y = first_frame_top_y_true + row_num * frame_height_true
                x = x_base if col_num == 0 else x_base + column_offset_x
                y_draw = y + text_offset_y

                if val in ['●', '○']:
                    x += circle_offset_x_true
                    y_draw += circle_offset_y_true
                elif val == '×':
                    x += cross_offset_x_true
                elif re.match(r"^\d+[a-zA-Z]$", val) or re.fullmatch(r"\d{2,}", val):
                    x += alphabet_offset_x_true

                if len(val) >= 3:
                    draw.text((x - 10 * scale_factor_w, y_draw), val, font=font_small_scaled, fill=(0, 0, 0, 255))
                else:
                    draw.text((x, y_draw), val, font=font_large_scaled, fill=(0, 0, 0, 255))

        # book描画
        for _, row in df_page.iterrows():
            frame = row['Frame']
            idx_in_col = (frame - 1) % frames_per_page
            col_num = idx_in_col // 72
            row_num = idx_in_col % 72
            y = first_frame_top_y_true + row_num * frame_height_true
            y_draw = y + text_offset_y
            for pos, books in book_positions.items():
                for book_col in books:
                    if book_col not in row or not str(row[book_col]).strip():
                        continue
                    label = str(row[book_col])
                    if pos.startswith("before_"):
                        cell = pos.replace("before_", "")
                        x_book = cell_x_positions_true.get(cell, 0) - 20 * scale_factor_w
                    elif pos.startswith("between_"):
                        parts = pos.split("_")
                        if len(parts) == 3:
                            _, left, right = parts
                            x_book = (cell_x_positions_true.get(left, 0) + cell_x_positions_true.get(right, 0)) / 2
                        else:
                            continue
                    else:
                        continue
                    for i, ch in enumerate(label):
                        draw.text((x_book, y_draw + i * 12 * scale_factor_h), ch, font=font_large_scaled, fill=(0, 0, 0, 255))

        if last_frame:
            idx_in_col = (last_frame - 1) % frames_per_page
            col_num = idx_in_col // 72
            row_num = idx_in_col % 72
            y = first_frame_top_y_true + (row_num + 1) * frame_height_true
            x = 0 if col_num == 0 else column_offset_x
            draw.rectangle([(x + 5 + bar_shift_x, y), (x + 5 + bar_shift_x + bar_width, y + frame_height_true * 2)], fill=(0, 0, 0, 128))

        result_images.append(img)

    return result_images, max_frame_num

# Streamlit UI
st.title("ちゃいむしーと Web版 v1.9.2 - book縦書き & 解像度対応")
selected_preset_name = st.selectbox("会社プリセットを選択してください", list(presets.keys()))
preset_cfg = presets[selected_preset_name]

uploaded_file = st.file_uploader("CSVファイルをアップロードしてください", type=["csv"])
if uploaded_file is not None and st.button("タイムシート生成！"):
    pages, total_frames = generate_timesheet(uploaded_file.read(), preset_cfg)
    if not pages:
        st.warning("有効なFrameデータが見つかりませんでした。")
    else:
        seconds = total_frames // 24
        remainder = total_frames % 24
        time_str = f"{seconds} + {remainder}"
        st.text_input("TIME", value=time_str)

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, img in enumerate(pages):
                st.image(img, caption=f"Page {idx + 1}")
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='PNG')
                img_bytes.seek(0)
                zip_file.writestr(f"timesheet_page_{idx + 1}.png", img_bytes.read())
                st.download_button(f"⬇️ ダウンロード Page {idx + 1}", img_bytes.getvalue(), file_name=f"timesheet_page_{idx + 1}.png", mime="image/png")

        zip_buffer.seek(0)
        st.download_button("📦 すべてまとめてダウンロード（ZIP）", data=zip_buffer, file_name="timesheets_all.zip", mime="application/zip")
