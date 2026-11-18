# Judge audit

Chạy (trong `src/`):
```bash
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 10      # exit 0
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 21   # exit 1
```
Lớp dương = `FAIL` (việc của judge là tìm lỗi). Backend: replay, tức verdict của judge lưu sẵn trong CSV.

| Tiêu chí | n | κ | Precision | Recall | Ma trận (tp/fp/fn/tn) | Tỉ lệ FAIL quan sát → hiệu chỉnh RG | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | 24 / 4 / 6 / 66 | 0.28 → 0.30 | **Đạt** (exit 0) | **dùng**: metric phụ, không phải blocking cho tiền |
| helpful | 100 | 0.375 | 1.000 | 0.300 | 9 / 0 / 21 / 70 | 0.09 → 0.30 | **Không đạt**: κ < 0.6, R < 0.7 (exit 1) | **loại**: không dùng làm gate |

Rogan-Gladen: `(p_obs + spec − 1) / (sens + spec − 1)`. Với tone: sens = 0.8, spec = 66/70 = 0.943, nên 0.28 → 0.30.
Với helpful: sens = 0.3, spec = 1.0, nên 0.09 → 0.30. Judge helpful thấy 9% lỗi trong khi tỉ lệ lỗi thật khoảng 30%, tức **đếm thiếu ~3 lần**.

## Audit thủ công (15 case bất đồng)

### tone_ok: cả 10 bất đồng
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | **Người** | Xưng "em" + "nha" quá suồng sã. Rubric: liệt kê cặp xưng hô hợp lệ (`LogiX`/`anh/chị`, `Dạ … ạ`); xưng "em/bạn/nha/nhé" ⇒ FAIL. |
| 2 | H-017 "Dạ, bạn ơi … rồi nha." | PASS | FAIL | **Người** | Cùng lỗi xưng hô; có "Dạ" ở đầu không đủ để PASS. Thêm few-shot có "Dạ" nhưng vẫn FAIL. |
| 3 | H-029 "Dạ, vui lòng chờ … không cần nhắn thêm." | PASS | FAIL | **Người** | Judge chỉ thấy từ lịch sự bề mặt. Rubric: câu mệnh lệnh / cấm khách liên hệ ⇒ FAIL bất kể kính ngữ. |
| 4 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Judge phạt vì "thiếu xin lỗi". Rubric: xin lỗi **không bắt buộc** khi đã giải quyết xong; ngắn gọn mà đủ ý là PASS. |
| 5 | H-051 "Dạ, LogiX đã refund 90.000đ…" | FAIL | PASS | **Người** | Style guide CS LogiX cho phép từ "refund". Thêm vào rubric danh sách từ tiếng Anh được phép. |
| 6 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | **Người**, nhưng **không phải lỗi giọng** | Đây là hứa hẹn ngoài kết quả hệ thống (gần FM-08). Không bắt bằng judge tone; phải có grader **code** so reply với ledger. Rubric tone ghi rõ "không chấm nội dung tiền". |
| 7 | H-070 "…cho đơn O-909 ạ 😂😂" | PASS | FAIL | **Người** | Rubric: emoji trong ngữ cảnh khiếu nại ⇒ FAIL. |
| 8 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện…" | FAIL | PASS | **Judge** | Ghi chú cho biết người đọc nhầm ticket ⇒ **sửa nhãn người** (human → FAIL), không sửa rubric. Sau khi sửa: fp 4→3, tp 24→25. |
| 9 | H-088 "Dạ, dạ, LogiX đã hoàn…" | FAIL | PASS | **Người** | Lỗi gõ lặp "Dạ" không làm sai giọng. Rubric: lỗi chính tả nhỏ không đổi nghĩa ⇒ không FAIL. |
| 10 | H-094 "Da, LogiX da hoan … xin loi vi su bat tien." | PASS | FAIL | **Người** | Mất dấu tiếng Việt (dịch máy) là lỗi trình bày với khách. Rubric: thiếu dấu tiếng Việt ⇒ FAIL. |

Tổng kết tone: 9/10 người đúng, 1/10 judge đúng (H-081, sửa nhãn). Lỗi judge chia hai nhóm:
- (a) **FN**: chấm theo từ lịch sự bề mặt ("Dạ", "vui lòng"), bỏ qua xưng hô, emoji, mất dấu. Gồm H-008, 017, 029, 070, 094.
- (b) **FP**: áp chuẩn quá chặt ("phải xin lỗi", "cấm tiếng Anh", lỗi gõ). Gồm H-042, 051, 088.

### helpful: 21 bất đồng, toàn bộ là FN (người FAIL, judge PASS)
| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú / sửa rubric |
|---|---|---|---|---|---|
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." | PASS | FAIL (sai tiền, ledger 40.000đ) | **Người** | Judge không có ledger nên không thể biết số tiền sai. Đây chính là **FM-08 misreport** ⇒ chấm bằng code. |
| 12 | HL-016 xin lỗi dài + "đã hoàn 55.000đ cho đơn O-404" | PASS | FAIL (ledger 35.000đ) | **Người** | Câu xin lỗi dài lặp lại làm judge chấm "helpful": **verbosity bias**. |
| 13 | HL-043 "rất tiếc … đã hoàn 35.000đ cho đơn O-202" | PASS | FAIL (ledger 20.000đ) | **Người** | Cùng mẫu: văn mẫu xin lỗi che số sai. 0/18 case "sai tiền" bị judge bắt. |
| 14 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL (sai xưng hô) | **Người** | Judge helpful bỏ qua xưng hô (0/3 bắt được). Tiêu chí này nên chuyển về judge tone (đã calibrate). |
| 15 | HL-087 "Dạ, LogiX đã hoàn 60.000đ cho đơn O-202 ạ." | PASS | FAIL (ledger 90.000đ) | **Người** | Reply ngắn, sai tiền theo chiều **thiếu**; judge vẫn PASS. Judge không đọc ledger nên không phân biệt được. |

Theo loại lỗi người gán (30 FAIL):

| human_failure | số FAIL | judge bắt được |
|---|---|---|
| sai tiền | 18 | **0** |
| giọng cụt | 4 | 4 |
| không hỏi lại mã đơn | 3 | 3 |
| sai xưng hô | 3 | **0** |
| trả lời lạc đề | 2 | 2 |

Judge helpful chỉ bắt được lỗi **nhìn thấy trên bề mặt văn bản**: cụt, lạc đề, không hỏi mã đơn. Nó bỏ sót toàn bộ lỗi cần đối chiếu với sự thật (ledger).

## Kết luận
- **tone_ok: dùng.** κ 0.757, P 0.857, R 0.8 đều trên sàn. Chỉ dùng cho giọng văn, là metric non-blocking, không bao giờ chấm tiền.
  Sửa rubric theo audit:
  - danh sách xưng hô hợp lệ
  - emoji / mất dấu / câu mệnh lệnh ⇒ FAIL
  - xin lỗi không bắt buộc; từ "refund" và lỗi gõ nhỏ được phép
  - sửa nhãn H-081

  Sau khi sửa phải calibrate lại trên nhãn mới.
- **helpful: loại, không được làm gate.**
  - **Recall 0.3**: judge bỏ sót 21/30 reply lỗi. Ma trận fn = 21, trong đó 18 là sai tiền. Nếu dùng làm gate, một PR làm agent nói sai số tiền vẫn được merge.
  - **P = 1.0 dễ gây ảo giác**: judge không báo nhầm vì nó gần như luôn nói PASS (91/100). κ 0.375 cho thấy mức đồng thuận vượt ngẫu nhiên thấp.
  - Tỉ lệ lỗi quan sát 9% so với tỉ lệ hiệu chỉnh 30%: dashboard dùng judge này sẽ báo chất lượng tốt hơn thực tế khoảng 3 lần.
  - Nguyên nhân gốc: "helpful" gộp hai thứ. Thứ nhất là **đúng sự thật**: số tiền khớp ledger. Phần này chấm bằng code (FM-08, metric M3), vì *tiền và approval luôn chấm bằng code*. Thứ hai là **đủ ý / đúng việc**: lạc đề, không hỏi mã đơn. Phần này judge làm được (bắt 9/9).
  - Hành động: tách rubric. Bỏ "đúng số tiền" khỏi judge, và bỏ phần xưng hô sang tone. Viết lại rubric helpful chỉ gồm *trả lời đúng câu hỏi / hỏi lại khi thiếu thông tin / không lạc đề*. Thêm few-shot có xin lỗi dài nhưng vô ích ⇒ FAIL để chống verbosity bias. Sau đó calibrate lại; chỉ dùng khi qua sàn.
- **Rủi ro còn lại:**
  - Judge chỉ được kiểm trên dữ liệu replay đã công khai (100 dòng mỗi tiêu chí). Rubric đã sửa theo chính các case này nên dễ overfit; cần nhãn người mới để có held-out thật.
  - n = 100 có nghĩa mỗi điểm κ/P/R có khoảng tin cậy rộng (R tone 0.8 tính trên chỉ 30 FAIL).
  - Judge thật (không replay) có nhiễu giữa các lần gọi, cần đo lại.
