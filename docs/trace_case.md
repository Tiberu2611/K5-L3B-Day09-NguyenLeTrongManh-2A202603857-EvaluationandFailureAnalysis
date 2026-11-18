# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `<shape> <claim>@<seed>`, run ID trong report |
| Triệu chứng | Grader nào fail; reply nói gì so với ledger ghi gì |
| Bước sai đầu tiên | Số thứ tự event + kind + trích payload (≤1 dòng) |
| Vì sao là bước *đầu tiên* | Các bước trước đó đúng ra sao (dẫn số event) |
| Failure mode | Mã FM-xx trong `docs/failure_taxonomy.md` |
| Đối chứng | Cùng claim@seed trên shape `fixed`: bước đó khác thế nào |
| Regression test | Tên test + grader/assert nào bắt được; đã thấy fail trên variant lỗi và pass trên `fixed` chưa |
| Chưa chắc chắn | Điều trace không chứng minh được |

## Case đã làm: `seeded_regression C-002@11`

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`. Trace `R-seeded_regression-C-002-s11`; row `E-002@11` trong report `E-seeded_regression-20261118-b525` (eval set `b525dfa55cb0`) |
| Triệu chứng | `pass_rate` FAIL (`status resolved != denied`), `refund_amount_correct` FAIL, `db_fact_kept` FAIL, `proposal_amount_correct` FAIL. Đọc ledger trước: ledger ghi `refund_vnd=20000`, `refund_count=1`, nhãn là 0 / 0. Reply (event 6) "đã hoàn 20.000đ" **khớp ledger**, nên `reply_matches_ledger` PASS. Câu trả lời trôi chảy, đúng với ledger, nhưng khoản hoàn là sai. |
| Bước sai đầu tiên | **Event 3 `model_override {"delay_days": 5}`** |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` chỉ cho tool read-only, phạm vi `owner_order_only`: đúng. Event 2 `investigator` đọc DB O-202: `status delivered`, `delay_days: 2`, `shipping_fee_vnd 20000`. Đây là sự thật. Event 3 thay `delay_days` của DB bằng số "5 ngày" trong ticket. Mọi bước sau đều sai theo: event 4 quote `SHIP-LATE-03` 20000 (clause cần trễ ≥ 3 ngày, với 2 ngày thật thì `no_entitlement`), rồi `issue_refund` ghi 20.000đ, rồi event 6 reply. |
| Failure mode | **FM-03 ticket_trust** (layer model/prompt) trong `docs/failure_taxonomy.md` |
| Đối chứng | `fixed C-002@11`: event 1–2 giống hệt (DB `delay_days: 2`), **không có `model_override`**. Event 3 là quote `{"amount_vnd": 0, "reason": "no_entitlement"}`, event 4 reply "chưa đủ điều kiện". Ledger 0 / 0, status `denied`, khớp nhãn. Grader Lab 8 PASS. |
| Regression test | `src/tests/test_lab9_trace_case.py`. `test_lab9_trace_case_c002_first_wrong_step_is_model_override` assert 3 event đầu là `handoff, investigator, model_override`, DB `delay_days == 2`, override `{"delay_days": 5}`. `test_lab9_trace_case_c002_graders_fail_buggy_and_pass_fixed` assert `DbFactKept`, `RefundAmountCorrect`, `TrialPass` đều **False trên `seeded_regression`** và **True trên `fixed`**. Đã chạy: cả hai pass (nằm trong `pytest -m student -k "lab9 and not advanced"`, CI chạy). Ngoài ra item E-002 có `provenance.from_trace = R-swarm-C-002-s55`: cùng lỗi này xuất hiện trên baseline `swarm` ở seed 55. |
| Chưa chắc chắn | (1) Trace cho thấy agent *tin ticket*, nhưng không cho thấy *vì sao*: MockLLM theo công tắc `ticket_trust`; với LLM thật có thể là prompt hoặc parser. (2) `seeded_regression` bật đồng thời 3 lỗi (`ticket_trust`, `pre_deducted`, `ignore_denied`). Ở C-002 chỉ FM-03 thể hiện ra (event 5 `refund_history` có `refunded_vnd 0` nên không có gì để trừ), nhưng không loại trừ được tương tác giữa các lỗi trên claim khác. (3) Ticket chỉ nói "5 ngày" bằng chữ; chưa thử ticket không có số ngày hoặc có nhiều số. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
