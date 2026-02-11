"""
Доменная модель отправленного вопроса для БД.

Использует dataclass из стандартной библиотеки.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SentQuestion:
    """
    Неизменяемая модель отправленного вопроса.
    
    Используется для отслеживания уже отправленных в бот вопросов,
    чтобы избежать дубликатов.
    
    Attributes:
        chat_id: ID чата, из которого был вопрос
        message_id: ID сообщения в чате
        question_hash: SHA256 хэш текста вопроса (для дополнительной проверки)
        sent_at: Дата и время отправки в бот
        
    Example:
        >>> from datetime import datetime
        >>> sent = SentQuestion(
        ...     chat_id=-1001234567890,
        ...     message_id=12345,
        ...     question_hash="abc123...",
        ...     sent_at=datetime.now()
        ... )
    """
    
    chat_id: int | str
    message_id: int
    question_hash: str
    sent_at: datetime
    
    @staticmethod
    def compute_hash(text: str) -> str:
        """
        Вычислить SHA256 хэш текста вопроса.
        
        Используется для создания уникального идентификатора текста.
        Это позволяет определить, был ли текст изменён после отправки.
        
        Args:
            text: Текст вопроса
            
        Returns:
            Hex-строка SHA256 хэша
            
        Example:
            >>> hash_value = SentQuestion.compute_hash("Как настроить Python?")
            >>> len(hash_value)
            64
        """
        import hashlib
        
        # Нормализуем текст: убираем пробелы по краям, приводим к lowercase
        normalized_text = text.strip().lower()
        
        # Вычисляем SHA256
        hash_object = hashlib.sha256(normalized_text.encode('utf-8'))
        
        return hash_object.hexdigest()
    
    def __str__(self) -> str:
        """Человекочитаемое представление."""
        return (
            f"SentQuestion(chat_id={self.chat_id}, "
            f"message_id={self.message_id}, "
            f"sent_at={self.sent_at.strftime('%Y-%m-%d %H:%M:%S')})"
        )
    
    def __repr__(self) -> str:
        """Техническое представление для отладки."""
        return (
            f"SentQuestion(chat_id={self.chat_id}, "
            f"message_id={self.message_id}, "
            f"question_hash='{self.question_hash[:8]}...', "
            f"sent_at={self.sent_at.isoformat()})"
        )