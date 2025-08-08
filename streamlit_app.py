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
base_font_size = int(12 / (1086 / 3508))  # 既存基準

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
        # 列名を正規化（全角・余分スペース除去）
        df.columns = [unicodedata.normalize("NFKC", str(c)).strip() for c in df.columns]
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
    """_book列の列順から、挿入位置（before_/between_/after_）を決める。"""
    cols = list(df.columns)
    # _book1 / book1 の両方を許容
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

def norm_str(s: object) -> str:
    # 全角→半角、全角スペース→半角、前後スペース除去
    return unicodedata.normalize("NFKC", str(s)).replace("\u3000", " ").strip()

def is_filled(v: object) -> bool:
    s = norm_str(v)
    return s not in ("", "nan", "None")

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
    label_font  = ImageFont.truetype(font_path, size=int(base_font_size * 0.5 * scale_h))

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

        # ---- bookマーカー描画（縦線＋水平ラベル）[3コマ上げ・番号若い順に上へ縦並び・重なり回避] ----
        for _, row in df_page.iterrows():
            frame = int(row['Frame'])
            idx = (frame - 1) % frames_per_page
            col_block = idx // 72                 # 0=左, 1=右
            row_pos = idx % 72

            # 行の基準位置
            y_base = first_frame_top_y_true + row_pos * frame_height_true
            x_col  = column_offset_x if col_block == 1 else 0

            # この行でbook値が入っているものだけ抽出（位置ごとにグループ化）
            present = {}
            for book_col, pos in book_positions.items():
                colname = norm_str(book_col)  # "_book2" でも "book2" でもOK
                if (colname in row.index) and is_filled(row[colname]):
                    present.setdefault(pos, []).append(colname)

            # 同一フレーム行内のラベル当たり判定箱
            placed_boxes = []  # [(x1,y1,x2,y2), ...]

            # 位置ごとに描画
            for pos, books_here in present.items():
                # 基準xの計算（before_/between_/after_）
                x_insert = None
                if pos.startswith("before_"):
                    tgt = pos.replace("before_", "")
                    if tgt in cell_x_positions_true:
                        x_insert = cell_x_positions_true[tgt] - 10 * scale_w
                elif pos.startswith("between_"):
                    parts = pos.split("_")
                    if len(parts) == 3:
                        _, left, right = parts
                        if left in cell_x_positions_true and right in cell_x_positions_true:
                            x_insert = (cell_x_positions_true[left] + cell_x_positions_true[right]) / 2
                elif pos.startswith("after_"):
                    tgt = pos.replace("after_", "")
                    if tgt in cell_x_positions_true:
                        x_insert = cell_x_positions_true[tgt] + 10 * scale_w
                if x_insert is None:
                    continue

                # 左に5px、上に3コマ分（縦線も同様）
                x_insert = x_insert + x_col - 5
                y_ref = y_base - (frame_height_true * 3)

                # 縦線（+1コマ長く）※縦線は動かさない
                line_top = y_ref - 4 * scale_h
                line_bottom = y_ref + (frame_height_true * 2) + 2 * scale_h
                line_w = max(1, int(2 * scale_w))
                draw.line([(x_insert, line_top), (x_insert, line_bottom)], fill=(0, 0, 0, 255), width=line_w)

                # --- ここから「番号若い順に上へ」縦並び ---
                # books_here を番号昇順に整列（book1, book2, ...）
                items = []
                for b in books_here:
                    s = norm_str(b).replace("_", "")  # "book2"
                    m = re.search(r"(\d+)$", s)
                    n = int(m.group(1)) if m else 0
                    items.append((n, s))
                items.sort(key=lambda t: t[0])  # 若い順（1が一番上）

                # ラベル間の縦間隔
                line_gap = 2 * scale_h

                # 端で切れないように使う余白
                margin = 12 * scale_w

                # 重なり判定
                def overlap(a, b):
                    ax1, ay1, ax2, ay2 = a
                    bx1, by1, bx2, by2 = b
                    return not (ax2 <= bx1 or bx2 <= ax1 or ay2 <= by1 or by2 <= ay1)

                # 上から（番号若い順）に一個ずつ配置
                for idx_item, (_, label) in enumerate(items):
                    # ラベルサイズ
                    bbox = draw.textbbox((0, 0), label, font=label_font)
                    label_w = bbox[2] - bbox[0]
                    label_h = bbox[3] - bbox[1]

                    # book1 を最上段、その下に book2… の基準y
                    base_y = (line_top - label_h - 2 * scale_h) - idx_item * (label_h + line_gap)

                    # 中央基準（縦線中心に置く予定の位置）
                    label_x_center = x_insert - (label_w / 2)
                    label_y = base_y

                    # 左右端で切れないように「ラベルだけ」クランプ（縦線はそのまま）
                    min_x = margin
                    max_x = true_width - margin - label_w
                    label_x = max(min_x, min(max_x, label_x_center))

                    # すでに置いた別位置のラベルと重なる場合は、さらに上へ逃がす
                    cur = (label_x, label_y, label_x + label_w, label_y + label_h)
                    while any(overlap(cur, box) for box in placed_boxes):
                        label_y -= (label_h + line_gap)
                        cur = (label_x, label_y, label_x + label_w, label_y + label_h)

                    # 描画＆登録
                    draw.text((label_x, label_y), label, fill=(0, 0, 0, 255), font=label_font)
                    placed_boxes.append(cur)
                    
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
st.title("ちゃいむしーと Web版 v1.9.6｜bookマーカー（縦線＋水平ラベル）× 3コマ上・重なり回避")
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
