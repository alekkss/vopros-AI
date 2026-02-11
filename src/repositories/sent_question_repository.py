"""
Репозиторий для работы с базой данных отправленных вопросов.

Реализует паттерн Repository для SQLite, обеспечивая
абстракцию над операциями с БД.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from src.config.logger import get_logger
from src.models.sent_question import SentQuestion

logger = get_logger(__name__)


class SentQuestionRepository:
    """
    Репозиторий для отслеживания отправленных вопросов.
    
    Использует SQLite для хранения информации о вопросах,
    которые уже были отправлены в бот, чтобы избежать дубликатов.
    
    Следует принципам:
    - Single Responsibility: только работа с БД отправленных вопросов
    - Open/Closed: можно заменить SQLite на другую БД
    - Dependency Inversion: изолирует детали работы с БД
    """
    
    def __init__(self, db_path: str | Path) -> None:
        """
        Инициализация репозитория.
        
        Args:
            db_path: Путь к файлу SQLite базы данных
        """
        self._db_path = Path(db_path)
        self._ensure_db_directory()
        self._init_database()
        
        logger.info(
            "sent_question_repository_initialized",
            db_path=str(self._db_path),
        )
    
    def _ensure_db_directory(self) -> None:
        """
        Создать директорию для БД, если её нет.
        
        Raises:
            OSError: При проблемах с созданием директории
        """
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            logger.debug(
                "db_directory_ensured",
                directory=str(self._db_path.parent),
            )
        except OSError as e:
            logger.error(
                "db_directory_creation_error",
                directory=str(self._db_path.parent),
                error=str(e),
            )
            raise
    
    def _init_database(self) -> None:
        """
        Инициализировать базу данных и создать таблицы.
        
        Создаёт таблицу sent_questions с индексами, если она не существует.
        Метод идемпотентен — повторный вызов безопасен.
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                
                # Создаём таблицу
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sent_questions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id TEXT NOT NULL,
                        message_id INTEGER NOT NULL,
                        question_hash TEXT NOT NULL,
                        sent_at TIMESTAMP NOT NULL,
                        UNIQUE(chat_id, message_id)
                    )
                """)
                
                # Создаём индексы для быстрого поиска
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sent_at 
                    ON sent_questions(sent_at)
                """)
                
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chat_message 
                    ON sent_questions(chat_id, message_id)
                """)
                
                conn.commit()
                
                logger.info("database_initialized", db_path=str(self._db_path))
                
        except sqlite3.Error as e:
            logger.error(
                "database_initialization_error",
                db_path=str(self._db_path),
                error=str(e),
            )
            raise
    
    def is_already_sent(
        self,
        chat_id: int | str,
        message_id: int,
    ) -> bool:
        """
        Проверить, был ли вопрос уже отправлен в бот.
        
        Проверка по уникальной паре (chat_id, message_id).
        
        Args:
            chat_id: ID чата источника
            message_id: ID сообщения в чате
            
        Returns:
            True если вопрос уже был отправлен, False в противном случае
            
        Example:
            >>> repository.is_already_sent(-1001234567890, 12345)
            False
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM sent_questions 
                    WHERE chat_id = ? AND message_id = ?
                    """,
                    (str(chat_id), message_id),
                )
                
                count = cursor.fetchone()[0]
                is_sent = count > 0
                
                logger.debug(
                    "checked_if_already_sent",
                    chat_id=chat_id,
                    message_id=message_id,
                    is_sent=is_sent,
                )
                
                return is_sent
                
        except sqlite3.Error as e:
            logger.error(
                "is_already_sent_check_error",
                chat_id=chat_id,
                message_id=message_id,
                error=str(e),
            )
            # В случае ошибки БД возвращаем False (лучше отправить дубликат, чем потерять вопрос)
            return False
    
    def mark_as_sent(self, sent_question: SentQuestion) -> bool:
        """
        Пометить вопрос как отправленный в бот.
        
        Сохраняет информацию о вопросе в БД. Использует UNIQUE constraint
        для предотвращения дубликатов по (chat_id, message_id).
        
        Args:
            sent_question: Объект отправленного вопроса
            
        Returns:
            True если успешно сохранено, False при ошибке
            
        Example:
            >>> from datetime import datetime
            >>> sent = SentQuestion(
            ...     chat_id=-1001234567890,
            ...     message_id=12345,
            ...     question_hash="abc123...",
            ...     sent_at=datetime.now()
            ... )
            >>> repository.mark_as_sent(sent)
            True
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO sent_questions 
                    (chat_id, message_id, question_hash, sent_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        str(sent_question.chat_id),
                        sent_question.message_id,
                        sent_question.question_hash,
                        sent_question.sent_at.isoformat(),
                    ),
                )
                
                conn.commit()
                
                logger.info(
                    "question_marked_as_sent",
                    chat_id=sent_question.chat_id,
                    message_id=sent_question.message_id,
                )
                
                return True
                
        except sqlite3.Error as e:
            logger.error(
                "mark_as_sent_error",
                chat_id=sent_question.chat_id,
                message_id=sent_question.message_id,
                error=str(e),
            )
            return False
    
    def cleanup_old_records(self, days_to_keep: int = 30) -> int:
        """
        Удалить записи старше указанного количества дней.
        
        Это помогает поддерживать размер БД в разумных пределах
        и ускоряет работу запросов.
        
        Args:
            days_to_keep: Сколько дней хранить записи (по умолчанию 30)
            
        Returns:
            Количество удалённых записей
            
        Example:
            >>> deleted_count = repository.cleanup_old_records(30)
            >>> print(f"Удалено {deleted_count} старых записей")
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute(
                    """
                    DELETE FROM sent_questions 
                    WHERE sent_at < ?
                    """,
                    (cutoff_date.isoformat(),),
                )
                
                deleted_count = cursor.rowcount
                conn.commit()
                
                logger.info(
                    "old_records_cleaned_up",
                    days_to_keep=days_to_keep,
                    deleted_count=deleted_count,
                    cutoff_date=cutoff_date.isoformat(),
                )
                
                return deleted_count
                
        except sqlite3.Error as e:
            logger.error(
                "cleanup_old_records_error",
                days_to_keep=days_to_keep,
                error=str(e),
            )
            return 0
    
    def get_statistics(self) -> dict[str, int]:
        """
        Получить статистику по отправленным вопросам.
        
        Полезно для мониторинга и отладки.
        
        Returns:
            Словарь со статистикой:
            - total: Общее количество записей
            - last_24h: Записей за последние 24 часа
            - last_7d: Записей за последние 7 дней
            
        Example:
            >>> stats = repository.get_statistics()
            >>> print(f"Всего отправлено: {stats['total']}")
        """
        try:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                
                # Общее количество
                cursor.execute("SELECT COUNT(*) FROM sent_questions")
                total = cursor.fetchone()[0]
                
                # За последние 24 часа
                cutoff_24h = (datetime.now() - timedelta(hours=24)).isoformat()
                cursor.execute(
                    "SELECT COUNT(*) FROM sent_questions WHERE sent_at >= ?",
                    (cutoff_24h,),
                )
                last_24h = cursor.fetchone()[0]
                
                # За последние 7 дней
                cutoff_7d = (datetime.now() - timedelta(days=7)).isoformat()
                cursor.execute(
                    "SELECT COUNT(*) FROM sent_questions WHERE sent_at >= ?",
                    (cutoff_7d,),
                )
                last_7d = cursor.fetchone()[0]
                
                stats = {
                    "total": total,
                    "last_24h": last_24h,
                    "last_7d": last_7d,
                }
                
                logger.debug("statistics_retrieved", **stats)
                
                return stats
                
        except sqlite3.Error as e:
            logger.error("get_statistics_error", error=str(e))
            return {"total": 0, "last_24h": 0, "last_7d": 0}


def create_sent_question_repository_from_settings() -> SentQuestionRepository:
    """
    Создать репозиторий на основе настроек.
    
    Функция-хелпер для быстрого создания репозитория
    с автоматической загрузкой конфигурации.
    
    Returns:
        Настроенный репозиторий
        
    Raises:
        ConfigurationError: При ошибках в конфигурации
        
    Example:
        >>> repository = create_sent_question_repository_from_settings()
        >>> repository.is_already_sent(-1001234567890, 12345)
        False
    """
    from src.config.settings import get_settings
    
    settings = get_settings()
    
    logger.info("creating_sent_question_repository_from_settings")
    
    return SentQuestionRepository(db_path=settings.db_path)