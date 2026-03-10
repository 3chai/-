import streamlit as st
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import math, re, io, os, unicodedata, zipfile
from typing import Optional

# =============== 基本定義 ===============
cell_offsets = {
    'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5, 'G': 6, 'H': 7,
    'I': 8, 'J': 9, 'K': 10, 'L': 11, 'M': 12, 'N': 13, 'O': 14, 'P': 15
}
CELLS_ALL = list(cell_offsets.keys())

presets = {
    "Andraft": {
        "first_frame_top_y_true": 1279,
        "frame_height_true": 49.6,
        "cell_x_positions_true": {cell: 108 + 55.8 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 1688,
        "true_width": 3508,
        "true_height": 4961,
        "default_book_koma": 6,
        "default_celllabel_koma": 2,
    },
    "BELLNOX FILMS": {
        "first_frame_top_y_true": 1383,
        "frame_height_true": 47.28,
        "cell_x_positions_true": {cell: 88   + 61 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 1703,
        "true_width": 3509,
        "true_height": 4961,
        "default_book_koma": 5,
        "default_celllabel_koma": 1
    },
    "CygamesPictures": {
        "first_frame_top_y_true": 779,
        "frame_height_true": 33.98 ,
        "cell_x_positions_true": {cell: 108.5 + 37.2 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 1168,
        "true_width": 2340,
        "true_height": 3307,
        "default_book_koma": 6,
        "default_celllabel_koma": 3
    },
    "J.C.STAFF": {
        "first_frame_top_y_true": 731,
        "frame_height_true": 34.65,
        "cell_x_positions_true": {cell: 90 + 43 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 1128,
        "true_width": 2338,
        "true_height": 3308,
        "default_book_koma": 6,
        "default_celllabel_koma": 2
    },
    "MAPPA": {
        "first_frame_top_y_true": 553,
        "frame_height_true": 26.57,
        "cell_x_positions_true": {cell: 84.5 + 26.7 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 876.5,
        "true_width": 1788,
        "true_height": 2514 ,
        "default_book_koma": 6,
        "default_celllabel_koma": 2
    },
    "ぴえろ（BLEACH用）": {
        "first_frame_top_y_true": 800,
        "frame_height_true": 27.5,
        "cell_x_positions_true": {cell: 86 + 30.8 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 950.5,
        "true_width": 2026,
        "true_height": 2866,
        "default_book_koma": 4,
        "default_celllabel_koma": 1
    },
    "ぴえろ(ブラクロ用）": {
        "first_frame_top_y_true": 591,                  # 最初のフレームの上端Y
        "frame_height_true": 20.98,                      # 1コマの高さ
        "cell_x_positions_true": {cell: 58 + 23.3 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 723,                         # 右カラムまでのXオフセット
        "true_width": 1518,
        "true_height": 2150,
        "default_book_koma": 4,
        "default_celllabel_koma": 1
    },
    "東映アニメーション": {
        "first_frame_top_y_true": 666,
        "frame_height_true": 35.75,
        "cell_x_positions_true": {cell: 94.5 + 41.5 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 1153,
        "true_width": 2338,
        "true_height": 3306,
        "default_book_koma": 5,
        "default_celllabel_koma": 1
    },
    "動画工房": {
        "first_frame_top_y_true": 468,
        "frame_height_true": 27.25,
        "cell_x_positions_true": {cell: 51.7 + 29 * offset for cell, offset in cell_offsets.items()},
        "column_offset_x": 870,
        "true_width": 1754,
        "true_height": 2480,
        "default_book_koma": 5,  
        "default_celllabel_koma": 0,
    }
}

# =============== 位置調整の基準（Andraft基準） ===============
BASE_FRAME_HEIGHT = 49.5
BASE_WIDTH = 3508
BASE_CIRCLE_OFFSET_X = -5
BASE_CIRCLE_OFFSET_Y = -2
BASE_ALPHABET_OFFSET_X = -13
BASE_CROSS_OFFSET_X = -5
BASE_CROSS_OFFSET_Y = -1
BASE_BAR_WIDTH = 1620
BASE_BAR_SHIFT_X = 88
text_offset_y = 4

BASE_BOOK_OFFSET_KOMA = 3

# 数字の段階的縮小
TWO_DIGIT_SCALE    = 0.85  # 例: 12
THREE_PLUS_SCALE   = 0.7  # 例: 100, 240

# ===== 数字の桁数別 位置補正（px相当；負=上/左, 正=下/右）=====
NUM1_NUDGE_X = 0
NUM1_NUDGE_Y = 0

NUM2_NUDGE_X = 0
NUM2_NUDGE_Y = 2

NUM3PLUS_NUDGE_X = -5
NUM3PLUS_NUDGE_Y = 5


# ====== 英字付き(例: 1a/12a/108a)の桁数別スケール＆位置補正 ======
ALPHA1_SCALE = 0.8   # 1a の基準スケール
ALPHA2_SCALE = 0.7   # 12a の基準スケール
ALPHA3PLUS_SCALE = 0.6  # 100a など

# 負=上/左, 正=下/右（px相当をスケールに掛ける）
ALPHA1_NUDGE_X = 5
ALPHA1_NUDGE_Y = 6.5

ALPHA2_NUDGE_X = 1.8
ALPHA2_NUDGE_Y = 9

ALPHA3PLUS_NUDGE_X = -1.8
ALPHA3PLUS_NUDGE_Y = 10


# --- 囲み描画の見た目（UIで上書き可） ---
ENC_PAD_W = 10   # テキスト左右余白(px相当)
ENC_PAD_H = 6    # テキスト上下余白(px相当)
ENC_STROKE = 4   # 線の太さ(px相当)

# セル名オフセット（px基準 → スケール）
HEADER_X_NUDGE_PX      = 10
HEADER_BOTTOM_NUDGE_PX = -80

# ○/●/〇 の専用縮小＆位置補正
CIRCLE_SCALE   = 0.5   # 1.0=等倍
CIRCLE_NUDGE_X = 8     # px（正=右, 負=左）
CIRCLE_NUDGE_Y = 10    # px（正=下,  負=上）

# フォント（Streamlit Cloud 対策：同梱フォント優先＋安全なフォールバック）
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
FONTS_DIR = APP_DIR / "fonts"

# ここにフォントを同梱しておくのが最も確実
# 例: fonts/DejaVuSans.ttf, fonts/NotoSansJP-Regular.otf
font_path_candidates = [
    str(FONTS_DIR / "DejaVuSans.ttf"),
    str(APP_DIR / "DejaVuSans.ttf"),
]
jp_font_path_candidates = [
    str(FONTS_DIR / "NotoSansJP-Regular.otf"),
    str(FONTS_DIR / "NotoSansJP-Regular.ttf"),
    str(APP_DIR / "NotoSansJP-Regular.otf"),
    str(APP_DIR / "NotoSansJP-Regular.ttf"),
]

base_font_size = int(12 / (1086 / 3508))

def _pick_existing_path(candidates):
    for p in candidates:
        try:
            if p and os.path.exists(p):
                return p
        except Exception:
            pass
    return None

FONT_PATH = _pick_existing_path(font_path_candidates)
JP_FONT_PATH = _pick_existing_path(jp_font_path_candidates)

def safe_truetype(path: str | None, size: int, *, fallback_to_default: bool = True):
    """Pillow の ImageFont.truetype を安全に呼ぶ。失敗したら load_default に落とす。"""
    try:
        if path:
            return ImageFont.truetype(path, size=size)
    except Exception:
        pass
    return ImageFont.load_default() if fallback_to_default else None

# =============== まとめ入力パーサー ===============
def parse_triangle_spec(s: str):
    """
    'A1, A10a, C24, 3, 5-7, 10a' などを一括で解釈。
    戻り値: (triangle_cell_refs, triangle_alpha_tokens, triangle_numbers)
      - triangle_cell_refs: {'A1', 'A10a', 'C24', ...}  ※セル優先
      - triangle_alpha_tokens: {'10a', '7b', ...}       ※全セルで英字付き
      - triangle_numbers: {3,5,6,7,...}                 ※全セルで数字のみ
    """
    cell_refs = set()
    alpha_tokens = set()
    numbers = set()

    s = (s or "").strip()
    if not s:
        return cell_refs, alpha_tokens, numbers

    for part in re.split(r"[,\u3001\s]+", s):
        part = part.strip()
        if not part:
            continue

        # セル指定（A-H + 数字 + 英字0/1）
        m_cell = re.fullmatch(r"([A-Ha-h])\s*(\d+)\s*([a-zA-Z]?)", part)
        if m_cell:
            c = m_cell.group(1).upper()
            n = m_cell.group(2)
            suf = m_cell.group(3).lower()
            cell_refs.add(f"{c}{n}{suf}")
            continue

        # 数字レンジ 5-12 / 12-5
        m_rng = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m_rng:
            a, b = int(m_rng.group(1)), int(m_rng.group(2))
            if a <= b:
                numbers.update(range(a, b+1))
            else:
                numbers.update(range(b, a+1))
            continue

        # 英字付き token (10a など)
        m_alpha = re.fullmatch(r"(\d+)([a-zA-Z])", part)
        if m_alpha:
            n = m_alpha.group(1)
            suf = m_alpha.group(2).lower()
            alpha_tokens.add(f"{n}{suf}")
            continue

        # 純数字
        if part.isdigit():
            numbers.add(int(part))
            continue

    return cell_refs, alpha_tokens, numbers

# =============== ユーティリティ ===============
def parse_mixed_triangle_targets(s: str):
    """
    例:
      "1, 4-6, 24, 10a,7b，12C"
      -> ( {1,4,5,6,24}, {"10a","7b","12C"} )
    ・数字は範囲対応 (a-b)
    ・英字付き(10aなど)はトークン単位。範囲は非対応
    """
    nums = set()
    alnum = set()
    s = (s or "").strip()
    if not s:
        return nums, alnum

    for part in re.split(r"[,\u3001]", s):
        part = part.strip()
        if not part:
            continue

        m_rng = re.fullmatch(r"(\d+)\s*-\s*(\d+)", part)
        if m_rng:
            a, b = int(m_rng.group(1)), int(m_rng.group(2))
            if a <= b:
                nums.update(range(a, b+1))
            else:
                nums.update(range(b, a+1))
            continue

        m_num      = re.fullmatch(r"\d+", part)
        m_numalpha = re.fullmatch(r"\d+[a-zA-Z]", part)
        if m_num:
            nums.add(int(part))
        elif m_numalpha:
            alnum.add(part)

    return nums, alnum

def clean_frame_column(series):
    series = series.astype(str).str.strip().map(lambda x: unicodedata.normalize("NFKC", x))
    series = pd.to_numeric(series, errors='coerce')
    return series

def normalize_for_vertical(text: str) -> str:
    return (text
            .replace("ー", "｜").replace("ｰ", "｜")
            .replace("－", "｜").replace("―", "｜")
            .replace("—", "｜").replace("–", "｜"))

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

 # 海外CSV対策：中割りが '?'（半角/全角）で入ってくる場合は ● として扱う
 # valid_cells（A〜H など）の列だけを対象に置換する
 # ※ 他の記号や数値は変更しない

def replace_question_with_circle(df: pd.DataFrame, valid_cells):
    for c in valid_cells:
        if c in df.columns:
            df[c] = df[c].apply(lambda v: '●' if str(v).strip() in ('?', '？') else v)
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

def get_book_positions(df, valid_cells):
    cols = list(df.columns)
    book_cols = [c for c in cols if re.match(r"^_?book\d+$", str(c), re.IGNORECASE)]
    positions = {}
    for b in book_cols:
        idx = cols.index(b)
        left_cell = None
        for i in range(idx - 1, -1, -1):
            if cols[i] in valid_cells:
                left_cell = cols[i]; break
        right_cell = None
        for i in range(idx + 1, len(cols)):
            if cols[i] in valid_cells:
                right_cell = cols[i]; break
        if left_cell is None and right_cell is None:
            continue
        if left_cell is None:
            positions[b] = f"before_{right_cell}"
        elif right_cell is None:
            positions[b] = f"after_{left_cell}"
        else:
            positions[b] = f"between_{left_cell}_{right_cell}"
    return positions

def norm_str(s):
    return unicodedata.normalize("NFKC", str(s)).replace("\u3000", " ").strip()

def is_filled(v):
    s = norm_str(v)
    return s not in ("", "nan", "None")

def draw_vertical_bottom(draw, text, bottom_x, bottom_y, font, spacing=0):
    if not text:
        return
    text = normalize_for_vertical(text)
    boxes, total_h = [], 0
    for ch in text:
        bbox = draw.textbbox((0, 0), ch, font=font)
        w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]
        boxes.append((ch, w, h)); total_h += h
    total_h += spacing * (len(boxes) - 1 if boxes else 0)
    y = bottom_y - total_h
    for ch, w, h in boxes:
        draw.text((bottom_x - w/2.0, y), ch, fill=(0,0,0,255), font=font)
        y += h + spacing

# 縦書きテキストの総高さを測る（文字間隔含む）
def vertical_text_total_height(draw, text, font, spacing=0):
    if not text:
        return 0
    text = normalize_for_vertical(text)
    total_h = 0
    count = 0
    for ch in text:
        bbox = draw.textbbox((0, 0), ch, font=font)
        h = (bbox[3] - bbox[1])
        total_h += h
        count += 1
    if count > 1:
        total_h += spacing * (count - 1)
    return total_h

# book X座標（before/between/after）

def calc_book_x(pos, cell_x_positions_true, koma_width, scale_w):
    book_x = None
    if pos.startswith("before_"):
        tgt = pos.replace("before_", "")
        if tgt in cell_x_positions_true:
            book_x = cell_x_positions_true[tgt] - 9 * scale_w
    elif pos.startswith("between_"):
        parts = pos.split("_")
        if len(parts) == 3:
            _, left, right = parts
            if left in cell_x_positions_true and right in cell_x_positions_true:
                book_x = cell_x_positions_true[left] + 0.8 * koma_width + 3 * scale_w
    elif pos.startswith("after_"):
        tgt = pos.replace("after_", "")
        if tgt in cell_x_positions_true:
            book_x = cell_x_positions_true[tgt] + 0.8 * koma_width + 3 * scale_w
    return book_x

# ---- 追加：判定＆描画ユーティリティ（ギャップ用） ----
def is_number_or_alnum(s: str) -> bool:
    """'12' や '10a' のような先頭が数字で英字1文字までのパターンを判定"""
    return bool(re.fullmatch(r"\d+([a-zA-Z])?", s.strip()))

def build_gap_markers(df: pd.DataFrame, valid_cells, threshold: int = 4, last_frame: Optional[int] = None):
    """
    各セル列について、連続する非空同士のギャップが threshold 以上なら
    直前のフレームにマーカーを付ける。
      - 直前値が '×' -> kind='wavy'
      - 直前値が 数字 or 数字+英字 -> kind='straight'
    さらに、列の「最後の非空」から end（last_frame）までの空白が threshold 以上なら
    その最後の非空にもマーカーを付ける（終端補正）。

    返り値: { (cell, frame): (kind, run_len, is_tail) }
       run_len は、その frame を含む直前の連続区間の長さ。
       is_tail は、その frame が列内の最後の非空（終端ギャップ）なら True、途中ギャップなら False。
    """
    markers = {}
    df_sorted = df.sort_values('Frame')
    end_frame = int(last_frame) if last_frame is not None else int(df_sorted['Frame'].max())

    for cell in valid_cells:
        col = df_sorted[['Frame', cell]].copy()
        col['val'] = col[cell].astype(str).map(lambda x: x.strip())
        nonempty = col[col['val'] != ""]
        frames = nonempty['Frame'].astype(int).tolist()
        vals   = nonempty['val'].tolist()
        if not frames:
            continue

        # 数字/英字付きのみカウント（×や記号は除外）
        is_straight_val = [is_number_or_alnum(v) for v in vals]
        total_straight_frames = sum(1 for ok in is_straight_val if ok)

        # 連続区間を抽出（フレーム番号が1刻みの塊）
        groups = []  # [(start_idx, end_idx)]  end_idx は inclusive
        start = 0
        for i in range(1, len(frames)):
            if frames[i] != frames[i-1] + 1 or vals[i] != vals[i-1]:
                groups.append((start, i-1))
                start = i
        groups.append((start, len(frames)-1))

        # 中間ギャップ（途中）
        for gi in range(len(groups) - 1):
            s, e = groups[gi]
            s2, e2 = groups[gi+1]
            f_cur = frames[e]
            v_cur = vals[e]
            f_next = frames[s2]
            gap = (f_next - f_cur - 1)
            if gap >= threshold:
                run_len = (e - s + 1)
                if v_cur == '×':
                    markers[(cell, f_cur)] = ('wavy', run_len, False, total_straight_frames)
                elif is_number_or_alnum(v_cur):
                    markers[(cell, f_cur)] = ('straight', run_len, False, total_straight_frames)
        # 終端ギャップ（最後の非空 -> end_frame）
        s_last, e_last = groups[-1]
        last_f = frames[e_last]
        last_v = vals[e_last]
        tail_gap = (end_frame - last_f)
        if tail_gap >= threshold:
            run_len_last = (e_last - s_last + 1)
            if last_v == '×':
                markers[(cell, last_f)] = ('wavy', run_len_last, True, total_straight_frames)
            elif is_number_or_alnum(last_v):
                markers[(cell, last_f)] = ('straight', run_len_last, True, total_straight_frames)

    return markers

# =================== 枚数カウントヘルパー ===================
def compute_sheet_counts(df: pd.DataFrame, valid_cells, triangle_cell_refs, triangle_alpha_tokens,
                         triangle_numbers, alpha_all_triangle=False):
    """
    タイムシート情報から枚数を集計する。
      - douga_count: 動画枚数（中割り点 + 数字/数字+英字の合計）
      - genga_count: 原画枚数（丸が付く数字/数字+英字）
      - sankou_count: 参考枚数（三角が付く数字/数字+英字）
    """
    douga_count = 0
    genga_count = 0
    sankou_count = 0

    for cell in valid_cells:
        if cell not in df.columns:
            continue

        for raw in df[cell].tolist():
            timing = "" if pd.isna(raw) else str(raw).strip()
            if not timing:
                continue

            # × は原画枚数に含めない（表示上の補完記号として扱う）
            if timing == '×':
                continue

            # 中割り点
            if timing in ('●', '○', '〇'):
                douga_count += 1
                continue

            # 数字 / 数字+英字
            m = re.fullmatch(r"(\d+)([a-zA-Z]?)", timing)
            if m:
                douga_count += 1

                num_text = m.group(1)
                suffix = m.group(2).lower()
                token = f"{num_text}{suffix}"
                cell_tok = f"{cell}{token}"

                is_triangle = (
                    (cell_tok in triangle_cell_refs) or
                    (suffix and (alpha_all_triangle or (token in triangle_alpha_tokens))) or
                    ((not suffix) and (int(num_text) in triangle_numbers))
                )

                if is_triangle:
                    sankou_count += 1
                else:
                    genga_count += 1

    return {
        "douga_count": douga_count,
        "genga_count": genga_count,
        "sankou_count": sankou_count,
    }

def draw_wavy_vertical(draw: ImageDraw.ImageDraw, cx: float, y_top: float, y_bottom: float,
                       amplitude: float, period_px: float, stroke: int):
    """
    縦に伸びる波線を描く（サイン波）。peak-to-peak で 2*amplitude。
    """
    import math
    pts = []
    y = y_top
    step = max(2.0, period_px / 12.0)  # なめらかさ
    while y <= y_bottom:
        x = cx + amplitude * math.sin(2 * math.pi * (y - y_top) / period_px)
        pts.append((x, y))
        y += step
    if len(pts) >= 2:
        draw.line(pts, fill=(0, 0, 0, 255), width=stroke)

# 三角の見た目調整
TRIANGLE_NUDGE_Y = -0.9  # 負=上、正=下（px）
TRIANGLE_BASE_W_SCALE = 1.2
TRIANGLE_HEIGHT_SCALE = 1
TRIANGLE_USE_FIXED = True  # Trueで三角の大きさを一定にする
TRIANGLE_FIXED_SIZE = 40   # 基準ピクセル（Andraft基準）。テンプレートに合わせ scale_h で拡大縮小
TRIANGLE_FILL_ALPHA = 0       # 三角の塗りの不透明度（0% = 0）
TRIANGLE_OUTLINE_ALPHA = 77  # 三角枠の不透明度（約50%）

# 丸の固定サイズ設定（三角と揃える）
CIRCLE_USE_FIXED  = True
CIRCLE_FIXED_SIZE = 48
CIRCLE_FILL_ALPHA = 0
CIRCLE_OUTLINE_ALPHA = 128 # 円の不透明度（塗りはデフォルト0%、枠はデフォルト50%）

# 囲み描画（数字の周りに丸/三角）
ENC_PAD_BASE    = 0    # 文字と円の基本余白(px)
ENC_GROWTH      = 0.53 # 横が縦より大きい時の増量係数
ENC_MAX_EXTRA   = 30   # 増量の上限(px)

def draw_enclosure(draw, bbox, shape="circle", stroke=2,
                   tri_outline_alpha=TRIANGLE_OUTLINE_ALPHA,
                   circ_outline_alpha=CIRCLE_OUTLINE_ALPHA,
                   tri_fill_alpha=TRIANGLE_FILL_ALPHA,
                   circ_fill_alpha=CIRCLE_FILL_ALPHA,
                   scale_w=1.0, scale_h=1.0):
    """
    bbox: テキストの描画境界 (x1,y1,x2,y2)
    shape: "circle" or "triangle"
    """
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1

    if shape == "triangle":
        # 二等辺三角形（上向き）
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0

        if TRIANGLE_USE_FIXED:
            # 一定サイズ（三角の見た目を安定させる）。高さと底辺は固定サイズを基準に scale_h を掛ける。
            height = TRIANGLE_FIXED_SIZE * scale_h * TRIANGLE_HEIGHT_SCALE
            base_half = (TRIANGLE_FIXED_SIZE * TRIANGLE_BASE_W_SCALE * scale_h) / 2.0
            top_y = cy - height / 2.0
            bottom_y = cy + height / 2.0
        else:
            # 従来：テキストbboxに追従（数値が長いと横に広がる）
            w = x2 - x1
            h = y2 - y1
            base_half = (w / 2.0) * TRIANGLE_BASE_W_SCALE
            top_y = y2 - h * TRIANGLE_HEIGHT_SCALE
            bottom_y = y2

        pts = [(cx, top_y), (cx - base_half, bottom_y), (cx + base_half, bottom_y)]
        # polygon による塗り（既定は透明）
        draw.polygon(pts, fill=(0, 0, 0, tri_fill_alpha))
        # 枠線（不透明度指定）
        draw.line(pts + [pts[0]], fill=(0, 0, 0, tri_outline_alpha), width=stroke, joint="curve")
        return

    # 真円（数字が横長でも半径に少し加算してキレイに収める）
    # --- circle（固定サイズ or 従来の自動） ---
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    if CIRCLE_USE_FIXED:
        # 一定半径（三角に合わせて scale_h で拡縮）
        r = (CIRCLE_FIXED_SIZE * scale_h) / 2.0
    else:
        extra = max(0, w - h) * ENC_GROWTH
        extra = min(extra, ENC_MAX_EXTRA)
        r = (h / 2.0) + ENC_PAD_BASE + (extra / 2.0)

    draw.ellipse(
        (cx - r, cy - r, cx + r, cy + r),
        fill=(0, 0, 0, circ_fill_alpha),
        outline=(0, 0, 0, circ_outline_alpha),
        width=stroke
    )

# --- ドリフトしないY計算（保険用） ---
def y_for_frame(top_y: int, n_frame: int, frame_h: float, fps: int = 24) -> int:
    sec, sub = divmod(n_frame, fps)
    y_sec = int(round(top_y + sec * fps * frame_h))
    return int(round(y_sec + sub * frame_h))

# =============== 本体 ===============
def generate_timesheet(
    file_bytes,
    preset,
    show_books=True,
    book_offset_koma=6,
    cell_labels=None,
    celllabel_koma=2,
    target_cell_for_enclose="A",
    mixed_triangle_str="",
    enc_pad_w=ENC_PAD_W,
    enc_pad_h=ENC_PAD_H,
    enc_stroke=ENC_STROKE,
    triangle_outline_alpha=TRIANGLE_OUTLINE_ALPHA,
    circle_outline_alpha=CIRCLE_OUTLINE_ALPHA,
    alpha_all_triangle=False,
):
    # 入力一発 → セル参照・英字付きトークン・数字セットに分解
    triangle_cell_refs, triangle_alpha_tokens, triangle_numbers = parse_triangle_spec(mixed_triangle_str)

    # プリセット
    true_width = preset["true_width"]; true_height = preset["true_height"]
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
    cross_offset_y = BASE_CROSS_OFFSET_Y * scale_h
    bar_width = BASE_BAR_WIDTH * scale_w
    bar_shift_x = BASE_BAR_SHIFT_X * scale_w

    # 1コマ幅推定
    try:
        koma_width = cell_x_positions_true['B'] - cell_x_positions_true['A']
    except Exception:
        items = sorted(cell_x_positions_true.items(), key=lambda kv: kv[1])
        coords = [v for _, v in items]
        diffs = [coords[i+1] - coords[i] for i in range(len(coords)-1)]
        diffs.sort()
        koma_width = diffs[len(diffs)//2] if diffs else 0.0

    # フォント（存在しないパスで落ちないように安全にロード）
    font_large  = safe_truetype(FONT_PATH, size=int(base_font_size * scale_h))
    font_small  = safe_truetype(FONT_PATH, size=int(base_font_size * 0.9 * scale_h))
    font_circle = safe_truetype(FONT_PATH, size=int(base_font_size * scale_h * CIRCLE_SCALE))
    label_font  = safe_truetype(FONT_PATH, size=int(base_font_size * 0.6 * scale_h))

    # 日本語フォント（無ければ英字フォントにフォールバック）
    cell_label_font = safe_truetype(JP_FONT_PATH, size=int(base_font_size * 0.6 * scale_h))
    jp_font_large   = safe_truetype(JP_FONT_PATH, size=int(base_font_size * scale_h))

    # もし load_default() に落ちてしまった場合、日本語は豆腐になることがあるので警告を出す
    if JP_FONT_PATH is None:
        st.warning("日本語フォントが見つかりませんでした。fonts/ に NotoSansJP-Regular.otf(または .ttf) を置くとセル名などが安定します。")
    if FONT_PATH is None:
        st.warning("英字フォントが見つかりませんでした。fonts/ に DejaVuSans.ttf を置くと描画が安定します。")

    # CSV
    df = read_csv_flexibly(file_bytes)
    if df.empty or 'Frame' not in df.columns:
        return [], 0, {"douga_count": 0, "genga_count": 0, "sankou_count": 0}

    df['Frame'] = clean_frame_column(df['Frame'])
    df = df.dropna(subset=['Frame'])
    df['Frame'] = df['Frame'].astype(int)
    df = df[df['Frame'] > 0]
    if df.empty:
        return [], 0, {"douga_count": 0, "genga_count": 0, "sankou_count": 0}

    valid_cells = [c for c in CELLS_ALL if c in df.columns]
    # '?'（半角/全角）を ● に変換（海外CSVの中割り表記対策）
    df = replace_question_with_circle(df, valid_cells)
    df = preprocess_cells(df, valid_cells)

    counts = compute_sheet_counts(
        df,
        valid_cells,
        triangle_cell_refs,
        triangle_alpha_tokens,
        triangle_numbers,
        alpha_all_triangle=alpha_all_triangle,
    )

    # 全体の最終フレーム
    max_frame = int(df['Frame'].max())

    # ★ ギャップ判定（終端も考慮）
    gap_markers = build_gap_markers(df, valid_cells, threshold=4, last_frame=max_frame)

    max_frame = df['Frame'].max()
    frames_per_page = 144
    total_pages = math.ceil(max_frame / frames_per_page)
    last_frame_global = max_frame
    result_images = []
    cell_labels = cell_labels or {}

    for page in range(total_pages):
        img = Image.new("RGBA", (true_width, true_height), (255, 255, 255, 0))
        draw = ImageDraw.Draw(img)

        start = page*frames_per_page + 1
        end = (page+1)*frames_per_page
        df_page = df[(df['Frame']>=start) & (df['Frame']<=end)]
        if df_page.empty:
            result_images.append(img); continue

        last_frame_in_page = df_page['Frame'].max()

        # ---- セル名（1ページ目のみ・左カラム・縦書き下揃え）----
        if page == 0:
            header_bottom_y = (first_frame_top_y_true
                               - celllabel_koma * frame_height_true
                               + (HEADER_BOTTOM_NUDGE_PX * scale_h))
            glyph_spacing = 2 * scale_h
            for cell in valid_cells:
                label = (cell_labels.get(cell) or "").strip()
                if not label:
                    continue
                x_center = cell_x_positions_true[cell] + (HEADER_X_NUDGE_PX * scale_w)
                draw_vertical_bottom(
                    draw, label,
                    bottom_x=x_center,
                    bottom_y=header_bottom_y,
                    font=cell_label_font,
                    spacing=glyph_spacing
                )

        # ---- 通常セル（丸/三角 囲み対応）----
        for cell in valid_cells:
            x_base = cell_x_positions_true[cell]
            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                timing = str(row[cell]) if not pd.isna(row[cell]) else ""
                idx = (frame-1) % frames_per_page
                col_block = idx // 72
                row_pos = idx % 72
                y = first_frame_top_y_true + row_pos*frame_height_true
                x = x_base if col_block==0 else x_base + column_offset_x
                y_draw = y + text_offset_y

                # 記号の扱い
                if timing in ('●','○','〇'):
                    x += circle_offset_x + (CIRCLE_NUDGE_X * scale_w)
                    y_draw += circle_offset_y + (CIRCLE_NUDGE_Y * scale_h)
                    font = font_circle
                elif timing == '×':
                    x += cross_offset_x
                    y_draw += cross_offset_y
                    font = font_large
                else:
                    # 文字種別でフォントとスケールを決定し、桁数別の補正を適用
                    m_num_alpha = re.fullmatch(r"(\d+)([a-zA-Z])", timing)  # 10a
                    m_digits    = re.fullmatch(r"\d+", timing)              # 12, 108 など

                    if m_num_alpha:
                        # 英字付き（例：10a）。数字部分の桁数で細かく最適化
                        digit_part = m_num_alpha.group(1)   # "10"
                        nlen = len(digit_part)

                        if nlen == 1:
                            scale = ALPHA1_SCALE
                            nx, ny = ALPHA1_NUDGE_X, ALPHA1_NUDGE_Y
                        elif nlen == 2:
                            scale = ALPHA2_SCALE
                            nx, ny = ALPHA2_NUDGE_X, ALPHA2_NUDGE_Y
                        else:
                            scale = ALPHA3PLUS_SCALE
                            nx, ny = ALPHA3PLUS_NUDGE_X, ALPHA3PLUS_NUDGE_Y

                        font = safe_truetype(FONT_PATH, size=int(base_font_size * scale_h * scale))

                        # 既存の横位置微調整は活かす（文字詰まり防止）
                        x += alphabet_offset_x
                        # 桁数別の最終補正
                        x += nx * scale_w
                        y_draw += ny * scale_h

                    elif m_digits:
                        nlen = len(timing)
                        if nlen == 1:
                            font = font_large
                            nx, ny = NUM1_NUDGE_X, NUM1_NUDGE_Y
                        elif nlen == 2:
                            scale = TWO_DIGIT_SCALE
                            font = safe_truetype(FONT_PATH, size=int(base_font_size * scale_h * scale))
                            x += alphabet_offset_x * 0.6
                            nx, ny = NUM2_NUDGE_X, NUM2_NUDGE_Y
                        else:
                            scale = THREE_PLUS_SCALE
                            font = safe_truetype(FONT_PATH, size=int(base_font_size * scale_h * scale))
                            x += alphabet_offset_x * 0.6
                            nx, ny = NUM3PLUS_NUDGE_X, NUM3PLUS_NUDGE_Y
                        x += nx * scale_w
                        y_draw += ny * scale_h
                    else:
                        font = font_small if len(timing) >= 3 else font_large

                # ===== 囲み（全セル対象：セル指定 > 英字付きtoken > 数字のみ の優先順）=====
                m_lead = re.match(r"\s*(\d+)([a-zA-Z]?)", timing)  # 先頭の「数字(+任意の英字1文字)」
                if m_lead:
                    num_text = m_lead.group(1)           # '12'
                    suffix   = m_lead.group(2).lower()   # 'a' or ''
                    token    = f"{num_text}{suffix}"     # '12a' or '12'
                    cell_tok = f"{cell}{token}"          # 例: 'A12a'

                    # --- 三角の判定（優先度：セル指定 > 英字付きtoken > 数字のみ） ---
                    is_triangle = (
                        (cell_tok in triangle_cell_refs) or
                        (suffix and (alpha_all_triangle or (token in triangle_alpha_tokens))) or
                        ((not suffix) and (int(num_text) in triangle_numbers))
                    )

                    # トークン全体（数字 + 任意の英字1文字）の bbox を取得
                    # suffix が空でも token は num_text と同じなのでそのまま使える
                    token_bbox = draw.textbbox((x, y_draw), token, font=font)

                    pad_w = enc_pad_w * scale_w
                    pad_h = enc_pad_h * scale_h
                    dy = (TRIANGLE_NUDGE_Y * scale_h) if is_triangle else 0

                    ebbox = (
                        token_bbox[0] - pad_w,
                        token_bbox[1] - pad_h + dy,
                        token_bbox[2] + pad_w,
                        token_bbox[3] + pad_h + dy
                    )
                    stroke_px = max(1, int(enc_stroke * scale_w))
                    draw_enclosure(
                        draw, ebbox,
                        shape=('triangle' if is_triangle else 'circle'),
                        stroke=stroke_px,
                        tri_outline_alpha=triangle_outline_alpha,
                        circ_outline_alpha=circle_outline_alpha,
                        tri_fill_alpha=TRIANGLE_FILL_ALPHA,
                        circ_fill_alpha=CIRCLE_FILL_ALPHA,
                        scale_w=scale_w, scale_h=scale_h
                    )

                # テキストを最後に描画
                draw.text((x, y_draw), timing, fill=(0,0,0,255), font=font)

                # ==== 直後 4コマ以上のギャップがある場合の補助線（2コマ分） ====
                mark_info = gap_markers.get((cell, frame))
                if mark_info:
                    # 対応: 2要素(old), 3要素(prev), 4要素(new)
                    if isinstance(mark_info, tuple):
                        if len(mark_info) == 4:
                            mark_kind, run_len, is_tail, total_straight = mark_info
                        elif len(mark_info) == 3:
                            mark_kind, run_len, is_tail = mark_info
                            total_straight = None
                        elif len(mark_info) == 2:
                            mark_kind, run_len = mark_info
                            is_tail = False
                            total_straight = None
                        else:
                            mark_kind, run_len, is_tail, total_straight = mark_info[0], None, False, None
                    else:
                        mark_kind, run_len, is_tail, total_straight = mark_info, None, False, None

                    if mark_kind in ('wavy', 'straight'):
                        # 線の中心Xは文字のbbox中心
                        tb = draw.textbbox((x, y_draw), timing, font=font)
                        cx = (tb[0] + tb[2]) / 2.0

                        # 基本の線開始位置は「次のコマの上端」
                        y_top = y + frame_height_true

                        # 「止め」は ① is_tail ② run_len==1 ③ 総フレーム数==1
                        if (mark_kind == 'straight' and is_tail and run_len == 1 and (total_straight == 1)):
                            vfont = jp_font_large  # 数字と同等サイズの日本語フォント

                            # 数字の描画位置に合わせた“上揃え”の開始位置を作る（そのコマの y_draw 相当）
                            def top_like_number(koma_index_from_current: int) -> float:
                                koma_top = y + frame_height_true * koma_index_from_current
                                return koma_top + text_offset_y + (NUM1_NUDGE_Y * scale_h)

                            # 1文字目：「止」→ 次のコマの“数字位置”で上揃え
                            y_top_like = top_like_number(1) - 3  # 3px 上へ
                            h_stop = draw.textbbox((0, 0), "止", font=vfont)[3] - draw.textbbox((0, 0), "止", font=vfont)[1]
                            draw_vertical_bottom(draw, "止", bottom_x=cx, bottom_y=y_top_like + h_stop, font=vfont, spacing=0)

                            # 2文字目：「め」→ その次のコマの“数字位置”で上揃え
                            y_top_like2 = top_like_number(2) - 3  # 3px 上へ
                            h_me = draw.textbbox((0, 0), "め", font=vfont)[3] - draw.textbbox((0, 0), "め", font=vfont)[1]
                            draw_vertical_bottom(draw, "め", bottom_x=cx, bottom_y=y_top_like2 + h_me, font=vfont, spacing=0)

                            # 縦線は「め」の直下から。さらに5px下げる
                            y_top = (y_top_like2 + h_me) + (20 * scale_h) 

                        # 線の終端（4コマ分）
                        y_bottom = y_top + frame_height_true * 4.0
                        stroke_px = max(1, int(3 * scale_w))

                        if mark_kind == 'wavy':
                            # 幅：コマ半分（peak-to-peak = 0.5コマ → 振幅は 0.25コマ）
                            amp = 0.08 * (cell_x_positions_true.get('B', 0) - cell_x_positions_true.get('A', 0) or koma_width)
                            # period は 2/3 コマぐらい
                            period = frame_height_true * 0.75
                            draw_wavy_vertical(draw, cx, y_top, y_bottom, amplitude=amp, period_px=period, stroke=stroke_px)
                        else:
                            draw.line([(cx, y_top), (cx, y_bottom)], fill=(0, 0, 0, 255), width=stroke_px)

        # ---- book マーカー（行内共有の重なり回避／枠は飾り）----
        if show_books:
            BOX_PAD_X = 1 * scale_w
            BOX_PAD_Y = 1 * scale_h
            BOX_OUTLINE_W = max(1, int(1.5 * scale_w))

            for _, row in df_page.iterrows():
                frame = int(row['Frame'])
                idx = (frame-1) % frames_per_page
                col_block = idx // 72
                row_pos = idx % 72

                row_y_base = first_frame_top_y_true + row_pos*frame_height_true
                col_x_offset = column_offset_x if col_block==1 else 0

                present = {}
                for book_col, pos in get_book_positions(df, valid_cells).items():
                    cname = norm_str(book_col)
                    if (cname in row.index) and is_filled(row[cname]):
                        present.setdefault(pos, []).append(cname)

                placed_boxes_row = []

                entries = []
                for pos, books_here in present.items():
                    bx = calc_book_x(pos, cell_x_positions_true, koma_width, scale_w)
                    if bx is not None:
                        entries.append((bx + col_x_offset - 5, pos, books_here))

                for book_x, pos, books_here in sorted(entries, key=lambda t: t[0]):
                    y_ref = row_y_base - (frame_height_true * book_offset_koma)
                    base_line_top    = y_ref - 4*scale_h
                    base_line_bottom = y_ref + (frame_height_true*2) + 2*scale_h

                    items = []
                    for b in books_here:
                        s = norm_str(b).replace("_","")
                        m = re.search(r"(\d+)$", s)
                        n = int(m.group(1)) if m else 0
                        items.append((n, s))
                    items.sort(key=lambda t: t[0])

                    line_gap    = 2*scale_h
                    extra_shift = 3*scale_h
                    margin      = 12*scale_w

                    bottom_label_bottom = None

                    def overlap(a,b):
                        ax1,ay1,ax2,ay2 = a
                        bx1,by1,bx2,by2 = b
                        return not (ax2<=bx1 or bx2<=ax1 or ay2<=by1 or by2<=ay1)

                    for idx_item, (_, label) in enumerate(items):
                        bbox0 = draw.textbbox((0, 0), label, font=label_font)
                        lw = bbox0[2] - bbox0[0]
                        lh = bbox0[3] - bbox0[1]

                        base_y = (base_line_top - lh - 2*scale_h) - idx_item * (lh + line_gap)
                        lx_center = book_x - (lw / 2)
                        ly = base_y
                        lx = max(margin, min(true_width - margin - lw, lx_center))

                        while True:
                            bbox_at = draw.textbbox((lx, ly), label, font=label_font)
                            cur_padded = (
                                bbox_at[0] - BOX_PAD_X,
                                bbox_at[1] - BOX_PAD_Y,
                                bbox_at[2] + BOX_PAD_X,
                                bbox_at[3] + BOX_PAD_Y
                            )
                            hit = any(overlap(cur_padded, box) for box in placed_boxes_row)
                            if not hit:
                                break
                            ly -= (lh + line_gap + extra_shift)

                        draw.text((lx, ly), label, fill=(0,0,0,255), font=label_font)
                        draw.rectangle([cur_padded[0], cur_padded[1], cur_padded[2], cur_padded[3]],
                                       outline=(0,0,0,255), width=max(1, int(1.5*scale_w)))
                        placed_boxes_row.append(cur_padded)
                        bottom_label_bottom = max(bottom_label_bottom or cur_padded[3], cur_padded[3])

                    pad_top = 2 * scale_h
                    line_top = (bottom_label_bottom + pad_top) if bottom_label_bottom is not None else base_line_top
                    extra_len = frame_height_true * max(0, book_offset_koma - BASE_BOOK_OFFSET_KOMA)
                    line_bottom = max(line_top + 1, base_line_bottom + extra_len)
                    line_w = max(1, int(2*scale_w))
                    draw.line([(book_x, line_top), (book_x, line_bottom)], fill=(0,0,0,255), width=line_w)

        # ---- 黒バー（全体の最後のフレーム位置のみ）----
        if page == total_pages - 1:
            idx_last = (last_frame_global - 1) % frames_per_page
            col_last = idx_last // 72
            row_last = idx_last % 72

            bar_y = first_frame_top_y_true + (row_last + 1) * frame_height_true
            bar_x = 0 if col_last == 0 else column_offset_x

            draw.rectangle(
                [
                    (bar_x + 5 + BASE_BAR_SHIFT_X * (true_width / BASE_WIDTH), bar_y),
                    (bar_x + 5 + BASE_BAR_SHIFT_X * (true_width / BASE_WIDTH) + BASE_BAR_WIDTH * (true_width / BASE_WIDTH),
                     bar_y + frame_height_true * 2)
                ],
                fill=(0, 0, 0, 128)
            )

        result_images.append(img)

    return result_images, max_frame, counts

# =============== UI（CSSでサイズ調整） ===============
st.markdown("""
    <style>
    .stApp h1 {
        font-size: 1.35rem !important;
        line-height: 1.3 !important;
        margin-bottom: 0.4rem !important;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    input[type="text"] {
        font-size: 0.8rem !important;
        height: 1.8rem !important;
        padding: 0 6px !important;
    }
    .stMarkdown h3, .stMarkdown h2 {
        font-size: 1rem !important;
        margin: 0.4rem 0 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.title("ちゃいむしーと Web版 v4")

# プリセット選択
selected_preset = st.selectbox("会社プリセット", list(presets.keys()))
preset_cfg = presets[selected_preset]

# デフォルト値（プリセットごと）
default_book_koma = preset_cfg.get("default_book_koma", 6)
default_celllabel_koma = preset_cfg.get("default_celllabel_koma", 2)

c1, c2, c3 = st.columns(3)
with c1:
    show_books = st.checkbox("Bookを描画する", value=True)
with c2:
    book_offset_koma = st.slider("Bookの高さ（何コマ上）", 0, 12, int(default_book_koma), 1)
with c3:
    celllabel_koma = st.slider("セル名の高さ（何コマ上）", 0, 6, int(default_celllabel_koma), 1)

# 丸/三角設定（入力はひとつだけ）
with st.expander("原画番号の丸/参考設定", expanded=True):
    # 例: A1, A10a, C24, 3, 5-7, 10a
    triangle_spec_str = st.text_input(
        "参考にする指定（A1,A6,A10a,コンマで区切る）",
        value=""
    )

    # 英字付き（例: 10a, 7b）は全て参考にする
    alpha_all_triangle = st.checkbox("英字付き(例: 10a, 7b)はすべて参考にする", value=True)

    # 不透明度（％）スライダー → 0〜255 に変換（枠のみ）
    tri_alpha_pct  = st.slider("三角の枠の不透明度(%)", 0, 100, int(round(TRIANGLE_OUTLINE_ALPHA * 100 / 255)))
    circ_alpha_pct = st.slider("丸の枠の不透明度(%)", 0, 100, int(round(CIRCLE_OUTLINE_ALPHA   * 100 / 255)))
    triangle_outline_alpha = int(round(tri_alpha_pct  * 255 / 100))
    circle_outline_alpha   = int(round(circ_alpha_pct * 255 / 100))

# セル名入力（1ページ目・縦書き）
with st.expander("セル名（A〜P）を入力）", expanded=False):
    default_labels = {c: "" for c in CELLS_ALL}
    cols = st.columns(4)
    cell_labels = {}
    for i, cell in enumerate(CELLS_ALL):
        with cols[i % 4]:
            cell_labels[cell] = st.text_input(f"{cell} セルのラベル", value=default_labels[cell], key=f"label_{cell}")

uploaded_file = st.file_uploader("CSVファイルをアップロード", type=["csv"])

if uploaded_file is not None:
    if st.button("タイムシート生成！"):
        pages, total_frames, counts = generate_timesheet(
            uploaded_file.read(),
            preset_cfg,
            show_books=show_books,
            book_offset_koma=book_offset_koma,
            cell_labels=cell_labels,
            celllabel_koma=celllabel_koma,
            mixed_triangle_str=triangle_spec_str,   # ← 入力ひとつを渡す（UIのテキストボックス値）
            triangle_outline_alpha=triangle_outline_alpha,
            circle_outline_alpha=circle_outline_alpha,
            alpha_all_triangle=alpha_all_triangle,
        )
        if not pages:
            st.warning("有効なFrameデータが見つかりませんでした。")
        else:
            seconds = total_frames // 24
            remainder = total_frames % 24
            st.text_input("TIME", value=f"{seconds} + {remainder}")

            c_douga, c_genga, c_sankou = st.columns(3)
            with c_douga:
                st.metric("動画枚数", counts["douga_count"])
            with c_genga:
                st.metric("原画枚数", counts["genga_count"])
            with c_sankou:
                st.metric("参考枚数", counts["sankou_count"])

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
                for i, page in enumerate(pages):
                    st.image(page, caption=f"Page {i+1}", use_container_width=True)
                    b = io.BytesIO(); page.save(b, format='PNG'); b.seek(0)
                    content = b.getvalue()
                    zipf.writestr(f"timesheet_page_{i+1}.png", content)
                    st.download_button(
                        label=f"⬇️ Page {i+1} ダウンロード",
                        data=content,
                        file_name=f"timesheet_page_{i+1}.png",
                        mime="image/png"
                    )
            zip_buffer.seek(0)
            st.download_button(
                label="📦 すべてまとめてダウンロード（ZIP）",
                data=zip_buffer.getvalue(),
                file_name="timesheets_all.zip",
                mime="application/zip"
            )
