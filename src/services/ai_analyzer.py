"""
Сервис AI-анализа вопросов через OpenRouter API.

Предоставляет методы для определения тематики чатов,
проверки соответствия вопросов тематике и оценки
уверенности AI в возможности дать качественный ответ.
"""

import re
from typing import Final

from openai import AsyncOpenAI

from src.config.logger import get_logger

logger = get_logger(__name__)


class AIAnalyzerService:
    """
    Сервис для AI-анализа вопросов.
    
    Использует OpenRouter API для интеллектуального анализа
    сообщений и определения их релевантности.
    
    Следует принципам:
    - Single Responsibility: только AI-анализ
    - Dependency Inversion: работает через интерфейс OpenAI клиента
    """
    
    # Промпт для определения тематики чата
    TOPIC_PROMPT_TEMPLATE: Final[str] = (
        "Типичный участник анализирует последние сообщения этого Telegram-чата "
        "и формулирует ключевую тему/темы чата буквально 1-2 предложениями "
        "без оценок и без приветствий.\n\n"
        "Примеры тем:\n"
        "- 'Обсуждение фриланса и автоматизации задач на Python'\n"
        "- 'Технический чат о парсинге данных и Telegram-ботах'\n"
        "- 'Чат по криптовалютам и инвестициям в крипту'\n"
        "- 'Общий чат для неформального общения'\n\n"
        "Вот сообщения:\n{messages}\n\n"
        "Какая тематика или основные темы чата по содержанию этих сообщений?"
    )
    
    # Системный промпт для определения тематики
    TOPIC_SYSTEM_PROMPT: Final[str] = (
        "Очень сжато и по делу: определи ТЕМУ чата. "
        "Игнорируй приветствия, оффтоп, расскажи только по содержательной части."
    )
    
    # Промпт для проверки соответствия вопроса тематике
    ON_TOPIC_PROMPT_TEMPLATE: Final[str] = (
        "Тематика Telegram-чата: {topic}\n"
        "Вопрос: {question}\n\n"
        "Ответь 'да', если вопрос явно по указанной тематике; "
        "иначе ответь 'нет'. Только 'да' или 'нет'."
    )
    
    # Системный промпт для проверки соответствия
    ON_TOPIC_SYSTEM_PROMPT: Final[str] = (
        "Ты эксперт по тематике чата. Очень строго — только 'да' или 'нет'."
    )
    
    # Промпт для проверки уверенности AI
    CONFIDENCE_PROMPT_TEMPLATE: Final[str] = (
        "Вопрос: {question}\n\n"
        "Можешь ли ты дать точный, конкретный и полезный ответ на этот вопрос, "
        "основываясь на твоих знаниях?\n\n"
        "Ответь 'да', если уверен в своих знаниях по этой теме "
        "и можешь дать качественный ответ.\n"
        "Ответь 'нет', если тема слишком специфична, требует актуальной информации, "
        "которой у тебя может не быть, или если вопрос слишком расплывчатый.\n\n"
        "Только 'да' или 'нет'."
    )
    
    # Системный промпт для проверки уверенности
    CONFIDENCE_SYSTEM_PROMPT: Final[str] = (
        "Честно оцени свои возможности ответить качественно. Только 'да' или 'нет'."
    )
    
    def __init__(self, api_key: str, model: str) -> None:
        """
        Инициализация сервиса AI-анализа.
        
        Args:
            api_key: API ключ OpenRouter
            model: Название модели для использования
        """
        self._client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )
        self._model = model
        
        logger.info(
            "ai_analyzer_service_initialized",
            model=model,
            base_url="https://openrouter.ai/api/v1",
        )
    
    async def determine_chat_topic(
        self,
        messages: list[str],
        max_messages: int = 100,
    ) -> str:
        """
        Определяет тематику чата на основе последних сообщений.
        
        Args:
            messages: Список текстов сообщений из чата
            max_messages: Максимальное количество сообщений для анализа
            
        Returns:
            Строка с описанием тематики чата
            
        Example:
            >>> topic = await analyzer.determine_chat_topic(messages)
            >>> print(topic)
            'Обсуждение Python разработки и автоматизации'
        """
        # Ограничиваем количество сообщений и их длину
        recent_messages = messages[:max_messages]
        truncated_messages = [msg[:250] for msg in recent_messages if msg]
        messages_text = "\n".join(truncated_messages)
        
        prompt = self.TOPIC_PROMPT_TEMPLATE.format(messages=messages_text)
        
        try:
            logger.debug(
                "determining_chat_topic",
                messages_count=len(truncated_messages),
                model=self._model,
            )
            
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self.TOPIC_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=80,
                temperature=0,
            )
            
            if response.choices:
                topic = response.choices[0].message.content.strip()
                # Удаляем специальные символы, оставляем только текст
                topic = re.sub(r'[^\w\s,\.]', '', topic, flags=re.UNICODE).strip()
                
                logger.info("chat_topic_determined", topic=topic)
                return topic
            
            logger.warning("chat_topic_empty_response")
            return "Общая тематика не определена"
            
        except Exception as e:
            logger.error(
                "chat_topic_determination_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return "Общая тематика не определена"
    
    async def is_question_on_topic(self, question: str, topic: str) -> bool:
        """
        Проверяет, соответствует ли вопрос тематике чата.
        
        Args:
            question: Текст вопроса
            topic: Тематика чата
            
        Returns:
            True если вопрос по теме, False в противном случае
            
        Example:
            >>> is_on_topic = await analyzer.is_question_on_topic(
            ...     "Как настроить async в Python?",
            ...     "Обсуждение Python разработки"
            ... )
            >>> print(is_on_topic)
            True
        """
        prompt = self.ON_TOPIC_PROMPT_TEMPLATE.format(
            topic=topic.strip(),
            question=question.strip(),
        )
        
        try:
            logger.debug(
                "checking_question_on_topic",
                question_preview=question[:50],
                topic=topic,
            )
            
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self.ON_TOPIC_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=3,
                temperature=0,
            )
            
            if response.choices:
                answer = response.choices[0].message.content.lower()
                is_on_topic = 'да' in answer
                
                logger.info(
                    "question_on_topic_checked",
                    is_on_topic=is_on_topic,
                    question_preview=question[:50],
                )
                
                return is_on_topic
            
            logger.warning("question_on_topic_empty_response")
            return False
            
        except Exception as e:
            logger.error(
                "question_on_topic_check_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False
    
    async def can_answer_confidently(self, question: str) -> bool:
        """
        Проверяет, может ли AI уверенно ответить на вопрос.
        
        Args:
            question: Текст вопроса
            
        Returns:
            True если AI уверен в своих знаниях, False в противном случае
            
        Example:
            >>> can_answer = await analyzer.can_answer_confidently(
            ...     "Как работает GIL в Python?"
            ... )
            >>> print(can_answer)
            True
        """
        prompt = self.CONFIDENCE_PROMPT_TEMPLATE.format(question=question.strip())
        
        try:
            logger.debug(
                "checking_ai_confidence",
                question_preview=question[:50],
            )
            
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": self.CONFIDENCE_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=3,
                temperature=0,
            )
            
            if response.choices:
                answer = response.choices[0].message.content.lower()
                is_confident = 'да' in answer
                
                logger.info(
                    "ai_confidence_checked",
                    is_confident=is_confident,
                    question_preview=question[:50],
                )
                
                return is_confident
            
            logger.warning("ai_confidence_empty_response")
            return False
            
        except Exception as e:
            logger.error(
                "ai_confidence_check_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return False


def create_ai_analyzer_from_settings() -> AIAnalyzerService:
    """
    Создать AI анализатор на основе текущих настроек.
    
    Функция-хелпер для быстрого создания сервиса
    с автоматической загрузкой конфигурации.
    
    Returns:
        Настроенный сервис AI-анализа
        
    Raises:
        ConfigurationError: При ошибках в конфигурации
        
    Example:
        >>> analyzer = create_ai_analyzer_from_settings()
        >>> topic = await analyzer.determine_chat_topic(messages)
    """
    from src.config.settings import get_settings
    
    settings = get_settings()
    
    logger.info("creating_ai_analyzer_from_settings")
    
    return AIAnalyzerService(
        api_key=settings.openrouter_api_key,
        model=settings.openrouter_model,
    )
