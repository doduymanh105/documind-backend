import os
import asyncio
import json
import re
from lightrag import LightRAG, QueryParam
from lightrag.utils import EmbeddingFunc
from sentence_transformers import SentenceTransformer
from fastapi import HTTPException
from openai import AsyncOpenAI


openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

BASE_STORAGE_DIR = "./lightrag_storage"


print("Loading local embedding")
embed_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
print("finish loading")

# force embedmodel encoding to another thread
async def local_embedding(texts: list[str]):
    return await asyncio.to_thread(embed_model.encode, texts)

async def openai_llm_complete(prompt, system_prompt=None, history_messages=[], **kwargs) -> str:
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history_messages:
        messages.extend(history_messages)
    messages.append({"role": "user", "content": prompt})

    temp = kwargs.pop("temperature", 0.7)
    junk_args = ["hashing_kv", "enable_cot", "response_format", "keyword_extraction"] 
    for arg in junk_args:
        kwargs.pop(arg, None)

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=temp,
            **kwargs
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"[OPENAI ERROR]: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi AI (OpenAI): {str(e)}")

def get_rag_engine(document_id: int) -> LightRAG:
    doc_dir = os.path.join(BASE_STORAGE_DIR, f"doc_{document_id}")
    os.makedirs(doc_dir, exist_ok=True)
    
    return LightRAG(
        working_dir=doc_dir,
        llm_model_func=openai_llm_complete,
        chunk_token_size=800,           
        chunk_overlap_token_size=100,
        embedding_func=EmbeddingFunc(
            embedding_dim=384,
            max_token_size=512,
            func=local_embedding
        )
    )

async def process_text_into_knowledge_graph(text: str, document_id: int):
    print(f"\n[GPT-4o-MINI + LOCAL] Processing document ID: {document_id}...")    
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
        raise HTTPException(status_code=500, detail="Internal ERROR when creating Quiz.")
    
async def generate_summary_from_rag(document_id: int):
    query = """
    A comprehensive overview and synthesis of the document's main arguments, 
    core methodology, significant findings, and concluding insights. 
    Search for the most semantically rich segments that define the overall purpose.
    """

    llm_instruction = """
    Role: Senior Research Analyst.
    Task: Synthesize a high-level Executive Summary.

    Structure:
    - ## Executive Overview: A brief 2-3 sentence introduction.
    - ## Key Pillars & Findings: Use bullet points to highlight the most critical insights.
    - ## Final Synthesis: A concluding paragraph on the document's overall impact or takeaway.

    Tone: Professional, academic, and objective. 
    Language: English.
    """

    rag_engine = get_rag_engine(document_id)
    await rag_engine.initialize_storages()

    try:
        result = await rag_engine.aquery(
            query, 
            param=QueryParam(
                mode="hybrid",         
                top_k=20,               
                response_type=llm_instruction,
                only_need_context=False,
                enable_rerank=False
            )
        )
    except Exception as e:
        print(f"Primary query error: {e}")
        result = None

    # Fallback: Nếu kết quả rỗng hoặc báo "No relevant"
    if not result or "No relevant" in str(result):
        print(f"Switching to Naive mode fallback for document: {document_id}")
        
        result = await rag_engine.aquery(
            " ", 
            param=QueryParam(
                mode="naive", 
                top_k=5,
                response_type=llm_instruction
            )
        )
        
    if result is None:
        print("Lỗi: AI không trả về kết quả sau khi fallback.")
        return "Sorry, I couldn't generate a summary because the AI service failed."

  
    clean_markdown = str(result).strip()
    clean_markdown = re.sub(r"(?i)^```markdown\n", "", clean_markdown) 
    clean_markdown = re.sub(r"^```\n", "", clean_markdown)
    clean_markdown = re.sub(r"\n```$", "", clean_markdown)

    return clean_markdown


async def generate_single_essay_question(document_id: int):
    query = "What is the most central and complex topic in this document that would be suitable for an academic essay?"

    llm_instruction = """
    Role: Senior University Professor.
    Task: Create EXACTLY ONE high-quality essay assignment based on the provided context.
    
    Structure your response as a JSON object:
    - 'essay_title': A professional academic title.
    - 'quick_explanation': A 1-sentence summary of the essay's core objective.
    - 'essay_content': The actual detailed essay prompt/question.
    - 'max_grade': 0.0

    Return ONLY the JSON object.
    """

    rag_engine = get_rag_engine(document_id)
    await rag_engine.initialize_storages()

    try:
        result = await rag_engine.aquery(
            query, 
            param=QueryParam(
                mode="hybrid", 
                response_type=llm_instruction,
                enable_rerank=False
            )
        )
        
        import json, re
        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        return None
    except Exception as e:
        print(f"RAG Error: {e}")
        return None
    
async def evaluate_essay_submission(essay_question: str, user_answer: str, context: str):
    prompt = f"""
    Role: Academic Professor.
    Context: {context}
    Question: {essay_question}
    Student Answer: {user_answer}
    
    Task: Grade the essay (0-100) and provide structured feedback.
    
    Return ONLY a JSON object:
    {{
      "score": float,
      "strengths": "A SINGLE STRING with Markdown bullet points (e.g., '- Point 1\\n- Point 2')",
      "growth_points": "A SINGLE STRING with Markdown bullet points",
      "enhancement": "A detailed Markdown section including specific advice and some rewritten sentence to enhance the point."
    }}
    """
    
    result = await openai_llm_complete(prompt)
    return json.loads(re.search(r'\{.*\}', result, re.DOTALL).group(0))


# async def generate_mindmap_from_rag(document_id: int):
#     prompt = """
#     Create a Mindmap in JSON format summarizing the document.
#     Structure: {"name": "Root Topic", "children": [{"name": "Subtopic", "children": []}]}
#     Return ONLY the JSON object, no markdown.
#     """
#     rag_engine = get_rag_engine(document_id)
#     await rag_engine.initialize_storages()
    
#     try:
#         result = await rag_engine.aquery(prompt, param=QueryParam(mode="naive"))
        
#         json_match = re.search(r'\{.*\}', result, re.DOTALL)
#         if json_match:
#             return json.loads(json_match.group(0))
#         return None
#     except Exception as e:
#         print(f"[MINDMAP ERROR]: {e}")
#         return None

async def generate_mindmap_from_rag(document_id: int):
    prompt = "Create a Mindmap in JSON format summarizing the main concepts of this document. Structure: {'name': '...', 'children': []}"
    
    rag_engine = get_rag_engine(document_id)
    await rag_engine.initialize_storages()
    
    try:
        # Hạ thấp threshold (độ tương đồng) xuống để nó chịu bốc dữ liệu
        result = await rag_engine.aquery(
            prompt, 
            param=QueryParam(
                mode="naive", 
                # Nếu tài liệu quá ngắn, đôi khi phải ép nó lấy chunk đầu tiên
                top_k=5,
                # Sếp có thể thử bỏ qua threshold nếu cần
            )
        )
        
        # Log ra để sếp debug cho dễ
        print(f"AI Output: {result}")

        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        
        # Nếu vẫn không ra JSON, thử gọi query 1 lần nữa với prompt đơn giản hơn
        return None
    except Exception as e:
        print(f"RAG Error: {e}")
        return None


        