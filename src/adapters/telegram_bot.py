"""
Адаптер для aiogram - отправка сообщений в Telegram бот.

Реализует паттерн Adapter, изолируя внешнюю библиотеку aiogram
от остальной части приложения.
"""

from typing import Final

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError

from src.config.logger import get_logger
from src.models.question import Question

logger = get_logger(__name__)


class TelegramBotAdapter:
    """
    Адаптер для отправки сообщений через Telegram бот.
    
    Инкапсулирует логику работы с aiogram Bot API,
    предоставляя простой интерфейс для отправки найденных вопросов.
    
    Следует принципам:
    - Single Responsibility: только отправка сообщений через бот
    - Adapter Pattern: изолирует aiogram от остального кода
    - Open/Closed: можно заменить на другую реализацию
    """
    
    # Максимальная длина сообщения в Telegram
    MAX_MESSAGE_LENGTH: Final[int] = 4096
    
    def __init__(self, token: str, chat_id: int) -> None:
        """
        Инициализация адаптера Telegram бота.
        
        Args:
            token: Токен Telegram бота
            chat_id: ID чата, куда отправлять сообщения
        """
        self._token = token
        self._chat_id = chat_id
        
        # Правильная инициализация для aiogram 3.x
        self._bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
        )
        
        logger.info(
            "telegram_bot_adapter_initialized",
            chat_id=chat_id,
            parse_mode="HTML",
        )
    
    async def send_question(self, question: Question) -> bool:
        """
        Отправить вопрос в Telegram бот.
        
        Args:
            question: Объект вопроса для отправки
            
        Returns:
            True если отправка успешна, False в противном случае
        """
        try:
            # Форматируем вопрос для отправки
            message_text = question.format_for_bot()
            
            # Проверяем длину сообщения
            if len(message_text) > self.MAX_MESSAGE_LENGTH:
                logger.warning(
                    "message_too_long_truncating",
                    original_length=len(message_text),
                    max_length=self.MAX_MESSAGE_LENGTH,
                )
                message_text = message_text[:self.MAX_MESSAGE_LENGTH - 3] + "..."
            
            logger.debug(
                "sending_question_to_bot",
                chat_id=self._chat_id,
                question_preview=question.get_short_preview(),
                from_chat=question.chat_title,
            )
            
            # Отправляем сообщение
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=message_text,
            )
            
            logger.info(
                "question_sent_to_bot",
                chat_id=self._chat_id,
                message_id=question.message_id,
                from_chat_id=question.chat_id,
                sender=question.sender_name,
            )
            
            return True
            
        except TelegramForbiddenError as e:
            logger.error(
                "bot_forbidden_error",
                chat_id=self._chat_id,
                error=str(e),
                hint="Бот заблокирован пользователем или не имеет доступа к чату",
            )
            return False
        
        except TelegramBadRequest as e:
            logger.error(
                "bot_bad_request",
                chat_id=self._chat_id,
                error=str(e),
                hint="Неверный chat_id или формат сообщения",
            )
            return False
        
        except TelegramNetworkError as e:
            logger.error(
                "bot_network_error",
                chat_id=self._chat_id,
                error=str(e),
                hint="Проблемы с сетевым подключением к Telegram",
            )
            return False
        
        except Exception as e:
            logger.error(
                "bot_send_error",
                chat_id=self._chat_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False
    
    async def send_text(self, text: str) -> bool:
        """
        Отправить произвольный текст в бот.
        
        Полезно для отправки системных сообщений,
        статистики или уведомлений.
        
        Args:
            text: Текст для отправки
            
        Returns:
            True если отправка успешна, False в противном случае
        """
        try:
            # Проверяем длину сообщения
            if len(text) > self.MAX_MESSAGE_LENGTH:
                logger.warning(
                    "text_too_long_truncating",
                    original_length=len(text),
                    max_length=self.MAX_MESSAGE_LENGTH,
                )
                text = text[:self.MAX_MESSAGE_LENGTH - 3] + "..."
            
            logger.debug(
                "sending_text_to_bot",
                chat_id=self._chat_id,
                text_preview=text[:50],
            )
            
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
            )
            
            logger.info("text_sent_to_bot", chat_id=self._chat_id)
            return True
            
        except Exception as e:
            logger.error(
                "bot_send_text_error",
                chat_id=self._chat_id,
                error=str(e),
                error_type=type(e).__name__,
            )
            return False
    
    async def close(self) -> None:
        """
        Закрыть сессию бота.
        
        Корректно завершает работу aiogram Bot и освобождает ресурсы.
        Метод идемпотентен - повторный вызов безопасен.
        """
        try:
            logger.info("closing_bot_session")
            await self._bot.session.close()
            logger.info("bot_session_closed")
            
        except Exception as e:
            logger.error("bot_close_error", error=str(e))
            # Не пробрасываем ошибку при закрытии
    
    async def __aenter__(self) -> "TelegramBotAdapter":
        """Поддержка async context manager."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Автоматическое закрытие при выходе из контекста."""
        await self.close()


def create_bot_adapter_from_settings() -> TelegramBotAdapter:
    """
    Создать адаптер бота на основе текущих настроек.
    
    Функция-хелпер для быстрого создания адаптера
    с автоматической загрузкой конфигурации.
    
    Returns:
        Настроенный адаптер Telegram бота
        
    Raises:
        ConfigurationError: При ошибках в конфигурации
        
    Example:
        >>> bot_adapter = create_bot_adapter_from_settings()
        >>> async with bot_adapter:
        ...     await bot_adapter.send_question(question)
    """
    from src.config.settings import get_settings
    
    settings = get_settings()
    
    logger.info("creating_bot_adapter_from_settings")
    
    return TelegramBotAdapter(
        token=settings.telegram_bot_token,
        chat_id=settings.telegram_bot_chat_id,
    )
