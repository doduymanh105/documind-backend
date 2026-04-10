from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, Float, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base 


class User(Base):
    __tablename__ = "users"
    
    user_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hashed = Column(String(255), nullable=False)
    avatar_url = Column(Text, nullable=True)
    role = Column(Enum('USER', 'ADMIN', name='user_roles'), default='USER')
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    documents = relationship("UserDocument", back_populates="owner")
    quiz_attempts = relationship("QuizAttempt", back_populates="user")
    created_quizzes = relationship("Quiz", back_populates="creator")

class UserDocument(Base):
    __tablename__ = "user_documents"
    
    document_id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    file_name = Column(String(255), nullable=False)
    document_url = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    size = Column(BigInteger, nullable=True)
    summary = Column(Text, nullable=True)
    processing_status = Column(String, default="PENDING")
    last_accessed_at = Column(DateTime, default=None, nullable=True)

    # Relationships
    owner = relationship("User", back_populates="documents")
    quizzes = relationship("Quiz", back_populates="document")
    mindmaps = relationship("Mindmap", back_populates="document")
    essays = relationship("Essay", back_populates="document")

class Mindmap(Base):
    __tablename__ = "mindmaps"
    
    mindmap_id = Column(BigInteger, primary_key=True, index=True)
    document_id = Column(BigInteger, ForeignKey("user_documents.document_id", ondelete="CASCADE"))
    title = Column(String(255), nullable=True)
    structure_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    document = relationship("UserDocument", back_populates="mindmaps")

class Quiz(Base):
    __tablename__ = "quizzes"
    
    quiz_id = Column(BigInteger, primary_key=True, index=True)
    document_id = Column(BigInteger, ForeignKey("user_documents.document_id", ondelete="SET NULL"), nullable=True)
    creator_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    difficulty = Column(Enum('EASY', 'MEDIUM', 'HARD', name='quiz_difficulty'), default='MEDIUM')
    estimated_time = Column(Integer, nullable=True)
    is_deleted = Column(Boolean, default=False)
    max_grade = Column(Float, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    document = relationship("UserDocument", back_populates="quizzes")
    creator = relationship("User", back_populates="created_quizzes")
    questions = relationship("Question", back_populates="quiz", cascade="all, delete-orphan")
    attempts = relationship("QuizAttempt", back_populates="quiz")

class Question(Base):
    __tablename__ = "questions"
    
    question_id = Column(BigInteger, primary_key=True, index=True)
    quiz_id = Column(BigInteger, ForeignKey("quizzes.quiz_id", ondelete="CASCADE"))
    content = Column(Text, nullable=False)
    question_type = Column(Enum('MULTIPLE_CHOICE', 'ESSAY', name='question_types'), nullable=False)
    explanation = Column(Text, nullable=True)
    order_index = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    quiz = relationship("Quiz", back_populates="questions")
    options = relationship("Option", back_populates="question", cascade="all, delete-orphan")
    user_answers = relationship("UserAnswer", back_populates="question")

class Option(Base):
    __tablename__ = "options"
    
    option_id = Column(BigInteger, primary_key=True, index=True)
    question_id = Column(BigInteger, ForeignKey("questions.question_id", ondelete="CASCADE"))
    content = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)

    # Relationships
    question = relationship("Question", back_populates="options")
    user_answers = relationship("UserAnswer", back_populates="selected_option")

class Essay(Base):
    __tablename__ = "essays"
    
    essay_id = Column(BigInteger, primary_key=True, index=True)
    document_id = Column(BigInteger, ForeignKey("user_documents.document_id", ondelete="CASCADE"))
    essay_title = Column(String(255), nullable=False)
    quick_explanation = Column(Text, nullable=True)
    essay_content = Column(Text, nullable=False)
    max_grade = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Relationships
    document = relationship("UserDocument", back_populates="essays")
    attempts = relationship("QuizAttempt", back_populates="essay")
    user_essay_answers = relationship("UserEssayAnswer", back_populates="essay")

class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    
    attempt_id = Column(BigInteger, primary_key=True, index=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"))
    quiz_id = Column(BigInteger, ForeignKey("quizzes.quiz_id", ondelete="CASCADE"), nullable=True)
    essay_id = Column(BigInteger, ForeignKey("essays.essay_id", ondelete="CASCADE"), nullable=True)
    score = Column(Float, nullable=True)
    status = Column(Enum('NOT_START', 'IN_PROGRESS', 'COMPLETED', name='attempt_status'), default='NOT_START')
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", back_populates="quiz_attempts")
    quiz = relationship("Quiz", back_populates="attempts")
    essay = relationship("Essay", back_populates="attempts")
    user_answers = relationship("UserAnswer", back_populates="attempt", cascade="all, delete-orphan")
    essay_answers = relationship("UserEssayAnswer", back_populates="attempt", cascade="all, delete-orphan")

class UserAnswer(Base):
    __tablename__ = "user_answers"
    
    answer_id = Column(BigInteger, primary_key=True, index=True)
    attempt_id = Column(BigInteger, ForeignKey("quiz_attempts.attempt_id", ondelete="CASCADE"))
    question_id = Column(BigInteger, ForeignKey("questions.question_id", ondelete="CASCADE"))
    selected_option_id = Column(BigInteger, ForeignKey("options.option_id", ondelete="SET NULL"), nullable=True)
    text_answer = Column(Text, nullable=True)
    score_obtained = Column(Float, nullable=True)
    ai_feedback = Column(Text, nullable=True)

    # Relationships
    attempt = relationship("QuizAttempt", back_populates="user_answers")
    question = relationship("Question", back_populates="user_answers")
    selected_option = relationship("Option", back_populates="user_answers")

class UserEssayAnswer(Base):
    __tablename__ = "user_essay_answers"
    
    essay_answer_id = Column(BigInteger, primary_key=True, index=True)
    attempt_id = Column(BigInteger, ForeignKey("quiz_attempts.attempt_id", ondelete="CASCADE"))
    essay_id = Column(BigInteger, ForeignKey("essays.essay_id", ondelete="CASCADE"))
    text_answer = Column(Text, nullable=True)
    score_obtained = Column(Float, nullable=True)

    feedb_strength = Column(Text, nullable=True)
    pointforgrow = Column(Text, nullable=True)
    suggest_enhancemance = Column(Text, nullable=True)

    ai_feedback = Column(Text, nullable=True)

    # Relationships
    attempt = relationship("QuizAttempt", back_populates="essay_answers")
    essay = relationship("Essay", back_populates="user_essay_answers")