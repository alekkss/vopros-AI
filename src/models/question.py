"""
Доменная модель вопроса из Telegram-чата.

Использует dataclass из стандартной библиотеки.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Question:
    """
    Неизменяемая модель вопроса из Telegram-чата.
    
    Attributes:
        text: Текст вопроса
        sender_name: Имя отправителя
        sender_id: Telegram ID отправителя
        message_id: ID сообщения в Telegram
        chat_id: ID чата, из которого вопрос
        chat_title: Название чата
        date: Дата и время отправки сообщения
        
    Example:
        >>> question = Question(
        ...     text="Как настроить Python окружение?",
        ...     sender_name="Александр",
        ...     sender_id=123456789,
        ...     message_id=987654321,
        ...     chat_id=-1001234567890,
        ...     chat_title="Python чат",
        ...     date=datetime.now()
        ... )
    """
    
    text: str
    sender_name: str
    sender_id: int
    message_id: int
    chat_id: int | str
    chat_title: str
    date: datetime
    
    def format_for_bot(self) -> str:
        """
        Форматирует вопрос для отправки в Telegram-бот.
        
        Создает читаемое сообщение с информацией о вопросе,
        авторе и источнике.
        
        Returns:
            Отформатированное сообщение для бота
            
        Example:
            >>> question.format_for_bot()
            '📝 Новый вопрос из чата "Python чат"\\n\\n...'
        """
        formatted_date = self.date.strftime("%d.%m.%Y %H:%M")
        
        message_parts = [
            f"📝 <b>Новый вопрос из чата</b> \"{self.chat_title}\"",
            "",
            f"<b>Автор:</b> {self.sender_name}",
            f"<b>Дата:</b> {formatted_date}",
            "",
            f"<b>Вопрос:</b>",
            f"{self.text}",
            "",
            f"<i>Chat ID: {self.chat_id} | Message ID: {self.message_id}</i>",
        ]
        
        return "\n".join(message_parts)
    
    def get_short_preview(self, max_length: int = 50) -> str:
        """
        Получить краткое превью вопроса для логирования.
        
        Args:
            max_length: Максимальная длина превью
            
        Returns:
            Обрезанный текст вопроса с многоточием
            
        Example:
            >>> question.get_short_preview(20)
            'Как настроить Pytho...'
        """
        if len(self.text) <= max_length:
            return self.text
        return self.text[:max_length] + "..."
    
    def __str__(self) -> str:
        """Человекочитаемое представление вопроса."""
        preview = self.get_short_preview(60)
        return f"Question(from={self.sender_name}, chat={self.chat_title}, text='{preview}')"
