import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile

# プリセット辞書（true_heightも追加）
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

# === ユーティリティ ===
def clean_frame_column(series):
    series = series.astype(str).str.strip().map(lambda x: unicodedata.normalize("NFKC", x))
    return pd.to_numeric(series, errors='coerce')

def read_csv_flexibly(file_bytes):
    df = pd.read_csv(io.BytesIO(file_bytes), encoding="shift_jis", header=[0, 1], keep_default_na=False)
    df.columns = [col[1] if col[1] != '' else col[0] for col in df.columns]
    if 'Unnamed: 0_level_1' in df.columns:
        df = df.rename(columns={'Unnamed: 0_level_1': 'Frame'})
    return df

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

# BOOK縦書き描画
def draw_vertical_text(draw, x, y, text, font, fill=(0, 0, 0, 255)):
    for i, char in enumerate(text):
        draw.text((x, y + i * font.size), char, font=font, fill=fill)

# === タイムシート画像生成 ===
def generate_timesheet(file_bytes, preset_cfg):
    true_width = preset_cfg["width"]
    true_height = preset_cfg["height"]
    frames_per_page = 144
    frame_height_true = preset_cfg["frame_height"]
    first_frame_top_y_true = preset_cfg["first_frame_top_y"]
    column_offset_x = preset_cfg["column_offset_x"]
    cell_x_positions_true = {cell: preset_cfg["cell_base_x"] + i * preset_cfg["cell_spacing"] for i, cell in enumerate("ABCDEFGH")}
    text_offset_y = 4

    font_size = int(12 * (true_width / 3508))
    font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
    font = ImageFont.truetype(font_path, font_size)

    df_raw = read_csv_flexibly(file_bytes)
    df_raw['Frame'] = clean_frame_column(df_raw['Frame'])
    df_raw = df_raw.dropna(subset=['Frame'])
    df_raw['Frame'] = df_raw['Frame'].astype(int)
    df_raw = df_raw[df_raw['Frame'] > 0]

    valid_cells = [c for c in 'ABCDEFGH' if c in df_raw.columns]
    df_raw = preprocess_cells(df_raw, valid_cells)

    result_images = []
    max_frame_num = df_raw['Frame'].max()
    total_pages = math.ceil(max_frame_num / frames_per_page)

    for page in range(total_pages):
        img = Image.new("RGBA", (true_width, true_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        start = page * frames_per_page + 1
        end = (page + 1) * frames_per_page
        df_page = df_raw[(df_raw['Frame'] >= start) & (df_raw['Frame'] <= end)]

        for cell in valid_cells:
            x_base = cell_x_positions_true[cell]
            for _, row in df_page.iterrows():
                frame = row['Frame']
                timing = str(row[cell]).strip()
                col = ((frame - 1) % frames_per_page) // 72
                line = (frame - 1) % 72
                x = x_base + (column_offset_x if col else 0)
                y = first_frame_top_y_true + line * frame_height_true + text_offset_y

                if re.fullmatch(r"\d{3,}", timing):
                    draw.text((x - 10, y), timing, fill=(0, 0, 0, 255), font=ImageFont.truetype(font_path, int(font_size * 0.85)))
                elif timing == "×":
                    draw.text((x - 5, y), timing, fill=(0, 0, 0, 255), font=font)
                else:
                    draw.text((x, y), timing, fill=(0, 0, 0, 255), font=font)

        # BOOK挿入処理
        if "_book" in df_raw.columns:
            books_this_page = df_page[['_book', 'Frame']].dropna()
            book_num = 1
            for _, row in books_this_page.iterrows():
                label = f"book{book_num}"
                frame = row['Frame']
                line = (frame - 1) % 72
                col = ((frame - 1) % frames_per_page) // 72
                x = cell_x_positions_true['A'] + 25 + (column_offset_x if col else 0)
                y = first_frame_top_y_true + line * frame_height_true
                draw_vertical_text(draw, x, y, label, font)
                book_num += 1

        # 黒バー
        if not df_page.empty:
            last_frame = df_page['Frame'].max()
            col = ((last_frame - 1) % frames_per_page) // 72
            line = (last_frame - 1) % 72 + 1
            bar_x = column_offset_x if col else 0
            bar_y = first_frame_top_y_true + line * frame_height_true
            draw.rectangle(
                [(bar_x + 93, bar_y), (bar_x + 93 + 1620, bar_y + frame_height_true * 2)],
                fill=(0, 0, 0, preset_cfg["black_bar_alpha"])
            )

        result_images.append(img)

    return result_images, max_frame_num

# === Streamlit UI ===
st.title("ちゃいむしーと Web版 v1.7")
uploaded_file = st.file_uploader("CSVファイルをアップロードしてください", type=["csv"])
preset_name = st.selectbox("用紙プリセットを選択", list(PRESETS.keys()))
preset_cfg = PRESETS[preset_name]

if uploaded_file and st.button("タイムシート生成！"):
    pages, total_frames = generate_timesheet(uploaded_file.read(), preset_cfg)

    if not pages:
        st.warning("データがありません")
    else:
        seconds, remain = divmod(total_frames, 24)
        st.text_input("TIME", f"{seconds} + {remain}")

        zip_io = io.BytesIO()
        with zipfile.ZipFile(zip_io, "w", zipfile.ZIP_DEFLATED) as zipf:
            for i, page in enumerate(pages):
                st.image(page, caption=f"Page {i+1}")
                img_io = io.BytesIO()
                page.save(img_io, format='PNG')
                img_io.seek(0)
                zipf.writestr(f"timesheet_page_{i+1}.png", img_io.read())

        zip_io.seek(0)
        st.download_button("📦 ZIPでまとめてDL", zip_io, file_name="timesheets_all.zip", mime="application/zip")
