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

# スケール基準値
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
base_font_size = int(12 / (1086 / 3508))  # 既存と同じ基準

# =============== ユーティリティ ===============
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
    """_book列の“列順”から、挿入位置（before_/between_/after_）を決める。
    隣接の非_book列（A〜H）を左右にサーチして決定するので、端に来ても安全。
    返り値: {book_col: "before_A" / "between_A_B" / "after_H" など}
    """
    cols = list(df.columns)
    book_cols = [c for c in cols if re.match(r"_book\d+", c)]
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
            # 周囲にA〜Hが見つからないならスキップ
            continue
        if left_cell is None and right_cell is not None:
            positions[b] = f"before_{right_cell}"
        elif left_cell is not None and right_cell is None:
            positions[b] = f"after_{left_cell}"
        else:
            positions[b] = f"between_{left_cell}_{right_cell}"
    return positions

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

    # フォント
    font_large = ImageFont.truetype(font_path, size=int(base_font_size * scale_h))
    font_small = ImageFont.truetype(font_path, size=int(base_font_size * 0.9 * scale_h))
    label_font  = ImageFont.truetype(font_path, size=int(base_font_size * 0.9 * scale_h))  # bookラベル用

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

        # ---- bookマーカー描画（縦線＋番号ラベル／複数は「book2-book3」結合） ----
        for _, row in df_page.iterrows():
            frame = int(row['Frame'])
            idx = (frame - 1) % frames_per_page
            col_block = idx // 72
            row_pos = idx % 72
        
            # 行の基準位置
            y_base = first_frame_top_y_true + row_pos * frame_height_true
            x_col  = column_offset_x if col_block == 1 else 0
        
            # ❶ この行でbook値が入っているものだけ抽出して位置ごとにグループ化
            present = {}  # ← これが無いと NameError
            for book_col, pos in book_positions.items():
                if book_col in row and str(row[book_col]).strip() != "":
                   present.setdefault(pos, []).append(book_col)
        
            # ❷ 位置ごとに描画
            for pos, books_here in present.items():
                # 基準x座標算出
                x_insert = None
                if pos.startswith("before_"):
                    target = pos.replace("before_", "")
                    if target in cell_x_positions_true:
                        x_insert = cell_x_positions_true[target] - 10 * scale_w
                elif pos.startswith("between_"):
                    parts = pos.split("_")
                    if len(parts) == 3:
                        _, left, right = parts
                        if left in cell_x_positions_true and right in cell_x_positions_true:
                            x_insert = (cell_x_positions_true[left] + cell_x_positions_true[right]) / 2
                elif pos.startswith("after_"):
                    target = pos.replace("after_", "")
                    if target in cell_x_positions_true:
                        x_insert = cell_x_positions_true[target] + 10 * scale_w
                if x_insert is None:
                    continue
                                    # 位置→x座標決定
                x_insert = None
                if pos.startswith("before_"):
                    target = pos.replace("before_", "")
                    if target in cell_x_positions_true:
                        x_insert = cell_x_positions_true[target] - 10 * scale_w
                elif pos.startswith("between_"):
                    parts = pos.split("_")
                    if len(parts) == 3:
                        _, left, right = parts
                        if left in cell_x_positions_true and right in cell_x_positions_true:
                            x_insert = (cell_x_positions_true[left] + cell_x_positions_true[right]) / 2
                elif pos.startswith("after_"):
                    target = pos.replace("after_", "")
                    if target in cell_x_positions_true:
                        x_insert = cell_x_positions_true[target] + 10 * scale_w

                if x_insert is None:
                    continue

                # ← 左へ5px
                x_insert = x_insert + x_col - 5

                # ↑ 上へ3コマ（frame_height_true * 3）
                y_ref = y_base - (frame_height_true * 3)

                # 縦線の長さ：元より +1コマ
                line_top = y_ref - 4 * scale_h
                line_bottom = y_ref + (frame_height_true * 2) + 2 * scale_h  # 1コマ分長く

                line_w = max(1, int(2 * scale_w))
                draw.line([(x_insert, line_top), (x_insert, line_bottom)], fill=(0, 0, 0, 255), width=line_w)

                # 縦線は常に1本（+1コマ長く）
                line_top = y_ref - 4 * scale_h
                line_bottom = y_ref + (frame_height_true * 2) + 2 * scale_h
                line_w = max(1, int(2 * scale_w))
                draw.line([(x_insert, line_top), (x_insert, line_bottom)], fill=(0, 0, 0, 255), width=line_w)

                # ラベル：単独 or 複数は「book2-book3」形式
                if len(books_here) == 1:
                    label = books_here[0].replace("_", "")         # "_book2" → "book2"
                else:
                    nums = []
                    for b in books_here:
                        s = b.replace("_", "")                     # "book2"
                        m = re.search(r'(\d+)$', s)
                        n = int(m.group(1)) if m else 0
                        nums.append((n, s))
                    nums.sort(key=lambda t: t[0])                  # 昇順。降順なら reverse=True
                    label = "-".join(s for _, s in nums)

                # ラベルを縦線の上に中央配置
                bbox = draw.textbbox((0, 0), label, font=label_font)
                label_w = bbox[2] - bbox[0]
                label_h = bbox[3] - bbox[1]
                label_x = x_insert - (label_w / 2)
                label_y = line_top - label_h - 2 * scale_h
                draw.text((label_x, label_y), label, fill=(0, 0, 0, 255), font=label_font)

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
st.title("ちゃいむしーと Web版 v1.9.4｜bookマーカー（縦線＋水平ラベル）対応")
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
