"""
Фабрика репозиториев для работы с чатами.

Реализует паттерн Factory для создания репозиториев с зависимостями.
Упрощает Dependency Injection и тестирование.
"""

from typing import Protocol

from src.adapters.telegram_client import TelegramClientAdapter
from src.config.logger import get_logger
from src.repositories.base import BaseChatRepository

logger = get_logger(__name__)


class ChatRepositoryConfig(Protocol):
    """
    Протокол для конфигурации репозитория.
    
    Определяет минимальный набор полей конфигурации,
    необходимых для создания репозитория.
    
    Следует Interface Segregation Principle - требуем
    только то, что действительно нужно.
    """
    
    telegram_api_id: int
    telegram_api_hash: str
    telegram_phone: str


class ChatRepositoryFactory:
    """
    Фабрика для создания репозиториев чатов.
    
    Инкапсулирует логику создания репозиториев с зависимостями,
    упрощая внедрение зависимостей в сервисах.
    
    Следует принципам:
    - Single Responsibility: только создание репозиториев
    - Dependency Inversion: возвращает абстракцию, а не конкретный класс
    - Open/Closed: легко добавить новые типы репозиториев
    """
    
    @staticmethod
    def create_telegram_repository(
        config: ChatRepositoryConfig,
        session_name: str = "monitor_session",
    ) -> BaseChatRepository:
        """
        Создать репозиторий для работы с Telegram через Telethon.
        
        Args:
            config: Конфигурация с API credentials
            session_name: Имя файла сессии Telegram
            
        Returns:
            Репозиторий, реализующий BaseChatRepository
            
        Example:
            >>> from src.config.settings import get_settings
            >>> settings = get_settings()
            >>> repository = ChatRepositoryFactory.create_telegram_repository(settings)
            >>> async with repository:
            ...     chat = await repository.get_chat_info("https://t.me/python_chat")
        """
        logger.info(
            "creating_telegram_repository",
            api_id=config.telegram_api_id,
            phone=config.telegram_phone,
            session=session_name,
        )
        
        repository = TelegramClientAdapter(
            api_id=config.telegram_api_id,
            api_hash=config.telegram_api_hash,
            phone=config.telegram_phone,
            session_name=session_name,
        )
        
        logger.debug("telegram_repository_created", session=session_name)
        
        return repository
    
    @staticmethod
    def create_mock_repository() -> BaseChatRepository:
        """
        Создать mock-репозиторий для тестирования.
        
        Полезно для unit-тестов, когда не нужно реальное
        подключение к Telegram.
        
        Returns:
            Mock-репозиторий для тестирования
            
        Note:
            Требует реализации MockChatRepository в тестах
        """
        logger.info("creating_mock_repository")
        
        # Импортируем здесь, чтобы не требовать mock в production
        from src.repositories.mock_repository import MockChatRepository
        
        return MockChatRepository()


def create_repository_from_settings() -> BaseChatRepository:
    """
    Создать репозиторий на основе текущих настроек приложения.
    
    Функция-хелпер для быстрого создания репозитория
    с автоматической загрузкой конфигурации.
    
    Returns:
        Настроенный репозиторий
        
    Raises:
        ConfigurationError: При ошибках в конфигурации
        
    Example:
        >>> repository = create_repository_from_settings()
        >>> async with repository:
        ...     # работа с репозиторием
    """
    from src.config.settings import get_settings
    
    settings = get_settings()
    
    logger.info("creating_repository_from_settings")
    
    return ChatRepositoryFactory.create_telegram_repository(
        config=settings,
        session_name="monitor_session",
    )
