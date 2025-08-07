Timesheet Book Insert
142
143
144
145
146
147
148
149
150
151
152
153
154
155
156
157
158
159
160
161
162
163
164
165
166
167
168
169
170
171
172
173
174
175
176
177
178
179
180
181
182
183
184
185
186
187
188
189
190
191
192
193
194
195
196
197
198
199
200
201
202
203
204
205
206
207
208
209
210
211
212
213
214
215
216
217
218
219
220
221
222
223
224
225
226
227
228
229
230
231
232
233
234
235
236
237
238
239
240
241
242
243
244
245
246
247
248
        last_frame_in_page = df_page['Frame'].max()

        for idx, row in df_page.iterrows():
            frame_num = row['Frame']
            frame_in_column_total = (frame_num - 1) % frames_per_page
            column = frame_in_column_total // 72
            frame_in_column = frame_in_column_total % 72
            y_true = first_frame_top_y_true + frame_in_column * frame_height_true
            y_draw_true = y_true + text_offset_y

            for cell in valid_cells:
                x_base_true = cell_x_positions_true[cell] + (column_offset_x * column)
                timing = str(row[cell]) if not pd.isna(row[cell]) else ""

                x_true = x_base_true
                if timing == '●' or timing == '○':
                    x_true += circle_offset_x_true
                    y_draw_true += circle_offset_y_true
                elif timing == '×':
                    x_true += cross_offset_x_true
                elif re.match(r"^\d+[a-zA-Z]$", timing) or re.fullmatch(r"\d{2,}", timing):
                    x_true += alphabet_offset_x_true

                font = font_small_scaled if len(timing) >= 3 else font_large_scaled
                draw.text((x_true, y_draw_true), timing, fill=(0, 0, 0, 255), font=font)

            for book_col, pos in book_positions.items():
                book_text = str(row[book_col]).strip()
                if book_text:
                    frame_tag = book_col.replace("_", "")
                    if pos.startswith("between_"):
                        _, left, right = pos.split("_")
                        if left in cell_x_positions_true and right in cell_x_positions_true:
                            x_left = cell_x_positions_true[left] + (column_offset_x * column)
                            x_right = cell_x_positions_true[right] + (column_offset_x * column)
                            x_center = (x_left + x_right) / 2
                        else:
                            continue
                    elif pos.startswith("before_"):
                        _, col = pos.split("_")
                        if col in cell_x_positions_true:
                            x_center = cell_x_positions_true[col] + (column_offset_x * column) - 20
                        else:
                            continue
                    else:
                        continue

                    for i, ch in enumerate(frame_tag):
                        draw.text((x_center, y_true + i * font_size_true), ch, fill=(0, 0, 0, 255), font=font_small_scaled)

        if last_frame_in_page:
            frame_in_column_total = (last_frame_in_page - 1) % frames_per_page
            column = frame_in_column_total // 72
            frame_in_column = frame_in_column_total % 72
            bar_y = first_frame_top_y_true + (frame_in_column + 1) * frame_height_true
            bar_x = 0 if column == 0 else column_offset_x
            draw.rectangle(
                [(bar_x + 5 + bar_shift_x, bar_y),
                 (bar_x + 5 + bar_shift_x + bar_width, bar_y + frame_height_true * 2)],
                fill=(0, 0, 0, 128)
            )

        result_images.append(img)

    return result_images, max_frame_num

# アプリUI
st.title("ちゃいむしーと Web版 v1.9.2 + book位置自動採用")
selected_preset_name = st.selectbox("会社プリセットを選択してください", list(presets.keys()))
preset_cfg = presets[selected_preset_name]

uploaded_file = st.file_uploader("CSVファイルをアップロードしてください", type=["csv"])

if uploaded_file is not None:
    if st.button("タイムシート生成!"):
        pages, total_frames = generate_timesheet(uploaded_file.read(), preset_cfg)

        if not pages:
            st.warning("有効なFrameデータが見つかりませんでした")
        else:
            seconds = total_frames // 24
            remainder = total_frames % 24
            time_str = f"{seconds} + {remainder}"
            st.text_input("TIME", value=time_str)

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for idx, page_img in enumerate(pages):
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
                label="📦 すべてまとめてダウンロード (ZIP)",
                data=zip_buffer,
                file_name="timesheets_all.zip",
                mime="application/zip"
            )

