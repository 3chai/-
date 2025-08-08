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

# 基準値
BASE_FRAME_HEIGHT = 49.5
BASE_WIDTH = 3508
BASE_CIRCLE_OFFSET_X = -5
BASE_CIRCLE_OFFSET_Y = -2
BASE_ALPHABET_OFFSET_X = -13
BASE_CROSS_OFFSET_X = -6
BASE_BAR_WIDTH = 1620
BASE_BAR_SHIFT_X = 88
font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
font_size_true = int(12 / (1086 / 3508))
text_offset_y = 4

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
    book_cols = [col for col in df.columns if re.match(r"_book\\d+", col)]
    positions = {}
    for book_col in book_cols:
        idx = df.columns.get_loc(book_col)
        if idx == 0:
            insert_pos = "before_A"
        elif idx + 1 < len(df.columns):
            insert_pos = f"between_{df.columns[idx-1]}_{df.columns[idx+1]}"
        else:
            insert_pos = f"after_{df.columns[idx-1]}"
        positions[book_col] = insert_pos
    return positions

def draw_vertical_text(draw, text, x, y, font):
    for i, char in enumerate(text):
        draw.text((x, y + i * font.size), char, fill=(0, 0, 0, 255), font=font)

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

    df_raw = read_csv_flexibly(file_bytes)
    if df_raw.empty or 'Frame' not in df_raw.columns:
        return [], 0

    df_raw['Frame'] = clean_frame_column(df_raw['Frame'])
    df_raw = df_raw.dropna(subset=['Frame'])
    df_raw['Frame'] = df_raw['Frame'].astype(int)
    df_raw = df_raw[df_raw['Frame'] > 0]

    valid_cells = [cell for cell in cell_offsets if cell in df_raw.columns]
    df_raw = preprocess_cells(df_raw, valid_cells)

    book_positions = get_book_positions(df_raw)
    max_frame_num = df_raw['Frame'].max()
    frames_per_page = 144
    total_pages = math.ceil(max_frame_num / frames_per_page)
    result_images = []

    for page in range(total_pages):
        img = Image.new("RGBA", (true_width, true_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        start_frame = page * frames_per_page + 1
        end_frame = (page + 1) * frames_per_page
        df_page = df_raw[(df_raw['Frame'] >= start_frame) & (df_raw['Frame'] <= end_frame)]
        last_frame_in_page = df_page['Frame'].max() if not df_page.empty else None

        for cell in valid_cells:
            x_base_true = cell_x_positions_true[cell]
            for _, row in df_page.iterrows():
                frame_num = int(row['Frame'])
                timing = str(row[cell]) if not pd.isna(row[cell]) else ""
                frame_in_column_total = (frame_num - 1) % frames_per_page
                column = frame_in_column_total // 72
                frame_in_column = frame_in_column_total % 72
                y_true = first_frame_top_y_true + frame_in_column * frame_height_true
                x_true = x_base_true if column == 0 else x_base_true + column_offset_x
                y_draw_true = y_true + text_offset_y

                if timing == '●' or timing == '○':
                    x_true += circle_offset_x_true
                    y_draw_true += circle_offset_y_true
                elif timing == '×':
                    x_true += cross_offset_x_true
                elif re.match(r"^\\d+[a-zA-Z]$", timing) or re.fullmatch(r"\\d{2,}", timing):
                    x_true += alphabet_offset_x_true

                font = font_small_scaled if len(timing) >= 3 else font_large_scaled
                draw.text((x_true, y_draw_true), timing, fill=(0, 0, 0, 255), font=font)

# 先頭あたりのフォント用意の近くで追加（小さめのラベル用）
label_font = ImageFont.truetype(font_path, size=int(font_size_true * 0.9 * scale_factor_h))

# …中略…

        # ===== book描画（縦線＋水平ラベル） =====
        for _, row in df_page.iterrows():
            frame_num = int(row['Frame'])
            frame_in_column_total = (frame_num - 1) % frames_per_page
            column = frame_in_column_total // 72       # 左=0 / 右=1
            frame_in_column = frame_in_column_total % 72
            y_true = first_frame_top_y_true + frame_in_column * frame_height_true
            x_col_offset = column_offset_x if column == 1 else 0

            for book_col, position in book_positions.items():
                # この行にその book が存在するか（空ならスキップ）
                if book_col not in row or str(row[book_col]).strip() == "":
                    continue

                # ラベルは列名から（_book1 → book1）
                label = book_col.replace("_", "")

                # 位置→x座標の決定
                x_insert = None
                if position.startswith("before_"):
                    target = position.replace("before_", "")
                    if target in cell_x_positions_true:
                        x_insert = cell_x_positions_true[target] - 10 * scale_factor_w
                elif position.startswith("between_"):
                    parts = position.split("_")
                    if len(parts) == 3:
                        _, left, right = parts
                        if left in cell_x_positions_true and right in cell_x_positions_true:
                            x_insert = (cell_x_positions_true[left] + cell_x_positions_true[right]) / 2
                elif position.startswith("after_"):
                    target = position.replace("after_", "")
                    if target in cell_x_positions_true:
                        x_insert = cell_x_positions_true[target] + 10 * scale_factor_w

                if x_insert is None:
                    continue

                x_insert += x_col_offset

                # 縦線の描画（1コマ分ちょい長め）
                line_top = y_true - 4 * scale_factor_h
                line_bottom = y_true + frame_height_true + 2 * scale_factor_h
                line_w = max(1, int(2 * scale_factor_w))
                draw.line([(x_insert, line_top), (x_insert, line_bottom)], fill=(0, 0, 0, 255), width=line_w)

                # ラベルを縦線の上に水平配置（中央寄せ）
                # textbboxで横幅を測って中央合わせ
                bbox = draw.textbbox((0, 0), label, font=label_font)
                label_w = bbox[2] - bbox[0]
                label_h = bbox[3] - bbox[1]
                label_x = x_insert - label_w / 2
                label_y = line_top - label_h - 2 * scale_factor_h  # 線の上に少し余白
                draw.text((label_x, label_y), label, fill=(0, 0, 0, 255), font=label_font)
# UI
st.title("ちゃいむしーと Web版 v1.9.3：book縦書き対応")
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
        st.text_input("TIME", value=f"{seconds} + {remainder}")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for idx, page_img in enumerate(pages):
                st.write(f"ページ {idx+1}")
                st.image(page_img, caption=f"Page {idx+1}", use_container_width=True)
                img_bytes = io.BytesIO()
                page_img.save(img_bytes, format='PNG')
                zip_file.writestr(f"timesheet_page_{idx+1}.png", img_bytes.getvalue())
                st.download_button(
                    label=f"⬇️ ダウンロード Page {idx+1}",
                    data=img_bytes,
                    file_name=f"timesheet_page_{idx+1}.png",
                    mime="image/png"
                )
        zip_buffer.seek(0)
        st.download_button(
            label="📦 すべてまとめてダウンロード（ZIP）",
            data=zip_buffer,
            file_name="timesheets_all.zip",
            mime="application/zip"
        )
