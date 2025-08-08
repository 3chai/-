import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile

# =============== 基本定義 ===============
cell_offsets = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7}
CELLS_ALL = list(cell_offsets.keys())

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

# 位置調整の基準（Andraft基準）
BASE_FRAME_HEIGHT = 49.5
BASE_WIDTH = 3508
BASE_CIRCLE_OFFSET_X = -5
BASE_CIRCLE_OFFSET_Y = -2
BASE_ALPHABET_OFFSET_X = -13
BASE_CROSS_OFFSET_X = -6
BASE_BAR_WIDTH = 1620
BASE_BAR_SHIFT_X = 88
text_offset_y = 4

# bookラインの旧デフォ（線の下端算出に使用）
BASE_BOOK_OFFSET_KOMA = 3

# セル名のオフセット（px基準）
HEADER_X_NUDGE_PX      = 10    # 右+ / 左-
HEADER_BOTTOM_NUDGE_PX = -80   # 下端からのオフセット（上- / 下+）

# フォント
font_path   = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
jp_font_path = os.path.join(os.path.dirname(__file__), "NotoSansJP-Regular.otf")
base_font_size = int(12 / (1086 / 3508))

# =============== ユーティリティ ===============
def clean_frame_column(series):
    series = series.astype(str).str.strip().map(lambda x: unicodedata.normalize("NFKC", x))
    series = pd.to_numeric(series, errors='coerce')
    return series

def normalize_for_vertical(text: str) -> str:
    return (text.replace("ー","｜").replace("ｰ","｜")
                .replace("－","｜").replace("―","｜")
                .replace("—","｜").replace("–","｜"))

def read_csv_flexibly(file_bytes):
    try:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding="shift_jis", header=[0, 1], keep_default_na=False)
        df.columns = [col[1] if col[1] != '' else col[0] for col in df.columns]
        if 'Unnamed: 0_level_1' in df.columns:
            df = df.rename(columns={'Unnamed: 0_level_1': 'Frame'})
        df.columns = [unicodedata.normalize("NFKC", str(c)).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"CSVの読み込みに失敗しました: {e}")
        return pd.DataFrame()

def preprocess_cells(df_raw, valid_cells):
    for cell in valid_cells:
        if df_raw[cell].astype(str).str.strip().replace("nan","").eq("").all():
            continue
        seen = False
        for idx, row in df_raw.iterrows():
            val = str(row[cell]).strip()
            if val == "" or pd.isna(row[cell]):
                if not seen:
                    df_raw.at[idx, cell] = "×"; seen = True
            else:
                seen = True
    return df_raw

def get_book_positions(df, valid_cells):
    cols = list(df.columns)
    book_cols = [c for c in cols if re.match(r"^_?book\d+$", str(c), re.IGNORECASE)]
    positions = {}
    for b in book_cols:
        i = cols.index(b)
        L = R = None
        for j in range(i-1, -1, -1):
            if cols[j] in valid_cells: L = cols[j]; break
        for j in range(i+1, len(cols)):
            if cols[j] in valid_cells: R = cols[j]; break
        if L is None and R is None: continue
        if L is None: positions[b] = f"before_{R}"
        elif R is None: positions[b] = f"after_{L}"
        else: positions[b] = f"between_{L}_{R}"
    return positions

def norm_str(s): return unicodedata.normalize("NFKC", str(s)).replace("\u3000"," ").strip()
def is_filled(v): s = norm_str(v); return s not in ("", "nan", "None")

def draw_vertical_bottom(draw, text, bottom_x, bottom_y, font, spacing=0):
    if not text: return
    text = normalize_for_vertical(text)
    boxes, total_h = [], 0
    for ch in text:
        bbox = draw.textbbox((0,0), ch, font=font)
        w = bbox[2]-bbox[0]; h = bbox[3]-bbox[1]
        boxes.append((ch,w,h)); total_h += h
    total_h += spacing * (len(boxes)-1 if boxes else 0)
    y = bottom_y - total_h
    for ch,w,h in boxes:
        draw.text((bottom_x - w/2.0, y), ch, fill=(0,0,0,255), font=font)
        y += h + spacing

# =============== 本体 ===============
def generate_timesheet(file_bytes, preset, show_books=True, book_offset_koma=6, cell_labels=None):
    true_width  = preset["true_width"]
    true_height = preset["true_height"]
    frame_h     = preset["frame_height_true"]
    first_y     = preset["first_frame_top_y_true"]
    col_off_x   = preset["column_offset_x"]
    cell_x      = preset["cell_x_positions_true"]

    # スケール
    scale_h = frame_h / BASE_FRAME_HEIGHT
    scale_w = true_width / BASE_WIDTH

    circle_dx = BASE_CIRCLE_OFFSET_X * scale_w
    circle_dy = BASE_CIRCLE_OFFSET_Y * scale_h
    alpha_dx  = BASE_ALPHABET_OFFSET_X * scale_w
    cross_dx  = BASE_CROSS_OFFSET_X * scale_w
    bar_w     = BASE_BAR_WIDTH * scale_w
    bar_dx    = BASE_BAR_SHIFT_X * scale_w

    # コマ幅
    try:
        koma_w = cell_x['B'] - cell_x['A']
    except Exception:
        xs = [v for _,v in sorted(cell_x.items(), key=lambda kv: kv[1])]
        diffs = [xs[i+1]-xs[i] for i in range(len(xs)-1)]
        diffs.sort()
        koma_w = diffs[len(diffs)//2] if diffs else 0.0

    # フォント
    font_large = ImageFont.truetype(font_path, size=int(base_font_size * scale_h))
    font_small = ImageFont.truetype(font_path, size=int(base_font_size * 0.9 * scale_h))
    book_font  = ImageFont.truetype(font_path, size=int(base_font_size * 0.6 * scale_h))
    try:
        cell_label_font = ImageFont.truetype(jp_font_path, size=int(base_font_size * 0.9 * scale_h))
    except Exception:
        cell_label_font = ImageFont.truetype(font_path, size=int(base_font_size * 0.9 * scale_h))

    # CSV
    df = read_csv_flexibly(file_bytes)
    if df.empty or 'Frame' not in df.columns: return [], 0
    df['Frame'] = clean_frame_column(df['Frame'])
    df = df.dropna(subset=['Frame'])
    df['Frame'] = df['Frame'].astype(int)
    df = df[df['Frame'] > 0]
    if df.empty: return [], 0

    valid_cells = [c for c in CELLS_ALL if c in df.columns]
    df = preprocess_cells(df, valid_cells)
    book_pos = get_book_positions(df, valid_cells)

    max_frame = df['Frame'].max()
    per_page = 144
    pages_n = math.ceil(max_frame / per_page)
    images = []

    cell_labels = cell_labels or {}

    for page in range(pages_n):
        img = Image.new("RGBA", (true_width, true_height), (255,255,255,0))
        draw = ImageDraw.Draw(img)

        start = page*per_page + 1
        end   = (page+1)*per_page
        dfp = df[(df['Frame']>=start) & (df['Frame']<=end)]
        if dfp.empty:
            images.append(img); continue

        last_frame = dfp['Frame'].max()

        # ====== セル名（1ページ目・左カラムのみ・下揃え） ======
        header_band = None
        if page == 0:
            header_bottom_y = first_y - 2*frame_h + (HEADER_BOTTOM_NUDGE_PX * scale_h)
            header_top_y    = header_bottom_y - (frame_h * 1.8)   # 適度に帯の厚みを確保
            header_band = (header_top_y, header_bottom_y)
            spacing = 2 * scale_h
            for c in valid_cells:
                label = (cell_labels.get(c) or "").strip()
                if not label: continue
                x_center = cell_x[c] + (HEADER_X_NUDGE_PX * scale_w)
                draw_vertical_bottom(draw, label, x_center, header_bottom_y, cell_label_font, spacing)

        # ====== 通常セル ======
        for c in valid_cells:
            x0 = cell_x[c]
            for _, row in dfp.iterrows():
                f = int(row['Frame'])
                s = str(row[c]) if not pd.isna(row[c]) else ""
                idx = (f-1) % per_page
                col = idx // 72
                r   = idx % 72
                y   = first_y + r*frame_h
                x   = x0 if col==0 else x0 + col_off_x
                y_draw = y + text_offset_y

                if s in ('●','○'):
                    x += circle_dx; y_draw += circle_dy
                elif s == '×':
                    x += cross_dx
                elif re.match(r"^\d+[a-zA-Z]$", s) or re.fullmatch(r"\d{2,}", s):
                    x += alpha_dx

                font = font_small if len(s)>=3 else font_large
                draw.text((x, y_draw), s, fill=(0,0,0,255), font=font)

        # ====== book マーカー ======
        if show_books:
            for _, row in dfp.iterrows():
                f = int(row['Frame'])
                idx = (f-1) % per_page
                col = idx // 72
                r   = idx % 72

                row_y = first_y + r*frame_h
                col_x_add = col_off_x if col==1 else 0

                # 行全体のラベル当たり判定（ポジション横断）
                row_boxes = []

                # その行に存在するbook
                present = {}
                for bcol, pos in book_pos.items():
                    cname = norm_str(bcol)
                    if (cname in row.index) and is_filled(row[cname]):
                        present.setdefault(pos, []).append(cname)

                for pos, books_here in present.items():
                    # X 位置
                    bx = None
                    if pos.startswith("before_"):
                        tgt = pos.replace("before_","")
                        if tgt in cell_x: bx = cell_x[tgt] - 12*scale_w
                    elif pos.startswith("between_"):
                        _, L, R = pos.split("_")
                        if L in cell_x and R in cell_x:
                            bx = cell_x[L] + 0.8*koma_w - 3*scale_w
                    elif pos.startswith("after_"):
                        tgt = pos.replace("after_","")
                        if tgt in cell_x: bx = cell_x[tgt] + 0.8*koma_w - 3*scale_w
                    if bx is None: continue

                    bx = bx + col_x_add - 5
                    y_ref = row_y - (frame_h * book_offset_koma)
                    base_top    = y_ref - 4*scale_h
                    base_bottom = y_ref + (frame_h*2) + 2*scale_h

                    items = []
                    for b in books_here:
                        s = norm_str(b).replace("_","")
                        m = re.search(r"(\d+)$", s)
                        n = int(m.group(1)) if m else 0
                        items.append((n, s))
                    items.sort(key=lambda t: t[0])

                    line_gap = 2*scale_h
                    margin   = 12*scale_w
                    bottom_label_bottom = None

                    def overlap(a,b):
                        ax1,ay1,ax2,ay2 = a; bx1,by1,bx2,by2 = b
                        return not (ax2<=bx1 or bx2<=ax1 or ay2<=by1 or by2<=ay1)

                    for k, (_, label) in enumerate(items):
                        bbox = draw.textbbox((0,0), label, font=book_font)
                        lw = bbox[2]-bbox[0]; lh = bbox[3]-bbox[1]
                        ly = (base_top - lh - 2*scale_h) - k*(lh+line_gap)
                        lx_center = bx - lw/2
                        lx = max(margin, min(true_width - margin - lw, lx_center))

                        cur = (lx, ly, lx+lw, ly+lh)
                        # 他のポジションのラベルとも当たり判定
                        while any(overlap(cur, box) for box in row_boxes):
                            ly -= (lh + line_gap)
                            cur = (lx, ly, lx+lw, ly+lh)

                        # セル名の帯と干渉するなら、帯の上端の少し上へ
                        if (page == 0 and col == 0 and header_band is not None):
                            band_top, band_bottom = header_band
                            if not (cur[3] <= band_top or cur[1] >= band_bottom):
                                ly = band_top - lh - 2*scale_h
                                cur = (lx, ly, lx+lw, ly+lh)

                        draw.text((lx, ly), label, fill=(0,0,0,255), font=book_font)
                        row_boxes.append(cur)

                        if (bottom_label_bottom is None) or (ly + lh > bottom_label_bottom):
                            bottom_label_bottom = ly + lh

                    # 線：最下段ラベルの直下から
                    pad = 2*scale_h
                    line_top = bottom_label_bottom + pad if bottom_label_bottom is not None else base_top
                    extra = frame_h * max(0, book_offset_koma - BASE_BOOK_OFFSET_KOMA)
                    line_bottom = max(line_top + 1, base_bottom + extra)
                    draw.line([(bx, line_top), (bx, line_bottom)], fill=(0,0,0,255), width=max(1, int(2*scale_w)))

        # 黒バー
        if last_frame:
            idx_last = (last_frame-1) % per_page
            col_last = idx_last // 72
            r_last   = idx_last % 72
            bar_y = first_y + (r_last + 1)*frame_h
            bar_x = 0 if col_last==0 else col_off_x
            draw.rectangle([(bar_x + 5 + bar_dx, bar_y),
                            (bar_x + 5 + bar_dx + bar_w, bar_y + frame_h*2)],
                           fill=(0,0,0,128))

        images.append(img)

    return images, max_frame

# =============== UI ===============
st.title("ちゃいむしーと Web版 v2.9.1｜セル名下揃え＋ヘッダ帯とbookの干渉回避")

c1, c2 = st.columns(2)
with c1:
    selected_preset = st.selectbox("会社プリセット", list(presets.keys()))
with c2:
    show_books = st.checkbox("Bookマーカーを描画する", value=True)

book_offset_koma = st.slider("Bookの高さ（何コマ上）", 0, 12, 6, 1)

with st.expander("セル名（A〜H）を入力（縦書き・1ページ目のみ / 日本語OK）", expanded=True):
    default_labels = {c: "" for c in CELLS_ALL}
    cols = st.columns(4)
    cell_labels = {}
    for i, c in enumerate(CELLS_ALL):
        with cols[i % 4]:
            cell_labels[c] = st.text_input(f"{c} セルのラベル", value=default_labels[c], key=f"label_{c}")

preset_cfg = presets[selected_preset]
uploaded = st.file_uploader("CSVファイルをアップロード", type=["csv"])

if uploaded is not None:
    if st.button("タイムシート生成！"):
        pages, total = generate_timesheet(uploaded.read(), preset_cfg,
                                          show_books=show_books,
                                          book_offset_koma=book_offset_koma,
                                          cell_labels=cell_labels)
        if not pages:
            st.warning("有効なFrameデータが見つかりませんでした。")
        else:
            secs, rem = total // 24, total % 24
            st.text_input("TIME", value=f"{secs} + {rem}")

            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zipf:
                for i, p in enumerate(pages):
                    st.image(p, caption=f"Page {i+1}", use_container_width=True)
                    b = io.BytesIO(); p.save(b, format='PNG'); b.seek(0)
                    data = b.getvalue()
                    zipf.writestr(f"timesheet_page_{i+1}.png", data)
                    st.download_button(f"⬇️ Page {i+1} ダウンロード", data, f"timesheet_page_{i+1}.png", "image/png")
            zip_buf.seek(0)
            st.download_button("📦 すべてまとめてダウンロード（ZIP）",
                               zip_buf.getvalue(), "timesheets_all.zip", "application/zip")
