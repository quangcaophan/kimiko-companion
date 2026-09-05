| Thuộc tính (Property) | Kiểu dữ liệu (Type) | Giá trị mẫu từ Log | Mô tả chi tiết & Enum Values (Nếu có) |
| --- | --- | --- | --- |
| `object` | `String` | `'interaction'` | Loại object trả về. Với API này, nó luôn cố định là `'interaction'`. |
| `id` | `String` | `'v1_Chd4OGV...'` | ID duy nhất của lượt giao dịch này. **Rất quan trọng:** Dùng nó truyền vào `previous_interaction_id` ở lượt sau để giữ mạch hội thoại. |
| `status` | `Enum` | `'completed'` | Trạng thái của request. Các giá trị: <br>- `completed`: Xong thành công.<br>- `in_progress`: Đang xử lý.<br>- `failed`: Lỗi hoặc bị hủy. |
| `model` | `String` | `'gemini-2.5-flash'` | Tên phiên bản mô hình ngôn ngữ đang được sử dụng. (VD: `gemini-2.5-flash`, `gemini-3.5-pro`). |
| `created` | `String` | `'2026-08-30T06:03:51Z'` | Dấu thời gian (Timestamp chuẩn ISO 8601) lúc request được tạo ra. |
| `updated` | `String` | `'2026-08-30T06:03:51Z'` | Dấu thời gian lúc request hoàn tất hoặc được cập nhật lần cuối. |
| `service_tier` | `Enum` | `'standard'` | Cấp độ dịch vụ API. Các giá trị: <br>- `standard`: Mặc định/Miễn phí.<br>- `pro`: Trả phí theo gói (ít bị nghẽn, tốc độ cao). |
| `usage` | `Object` | `Usage(...)` | Object chứa chi tiết tiêu thụ Token. Bao gồm các trường con quan trọng: `total_tokens`, `input_tokens`, `output_tokens`, và `thought_tokens` (token AI tự suy nghĩ ngầm). |
| `steps` | `Array` | `[ThoughtStep, ModelOutputStep]` | Danh sách diễn biến quá trình AI xử lý. Các loại Step Enum: <br>- `ThoughtStep`: Suy nghĩ ngầm của AI.<br>- `ModelOutputStep`: Sinh ra câu trả lời.<br>- `ToolCallStep`: Kích hoạt function/công cụ. |
| `output_text` | `String` | `'Hello!\n\nAs an AI...'` | Nội dung văn bản cuối cùng AI trả về cho người dùng. (Dùng để đưa vào ElevenLabs/TTS). |
| `output_image` | `Object` | `None` | Chứa dữ liệu ảnh nếu AI sinh ra ảnh (hiện tại là None vì bạn chỉ chat text). |
| `output_audio` | `Object` | `None` | Chứa dữ liệu âm thanh nếu bạn dùng model hỗ trợ sinh audio. |
| `output_video` | `Object` | `None` | Chứa dữ liệu video (hiện tại rất hiếm khi được trả về trực tiếp). |
| `agent` | `Object` | `None` | Thông tin Agent (nếu bạn khai báo AI này thuộc một Agent cụ thể trên hệ thống). |
| `system_instruction` | `String` | `None` | Nội dung System Prompt (Tính cách Riko/Neuro-sama) nếu bạn có gửi kèm trong request này. |
| `tools` | `Array` | `None` | Danh sách các function/công cụ (Function Calling) mà AI có quyền sử dụng trong lượt chat này. |
| `previous_interaction_id` | `String` | `None` | Chứa ID của lượt chat trước đó nếu bạn có nối chuỗi (hiện là None vì đây có thể là câu chat đầu tiên). |
| `response_modalities` | `Array` | `None` | Yêu cầu ép AI trả về định dạng nào (Ví dụ: ép chỉ trả về `['TEXT']` hoặc `['AUDIO']`). |
| `response_mime_type` | `String` | `None` | Ép kiểu dữ liệu (Ví dụ: `application/json` nếu muốn AI chỉ trả ra file JSON chuẩn). |
| `response_format` | `Object` | `None` | Định nghĩa schema JSON cấu trúc (Structured Output) nếu muốn AI trả về data định dạng nghiêm ngặt. |
| `generation_config` | `Object` | `None` | Các cài đặt tinh chỉnh bộ não AI như: `temperature` (độ ngẫu nhiên), `top_p`, `top_k`, `max_output_tokens`. |
| `safety_settings` | `Array` | `None` | Cấu hình mức độ kiểm duyệt (chặn nội dung bạo lực, 18+...). |
| `input` | `String` | `None` | Text đầu vào của người dùng. |
| `environment_id` | `String` | `None` | Mã định danh môi trường nếu bạn set up (vd: dev, prod). |
| `environment` | `Object` | `None` | Object chi tiết về cấu hình môi trường. |
| `agent_config` | `Object` | `None` | Các cấu hình đặc thù dành riêng cho hệ thống Multi-Agent. |
| `webhook_config` | `Object` | `None` | Cấu hình Webhook URL nếu bạn muốn Google bắn kết quả về server của bạn thay vì đợi kết nối trực tiếp. |
| `labels` | `Dict` | `None` | Các tag/nhãn (Key-Value) tự do bạn gán vào để phân loại log chi phí trên Google Cloud. |

---

stream structure output sample

```markdown
InteractionCreatedEvent(event_type='interaction.created', interaction=Interaction(id='v1_Chd2U0tZYW9QcUllM2FnOFVQN1lfamtBbxIXdlNLWWFvUHFJZTNhZzhVUDdZX2prQW8', created=None, status='in_progress', steps=None, updated=None, agent=None, agent_config=None, environment=None, environment_id=None, input=None, model='gemini-3.5-flash-lite', previous_interaction_id=None, response_format=None, response_mime_type=None, response_modalities=None, role=None, service_tier=None, system_instruction=None, tools=None, usage=None, webhook_config=None, object='interaction'), event_id=None, metadata=None)

----------------------------------------

InteractionStatusUpdate(event_type='interaction.status_update', interaction_id='v1_Chd2U0tZYW9QcUllM2FnOFVQN1lfamtBbxIXdlNLWWFvUHFJZTNhZzhVUDdZX2prQW8', status='in_progress', event_id=None, metadata=None)

----------------------------------------

StepStart(event_type='step.start', index=0, step=ThoughtStep(type='thought', signature=None, summary=None), event_id=None, metadata=None)

----------------------------------------

StepDelta(delta=DeltaThoughtSignature(type='thought_signature', signature='El4KXAERTTIPgdC4BLweY6wTqR8kHviAWuHLKAG493JUbWWV/kw4qxUSa52m6pvUUln7Msky3qR3h0lX3uqc3t+fSx6tOqH8iA4Dqfly4HV5/H2M2Li58lRfEmkWFPGi'), event_type='step.delta', index=0, event_id=None, metadata=None)

----------------------------------------

StepStop(event_type='step.stop', index=0, event_id=None, metadata=None)

----------------------------------------

StepStart(event_type='step.start', index=1, step=ModelOutputStep(type='model_output', content=None), event_id=None, metadata=None)

----------------------------------------

StepDelta(delta=DeltaText(text='Chào bạn', type='text'), event_type='step.delta', index=1, event_id=None, metadata=None)

----------------------------------------

StepDelta(delta=DeltaText(text='! Riko rất sẵn lòng ạ. ✨', type='text'), event_type='step.delta', index=1, event_id=None, metadata=None)

----------------------------------------

StepStop(event_type='step.stop', index=1, event_id=None, metadata=None)

----------------------------------------

StepStart(event_type='step.start', index=2, step=ThoughtStep(type='thought', signature=None, summary=None), event_id=None, metadata=None)

----------------------------------------

StepDelta(delta=DeltaThoughtSignature(type='thought_signature', signature='El4KXAERTTIPZ+6H1DxNvKD6i+hXtL8sOVFt5M0cvmQs+bnlCCq90DzRNst4mBieU0Tv5FXd3CHc34gjx+8Wf6Wpnu8ZRirSQ/AEuxhu/LkZWVxYxonDGrk7ggg7JkkY'), event_type='step.delta', index=2, event_id=None, metadata=None)

----------------------------------------

StepStop(event_type='step.stop', index=2, event_id=None, metadata=None)

----------------------------------------

StepStart(event_type='step.start', index=3, step=FunctionCallStep(id='call_2455036', arguments={}, name='perform_action', type='function_call', signature=None), event_id=None, metadata=None)

----------------------------------------

StepDelta(delta=DeltaArgumentsDelta(type='arguments_delta', arguments='{"action":"wave"}'), event_type='step.delta', index=3, event_id=None, metadata=None)

----------------------------------------

StepStop(event_type='step.stop', index=3, event_id=None, metadata=None)

----------------------------------------

InteractionCompletedEvent(event_type='interaction.completed', interaction=Interaction(id='v1_Chd2U0tZYW9QcUllM2FnOFVQN1lfamtBbxIXdlNLWWFvUHFJZTNhZzhVUDdZX2prQW8', created=datetime.datetime(2026, 9, 2, 13, 21, 2, tzinfo=datetime.timezone.utc), status='requires_action', steps=None, updated=datetime.datetime(2026, 9, 2, 13, 21, 2, tzinfo=datetime.timezone.utc), agent=None, agent_config=None, environment=None, environment_id=None, input=None, model='gemini-3.5-flash-lite', previous_interaction_id=None, response_format=None, response_mime_type=None, response_modalities=None, role=None, service_tier='standard', system_instruction=None, tools=None, usage=Usage(cached_tokens_by_modality=None, grounding_tool_count=None, input_tokens_by_modality=[InputTokensByModality(modality='text', tokens=139)], output_tokens_by_modality=None, tool_use_tokens_by_modality=None, total_cached_tokens=0, total_input_tokens=139, total_output_tokens=27, total_thought_tokens=0, total_tokens=166, total_tool_use_tokens=0, raw_prompt_token=178), webhook_config=None, object='interaction'), event_id=None, metadata=None)

----------------------------------------
```