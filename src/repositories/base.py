"""
Базовые интерфейсы для репозиториев.

Определяет контракты для работы с внешними источниками данных.
Следует принципу Dependency Inversion - зависимость от абстракций.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator

from src.models.chat import Chat
from src.models.question import Question


class BaseChatRepository(ABC):
    """
    Абстрактный репозиторий для работы с чатами.
    
    Определяет контракт для получения данных из чатов.
    Конкретные реализации могут использовать Telegram API,
    mock-данные для тестов или любой другой источник.
    
    Следует Interface Segregation Principle - минимальный
    необходимый набор методов для работы с чатами.
    """
    
    @abstractmethod
    async def get_chat_info(self, chat_link: str) -> Chat:
        """
        Получить информацию о чате.
        
        Args:
            chat_link: Ссылка на чат или его идентификатор
            
        Returns:
            Объект Chat с информацией о чате
            
        Raises:
            ChatNotFoundError: Если чат не найден
            ConnectionError: При проблемах с подключением
            
        Example:
            >>> chat = await repository.get_chat_info("https://t.me/python_chat")
            >>> print(chat.title)
            'Python разработчики'
        """
        pass
    
    @abstractmethod
    async def get_recent_messages(
        self,
        chat: Chat,
        limit: int = 100,
    ) -> AsyncIterator[tuple[str, dict]]:
        """
        Получить последние сообщения из чата.
        
        Возвращает асинхронный итератор для эффективной обработки
        большого количества сообщений без загрузки всех в память.
        
        Args:
            chat: Объект чата для получения сообщений
            limit: Максимальное количество сообщений
            
        Yields:
            Кортеж (текст_сообщения, метаданные) где метаданные
            содержат sender_name, sender_id, message_id, date
            
        Raises:
            ConnectionError: При проблемах с подключением
            PermissionError: При отсутствии доступа к чату
            
        Example:
            >>> async for text, meta in repository.get_recent_messages(chat, limit=50):
            ...     print(f"{meta['sender_name']}: {text}")
        """
        pass
    
    @abstractmethod
    async def connect(self) -> None:
        """
        Установить соединение с Telegram.
        
        Инициализирует клиента и выполняет авторизацию.
        Метод идемпотентен - повторный вызов не создает
        новые соединения.
        
        Raises:
            AuthenticationError: При проблемах с авторизацией
            ConnectionError: При проблемах с подключением
            
        Example:
            >>> await repository.connect()
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """
        Закрыть соединение с Telegram.
        
        Корректно завершает работу клиента и освобождает ресурсы.
        Метод идемпотентен - повторный вызов безопасен.
        
        Example:
            >>> await repository.disconnect()
        """
        pass
    
    async def __aenter__(self) -> "BaseChatRepository":
        """Поддержка async context manager для автоматического управления соединением."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Автоматическое закрытие соединения при выходе из контекста."""
        await self.disconnect()
