from sqlalchemy.orm import Session, joinedload
from app.models.models import Quiz, Question, Option, QuizAttempt, UserAnswer
from app.schemas.quiz_schemas import QuizSubmitRequest
from datetime import datetime

class QuizService:

    @staticmethod
    def save_generated_quiz_to_db(db: Session, quiz_json: dict, document_id: int, user_id: int):
        try:
            
            estimated_time = QuizService.calculate_estimated_time(quiz_json)
            new_quiz = Quiz(
                document_id=document_id,
                creator_id=user_id,
                title= quiz_json.get("quiz_title", "New quiz"),
                description= quiz_json.get("quiz_description"),
                difficulty=quiz_json.get("difficulty", "MEDIUM").upper(),
                estimated_time = estimated_time,
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
        
    @staticmethod
    def get_quiz_detail(
            db: Session,
            quiz_id: int
    ):
        quiz = db.query(Quiz).options(
            joinedload(Quiz.questions).joinedload(Question.options)
        ).filter(Quiz.quiz_id== quiz_id, Quiz.is_deleted== False).first()

        return quiz
    
    @staticmethod
    def calculate_estimated_time(quiz_json: dict):
        num_questions = len(quiz_json.get("questions", []))
        difficulty = quiz_json.get("difficulty", "MEDIUM").upper()

        time_map = {
            "EASY": 1,
            "MEDIUM": 1.5,
            "HARD": 2
        }

        per_question_time = time_map.get(difficulty, 1.5)
        total_estimated_minutes = int(num_questions * per_question_time)
        if(total_estimated_minutes == 0 and num_questions > 0):
            total_estimated_minutes = 1

        return total_estimated_minutes       


    @staticmethod
    def submit_quiz_logic(db: Session, quiz_id :int, user_id, submission: QuizSubmitRequest):
        quiz = QuizService.get_quiz_detail(db, quiz_id)
        if not quiz:
            return None
        
        attempt = QuizAttempt(
            user_id= user_id,
            quiz_id=quiz_id,
            status = 'COMPLETED',
            started_at = datetime.now(),
            completed_at = datetime.now()
        )

        db.add(attempt)
        db.flush()

        correct_count =0
        total_questions = len(quiz.questions)
        result_detail=[]

        correct_map={}
        for q in quiz.questions:
            for option in q.options:
                if option.is_correct:
                    correct_map[q.question_id] = option.option_id

        user_answers_dict = {
            a.question_id : a.selected_option_id for a in submission.answers
        }

        for question in quiz.questions:
            user_opt_id = user_answers_dict.get(question.question_id)
            correct_opt_id = correct_map.get(question.question_id)
            is_correct =(user_opt_id== correct_opt_id)

            if is_correct:
                correct_count += 1

            user_ans_record = UserAnswer(
                attempt_id = attempt.attempt_id,
                question_id=question.question_id,
                selected_option_id = user_opt_id,
                score_obtained = 1.0 if is_correct else 0.0
            )
            db.add(user_ans_record)

            result_detail.append({
                "question_id": question.question_id,
                "is_correct": is_correct,
                "user_selected_option_id": user_opt_id,
                "correct_option_id": correct_opt_id,
                "explanation": question.explanation
            })

        final_score = round((correct_count / total_questions) * 10, 2) if total_questions > 0 else 0
        attempt.score = final_score

        if final_score > quiz.max_grade:
            quiz.max_grade = final_score

        db.commit()

        return {
            "attempt_id": attempt.attempt_id,
            "score": final_score,
            "total_questions": total_questions,
            "correct_answers": correct_count,
            "result": result_detail
        }



        