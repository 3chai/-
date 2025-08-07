import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile

# セル定義
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

# その他の定数
text_offset_y = 4
circle_offset_x_true = -5
circle_offset_y_true = -2
alphabet_offset_x_true = -13
cross_offset_x_true = -5

font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")

# 縦書き変換
def to_vertical_text(text):
    return "\n".join(text)

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

def generate_timesheet(file_bytes, preset_cfg):
    df_raw = read_csv_flexibly(file_bytes)
    if df_raw.empty or 'Frame' not in df_raw.columns:
        return [], 0

    all_columns = ['Frame', 'A', 'B', '_book', 'C', 'D', 'E', 'H']
    for col in all_columns:
        if col not in df_raw.columns:
            df_raw[col] = ""

    df_raw['Frame'] = clean_frame_column(df_raw['Frame'])
    df_raw = df_raw.dropna(subset=['Frame'])
    df_raw['Frame'] = df_raw['Frame'].astype(int)
    df_raw = df_raw[df_raw['Frame'] > 0]

    if df_raw.empty:
        return [], 0

    valid_cells = [cell for cell in cell_offsets.keys() if cell in df_raw.columns]

    # フォント設定
    font_size_true = int(12 / (1086 / preset_cfg['true_height']))
    font_large = ImageFont.truetype(font_path, size=font_size_true)

    max_frame_num = df_raw['Frame'].max()
    frames_per_page = 144
    total_pages = math.ceil(max_frame_num / frames_per_page)
    result_images = []

    for page in range(total_pages):
        img = Image.new("RGBA", (preset_cfg['true_width'], preset_cfg['true_height']), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        start_frame = page * frames_per_page + 1
        end_frame = (page + 1) * frames_per_page
        df_page = df_raw[(df_raw['Frame'] >= start_frame) & (df_raw['Frame'] <= end_frame)]

        for cell in valid_cells:
            x_base_true = preset_cfg['cell_x_positions_true'][cell]
            for _, row in df_page.iterrows():
                frame_num = int(row['Frame'])
                timing = str(row[cell]) if not pd.isna(row[cell]) else ""
                frame_in_column_total = (frame_num - 1) % frames_per_page
                column = frame_in_column_total // 72
                frame_in_column = frame_in_column_total % 72
                y_true = preset_cfg['first_frame_top_y_true'] + frame_in_column * preset_cfg['frame_height_true']
                x_true = x_base_true + (preset_cfg['column_offset_x'] if column == 1 else 0)
                y_draw_true = y_true + text_offset_y

                # 位置調整
                if timing == '●' or timing == '○':
                    x_true += circle_offset_x_true
                    y_draw_true += circle_offset_y_true
                elif timing == '×':
                    x_true += cross_offset_x_true
                elif re.match(r"^\d+[a-zA-Z]$", timing) or re.fullmatch(r"\d{2,}", timing):
                    x_true += alphabet_offset_x_true

                draw.text((x_true, y_draw_true), timing, fill=(0, 0, 0, 255), font=font_large)

        # book列の挿入処理
        book_count = 1
        for _, row in df_page.iterrows():
            frame_num = int(row['Frame'])
            book_val = str(row['_book']).strip()
            if book_val:
                m = re.match(r"([A-H])\s*[-~]\s*([A-H])", book_val)
                if not m:
                    continue
                cell1, cell2 = m.group(1), m.group(2)
                offset1 = cell_offsets.get(cell1)
                offset2 = cell_offsets.get(cell2)
                if offset1 is None or offset2 is None:
                    continue
                offset_mid = (offset1 + offset2) / 2
                x_true = 110 + 55 * offset_mid
                frame_in_column_total = (frame_num - 1) % frames_per_page
                column = frame_in_column_total // 72
                frame_in_column = frame_in_column_total % 72
                y_true = preset_cfg['first_frame_top_y_true'] + frame_in_column * preset_cfg['frame_height_true']
                x_true += (preset_cfg['column_offset_x'] if column == 1 else 0)
                y_draw_true = y_true + text_offset_y
                vertical = to_vertical_text(f"book{book_count}")
                draw.text((x_true, y_draw_true), vertical, fill=(0, 0, 0, 255), font=font_large, anchor="mm")
                book_count += 1

        result_images.append(img)

    return result_images, max_frame_num
