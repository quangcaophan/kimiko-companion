from openai import OpenAI



class LMStudioEmbedder:
    def __init__(self, base_url, model):
        self.client = OpenAI(base_url=base_url, api_key="lm-studio", timeout=60.0)
        self.model = model

    def embed(self, input):
        is_list = isinstance(input, list)
        texts = input if is_list else [input]
        response = self.client.embeddings.create(model=self.model, input=texts)
        embeddings = [d.embedding for d in response.data]
        return embeddings if is_list else embeddings[0]


# --- Chạy test 1 lần duy nhất ---
# from core.memory.lifecycle import *

# server_ready = start_llm(BASE_URL)
# embedder = LMStudioEmbedder(base_url=BASE_URL, model='text-embedding-bge-m3')

# try:
#     if server_ready:
#         models = embedder.client.models.list()
#         print("✅ Kết nối OK. Model đang load:", [m.id for m in models.data])
#     else:
#         print("❌ Hết thời gian chờ! Hãy kiểm tra xem lms CLI có hoạt động không.")
# except Exception as e:
#     print("❌ Lỗi trong quá trình tương tác:", repr(e))
# finally:
#     end_llm()