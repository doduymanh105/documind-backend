import os
import asyncio
import json
import re
import google.generativeai as genai
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
from sentence_transformers import SentenceTransformer



GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)

BASE_STORAGE_DIR = "./lightrag_storage"


print("Loading local embedding")
embed_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
print("finish loading")

# force embedmodel encoding to another thread
async def local_embedding(texts: list[str]):
    return await asyncio.to_thread(embed_model.encode, texts)

# make request to GEMINI like a queue
gemini_semaphore = asyncio.Semaphore(1)

async def gemini_complete(prompt, system_prompt=None, history_messages=[], **kwargs):
    async with gemini_semaphore:
        
        kwargs.pop("model", None)
        kwargs.pop("response_format", None)
        
        print(f"[Gemini] waiting 5 seconds")
        await asyncio.sleep(5) 

        model = genai.GenerativeModel(
            model_name="gemini-2.5-flash",
            system_instruction=system_prompt if system_prompt else "Bạn là một chuyên gia hỗ trợ học tập."
        )

        try:
            response = await model.generate_content_async(prompt)
            return response.text
        except Exception as e:
            print(f"[GEMINI ERROR]: {e}")
            return f"Error from Gemini: {str(e)}"


def get_rag_engine(document_id: int) -> LightRAG:
    doc_dir = os.path.join(BASE_STORAGE_DIR, f"doc_{document_id}")
    os.makedirs(doc_dir, exist_ok=True)
    
    return LightRAG(
        working_dir=doc_dir,
        llm_model_func=gemini_complete,
        chunk_token_size=800,           
        chunk_overlap_token_size=100,
        embedding_func=EmbeddingFunc(
            embedding_dim=384,
            max_token_size=512,
            func=local_embedding
        )
    )

async def process_text_into_knowledge_graph(text: str, document_id: int):
    print(f"\n [GEMINI + LOCAL] processing document ID: {document_id}...")
    rag_engine = get_rag_engine(document_id)
    try:
        await rag_engine.initialize_storages()
        await rag_engine.ainsert(text)
        print(f"[SUCCESS] building KG document ID: {document_id}")
    except Exception as e:
        print(f"[INSERT ERROR]: {e}")
        raise e 

async def generate_quiz_from_rag(document_id: int, num_questions: int = 10, difficulty: str ="MEDIUM"):
    difficulty = difficulty.upper()
    # prompt = f"""[Lý thuyết, khái niệm, định nghĩa, đặc điểm, nội dung bài học, thuật toán, code]
    
    # Dựa trên tài liệu, hãy tạo ra {num_questions} câu hỏi trắc nghiệm.
    # Yêu cầu định dạng JSON BẮT BUỘC:
    # {{
    #   "quiz_title": "Tiêu đề bài trắc nghiệm",
    #   "quiz_description": "Mô tả ngắn gọn",
    #   "difficulty": "{difficulty}", 
    #   "questions": [
    #     {{
    #       "content": "Nội dung câu hỏi?",
    #       "explanation": "Giải thích chi tiết",
    #       "options": ["Lựa chọn 1", "Lựa chọn 2", "Lựa chọn 3", "Lựa chọn 4"],
    #       "correct_index": 0
    #     }}
    #   ]
    # }}
    # Lưu ý: Không thêm tiền tố A, B, C, D vào các lựa chọn."""

    prompt = f"""[Theory, concepts, definitions, characteristics, lesson content, algorithms, code]
    
    Based on the document, please generate {num_questions} multiple-choice questions.
    STRICT JSON FORMAT REQUIRED:
    {{
      "quiz_title": "Quiz title",
      "quiz_description": "Brief description",
      "difficulty": "{difficulty}", 
      "questions": [
        {{
          "content": "Question content?",
          "explanation": "Detailed explanation",
          "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
          "correct_index": 0
        }}
      ]
    }}
    Note: Do not add A, B, C, D prefixes to the options."""

    rag_engine = get_rag_engine(document_id)
    try:
        await rag_engine.initialize_storages()
        
        result = await rag_engine.aquery(prompt, param=QueryParam(mode="naive"))
        
        print(f"DEBUG - AI Result: {result}")

        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            clean_json = json_match.group(0)
            return json.loads(clean_json)
        else:
            return {"error": "AI not return JSON ", "raw": result}
            
    except Exception as e:
        print(f"[CREATING QUIZ ERROR]: {e}")
        return {"error": str(e)}
    
async def generate_summary_from_rag(document_id: int):

    universal_query = "Introduction, Overview, Main Concepts, Important Data, Core Content, Conclusion, Summary."

    # 2. LỆNH CHO LLM: Ngắn gọn, không rườm rà
    llm_instruction = """
    Task: Based on the retrieved context, summarize the document.
    Format requirements:
    1. Strictly use Markdown.
    2. Use '##' for headings.
    3. Use '-' for bullets.
    """

    # Gộp 2 phần lại
    prompt = f"{universal_query}\n\n{llm_instruction}"
    rag_engine = get_rag_engine(document_id)
    await rag_engine.initialize_storages()

    # Nhớ dùng aquery vì hàm này là async
    result = await rag_engine.aquery(prompt, param=QueryParam(mode="naive"))
    clean_markdown = result.strip()

    # Vẫn giữ lại bộ Regex phòng thủ trường hợp AI "tăng động" tự bọc code block
    clean_markdown = re.sub(r"(?i)^```markdown\n", "", clean_markdown) 
    clean_markdown = re.sub(r"^```\n", "", clean_markdown)
    clean_markdown = re.sub(r"\n```$", "", clean_markdown)

    return clean_markdown



        