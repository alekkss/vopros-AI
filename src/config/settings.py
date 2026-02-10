"""
Модуль конфигурации приложения.

Загружает переменные окружения из .env файла и валидирует их.
Использует только стандартные библиотеки + python-dotenv.
"""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class ConfigurationError(Exception):
    """Исключение при ошибках конфигурации."""
    pass


def get_required_env(key: str) -> str:
    """
    Получить обязательную переменную окружения.
    
    Args:
        key: Имя переменной окружения
        
    Returns:
        Значение переменной
        
    Raises:
        ConfigurationError: Если переменная не установлена
    """
    value = os.getenv(key)
    if value is None or value.strip() == "":
        raise ConfigurationError(
            f"Обязательная переменная окружения {key} не установлена. "
            f"Проверьте файл .env"
        )
    return value.strip()


def get_optional_env(key: str, default: str) -> str:
    """
    Получить опциональную переменную окружения с дефолтным значением.
    
    Args:
        key: Имя переменной окружения
        default: Значение по умолчанию
        
    Returns:
        Значение переменной или default
    """
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def parse_chat_list(chats_string: str) -> list[str]:
    """
    Парсит строку с чатами, разделенными запятыми.
    
    Args:
        chats_string: Строка вида "chat1,chat2,chat3"
        
    Returns:
        Список чатов с удаленными пробелами
    """
    chats = [chat.strip() for chat in chats_string.split(",") if chat.strip()]
    if not chats:
        raise ConfigurationError(
            "MONITORED_CHATS не содержит ни одного чата. "
            "Укажите хотя бы один чат для мониторинга."
        )
    return chats


class Settings:
    """
    Класс с настройками приложения.
    
    Загружает конфигурацию из переменных окружения и валидирует их.
    Следует принципу Single Responsibility - отвечает только за конфигурацию.
    """
    
    def __init__(self) -> None:
        """
        Инициализация настроек с валидацией.
        
        Raises:
            ConfigurationError: При отсутствии обязательных переменных
        """
        # Загружаем .env файл
        load_dotenv()
        
        # Telegram Client (Telethon)
        self.telegram_api_id: int = self._parse_api_id(
            get_required_env("TELEGRAM_API_ID")
        )
        self.telegram_api_hash: str = get_required_env("TELEGRAM_API_HASH")
        self.telegram_phone: str = get_required_env("TELEGRAM_PHONE")
        
        # Telegram Bot (aiogram)
        self.telegram_bot_token: str = get_required_env("TELEGRAM_BOT_TOKEN")
        self.telegram_bot_chat_id: int = self._parse_chat_id(
            get_required_env("TELEGRAM_BOT_CHAT_ID")
        )
        
        # Чаты для мониторинга
        chats_string = get_required_env("MONITORED_CHATS")
        self.monitored_chats: list[str] = parse_chat_list(chats_string)
        
        # OpenRouter AI
        self.openrouter_api_key: str = get_required_env("OPENROUTER_API_KEY")
        self.openrouter_model: str = get_optional_env(
            "OPENROUTER_MODEL",
            "google/gemini-2.0-flash-exp:free"
        )
        
        # Настройки мониторинга
        self.monitoring_interval: int = self._parse_positive_int(
            get_optional_env("MONITORING_INTERVAL", "3600"),
            "MONITORING_INTERVAL"
        )
        self.messages_limit: int = self._parse_positive_int(
            get_optional_env("MESSAGES_LIMIT", "100"),
            "MESSAGES_LIMIT"
        )
        
        # Логирование
        self.log_level: str = get_optional_env("LOG_LEVEL", "INFO").upper()
        self.log_format: str = get_optional_env("LOG_FORMAT", "json").lower()
        self.log_file: Optional[str] = os.getenv("LOG_FILE")
        
        # Валидация log_level
        valid_log_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if self.log_level not in valid_log_levels:
            raise ConfigurationError(
                f"LOG_LEVEL должен быть одним из: {', '.join(valid_log_levels)}"
            )
        
        # Валидация log_format
        valid_log_formats = {"json", "console"}
        if self.log_format not in valid_log_formats:
            raise ConfigurationError(
                f"LOG_FORMAT должен быть одним из: {', '.join(valid_log_formats)}"
            )
    
    @staticmethod
    def _parse_api_id(value: str) -> int:
        """Парсит и валидирует TELEGRAM_API_ID."""
        try:
            api_id = int(value)
            if api_id <= 0:
                raise ValueError
            return api_id
        except ValueError:
            raise ConfigurationError(
                f"TELEGRAM_API_ID должен быть положительным числом, получено: {value}"
            )
    
    @staticmethod
    def _parse_chat_id(value: str) -> int:
        """Парсит и валидирует TELEGRAM_BOT_CHAT_ID."""
        try:
            return int(value)
        except ValueError:
            raise ConfigurationError(
                f"TELEGRAM_BOT_CHAT_ID должен быть числом, получено: {value}"
            )
    
    @staticmethod
    def _parse_positive_int(value: str, param_name: str) -> int:
        """Парсит и валидирует положительное целое число."""
        try:
            number = int(value)
            if number <= 0:
                raise ValueError
            return number
        except ValueError:
            raise ConfigurationError(
                f"{param_name} должен быть положительным числом, получено: {value}"
            )
    
    def __repr__(self) -> str:
        """Строковое представление без секретов."""
        return (
            f"Settings("
            f"api_id={self.telegram_api_id}, "
            f"phone={self.telegram_phone}, "
            f"monitored_chats={len(self.monitored_chats)}, "
            f"model={self.openrouter_model}, "
            f"interval={self.monitoring_interval}s"
            f")"
        )


# Singleton instance для удобного доступа
_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Получить экземпляр настроек (Singleton).
    
    При первом вызове создает экземпляр и валидирует конфигурацию.
    
    Returns:
        Экземпляр Settings
        
    Raises:
        ConfigurationError: При ошибках в конфигурации
    """
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance
