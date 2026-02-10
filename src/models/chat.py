"""
Доменная модель чата для мониторинга.

Использует dataclass из стандартной библиотеки.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Chat:
    """
    Неизменяемая модель Telegram-чата.
    
    Attributes:
        id: Уникальный идентификатор чата в Telegram
        title: Название чата
        link: Ссылка на чат или его строковый идентификатор
        username: Username чата (для публичных чатов), опционально
        
    Example:
        >>> chat = Chat(
        ...     id=-1001234567890,
        ...     title="Python разработчики",
        ...     link="https://t.me/+zjMrnpvCxKthNDI6",
        ...     username="python_devs"
        ... )
    """
    
    id: int | str
    title: str
    link: str
    username: str | None = None
    
    def is_public(self) -> bool:
        """
        Проверяет, является ли чат публичным.
        
        Публичные чаты имеют username и доступны по прямой ссылке.
        
        Returns:
            True если чат публичный, False в противном случае
            
        Example:
            >>> chat.is_public()
            True
        """
        return self.username is not None
    
    def get_display_name(self) -> str:
        """
        Получить отображаемое имя чата для логирования.
        
        Использует username если доступен, иначе title.
        
        Returns:
            Отображаемое имя чата
            
        Example:
            >>> chat.get_display_name()
            '@python_devs'
        """
        if self.username:
            return f"@{self.username}"
        return self.title
    
    def __str__(self) -> str:
        """Человекочитаемое представление чата."""
        display = self.get_display_name()
        return f"Chat(id={self.id}, name={display})"
    
    def __repr__(self) -> str:
        """Техническое представление для отладки."""
        return (
            f"Chat(id={self.id}, title='{self.title}', "
            f"link='{self.link}', username={self.username})"
        )
