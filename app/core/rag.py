import os
import asyncio
import json
import re
import ast
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
        ),
        enable_llm_cache=False
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

    rag_engine = get_rag_engine(document_id)
    await rag_engine.initialize_storages()

    def has_no_context(text: str | None) -> bool:
        if not text:
            return True
        normalized = text.strip().lower()
        return any(
            phrase in normalized
            for phrase in [
                "no-context",
                "no relevant document chunks",
                "not able to provide an answer",
                "document content not available",
                "could not find",
                "no relevant"
            ]
        )

    context_query = "Tóm tắt các chủ đề chính và khái niệm chính từ tài liệu này."
    try:
        context_result = await rag_engine.aquery(
            context_query,
            param=QueryParam(mode="hybrid", top_k=20, chunk_top_k=20),
        )
        document_context = str(context_result).strip()
        if has_no_context(document_context):
            document_context = None
    except Exception:
        document_context = None

    if document_context:
        prompt = f"""[Theory, concepts, definitions, characteristics, lesson content, algorithms, code]

        Document Context: {document_context}

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
    else:
        prompt = f"""[Theory, concepts, definitions, characteristics, lesson content, algorithms, code]

        Please generate {num_questions} multiple-choice questions.
        Use document content if available, otherwise create a coherent quiz based on the topic.
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

    try:
        query_param = QueryParam(mode="naive", top_k=20, chunk_top_k=20)
        result = await rag_engine.aquery(prompt, param=query_param)

        print(f"DEBUG - AI Result: {result}")

        if has_no_context(result):
            print("Naive retrieval returned no relevant document chunks. Retrying with RAG-only strategy.")
            result = await rag_engine.aquery(
                prompt,
                param=QueryParam(mode="naive", top_k=10, chunk_top_k=10),
            )
            print(f"DEBUG - Naive retry result: {result}")

            if has_no_context(result):
                return {"error": "RAG retrieval failed, no relevant document chunks found", "raw": result}

        json_match = re.search(r'\{.*\}', result, re.DOTALL)
        if json_match:
            clean_json = json_match.group(0)
            parsed = json.loads(clean_json)
            if "difficulty" not in parsed:
                parsed["difficulty"] = difficulty
            else:
                parsed["difficulty"] = str(parsed["difficulty"]).upper()
            return parsed

        return {"error": "AI did not return JSON", "raw": result}
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
                enable_rerank=False,
            ),
        )
    except Exception as e:
        print(f"Primary query error: {e}")
        result = None

    if not result or "No relevant" in str(result):
        print(f"Switching to Naive mode fallback for document: {document_id}")
        result = await rag_engine.aquery(
            " ",
            param=QueryParam(
                mode="naive",
                top_k=5,
                response_type=llm_instruction,
            ),
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


async def generate_mindmap_from_rag(document_id: int):
    def has_no_context(text: str | None) -> bool:
        if not text:
            return True
        normalized = text.strip().lower()
        return any(
            phrase in normalized
            for phrase in [
                "no-context",
                "no relevant document chunks",
                "not able to provide an answer",
                "document content not available",
                "could not find",
                "no relevant"
            ]
        )

    rag_engine = get_rag_engine(document_id)
    await rag_engine.initialize_storages()

    context_prompt = "Tóm tắt các chủ đề chính và khái niệm chính từ tài liệu này."

    try:
        document_context = await rag_engine.aquery(
            context_prompt,
            param=QueryParam(mode="hybrid", top_k=20, chunk_top_k=20),
        )
        document_context = str(document_context).strip()
        if has_no_context(document_context):
            document_context = str(await rag_engine.aquery(
                context_prompt,
                param=QueryParam(mode="naive", top_k=20, chunk_top_k=20),
            )).strip()
        if has_no_context(document_context):
            document_context = None
    except Exception as e:
        print(f"Mindmap context retrieval error: {e}")
        document_context = None

    if document_context:
        prompt = f"""Based on the following document context, create a detailed mindmap in JSON format.

        Document Context: {document_context}

        Requirements:
        - Return ONLY JSON.
        - Exact structure: {{"name": "Root Topic", "children": [{{"name": "Subtopic", "children": []}}]}}
        - Include at least 3 levels of depth when possible.
        - For each main branch, include specific subpoints, examples, or supporting details as child nodes.
        - Output the mindmap in English.
        - No markdown, no explanation outside JSON.
        """

        try:
            result = await openai_llm_complete(prompt)
            print(f"Mindmap AI Output: {result}")
        except Exception as e:
            print(f"Mindmap generation error: {e}")
            return None

        if not result:
            print("No result from LLM")
            return None

        print(f"Raw result: '{result}'")
        print(f"Raw result repr: {repr(result)}")
        print(f"Length: {len(result)}")
        print(f"End: {repr(result[-10:])}")
        # Balance braces
        open_braces = result.count('{')
        close_braces = result.count('}')
        if close_braces > open_braces:
            extra = close_braces - open_braces
            for _ in range(extra):
                last = result.rfind('}')
                if last != -1:
                    result = result[:last] + result[last+1:]
        result = result.strip()

        try:
            mindmap_json = ast.literal_eval(result)
            print(f"Parsed mindmap: {mindmap_json}")
            return mindmap_json
        except Exception as e:
            print(f"JSON decode error: {e}")
            print(f"Result that failed: {repr(result)}")
            return None
    else:
        # Fallback without context
        prompt = """Create a detailed mindmap in JSON format about basic AI concepts.

        Requirements:
        - Return ONLY JSON.
        - Exact structure: {{"name": "Root Topic", "children": [{{"name": "Subtopic", "children": []}}]}}
        - Include at least 3 levels of depth, with specific subpoints under each main branch.
        - Output the mindmap in English.
        - No markdown, no explanation outside JSON.
        """

        try:
            result = await openai_llm_complete(prompt)
            print(f"Mindmap fallback output: {result}")
        except Exception as e:
            print(f"Mindmap fallback error: {e}")
            return None

        # Clean and parse JSON
        result = result.strip()
        if not result:
            return None

        # Balance braces if needed
        open_braces = result.count('{')
        close_braces = result.count('}')
        if close_braces > open_braces:
            extra = close_braces - open_braces
            for _ in range(extra):
                last = result.rfind('}')
                if last != -1:
                    result = result[:last] + result[last+1:]
        result = result.strip()

        try:
            mindmap_json = ast.literal_eval(result)
            return mindmap_json
        except Exception as e:
            print(f"JSON decode error: {e}")
            return None


        