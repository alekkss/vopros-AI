"""
Главный сервис мониторинга Telegram чатов.

Координирует работу всех компонентов: репозиториев,
фильтров, AI-анализатора и бот-адаптера.

Реализует паттерн Service Layer - бизнес-логика приложения.
"""

import asyncio
from datetime import datetime

from src.adapters.telegram_bot import TelegramBotAdapter
from src.config.logger import get_logger
from src.models.chat import Chat
from src.models.question import Question
from src.repositories.base import BaseChatRepository
from src.services.ai_analyzer import AIAnalyzerService
from src.services.question_filter import QuestionFilterService

logger = get_logger(__name__)


class TelegramMonitorService:
    """
    Сервис мониторинга Telegram чатов.
    
    Координирует процесс получения сообщений из чатов,
    их фильтрации, AI-анализа и отправки в бот.
    
    Следует принципам:
    - Single Responsibility: координация процесса мониторинга
    - Dependency Inversion: зависит от абстракций, а не реализаций
    - Open/Closed: легко добавить новые этапы обработки
    """
    
    def __init__(
        self,
        chat_repository: BaseChatRepository,
        bot_adapter: TelegramBotAdapter,
        filter_service: QuestionFilterService,
        ai_analyzer: AIAnalyzerService,
        messages_limit: int = 100,
    ) -> None:
        """
        Инициализация сервиса мониторинга.
        
        Args:
            chat_repository: Репозиторий для работы с чатами
            bot_adapter: Адаптер для отправки в бот
            filter_service: Сервис фильтрации вопросов
            ai_analyzer: Сервис AI-анализа
            messages_limit: Количество сообщений для анализа
        """
        self._chat_repository = chat_repository
        self._bot_adapter = bot_adapter
        self._filter_service = filter_service
        self._ai_analyzer = ai_analyzer
        self._messages_limit = messages_limit
        
        logger.info(
            "telegram_monitor_service_initialized",
            messages_limit=messages_limit,
        )
    
    async def validate_chats(self, chat_links: list[str]) -> list[str]:
        """
        Проверяет доступность чатов и возвращает только доступные.
        
        Args:
            chat_links: Список ссылок на чаты
            
        Returns:
            Список доступных чатов
        """
        valid_chats: list[str] = []
        
        print("\n🔍 Проверка доступности чатов...\n")
        
        for chat_link in chat_links:
            try:
                chat = await self._chat_repository.get_chat_info(chat_link)
                valid_chats.append(chat_link)
                print(f"   ✅ {chat.title}")
                logger.info(
                    "chat_validated",
                    chat_link=chat_link,
                    chat_id=chat.id,
                    chat_title=chat.title,
                )
                
            except ValueError as e:
                # Чат не найден
                print(f"   ❌ Чат не найден: {chat_link}")
                logger.warning(
                    "chat_not_found",
                    chat_link=chat_link,
                    error=str(e),
                )
                
            except PermissionError as e:
                # Нет доступа к чату
                print(f"   ❌ Нет доступа: {chat_link}")
                logger.warning(
                    "chat_access_denied",
                    chat_link=chat_link,
                    error=str(e),
                )
                
            except Exception as e:
                # Другие ошибки
                print(f"   ❌ Ошибка при проверке {chat_link}: {e}")
                logger.warning(
                    "chat_validation_error",
                    chat_link=chat_link,
                    error=str(e),
                    error_type=type(e).__name__,
                )
        
        if not valid_chats:
            print("\n⚠️  Нет доступных чатов для мониторинга!")
            logger.error("no_valid_chats")
        else:
            print(f"\n✅ Доступных чатов: {len(valid_chats)} из {len(chat_links)}\n")
            logger.info(
                "chats_validated",
                total=len(chat_links),
                valid=len(valid_chats),
            )
        
        return valid_chats

    
    async def process_chat(self, chat_link: str) -> int:
        """
        Обработать один чат: получить сообщения, найти вопросы, отправить в бот.
        
        Args:
            chat_link: Ссылка на чат или его идентификатор
            
        Returns:
            Количество найденных и отправленных вопросов
            
        Raises:
            ConnectionError: При проблемах с подключением
            ValueError: Если чат не найден
            PermissionError: Если нет доступа к чату
        """
        
        try:
            # 1. Получаем информацию о чате
            chat = await self._chat_repository.get_chat_info(chat_link)
            print(f"📱 Обработка: {chat.title}")
            
            # 2. Собираем сообщения
            messages: list[tuple[str, dict]] = []
            all_message_texts: list[str] = []
            
            async for text, metadata in self._chat_repository.get_recent_messages(
                chat, limit=self._messages_limit
            ):
                messages.append((text, metadata))
                all_message_texts.append(text)
            
            if not messages:
                print(f"   ⚠️  Нет сообщений")
                return 0
            
            # 3. Фильтруем вопросы
            filtered_questions = self._filter_service.filter_questions(messages)
            print(f"   🔍 Найдено потенциальных вопросов: {len(filtered_questions)}")
            
            if not filtered_questions:
                return 0
            
            # 4. Определяем тематику через AI
            chat_topic = await self._ai_analyzer.determine_chat_topic(
                all_message_texts,
                max_messages=100,
            )
            topic_preview = chat_topic[:60] + "..." if len(chat_topic) > 60 else chat_topic
            print(f"   📌 Тема чата: {topic_preview}")
            
            # 5. Проверяем вопросы через AI
            suitable_questions: list[tuple[str, dict]] = []
            
            for question_text, metadata in filtered_questions:
                # Проверка 1: Соответствие тематике
                is_on_topic = await self._ai_analyzer.is_question_on_topic(
                    question_text, chat_topic
                )
                
                if not is_on_topic:
                    continue
                
                # Проверка 2: Уверенность AI в ответе
                can_answer = await self._ai_analyzer.can_answer_confidently(
                    question_text
                )
                
                if not can_answer:
                    continue
                
                # НОВАЯ Проверка 3: Потенциальный заказ для Python разработчика
                is_order = await self._ai_analyzer.is_potential_order(question_text)
                
                if not is_order:
                    logger.debug(
                        "question_not_potential_order",
                        question_preview=question_text[:50],
                    )
                    continue
                
                suitable_questions.append((question_text, metadata))
            
            print(f"   ✅ Подходящих вопросов (потенциальные заказы): {len(suitable_questions)}")
            
            # 6. Отправляем вопросы в бот
            sent_count = 0
            
            for question_text, metadata in suitable_questions:
                question = Question(
                    text=question_text,
                    sender_name=metadata['sender_name'],
                    sender_id=metadata['sender_id'],
                    message_id=metadata['message_id'],
                    chat_id=chat.id,
                    chat_title=chat.title,
                    date=metadata['date'],
                )
                
                success = await self._bot_adapter.send_question(question)
                
                if success:
                    sent_count += 1
                    print(f"   📤 Отправлен вопрос от {question.sender_name}")
                
                await asyncio.sleep(0.5)
            
            logger.info(
                "chat_processing_completed",
                chat_id=chat.id,
                questions_sent=sent_count,
            )
            
            return sent_count
            
        except (ValueError, PermissionError, ConnectionError):
            # Пробрасываем эти исключения наверх для обработки
            raise
            
        except Exception as e:
            logger.error(
                "chat_processing_error",
                chat_link=chat_link,
                error=str(e),
                error_type=type(e).__name__,
            )
            # Преобразуем неизвестную ошибку в ConnectionError
            raise ConnectionError(f"Ошибка обработки чата: {e}") from e
    
    async def monitor_chats(self, chat_links: list[str]) -> dict[str, int]:
        """
        Мониторить список чатов и собрать вопросы из всех.
        
        Args:
            chat_links: Список ссылок на чаты
            
        Returns:
            Словарь {chat_link: количество_вопросов}
        """
        logger.info(
            "monitoring_started",
            chats_count=len(chat_links),
        )
        
        results: dict[str, int] = {}
        
        for chat_link in chat_links:
            try:
                questions_count = await self.process_chat(chat_link)
                results[chat_link] = questions_count
                
            except ValueError as e:
                # Чат не найден - пропускаем
                print(f"   ⚠️  Чат не найден, пропускаем")
                logger.warning(
                    "chat_not_found_skipping",
                    chat_link=chat_link,
                    error=str(e),
                )
                results[chat_link] = 0
                
            except PermissionError as e:
                # Нет доступа - пропускаем
                print(f"   ⚠️  Нет доступа к чату, пропускаем")
                logger.warning(
                    "chat_access_denied_skipping",
                    chat_link=chat_link,
                    error=str(e),
                )
                results[chat_link] = 0
                
            except ConnectionError as e:
                # Проблемы с сетью - пропускаем
                print(f"   ⚠️  Ошибка подключения, пропускаем")
                logger.warning(
                    "chat_connection_error_skipping",
                    chat_link=chat_link,
                    error=str(e),
                )
                results[chat_link] = 0
                
            except Exception as e:
                # Любые другие ошибки - пропускаем
                print(f"   ⚠️  Ошибка обработки, пропускаем: {e}")
                logger.error(
                    "chat_monitoring_failed",
                    chat_link=chat_link,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                results[chat_link] = 0
            
            # Задержка между обработкой чатов
            await asyncio.sleep(1)
        
        total_questions = sum(results.values())
        logger.info(
            "monitoring_completed",
            chats_processed=len(results),
            total_questions=total_questions,
        )
        
        return results
    
    async def start_continuous_monitoring(
        self,
        chat_links: list[str],
        interval_seconds: int,
    ) -> None:
        """
        Запустить непрерывный мониторинг чатов с заданным интервалом.
        
        Args:
            chat_links: Список ссылок на чаты
            interval_seconds: Интервал проверки в секундах
        """
        
        # Валидируем чаты при старте
        valid_chats = await self.validate_chats(chat_links)
        
        if not valid_chats:
            logger.error("no_valid_chats_stopping")
            print("❌ Нет доступных чатов. Остановка мониторинга.")
            return
        
        # Отправляем уведомление о старте
        start_message = (
            f"🚀 <b>Мониторинг запущен</b>\n\n"
            f"Доступных чатов: {len(valid_chats)}/{len(chat_links)}\n"
            f"Интервал проверки: {interval_seconds // 60} минут\n"
            f"Время запуска: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        await self._bot_adapter.send_text(start_message)
        
        iteration = 0
        
        while True:
            iteration += 1
            print(f"\n{'='*60}")
            print(f"  Итерация #{iteration} — {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*60}\n")
            
            try:
                # Используем только валидные чаты
                results = await self.monitor_chats(valid_chats)
                
                # Простая статистика
                total_questions = sum(results.values())
                print(f"\n✅ Найдено вопросов: {total_questions}")
                
                if total_questions > 0:
                    for chat_link, count in results.items():
                        if count > 0:
                            print(f"   • {count} вопросов")
                
                # Отправляем статистику в бот
                stats_message = (
                    f"📊 <b>Итерация #{iteration}</b>\n\n"
                    f"Найдено вопросов: {total_questions}\n"
                    f"Время: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
                )
                await self._bot_adapter.send_text(stats_message)
                
            except Exception as e:
                logger.error(
                    "monitoring_iteration_error",
                    iteration=iteration,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                print(f"❌ Ошибка в итерации #{iteration}: {e}")
            
            # Ожидаем до следующей проверки
            next_time = datetime.now().timestamp() + interval_seconds
            next_time_str = datetime.fromtimestamp(next_time).strftime('%H:%M:%S')
            print(f"\n⏳ Следующая проверка в {next_time_str}")
            await asyncio.sleep(interval_seconds)


def create_monitor_service_from_settings(
    chat_repository: BaseChatRepository,
    bot_adapter: TelegramBotAdapter,
) -> TelegramMonitorService:
    """
    Создать сервис мониторинга на основе настроек.
    
    Args:
        chat_repository: Репозиторий для работы с чатами
        bot_adapter: Адаптер для отправки в бот
        
    Returns:
        Настроенный сервис мониторинга
        
    Example:
        >>> repository = create_repository_from_settings()
        >>> bot = create_bot_adapter_from_settings()
        >>> monitor = create_monitor_service_from_settings(repository, bot)
    """
    from src.config.settings import get_settings
    
    settings = get_settings()
    
    logger.info("creating_monitor_service_from_settings")
    
    # Создаем зависимости
    filter_service = QuestionFilterService()
    ai_analyzer = AIAnalyzerService(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
    )
    
    return TelegramMonitorService(
        chat_repository=chat_repository,
        bot_adapter=bot_adapter,
        filter_service=filter_service,
        ai_analyzer=ai_analyzer,
        messages_limit=settings.messages_limit,
    )
