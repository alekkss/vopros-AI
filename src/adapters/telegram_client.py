"""
Адаптер для Telethon - клиент для чтения сообщений из Telegram.

Реализует паттерн Adapter, изолируя внешнюю библиотеку Telethon
от остальной части приложения через интерфейс BaseChatRepository.
"""

from datetime import datetime
from typing import AsyncIterator

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.tl.types import Channel, Chat as TelegramChat, User

from src.config.logger import get_logger
from src.models.chat import Chat
from src.repositories.base import BaseChatRepository

logger = get_logger(__name__)


class TelegramClientAdapter(BaseChatRepository):
    """
    Адаптер для Telethon, реализующий BaseChatRepository.
    
    Инкапсулирует логику работы с Telegram API через Telethon,
    предоставляя единый интерфейс для получения сообщений из чатов.
    
    Следует принципам:
    - Single Responsibility: только работа с Telegram через Telethon
    - Dependency Inversion: реализует абстрактный интерфейс
    - Open/Closed: можно заменить на другую реализацию без изменения кода
    """
    
    def __init__(
        self,
        api_id: int,
        api_hash: str,
        phone: str,
        session_name: str = "monitor_session",
    ) -> None:
        """
        Инициализация адаптера Telegram.
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            phone: Номер телефона для авторизации
            session_name: Имя файла сессии
        """
        self._api_id = api_id
        self._api_hash = api_hash
        self._phone = phone
        self._session_name = session_name
        self._client: TelegramClient | None = None
        self._is_connected = False
        
        logger.info(
            "telegram_client_initialized",
            api_id=api_id,
            phone=phone,
            session=session_name,
        )
    
    async def connect(self) -> None:
        """
        Установить соединение с Telegram.
        
        Создает клиента Telethon и выполняет авторизацию.
        Метод идемпотентен - повторный вызов безопасен.
        
        Raises:
            AuthenticationError: При проблемах с авторизацией
            ConnectionError: При проблемах с подключением
        """
        if self._is_connected and self._client:
            logger.debug("telegram_already_connected")
            return
        
        try:
            logger.info("telegram_connecting")
            
            self._client = TelegramClient(
                self._session_name,
                self._api_id,
                self._api_hash,
            )
            
            await self._client.start(phone=self._phone)
            self._is_connected = True
            
            # Получаем информацию о текущем пользователе
            me = await self._client.get_me()
            
            logger.info(
                "telegram_connected",
                user_id=me.id,
                username=me.username or "no_username",
                phone=me.phone,
            )
            
        except PhoneNumberInvalidError as e:
            logger.error("telegram_invalid_phone", phone=self._phone, error=str(e))
            raise ConnectionError(f"Неверный номер телефона: {self._phone}") from e
        
        except SessionPasswordNeededError as e:
            logger.error("telegram_2fa_required", error=str(e))
            raise ConnectionError(
                "Требуется двухфакторная аутентификация. "
                "Настройте её через интерактивную сессию."
            ) from e
        
        except Exception as e:
            logger.error("telegram_connection_failed", error=str(e), error_type=type(e).__name__)
            raise ConnectionError(f"Ошибка подключения к Telegram: {e}") from e
    
    async def disconnect(self) -> None:
        """
        Закрыть соединение с Telegram.
        
        Корректно завершает работу клиента и освобождает ресурсы.
        Метод идемпотентен - повторный вызов безопасен.
        """
        if not self._is_connected or not self._client:
            logger.debug("telegram_already_disconnected")
            return
        
        try:
            logger.info("telegram_disconnecting")
            await self._client.disconnect()
            self._is_connected = False
            self._client = None
            logger.info("telegram_disconnected")
            
        except Exception as e:
            logger.error("telegram_disconnect_error", error=str(e))
            # Не пробрасываем ошибку при отключении
            self._is_connected = False
            self._client = None
    
    async def get_chat_info(self, chat_link: str) -> Chat:
        """
        Получить информацию о чате.
        
        Args:
            chat_link: Ссылка на чат или его идентификатор
            
        Returns:
            Объект Chat с информацией о чате
            
        Raises:
            ValueError: Если чат не найден
            ConnectionError: При проблемах с подключением
        """
        if not self._client or not self._is_connected:
            raise ConnectionError("Telegram клиент не подключен. Вызовите connect() сначала.")
        
        try:
            logger.debug("fetching_chat_info", chat_link=chat_link)
            
            entity = await self._client.get_entity(chat_link)
            
            # Извлекаем информацию в зависимости от типа сущности
            if isinstance(entity, Channel):
                chat_id = entity.id
                title = entity.title
                username = entity.username
            elif isinstance(entity, TelegramChat):
                chat_id = entity.id
                title = entity.title
                username = None
            elif isinstance(entity, User):
                chat_id = entity.id
                title = f"{entity.first_name or ''} {entity.last_name or ''}".strip()
                username = entity.username
            else:
                raise ValueError(f"Неизвестный тип чата: {type(entity)}")
            
            chat = Chat(
                id=chat_id,
                title=title,
                link=chat_link,
                username=username,
            )
            
            logger.info(
                "chat_info_fetched",
                chat_id=chat_id,
                title=title,
                username=username,
                is_public=chat.is_public(),
            )
            
            return chat
            
        except ValueError as e:
            logger.error("chat_not_found", chat_link=chat_link, error=str(e))
            raise ValueError(f"Чат не найден: {chat_link}") from e
        
        except Exception as e:
            logger.error(
                "chat_info_fetch_error",
                chat_link=chat_link,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ConnectionError(f"Ошибка получения информации о чате: {e}") from e
    
    async def get_recent_messages(
        self,
        chat: Chat,
        limit: int = 100,
    ) -> AsyncIterator[tuple[str, dict]]:
        """
        Получить последние сообщения из чата.
        
        Args:
            chat: Объект чата для получения сообщений
            limit: Максимальное количество сообщений
            
        Yields:
            Кортеж (текст_сообщения, метаданные)
            
        Raises:
            ConnectionError: При проблемах с подключением
            PermissionError: При отсутствии доступа к чату
        """
        if not self._client or not self._is_connected:
            raise ConnectionError("Telegram клиент не подключен. Вызовите connect() сначала.")
        
        try:
            logger.info(
                "fetching_messages",
                chat_id=chat.id,
                chat_title=chat.title,
                limit=limit,
            )
            
            messages_count = 0
            
            async for message in self._client.iter_messages(chat.link, limit=limit):
                # Пропускаем закрепленные и сообщения без текста
                if message.pinned or not message.text:
                    continue
                
                # Получаем информацию об отправителе
                sender_name = "Неизвестно"
                try:
                    sender = await message.get_sender()
                    if sender:
                        if hasattr(sender, 'first_name'):
                            sender_name = sender.first_name or "Неизвестно"
                            if hasattr(sender, 'last_name') and sender.last_name:
                                sender_name += f" {sender.last_name}"
                        elif hasattr(sender, 'title'):
                            sender_name = sender.title
                except Exception as e:
                    logger.warning("sender_info_error", message_id=message.id, error=str(e))
                
                # Формируем метаданные
                metadata = {
                    'sender_name': sender_name,
                    'sender_id': message.sender_id or 0,
                    'message_id': message.id,
                    'date': message.date or datetime.now(),
                }
                
                messages_count += 1
                yield message.text, metadata
            
            logger.info(
                "messages_fetched",
                chat_id=chat.id,
                chat_title=chat.title,
                count=messages_count,
            )
            
        except FloodWaitError as e:
            logger.warning("telegram_flood_wait", chat_id=chat.id, wait_seconds=e.seconds)
            raise ConnectionError(
                f"Telegram ограничил запросы. Подождите {e.seconds} секунд."
            ) from e
        
        except PermissionError as e:
            logger.error("chat_access_denied", chat_id=chat.id, error=str(e))
            raise PermissionError(f"Нет доступа к чату {chat.title}") from e
        
        except Exception as e:
            logger.error(
                "messages_fetch_error",
                chat_id=chat.id,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ConnectionError(f"Ошибка получения сообщений: {e}") from e
