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
    """Настроить обработчики сигналов для graceful shutdown."""
    def signal_handler(sig: int, frame) -> None:
        """Обработчик сигналов остановки."""
        print(f"\n⚠️  Остановка мониторинга...")
        if shutdown_event:
            shutdown_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> int:
    """Главная асинхронная функция приложения."""
    global shutdown_event
    shutdown_event = asyncio.Event()
    
    logger = None
    repository = None
    bot_adapter = None
    
    try:
        # 1. Настраиваем логирование
        setup_logging_from_settings()
        logger = get_logger(__name__)
        
        # 2. Загружаем конфигурацию
        settings = get_settings()
        print(f"✅ Конфигурация загружена ({len(settings.monitored_chats)} чатов)")
        
        # 3. Создаем компоненты
        repository = create_repository_from_settings()
        bot_adapter = create_bot_adapter_from_settings()
        monitor_service = create_monitor_service_from_settings(
            chat_repository=repository,
            bot_adapter=bot_adapter,
        )
        
        # 4. Подключаемся к Telegram
        print("🔌 Подключение к Telegram...")
        await repository.connect()
        print("✅ Подключено к Telegram\n")
        
        # 5. Запускаем непрерывный мониторинг
        print(f"🚀 Мониторинг запущен")
        print(f"⏱️  Интервал: {settings.monitoring_interval // 60} минут\n")
        
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
        
        # Отменяем задачу мониторинга
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass
        
        print("✅ Мониторинг остановлен")
        
        return 0
        
    except ConfigurationError as e:
        print(f"\n❌ Ошибка конфигурации: {e}", file=sys.stderr)
        print("\n💡 Проверьте файл .env и убедитесь, что все переменные установлены.\n")
        return 1
    
    except ConnectionError as e:
        print(f"\n❌ Ошибка подключения: {e}", file=sys.stderr)
        print("\n💡 Проверьте интернет-соединение и API credentials\n")
        return 1
    
    except Exception as e:
        print(f"\n❌ Ошибка: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Закрываем все соединения
        if repository:
            try:
                await repository.disconnect()
            except Exception:
                pass
        
        if bot_adapter:
            try:
                await bot_adapter.close()
            except Exception:
                pass
        
        print("\n👋 Завершено\n")


def run() -> None:
    """Синхронная обертка для запуска асинхронного main()."""
    print("=" * 60)
    print("  Telegram Question Monitor")
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
