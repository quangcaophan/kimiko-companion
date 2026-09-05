# Riko v2 — Implementation Plan

Rewrite từ đầu, tái sử dụng assets (VRM client, animation, voice reference, mapping bảng click reaction) từ project gốc. Không tái sử dụng code Python gốc.

**Trạng thái tổng:** Phase 0–3 hoàn tất, Phase 4 (memory_service.py) đang làm.

---

## 1. Quyết định kiến trúc đã chốt

| Hạng mục | Quyết định | Lý do |
|---|---|---|
| LLM | `gemini-3.5-flash-lite` qua **Interactions API** (`client.interactions.create`) | Model rẻ, hỗ trợ function calling native — bỏ được MCP |
| Function calling | Native tool-calling của Gemini, thay thế hoàn toàn MCP server cũ | Bớt 1 tầng hạ tầng (không cần chạy `riko_project_MCP` riêng) |
| Embedding | LM Studio local server, model `text-embedding-bge-m3` | Multilingual tốt cho Việt/Anh trộn; `bge-m3` **không cần prefix** (khác `nomic-embed-text`) |
| Retrieval | Hybrid: `VectorIndex` + `BM25Index` + `Retriever` (Reciprocal Rank Fusion) — port từ `rag.ipynb` | BM25 bắt tốt tên riêng/chi tiết cụ thể mà semantic search dễ bỏ sót |
| Memory (giữa các turn) | **Tự quản lý qua SQLite + hybrid store**, không dùng `previous_interaction_id` để persist dài hạn | Tránh vendor lock-in vào retention policy của Google; `previous_interaction_id` chỉ dùng nội bộ 1 turn (nối bước tool-call) |
| DB | SQLite, `PRAGMA journal_mode=WAL`, `row_factory=sqlite3.Row` | Cho phép 2 thread (voice loop + click dispatcher) truy cập an toàn |
| Server LM Studio | Tự động start/stop qua `lms` CLI trong `lifecycle.py`, gọi ở đầu/cuối `main.py` | Đỡ phải mở tay như GPT-SoVITS |
| Phạm vi | 1 user cá nhân, không multi-tenant | Theo lựa chọn ban đầu — ưu tiên memory + kiến trúc tốt hơn, không phải scale nhiều user |

### Assets tái sử dụng nguyên trạng

- `client/` (VRM three-vrm frontend)
- `animations/vrma_xr/`, `animations/mixamo/`
- `character_files/*.wav` (voice reference cho GPT-SoVITS)
- Bảng mapping region/bone → animation từ `click_reactions.py` gốc (port sang `avatar/reactions.py`)
- Logic ASR (Groq/faster-whisper) và TTS (GPT-SoVITS ping) từ `main_chat_v9.py` gốc
- Hợp đồng REST endpoint của `server.py` gốc (`/talk`, `/animate`, `/set_state`, `/walk_to`, `/send_click_interaction`...) — giữ nguyên để client VRM không cần sửa

---

## 2. Cấu trúc thư mục

```
riko2/
  assets/                          # animations/, character_files/, client/ — nguyên trạng
  config/
    persona.yaml
    settings.yaml                  # embedding, memory (window_size, top_k, summarize_every_n_turns)
  core/
    gemini/
      adapter.py                   # ĐÃ TEST — cô lập client.interactions.create
      tools.py                     # ĐÃ TEST — schema function-calling
    memory/
      lifecycle.py                 # ĐÃ TEST — start_llm()/end_llm() LM Studio
      embedder.py                  # ĐÃ TEST — LMStudioEmbedder (bge-m3, không prefix)
      vector_store.py              # ĐÃ TEST — VectorIndex, BM25Index, Retriever, PersistentHybridStore
      db.py                        # ĐÃ TEST — MemoryDB (đầy đủ CRUD)
      memory_service.py            # ĐANG LÀM — orchestration layer
    audio/
      asr.py                       # CHƯA LÀM — port từ bản gốc
      tts.py                       # CHƯA LÀM — port từ bản gốc
    avatar/
      reactions.py                 # CHƯA LÀM — port bảng mapping click_reactions.py
      actions.py                   # CHƯA LÀM — thực thi tool call từ Gemini
      playback_worker.py           # CHƯA LÀM
    server/
      app.py                       # CHƯA LÀM — FastAPI, giữ nguyên endpoint contract cũ
  turn_engine.py                   # CHƯA LÀM — ghép memory + gemini + audio + action
  main.py                          # CHƯA LÀM — orchestrator, gọi lifecycle start/stop
```

---

## 3. Schema SQLite hiện tại (đã test đầy đủ)

```sql
CREATE TABLE turns(
    id INTEGER PRIMARY KEY, ts REAL, role TEXT, content TEXT,
    embedded INTEGER DEFAULT 0
);
CREATE TABLE memory_facts(
    id INTEGER PRIMARY KEY, content TEXT, ts REAL,
    session_id INTEGER, vector_json TEXT
);
CREATE TABLE profile(
    id INTEGER PRIMARY KEY, summary TEXT, updated_at REAL
);
CREATE TABLE pending_actions(
    id INTEGER PRIMARY KEY, region TEXT, bone TEXT, ts REAL,
    consumed INTEGER DEFAULT 0
);
CREATE TABLE sessions(
    id INTEGER PRIMARY KEY, started_at REAL, ended_at REAL
);
```

`MemoryDB` class — method đã viết + test pass:

| Method | Trạng thái |
|---|---|
| `insert_turn`, `get_recent_turns` | ✅ pass |
| `insert_memory_fact`, `get_all_memory_facts` | ✅ pass |
| `get_or_create_session`, `close_session` | ✅ pass (test cả 2 nhánh: session đang mở vs đã đóng) |
| `get_profile_summary`, `set_profile_summary` | ✅ pass (lưu ý: hiện tại `set_profile_summary` luôn INSERT, không UPDATE — bảng `profile` sẽ phình theo thời gian, giữ làm audit trail có chủ đích) |
| `insert_pending_action`, `pop_pending_actions` | ✅ pass (atomic: gọi lần 2 liên tiếp phải trả `[]`) |
| `get_turns_to_embed`, `mark_turns_embedded` | ✅ pass — dùng `boundary_id` (offset theo `id`), **không** dùng `total - window_size` (bug đã gặp: công thức trừ tổng số dòng không "nhớ" đã embed bao nhiêu, lôi nhầm turn còn trong window ra ngoài) |

---

## 4. Gemini Interactions API — field schema đã verify bằng gọi thật (không phải đoán từ doc)

**Model:** `gemini-3.5-flash-lite`. **Cảnh báo:** API đang Beta, đã tự gặp warning `UserWarning: Interactions usage is experimental and may change in future versions`.

### Streaming events (từ `run_turn`)

| Event | Field xác nhận đúng |
|---|---|
| Bắt đầu 1 tool call | `event.event_type == "step.start"`, `event.step.type == "function_call"`, `event.step.id`, `event.step.name` |
| Text chunk | `event.event_type == "step.delta"`, `event.delta.type == "text"`, `event.delta.text` |
| Arguments chunk (JSON string) | `event.event_type == "step.delta"`, `event.delta.type == "arguments_delta"`, `event.delta.arguments` |
| Phân biệt nhiều step song song | `event.index` (top-level mọi event) |
| Interaction ID (cần cho turn tiếp theo) | `event.event_type == "interaction.created"`, `event.interaction.id` |
| Step "thought" (model suy nghĩ trước khi hành động) | Xuất hiện tự nhiên trước function_call, code hiện tại tự bỏ qua đúng (không khớp nhánh if/elif nào, không crash) |

### Nộp kết quả tool (`continue_with_tool_result`)

**Field đã sửa 2 lỗi so với bản đầu:**

```python
input=[{
    "type": "function_result",
    "name": tool_name,
    "call_id": tool_call_id,      # KHÔNG phải "id" — đã confirm qua lỗi 400 + đối chiếu doc
    "result": [{"type": "text", "text": result_text}],   # KHÔNG phải string thô
}]
```

Test full round-trip (function_call → thực thi → continue_with_tool_result → model nói tiếp) đã **pass thực tế**.

**Lưu ý quan trọng cho `turn_engine.py`:** mỗi lần gọi `interactions.create` trả về `interaction_id` MỚI, kể cả khi đang "tiếp tục" qua `previous_interaction_id`. Nếu 1 turn có nhiều tool call nối tiếp, phải luôn dùng `interaction_id` mới nhất làm `previous_id` cho vòng kế — cần vòng `while` theo dõi biến này trong `turn_engine`, không gọi cố định 1 lần.

### `tools.py` schema

Format `{"type": "function", "name": ..., "description": ..., "parameters": {...}}` đã confirm đúng khớp doc chính thức Interactions API — không cần sửa.

---

## 5. Bug đã gặp & fix trong quá trình build (lessons learned)

| # | File | Bug | Fix |
|---|---|---|---|
| 1 | `db.py` (bản đầu) | `memory_facts` `CREATE TABLE IF NOT EXISTS` 2 lần khác schema → schema đầu thắng, schema cần lại bị bỏ qua âm thầm | Chỉ giữ 1 định nghĩa đúng |
| 2 | `embedder.py` vs `vector_store.py` | Signature mismatch: `embed()` chỉ nhận 1 tham số nhưng nơi gọi truyền 2 (`embed(t, "document")`) | Bỏ lambda bọc, truyền thẳng `embedder.embed` |
| 3 | `vector_store.py` | Thiếu `import math`, `import json` (copy từ notebook, nơi 2 module này đã import ở cell khác) | Thêm 2 import |
| 4 | `db.py` | `get_connection()` không set `row_factory` → `row["content"]` lỗi `TypeError` vì row là tuple | `conn.row_factory = sqlite3.Row` |
| 5 | `db.py` | `init_db()` gọi `conn.close()` bên trong `with conn:` — `with` tự commit khi thoát, cố commit trên connection đã đóng → `ProgrammingError` | Bỏ `commit()`/`close()` thủ công, để `with` tự lo |
| 6 | Test cell | `from datetime import time` đè lên `import time` thật trong notebook namespace → `AttributeError` khi gọi `time.time()` | Luôn `import time` tường minh, tránh wildcard import |
| 7 | Test cell | Dùng `":memory:"` để test — mỗi lần `connect(":memory:")` tạo DB RAM **độc lập mới**, không phải DB dùng chung giữa các lần gọi | Dùng file tạm thật (`tempfile.mkstemp`) cho test |
| 8 | Test | Tái sử dụng cùng 1 file DB giữa các phase test khác nhau → dữ liệu rác từ test trước (vector 3 chiều giả) làm vỡ `_vector_dim` khi test embedding thật (1024 chiều) | Mỗi khối test tạo file mới, dọn sau khi xong |
| 9 | `lifecycle.py` (bản giữa) | Gọi `start_llm()` 2 lần, lần 2 truyền nhầm object `OpenAI` vào tham số `base_url: str` | Xoá lời gọi thừa |
| 10 | Notebook `LM Studio` gốc | `start_llm(client)` — `client` là `LMStudioEmbedder` wrapper, không có `.models`, chỉ có `.client.models` | Truyền đúng `client.client`, hoặc tách `start_llm` nhận `base_url` riêng |
| 11 | `db.py` | `get_turns_to_embed` dùng công thức `total - window_size` — sai vì `total` không giảm sau khi mark embedded, dẫn tới lôi nhầm turn còn trong window ra ngoài ở lần gọi thứ 2 trở đi | Dùng `boundary_id` qua `ORDER BY id DESC LIMIT 1 OFFSET window_size-1`, so sánh `id < boundary_id` |
| 12 | `embedder.py` (bản đầu) | Có tham số `query_prefix`/`document_prefix` — thừa vì `bge-m3` không cần prefix (khác `nomic-embed-text`) | Bỏ hẳn tham số, `embed()` chỉ nhận `input` |

---

## 6. Việc còn lại

### Phase 4 — `memory_service.py` (đang làm)

- [ ] `get_context(user_text) -> dict{profile, facts, recent_turns}`
- [ ] `record_turn(role, content, session_id)` — gọi `db.insert_turn` + `_flush_aging_turns`
- [ ] `_flush_aging_turns(session_id)` — `db.get_turns_to_embed` → `store.add_fact` → `db.mark_turns_embedded`
- [ ] `build_system_prompt(persona, context)` — ghép persona + profile + block "Ký ức liên quan" (tách rõ heading để model không nhầm ký ức với hội thoại hiện tại)
- [ ] Test: window trượt đúng qua nhiều chu kỳ ghi turn liên tục (không chỉ test tĩnh 1 lần)

### Phase 5 — Audio layer

- [ ] `audio/asr.py` — port logic Groq/faster-whisper từ `main_chat_v9.py` gốc
- [ ] `audio/tts.py` — port logic GPT-SoVITS ping + chunk-theo-dấu-câu (giữ nguyên cơ chế streaming TTS của bản gốc)

### Phase 6 — Avatar & actions

- [ ] `avatar/reactions.py` — port bảng mapping click_reactions.py (rule-based, không LLM, phản ứng tức thời)
- [ ] `avatar/actions.py` — map tool call từ Gemini (`perform_action`) sang animation file thật
- [ ] `avatar/playback_worker.py` — hàng đợi tuần tự, đảm bảo audio không chồng lấn giữa voice loop và click dispatcher

### Phase 7 — `turn_engine.py`

- [ ] Vòng lặp chính: `memory_service.get_context()` → `gemini.run_turn()` → stream qua `parse_text()` (generator, đã test) → text chunk đẩy TTS theo câu, tool_call đẩy `actions.execute()`
- [ ] Vòng `while` theo dõi `interaction_id` mới nhất khi có nhiều tool call nối tiếp trong 1 turn
- [ ] Sau turn: `memory_service.record_turn()` cho cả user và assistant

### Phase 8 — Bridge server + main loop

- [ ] `server/app.py` — giữ nguyên endpoint contract cũ, `pending_actions` qua SQLite thay vì list Python in-memory
- [ ] `main.py` — gọi `lifecycle.start_llm()` đầu chương trình (fail-fast nếu không lên), 2 thread (voice loop + click dispatcher) dùng chung 1 Lock quanh phần ghi memory, `lifecycle.end_llm()` trong `finally`

### Phase 9 — Test tổng + cutover

- [ ] End-to-end 20-30 lượt thật, kiểm tra `memory.db` + hybrid index tăng đúng
- [ ] Test avatar phản ứng đúng khi model gọi tool
- [ ] Test restart giữa chừng — `pending_actions` không mất, LM Studio tự start lại đúng

---

## 7. Quyết định còn để ngỏ (chưa chốt, cần quyết định khi đến phase liên quan)

- Trigger `maybe_summarize()` cho `profile.summary`: theo số turn cố định hay theo gap thời gian (session mới)? — chưa chọn.
- `set_profile_summary` giữ lịch sử (INSERT) hay chỉ giữ bản mới nhất (UPDATE/REPLACE)? — hiện đang INSERT, cần chủ động quyết định trước khi bảng phình quá lớn.
- Field `"result"` trong `function_result` — đã test pass với format `[{"type": "text", "text": ...}]`, nhưng doc Beta có 1 số ví dụ khác dùng dict thô — nếu sau này gặp lỗi 400 tương tự ở use case khác, đọc message lỗi trước khi đoán lại.