"""
Модуль структурированного логирования.

Настраивает structlog для JSON и console форматов логирования
с поддержкой различных уровней и записи в файл.
"""

import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict, Processor


def add_app_context(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """
    Добавляет контекст приложения в каждое событие лога.
    
    Args:
        logger: Экземпляр логгера
        method_name: Имя метода логирования
        event_dict: Словарь события
        
    Returns:
        Обогащенный словарь события
    """
    event_dict["app"] = "telegram_question_monitor"
    return event_dict


def suppress_third_party_logs() -> None:
    """
    Подавляет все логи от сторонних библиотек.
    
    Оставляет только логи нашего приложения (модули с префиксом 'src.').
    """
    # Список библиотек для полного подавления
    libraries_to_silence = [
        "telethon",
        "aiogram",
        "httpx",
        "httpcore",
        "asyncio",
        "aiohttp",
        "urllib3",
        "charset_normalizer",
        "multipart",
        "telegram",
        "openai",
        "httpcore.connection",
        "httpcore.http11",
        "httpx._client",
    ]
    
    # Устанавливаем CRITICAL для всех сторонних библиотек
    # (они будут логировать только критические ошибки)
    for lib_name in libraries_to_silence:
        logging.getLogger(lib_name).setLevel(logging.CRITICAL)
    
    # Дополнительно подавляем все логгеры, которые не начинаются с 'src.'
    for name in logging.root.manager.loggerDict:
        if not name.startswith('src.') and not name.startswith('__main__'):
            logging.getLogger(name).setLevel(logging.CRITICAL)


def configure_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_file: str | None = None,
) -> None:
    """
    Конфигурирует систему логирования.
    
    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Формат вывода ("json" или "console")
        log_file: Путь к файлу логов (опционально)
    """
    # Преобразуем строковый уровень в константу logging
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Создаем директорию для логов, если указан файл
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Базовые процессоры для structlog
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=False),  # Локальное время
        structlog.processors.StackInfoRenderer(),
        add_app_context,
    ]
    
    # Выбираем процессор форматирования в зависимости от формата
    if log_format == "json":
        shared_processors.append(structlog.processors.format_exc_info)
        renderer: Processor = structlog.processors.JSONRenderer()
    else:  # console
        shared_processors.append(structlog.processors.format_exc_info)
        shared_processors.append(structlog.dev.set_exc_info)
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        )
    
    # Настраиваем structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Настраиваем стандартный logging
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)
    
    # Обработчик для файла (если указан)
    handlers: list[logging.Handler] = [console_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)
    
    # Настраиваем root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)
    for handler in handlers:
        root_logger.addHandler(handler)
    
    # Подавляем все логи сторонних библиотек
    suppress_third_party_logs()


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Получить логгер для конкретного модуля.
    
    Args:
        name: Имя модуля (обычно __name__)
        
    Returns:
        Настроенный структурированный логгер
        
    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("user_created", user_id=123, email="test@example.com")
    """
    return structlog.get_logger(name)


def setup_logging_from_settings() -> None:
    """
    Настраивает логирование на основе конфигурации из settings.
    
    Использует Dependency Injection - импортирует settings только при вызове,
    что позволяет легко подменить конфигурацию в тестах.
    
    Raises:
        ConfigurationError: При ошибках в конфигурации
    """
    from src.config.settings import get_settings
    
    settings = get_settings()
    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
        log_file=settings.log_file,
    )
    
    logger = get_logger(__name__)
    logger.info(
        "logging_configured",
        level=settings.log_level,
        format=settings.log_format,
        file=settings.log_file or "console_only",
    )
