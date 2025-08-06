import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile

# 定数
true_width, true_height = 3508, 4961
frames_per_page = 144
frame_height_true = 49.5
first_frame_top_y_true = 1278.67
cell_offsets = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7}
cell_x_positions_true = {cell: 110 + 55 * offset for cell, offset in cell_offsets.items()}
column_offset_x = 1800 - 110
text_offset_y = 4
circle_offset_x_true = -5
circle_offset_y_true = -2
alphabet_offset_x_true = -13

# フォント
font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
font_size_true = int(12 / (1086 / 3508))
font_large = ImageFont.truetype(font_path, size=font_size_true)

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
    """冒頭×（1コマのみ）、5コマ以上空白で縦書き〜 or ーを入れる"""
    for cell in valid_cells:
        seen_content = False
        empty_count = 0
        last_type = None

        for idx, row in df_raw.iterrows():
            val = str(row[cell]).strip()

            if val == "" or pd.isna(row[cell]):
                if not seen_content:
                    # 冒頭は最初の1コマだけ×
                    if empty_count == 0:
                        df_raw.at[idx, cell] = "×"
                        last_type = "cross"
                    empty_count += 1
                else:
                    empty_count += 1
                    if empty_count == 5:
                        if last_type == "cross":
                            df_raw.at[idx, cell] = "\uFF5E"  # 全角チルダ 〜
                        elif last_type == "number":
                            df_raw.at[idx, cell] = "\u30FC"  # 全角長音符 ー
            else:
                seen_content = True
                empty_count = 0
                if val == "×":
                    last_type = "cross"
                elif val.isdigit():
                    last_type = "number"
                else:
                    last_type = "other"
    return df_raw

def generate_timesheet(file_bytes):
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

    valid_cells = [cell for cell in ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'] if cell in df_raw.columns]

    # 冒頭× & 空白5コマ縦記号処理
    df_raw = preprocess_cells(df_raw, valid_cells)

    max_frame_num = df_raw['Frame'].max()
    total_pages = math.ceil(max_frame_num / frames_per_page)
    result_images = []

    for page in range(total_pages):
        img = Image.new("RGBA", (true_width, true_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        start_frame = page * frames_per_page + 1
        end_frame = (page + 1) * frames_per_page
        df_page = df_raw[(df_raw['Frame'] >= start_frame) & (df_raw['Frame'] <= end_frame)]

        if not df_page.empty:
            last_frame_in_page = df_page['Frame'].max()
        else:
            last_frame_in_page = None

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

                # 位置調整
                if timing == '●' or timing == '○':
                    x_true += circle_offset_x_true
                    y_draw_true += circle_offset_y_true
                elif re.match(r"^\d+[a-zA-Z]$", timing) or re.fullmatch(r"\d{2,}", timing):
                    x_true += alphabet_offset_x_true

                # 縦書き描画
                if timing in ["\uFF5E", "\u30FC"]:
                    draw.text((x_true, y_draw_true), "\n".join(list(timing)), fill=(0, 0, 0, 255), font=font_large)
                else:
                    draw.text((x_true, y_draw_true), timing, fill=(0, 0, 0, 255), font=font_large)

        # 黒バー（太さ倍・右に2マス・半透明）
        if last_frame_in_page:
            frame_in_column_total = (last_frame_in_page - 1) % frames_per_page
            column = frame_in_column_total // 72
            frame_in_column = frame_in_column_total % 72
            bar_y = first_frame_top_y_true + (frame_in_column + 1) * frame_height_true
            bar_x = 0 if column == 0 else column_offset_x
            bar_width = 1700 - 5
            bar_height = frame_height_true * 2
            bar_shift_x = 110
            draw.rectangle(
                [(bar_x + 5 + bar_shift_x, bar_y),
                 (bar_x + 5 + bar_shift_x + bar_width, bar_y + bar_height)],
                fill=(0, 0, 0, 128)  # 半透明
            )

        result_images.append(img)

    return result_images, max_frame_num

# Streamlit UI
st.title("ちゃいむしーと Web版 v1.4 ⭕️〜ー対応")
uploaded_file = st.file_uploader("CSVファイルをアップロードしてください", type=["csv"])

if uploaded_file is not None:
    if st.button("タイムシート生成！"):
        pages, total_frames = generate_timesheet(uploaded_file.read())

        if not pages:
            st.warning("有効なFrameデータが見つかりませんでした。")
        else:
            seconds = total_frames // 24
            remainder = total_frames % 24
            time_str = f"{seconds} + {remainder}"
            st.text_input("TIME", value=time_str)

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for idx, page_img in enumerate(pages):
                    st.write(f"ページ {idx+1}")
                    st.image(page_img, caption=f"Page {idx+1}", use_container_width=True)

                    img_bytes = io.BytesIO()
                    page_img.save(img_bytes, format='PNG')
                    img_bytes.seek(0)

                    filename = f"timesheet_page_{idx+1}.png"
                    zip_file.writestr(filename, img_bytes.getvalue())

                    st.download_button(
                        label=f"⬇️ ダウンロード Page {idx+1}",
                        data=img_bytes,
                        file_name=filename,
                        mime="image/png"
                    )

            zip_buffer.seek(0)
            st.download_button(
                label="📦 すべてまとめてダウンロード（ZIP）",
                data=zip_buffer,
                file_name="timesheets_all.zip",
                mime="application/zip"
            )
