from sqlalchemy.orm import Session
from app.models.models import Quiz, Question, Option

def save_generated_quiz_to_db(db: Session, quiz_json: dict, document_id: int, user_id: int):
    try:


        new_quiz = Quiz(
            document_id=document_id,
            creator_id=user_id,
            title= quiz_json.get("quiz_title", "New quiz"),
            description= quiz_json.get("quiz_description"),
            difficulty=quiz_json.get("difficulty", "MEDIUM").upper(),
            max_grade=0.0
        )
        db.add(new_quiz)
        db.flush()

        for index, q_data in enumerate(quiz_json.get("questions",[])):
            new_question = Question(
                quiz_id = new_quiz.quiz_id,
                content = q_data["content"],
                question_type="MULTIPLE_CHOICE",
                explanation=q_data.get("explanation"),
                order_index=index +1
            )
            db.add(new_question)
            db.flush()

            option_correct_index = q_data.get("correct_index")

            for option_index, option_text in enumerate(q_data["options"]):
                new_option = Option(
                    question_id= new_question.question_id,
                    content=option_text,
                    is_correct=(option_index== option_correct_index)
                )
                db.add(new_option)

        db.commit()
        db.refresh(new_quiz)
        return new_quiz
    except Exception as e:
        db.rollback()
        print(f"ERROR when saving new quiz: {e}")
        raise e