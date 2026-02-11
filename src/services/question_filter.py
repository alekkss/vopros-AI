"""
Сервис фильтрации вопросов из сообщений.

Содержит бизнес-логику определения реальных вопросов
и отсеивания рекламы, риторики, приветствий.
"""

import re
from typing import Final

from src.config.logger import get_logger

logger = get_logger(__name__)


class QuestionFilterService:
    """
    Сервис для фильтрации и валидации вопросов.
    
    Анализирует текст сообщения и определяет, является ли
    оно реальным вопросом, требующим ответа эксперта.
    
    Следует принципам:
    - Single Responsibility: только фильтрация вопросов
    - Open/Closed: легко добавить новые правила фильтрации
    """
    
    # Паттерны для риторических вопросов
    RHETORICAL_PATTERNS: Final[list[str]] = [
        r'ваше мнение', r'что думаете', r'интересно.*мнение',
        r'зачем.*собрались', r'как так получилось', r'что это значит',
        r'в чем суть', r'в чем смысл',
    ]
    
    # Паттерны для рекламы и спама
    SPAM_PATTERNS: Final[list[str]] = [
        r'сотрудничество', r'предлагаю', r'услуги', r'гаранти',
        r'кейсы', r'бизнес.*авито', r'по договору',
        r'привлечен\w*.*клиент',
    ]
    
    # Эмодзи, часто используемые в рекламе
    SPAM_EMOJI: Final[str] = r'[🤝🙌🏻👋🚀🤩😂😅😉😀😊👍👏🙏🔥📌]'
    
    # Паттерны бесполезных вопросов
    USELESS_PATTERNS: Final[list[str]] = [
        r'какое.*отношение.*имеет.*к.*диалогу\??',
        r'к.*нашему.*разговору\??',
        r'что это значит',
        r'просто интересно',
        r'уточнить.*контекст',
        r'при чем тут',
    ]
    
    # Паттерны неинтересных сообщений
    BORING_PATTERNS: Final[list[str]] = [
        r'понедельник', r'^всем\s*привет', r'добр(ый|ого)',
        r'доброе утро', r'удачи', r'#', r'завелся', r'вдохновени',
        r'дай(те)? совет', r'мотиваци', r'успеха', r'подпиш',
        r'как дела', r'работает кто', r'есть кто', r'всем приветик',
        r'кого нет', r'кого добавить', r'без темы', r'на подумать',
        r'почти вопрос', r'кстати',
    ]
    
    # Паттерны реальных вопросов
    QUESTION_PATTERNS: Final[list[str]] = [
        r'(как|что|где|когда|почему|зачем|кто|какой|кому|сколько|нужно ли|стоит ли)[^\.\!\?]*\?',
        r'подскажите', r'посоветуйте',
        r'может (кто|кто-нибудь|у кого)',
        r'\w+\?',
    ]
    
    # Паттерны исключений
    EXCLUSION_PATTERNS: Final[list[str]] = [
        r'(lol|ахах|прикол|шутка|ржу|😂|😆|🤔|😅|😜|😏|😎|😉|бот|ушёл|отдыхать|устал)',
        r'^[^а-яА-Я]*$',
        r'^(класс|понятно|ясно|спасибо).{,12}$',
    ]
    
    def __init__(self) -> None:
        """Инициализация сервиса фильтрации."""
        logger.info("question_filter_service_initialized")
    
    def is_advertising(self, text: str) -> bool:
        """
        Проверяет, является ли сообщение рекламой.
        
        Args:
            text: Текст сообщения
            
        Returns:
            True если сообщение рекламное, False в противном случае
        """
        text_lower = text.lower()
        
        # Проверка по паттернам спама
        for pattern in self.SPAM_PATTERNS:
            if re.search(pattern, text_lower):
                logger.debug("message_is_spam", pattern=pattern)
                return True
        
        # Подсчет спам-эмодзи
        emoji_count = len(re.findall(self.SPAM_EMOJI, text))
        if emoji_count > 3:
            logger.debug("message_has_many_emoji", count=emoji_count)
            return True
        
        return False
    
    def is_rhetorical_question(self, text: str) -> bool:
        """
        Проверяет, является ли вопрос риторическим.
        
        Args:
            text: Текст сообщения
            
        Returns:
            True если вопрос риторический, False в противном случае
        """
        text_lower = text.lower()
        
        # Проверка по паттернам риторики
        for pattern in self.RHETORICAL_PATTERNS:
            if re.search(pattern, text_lower):
                logger.debug("message_is_rhetorical", pattern=pattern)
                return True
        
        # Риторика - нет четкого запроса
        if len(text_lower) < 40:
            if text_lower.count('?') > 0:
                if not re.search(r'(как|что|почему|зачем|где)', text_lower):
                    logger.debug("message_is_short_rhetorical")
                    return True
        
        return False
    
    def has_links(self, text: str) -> bool:
        """
        Проверяет, содержит ли сообщение ссылки.
        
        Args:
            text: Текст сообщения
            
        Returns:
            True если содержит ссылки, False в противном случае
        """
        # Паттерны для различных типов ссылок
        link_patterns = [
            r'https?://[^\s]+',           # http:// или https://
            r'www\.[^\s]+',                # www.example.com
            r't\.me/[^\s]+',               # Telegram ссылки
            r'@\w+\.\w+',                  # email-подобные
            r'\w+\.(com|ru|org|net|io|ai|xyz|app)[^\s]*',  # домены
        ]
        
        text_lower = text.lower()
        
        for pattern in link_patterns:
            if re.search(pattern, text_lower):
                logger.debug("message_has_link", pattern=pattern)
                return True
        
        return False

    
    def is_real_question(self, text: str) -> bool:
        """
        Определяет, является ли сообщение реальным вопросом.
        
        Комплексная проверка сообщения на соответствие критериям
        реального вопроса, требующего ответа.
        
        Args:
            text: Текст сообщения
            
        Returns:
            True если сообщение является реальным вопросом
        """
        if not text or not text.strip():
            logger.debug("message_is_empty")
            return False
        
        text_stripped = text.strip()
        text_lower = text_stripped.lower()
        
        # Проверка длины
        if len(text_stripped) < 20 or len(text_stripped) > 700:
            logger.debug("message_length_invalid", length=len(text_stripped))
            return False
        
        # Проверка на наличие ссылок
        if self.has_links(text_stripped):
            logger.debug("message_has_links")
            return False
        
        # Проверка на слишком много переносов строк
        if text_stripped.count('\n') > 3:
            logger.debug("message_has_many_newlines", count=text_stripped.count('\n'))
            return False
        
        # Проверка на бесполезные вопросы
        for pattern in self.USELESS_PATTERNS:
            if re.search(pattern, text_lower):
                logger.debug("message_is_useless", pattern=pattern)
                return False
        
        # Проверка на саморефлексию
        if re.search(r'(я спросил.*\?|ответ:)', text_lower):
            logger.debug("message_is_self_reflection")
            return False
        
        # Проверка на риторику
        if self.is_rhetorical_question(text_stripped):
            logger.debug("message_is_rhetorical_question")
            return False
        
        # Проверка на неинтересные сообщения
        for pattern in self.BORING_PATTERNS:
            if re.search(pattern, text_lower):
                logger.debug("message_is_boring", pattern=pattern)
                return False
        
        # Проверка на наличие вопросительных паттернов
        has_question_pattern = any(
            re.search(pattern, text_lower)
            for pattern in self.QUESTION_PATTERNS
        )
        
        if not has_question_pattern:
            logger.debug("message_has_no_question_pattern")
            return False
        
        # Проверка исключений
        for pattern in self.EXCLUSION_PATTERNS:
            if re.search(pattern, text_lower):
                logger.debug("message_matches_exclusion", pattern=pattern)
                return False
        
        # Проверка на "о себе" без задачи
        if re.search(r'я .*думаю|я .*узнал|я .*считаю', text_lower):
            logger.debug("message_is_about_self")
            return False
        
        logger.debug("message_is_real_question", text_preview=text_stripped[:50])
        return True
    
    def filter_questions(self, messages: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
        """
        Фильтрует список сообщений, оставляя только реальные вопросы.
        
        Args:
            messages: Список кортежей (текст, метаданные)
            
        Returns:
            Отфильтрованный список вопросов
            
        Example:
            >>> messages = [("Привет!", {}), ("Как настроить Python?", {})]
            >>> questions = filter_service.filter_questions(messages)
            >>> len(questions)
            1
        """
        questions = []
        
        for text, metadata in messages:
            if self.is_real_question(text):
                questions.append((text, metadata))
        
        logger.info(
            "messages_filtered",
            total=len(messages),
            questions_found=len(questions),
            filter_rate=f"{len(questions)/len(messages)*100:.1f}%" if messages else "0%",
        )
        
        return questions