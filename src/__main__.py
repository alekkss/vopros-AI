"""
Точка входа приложения Telegram Question Monitor.

Запуск: python -m src
"""

import asyncio
import signal
import sys
from typing import Optional

from src.adapters.telegram_bot import create_bot_adapter_from_settings
from src.config.logger import get_logger, setup_logging_from_settings
from src.config.settings import ConfigurationError, get_settings
from src.repositories.chat_repository import create_repository_from_settings
from src.services.telegram_monitor_service import create_monitor_service_from_settings

# Глобальные переменные для graceful shutdown
shutdown_event: Optional[asyncio.Event] = None


def setup_signal_handlers() -> None:
    """
    Настроить обработчики сигналов для graceful shutdown.
    
    Регистрирует обработчики SIGINT (Ctrl+C) и SIGTERM
    для корректного завершения работы приложения.
    """
    def signal_handler(sig: int, frame) -> None:
        """Обработчик сигналов остановки."""
        print(f"\n⚠️  Получен сигнал {sig}, останавливаем мониторинг...")
        if shutdown_event:
            shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> int:
    """
    Главная асинхронная функция приложения.
    
    Выполняет:
    1. Настройку логирования
    2. Загрузку конфигурации
    3. Создание всех компонентов через фабрики
    4. Подключение к Telegram
    5. Запуск непрерывного мониторинга
    6. Graceful shutdown при остановке
    
    Returns:
        Код возврата: 0 при успехе, 1 при ошибке
    """
    global shutdown_event
    shutdown_event = asyncio.Event()
    
    logger = None
    repository = None
    bot_adapter = None
    
    try:
        # 1. Настраиваем логирование
        print("🔧 Настройка логирования...")
        setup_logging_from_settings()
        logger = get_logger(__name__)
        logger.info("application_starting")
        
        # 2. Загружаем конфигурацию
        logger.info("loading_configuration")
        settings = get_settings()
        logger.info(
            "configuration_loaded",
            monitored_chats=len(settings.monitored_chats),
            monitoring_interval=settings.monitoring_interval,
            log_level=settings.log_level,
        )
        
        # 3. Создаем компоненты через фабрики
        logger.info("creating_components")
        
        # Репозиторий для работы с чатами
        repository = create_repository_from_settings()
        logger.info("repository_created")
        
        # Адаптер для отправки в бот
        bot_adapter = create_bot_adapter_from_settings()
        logger.info("bot_adapter_created")
        
        # Главный сервис мониторинга
        monitor_service = create_monitor_service_from_settings(
            chat_repository=repository,
            bot_adapter=bot_adapter,
        )
        logger.info("monitor_service_created")
        
        # 4. Подключаемся к Telegram
        logger.info("connecting_to_telegram")
        print("🔌 Подключение к Telegram...")
        await repository.connect()
        logger.info("telegram_connected")
        print("✅ Подключено к Telegram\n")
        
        # 5. Запускаем непрерывный мониторинг
        logger.info(
            "starting_monitoring",
            chats=settings.monitored_chats,
            interval=settings.monitoring_interval,
        )
        print(f"🚀 Запуск мониторинга {len(settings.monitored_chats)} чатов...")
        print(f"⏱️  Интервал проверки: {settings.monitoring_interval // 60} минут\n")
        
        # Создаем задачу мониторинга
        monitor_task = asyncio.create_task(
            monitor_service.start_continuous_monitoring(
                chat_links=settings.monitored_chats,
                interval_seconds=settings.monitoring_interval,
            )
        )
        
        # Ожидаем сигнала остановки
        await shutdown_event.wait()
        
        # 6. Graceful shutdown
        logger.info("shutdown_initiated")
        print("\n🛑 Остановка мониторинга...")
        
        # Отменяем задачу мониторинга
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            logger.info("monitoring_task_cancelled")
        
        logger.info("application_stopped")
        print("✅ Мониторинг остановлен")
        
        return 0
        
    except ConfigurationError as e:
        if logger:
            logger.error("configuration_error", error=str(e))
        else:
            print(f"❌ Ошибка конфигурации: {e}", file=sys.stderr)
        print("\n💡 Проверьте файл .env и убедитесь, что все переменные установлены.")
        print("   Используйте .env.example как шаблон.\n")
        return 1
    
    except ConnectionError as e:
        if logger:
            logger.error("connection_error", error=str(e))
        else:
            print(f"❌ Ошибка подключения: {e}", file=sys.stderr)
        print("\n💡 Проверьте:")
        print("   - Правильность API credentials в .env")
        print("   - Интернет-соединение")
        print("   - Доступность Telegram API\n")
        return 1
    
    except Exception as e:
        if logger:
            logger.error(
                "unexpected_error",
                error=str(e),
                error_type=type(e).__name__,
            )
        else:
            print(f"❌ Неожиданная ошибка: {e}", file=sys.stderr)
        
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Закрываем все соединения
        if logger:
            logger.info("cleanup_started")
        
        if repository:
            try:
                await repository.disconnect()
                if logger:
                    logger.info("repository_disconnected")
            except Exception as e:
                if logger:
                    logger.error("repository_disconnect_error", error=str(e))
        
        if bot_adapter:
            try:
                await bot_adapter.close()
                if logger:
                    logger.info("bot_adapter_closed")
            except Exception as e:
                if logger:
                    logger.error("bot_adapter_close_error", error=str(e))
        
        if logger:
            logger.info("cleanup_completed")
        
        print("\n👋 До свидания!\n")


def run() -> None:
    """
    Синхронная обертка для запуска асинхронного main().
    
    Настраивает обработчики сигналов и запускает event loop.
    """
    print("=" * 60)
    print("  Telegram Question Monitor")
    print("  Мониторинг вопросов из Telegram чатов")
    print("=" * 60)
    print()
    
    # Настраиваем обработчики сигналов
    setup_signal_handlers()
    
    # Запускаем асинхронное приложение
    exit_code = asyncio.run(main())
    
    # Выходим с соответствующим кодом
    sys.exit(exit_code)


if __name__ == "__main__":
    run()
