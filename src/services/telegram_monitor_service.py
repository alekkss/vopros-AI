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
        """
        logger.info("processing_chat_started", chat_link=chat_link)
        
        try:
            # 1. Получаем информацию о чате
            chat = await self._chat_repository.get_chat_info(chat_link)
            logger.info(
                "chat_info_retrieved",
                chat_id=chat.id,
                chat_title=chat.title,
            )
            
            # 2. Собираем сообщения из чата
            messages: list[tuple[str, dict]] = []
            all_message_texts: list[str] = []
            
            async for text, metadata in self._chat_repository.get_recent_messages(
                chat, limit=self._messages_limit
            ):
                messages.append((text, metadata))
                all_message_texts.append(text)
            
            logger.info(
                "messages_collected",
                chat_id=chat.id,
                total_messages=len(messages),
            )
            
            if not messages:
                logger.warning("no_messages_found", chat_id=chat.id)
                return 0
            
            # 3. Фильтруем сообщения (базовая фильтрация по регулярным выражениям)
            filtered_questions = self._filter_service.filter_questions(messages)
            
            if not filtered_questions:
                logger.info(
                    "no_questions_after_filter",
                    chat_id=chat.id,
                    total_messages=len(messages),
                )
                return 0
            
            # 4. Определяем тематику чата через AI
            chat_topic = await self._ai_analyzer.determine_chat_topic(
                all_message_texts,
                max_messages=100,
            )
            logger.info("chat_topic_determined", chat_id=chat.id, topic=chat_topic)
            
            # 5. Проверяем вопросы на соответствие тематике и уверенность AI
            suitable_questions: list[tuple[str, dict]] = []
            
            for question_text, metadata in filtered_questions:
                # Проверяем соответствие тематике
                is_on_topic = await self._ai_analyzer.is_question_on_topic(
                    question_text, chat_topic
                )
                
                if not is_on_topic:
                    logger.debug(
                        "question_not_on_topic",
                        question_preview=question_text[:50],
                    )
                    continue
                
                # Проверяем уверенность AI
                can_answer = await self._ai_analyzer.can_answer_confidently(
                    question_text
                )
                
                if not can_answer:
                    logger.debug(
                        "ai_not_confident",
                        question_preview=question_text[:50],
                    )
                    continue
                
                suitable_questions.append((question_text, metadata))
            
            logger.info(
                "questions_after_ai_analysis",
                chat_id=chat.id,
                suitable_questions=len(suitable_questions),
                filtered_questions=len(filtered_questions),
            )
            
            if not suitable_questions:
                logger.info("no_suitable_questions", chat_id=chat.id)
                return 0
            
            # 6. Отправляем найденные вопросы в бот
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
                    logger.info(
                        "question_sent",
                        chat_id=chat.id,
                        message_id=question.message_id,
                        sender=question.sender_name,
                    )
                else:
                    logger.warning(
                        "question_send_failed",
                        chat_id=chat.id,
                        message_id=question.message_id,
                    )
                
                # Небольшая задержка между отправками
                await asyncio.sleep(0.5)
            
            logger.info(
                "chat_processing_completed",
                chat_id=chat.id,
                questions_sent=sent_count,
            )
            
            return sent_count
            
        except Exception as e:
            logger.error(
                "chat_processing_error",
                chat_link=chat_link,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise
    
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
                
            except Exception as e:
                logger.error(
                    "chat_monitoring_failed",
                    chat_link=chat_link,
                    error=str(e),
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
            interval_seconds: Интервал между проверками в секундах
        """
        logger.info(
            "continuous_monitoring_started",
            chats_count=len(chat_links),
            interval_seconds=interval_seconds,
        )
        
        # Отправляем уведомление о старте
        start_message = (
            f"🚀 <b>Мониторинг запущен</b>\n\n"
            f"Отслеживаемых чатов: {len(chat_links)}\n"
            f"Интервал проверки: {interval_seconds // 60} минут\n"
            f"Время запуска: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        await self._bot_adapter.send_text(start_message)
        
        iteration = 0
        
        while True:
            iteration += 1
            logger.info("monitoring_iteration_started", iteration=iteration)
            
            try:
                results = await self.monitor_chats(chat_links)
                
                # Отправляем статистику
                total_questions = sum(results.values())
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
            
            logger.info(
                "monitoring_iteration_completed",
                iteration=iteration,
                next_check_in_seconds=interval_seconds,
            )
            
            # Ожидаем до следующей проверки
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
