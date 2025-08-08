        # ---- bookマーカー描画（縦線＋番号ラベル／複数は縦積み、線は1本） ----
        for _, row in df_page.iterrows():
            frame = int(row['Frame'])
            idx = (frame - 1) % frames_per_page
            col_block = idx // 72
            row_pos = idx % 72

            # 行の基準位置（このフレームの行の上端）
            y_base = first_frame_top_y_true + row_pos * frame_height_true
            x_col  = column_offset_x if col_block == 1 else 0

            # ❶ この行でbook値が入っているものだけ抽出して位置ごとにグループ化
            present = {}  # ← これが無いと NameError
            for book_col, pos in book_positions.items():
                if book_col in row and str(row[book_col]).strip() != "":
                    present.setdefault(pos, []).append(book_col)

            # ❷ 位置ごとに描画
            for pos, books_here in present.items():
                # 基準x座標（pos → x_insert）
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

                # 列ブロック／手動オフセット：左に5px、上に「1文字分」
                x_insert = x_insert + x_col - 5
                y_ref = y_base - label_font.size  # 1文字分上

                # --- 縦線は常に1本（+1コマ長く） ---
                line_top = y_ref - 4 * scale_h
                line_bottom = y_ref + (frame_height_true * 2) + 2 * scale_h
                line_w = max(1, int(2 * scale_w))
                draw.line([(x_insert, line_top), (x_insert, line_bottom)], fill=(0, 0, 0, 255), width=line_w)

                # --- ラベル配置 ---
                if len(books_here) == 1:
                    # 単独：番号あり（_book2 → book2）を線の上に中央で
                    label = books_here[0].replace("_", "")
                    bbox = draw.textbbox((0, 0), label, font=label_font)
                    label_w = bbox[2] - bbox[0]
                    label_h = bbox[3] - bbox[1]
                    label_x = x_insert - (label_w / 2)
                    label_y = line_top - label_h - 2 * scale_h
                    draw.text((label_x, label_y), label, fill=(0, 0, 0, 255), font=label_font)
                else:
                    # 複数：縦積み。数字降順（book3, book2, ...）
                    labels = [b.replace("_", "") for b in books_here]
                    def num_suffix(s):
                        m = re.search(r'(\d+)$', s)
                        return int(m.group(1)) if m else -1
                    labels.sort(key=num_suffix, reverse=True)

                    # 全体高さを計算して上から順に配置
                    bboxes = [draw.textbbox((0, 0), lb, font=label_font) for lb in labels]
                    heights = [(bx[3] - bx[1]) for bx in bboxes]
                    widths  = [(bx[2] - bx[0]) for bx in bboxes]
                    gap = 2 * scale_h  # ラベル間の縦間隔
                    total_h = sum(heights) + gap * (len(labels) - 1)
                    top_y = line_top - total_h - 2 * scale_h

                    for lb, w, h in zip(labels, widths, heights):
                        label_x = x_insert - (w / 2)
                        draw.text((label_x, top_y), lb, fill=(0, 0, 0, 255), font=label_font)
                        top_y += h + gap
