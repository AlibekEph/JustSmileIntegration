# Синхронизация Приёмов IDENT → AmoCRM

## Обзор

Данная функциональность реализует синхронизацию приёмов из МИС IDENT в AmoCRM согласно техническому заданию. Синхронизация автоматически распределяет пациентов по воронкам и создаёт/обновляет сделки в AmoCRM.

## Ключевые Особенности

### Автоматическое Распределение по Воронкам

- **Первичные приёмы**: Пациенты с 0 завершенных приёмов
- **Повторные приёмы**: Пациенты с 1+ завершенных приёмов

### Иерархия Поиска

Поиск существующих сделок происходит в следующем порядке:

1. **ID Приёма** (высший приоритет) - поиск в активных этапах обеих воронок
2. **Порядковый номер в МИС** - поиск среди сделок с пустым ID Приёма
3. **Номер телефона** (низший приоритет) - поиск среди контактов

### Исключенные Этапы

Поиск НЕ производится в этапах:
- "Успешно завершена"
- "Не реализована"

## Архитектура

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   IDENT DB      │    │ Reception Sync  │    │   AmoCRM API    │
│                 │    │    Manager      │    │                 │
│ ┌─────────────┐ │    │                 │    │ ┌─────────────┐ │
│ │ Receptions  │ │────│ 1. Find existing│────│ │ Pipelines   │ │
│ │ Patients    │ │    │ 2. Determine    │    │ │ - Primary   │ │
│ │ Persons     │ │    │    funnel       │    │ │ - Secondary │ │
│ └─────────────┘ │    │ 3. Create/Update│    │ └─────────────┘ │
└─────────────────┘    │    deals        │    └─────────────────┘
                       └─────────────────┘
```

## Основные Компоненты

### 1. ReceptionSyncManager

Основной класс для управления синхронизацией приёмов:

```python
from src.reception_sync import ReceptionSyncManager

# Инициализация
sync_manager = ReceptionSyncManager(use_mock=False)

# Синхронизация всех приёмов
results = sync_manager.sync_receptions()

# Синхронизация изменений с определённого времени
results = sync_manager.sync_receptions(since=datetime.now() - timedelta(hours=1))

# Синхронизация одного приёма
result = sync_manager.sync_single_reception_by_id(12345)
```

### 2. Расширенный AmoCRM Client

Новые методы для работы с сделками:

```python
# Поиск по ID приёма
result = amocrm.find_deal_by_reception_id(12345)

# Поиск по номеру пациента (с пустым ID приёма)
result = amocrm.find_deal_by_patient_number("PAT001")

# Поиск контакта по телефону с проверкой активных сделок
result = amocrm.find_contact_by_phone("+79161234567")

# Создание сделки
deal_id = amocrm.create_deal(deal_data, contact_id)
```

### 3. Модели Данных

#### Reception
```python
@dataclass
class Reception:
    id_reception: int
    id_patient: int
    reception_datetime: datetime
    status: ReceptionStatus
    doctor_name: Optional[str] = None
    service_name: Optional[str] = None
    cost: Optional[float] = None
    
    def get_search_keys(self) -> Dict[str, Any]:
        """Возвращает ключи для поиска в AmoCRM."""
    
    def to_amocrm_deal_format(self, pipeline_id: int, stage_id: int) -> Dict[str, Any]:
        """Конвертирует в формат сделки AmoCRM."""
```

#### ContactSearchResult
```python
@dataclass
class ContactSearchResult:
    contact_id: Optional[int] = None
    deal_id: Optional[int] = None
    pipeline_id: Optional[int] = None
    stage_id: Optional[int] = None
    reception_id: Optional[int] = None
    patient_number: Optional[str] = None
    phone: Optional[str] = None
```

## Конфигурация

В `config.py` добавлены новые настройки:

```python
# AmoCRM Configuration
AMOCRM_CONFIG = {
    "primary_pipeline_id": 123,      # ID воронки "Первичные приёмы"
    "secondary_pipeline_id": 456,    # ID воронки "Повторные приёмы"
    "default_stage_id": 789,         # ID этапа по умолчанию
    "excluded_stages": [111, 222],   # Исключенные этапы
    "responsible_user_id": 333       # Ответственный сотрудник
}

# Field Mapping (дополнительные поля)
FIELD_MAPPING = {
    # ... существующие поля ...
    "reception_id": 26,              # ID Приёма
    "reception_date": 27,            # Дата приёма
    "doctor_name": 28,               # Врач
    "service_name": 29,              # Услуга
    "reception_cost": 30,            # Стоимость приёма
    "patient_number": 17             # Порядковый номер пациента
}
```

## Использование

### Командная Строка

```bash
# Синхронизация всех приёмов
python main.py reception-sync

# Тестирование одного приёма
python main.py test-reception 12345

# Запуск сервиса с автоматической синхронизацией
python main.py service

# Просмотр статистики
python main.py stats
```

### Программное Использование

```python
from src.sync import SyncManager

# Полная синхронизация (пациенты + приёмы)
sync_manager = SyncManager()
sync_manager.full_sync()

# Только синхронизация приёмов
sync_manager.incremental_reception_sync()

# Синхронизация одного приёма
success = sync_manager.sync_single_reception(12345)
```

## Логика Синхронизации

### 1. Поиск Существующих Сделок

```python
def _find_existing_deal_or_contact(self, reception):
    # Шаг 1: Поиск по ID Приёма
    if reception_id:
        result = amocrm.find_deal_by_reception_id(reception_id)
        if result:
            return result
    
    # Шаг 2: Поиск по номеру пациента (с пустым ID приёма)
    if patient_number:
        result = amocrm.find_deal_by_patient_number(patient_number)
        if result:
            return result
    
    # Шаг 3: Поиск по телефону
    if phone:
        result = amocrm.find_contact_by_phone(phone)
        if result:
            return result
    
    return None
```

### 2. Определение Воронки

```python
def get_funnel_type(self) -> FunnelType:
    if self.completed_receptions_count == 0:
        return FunnelType.PRIMARY
    else:
        return FunnelType.SECONDARY
```

### 3. Создание/Обновление

```python
if search_result:
    # Обновление существующей сделки
    if search_result.deal_id:
        update_deal(search_result.deal_id, deal_data)
    else:
        # Контакт есть, сделки нет - создаём сделку
        create_deal(deal_data, search_result.contact_id)
else:
    # Создание нового контакта и сделки
    contact_id = create_contact(contact_data)
    deal_id = create_deal(deal_data, contact_id)
```

## Тестирование

### Автоматические Тесты

```bash
# Запуск тестов синхронизации приёмов
python test_reception_integration.py

# Интеграционные тесты
python test_mock_integration.py
```

### Ручное Тестирование

```bash
# Тест подключения к БД
python main.py test-db

# Тест подключения к AmoCRM
python main.py test-amocrm

# Тест синхронизации пациента
python main.py test-patient 123

# Тест синхронизации приёма
python main.py test-reception 456
```

## Мониторинг и Логирование

### Логи Синхронизации

```
2024-01-15 10:30:00 | INFO     | Starting reception synchronization
2024-01-15 10:30:01 | INFO     | Found 25 receptions to sync
2024-01-15 10:30:01 | DEBUG    | Syncing reception 12345 for patient 100
2024-01-15 10:30:02 | DEBUG    | Found deal by reception ID: 12345
2024-01-15 10:30:02 | INFO     | Updated deal with ID: 67890
2024-01-15 10:30:05 | INFO     | Reception sync completed: 23 successful, 2 failed
2024-01-15 10:30:05 | INFO     | Funnel distribution: 15 primary, 8 secondary
```

### Статистика

```python
stats = sync_manager.get_sync_statistics()
# {
#     "last_reception_sync": "2024-01-15 10:30:00",
#     "total_receptions": 150,
#     "primary_funnel_count": 89,
#     "secondary_funnel_count": 61,
#     "sync_errors": []
# }
```

## Расписание Синхронизации

В сервисном режиме:

- **Синхронизация пациентов**: каждые 5 минут (настраивается)
- **Синхронизация приёмов**: каждую минуту
- **Глубокая синхронизация**: 2 раза в день (утром и вечером)

## Обработка Ошибок

### Типичные Ошибки

1. **Пациент не найден**: `SyncResult.error = "Patient not found"`
2. **Ошибка создания контакта**: `SyncResult.error = "Failed to create contact"`
3. **Ошибка создания сделки**: `SyncResult.error = "Failed to create deal"`
4. **Ошибка API AmoCRM**: Автоматическая попытка обновления токена

### Retry Logic

- Автоматическое обновление токенов при 401 ошибке
- Соблюдение rate limits AmoCRM
- Batch обработка для уменьшения нагрузки

## Производительность

### Оптимизации

- Batch запросы к AmoCRM (до 50 записей)
- Rate limiting (7 запросов в секунду)
- Инкрементальная синхронизация по времени изменения
- Кеширование результатов поиска

### Метрики

- Время полной синхронизации: ~30 сек для 1000 приёмов
- Время инкрементальной синхронизации: ~5 сек для 50 приёмов
- Потребление памяти: ~50MB для 1000 записей

## Безопасность

- Токены AmoCRM хранятся в Redis с TTL
- Автоматическое обновление refresh токенов
- Логирование без персональных данных
- Валидация входящих данных

## Развёртывание

См. документы:
- `PRODUCTION_SETUP.md` - настройка продакшена
- `QUICK_START.md` - быстрый старт
- `docker-compose.yml` - контейнеризация

## Поддержка

При возникновении проблем:

1. Проверьте логи: `tail -f logs/app.log`
2. Проверьте статус: `python main.py stats`
3. Протестируйте подключения: `python main.py test-db && python main.py test-amocrm`
4. Запустите диагностику: `python test_reception_integration.py` 