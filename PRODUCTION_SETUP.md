# 🚀 Инструкция по запуску в продакшене: IDENT ↔ AmoCRM

## 📋 Что уже готово ✅

- ✅ Полный интеграционный модуль
- ✅ Mock AmoCRM клиент (протестирован)
- ✅ Модели данных для всех 26 полей
- ✅ Логика синхронизации
- ✅ Docker контейнеризация
- ✅ Тестовая база данных

## 🎯 Что нужно сделать для продакшена

### 1. Настройка OAuth 2.0 в AmoCRM

#### 1.1. Создание интеграции в AmoCRM

1. **Войдите в AmoCRM** и перейдите в настройки
2. **Откройте раздел "Интеграции"**:
   - Настройки → Интеграции → Создать интеграцию
3. **Заполните данные интеграции**:
   - Название: "IDENT Integration"
   - Описание: "Синхронизация пациентов из системы IDENT"
   - Redirect URI: `http://your-server.com:8080/callback`

**Документация AmoCRM**: [Создание интеграции](https://www.amocrm.ru/developers/content/oauth/step-by-step)

#### 1.2. Получение client_id и client_secret

После создания интеграции вы получите:
- **Client ID** (публичный ключ)
- **Client Secret** (секретный ключ)

**Сохраните эти данные** - они понадобятся для настройки .env файла.

### 2. Создание кастомных полей в AmoCRM

Необходимо создать **26 кастомных полей** для хранения данных пациентов из IDENT.

#### 2.1. Создание полей через интерфейс AmoCRM

1. **Перейдите в настройки полей**:
   - Настройки → Поля → Контакты → Добавить поле

2. **Создайте следующие поля**:

| № | Название поля | Тип поля | Обязательное | Описание |
|---|---------------|----------|--------------|----------|
| 1 | ID пациента IDENT | Текст | Да | Уникальный ID из системы IDENT |
| 2 | Возраст | Число | Нет | Возраст пациента |
| 3 | Пол | Список | Нет | Мужской/Женский/Не указан |
| 4 | Дата рождения | Дата | Нет | Дата рождения пациента |
| 5 | Номер карты | Текст | Нет | Номер карты пациента |
| 6 | Комментарий IDENT | Текст (многострочный) | Нет | Комментарии из IDENT |
| 7 | Номер пациента | Текст | Нет | Внутренний номер пациента |
| 8 | Статус пациента | Список | Нет | Активный/Архивный/Удален |
| 9 | Причина архивирования | Текст | Нет | Причина архивирования |
| 10 | Филиал | Текст | Нет | Филиал клиники |
| 11 | Город | Текст | Нет | Город проживания |
| 12 | ИНН | Текст | Нет | ИНН пациента |
| 13 | СНИЛС | Текст | Нет | СНИЛС пациента |
| 14 | Паспорт | Текст | Нет | Паспортные данные |
| 15 | Дата первого визита | Дата | Нет | Дата первого посещения |
| 16 | Количество визитов | Число | Нет | Общее количество визитов |
| 17 | Сумма всех визитов | Число | Нет | Общая сумма лечения |
| 18 | Скидка | Число | Нет | Процент скидки |
| 19 | Аванс | Число | Нет | Сумма аванса |
| 20 | Долг | Число | Нет | Сумма долга |
| 21 | SMS отказ | Чекбокс | Нет | Отказ от SMS уведомлений |
| 22 | Дата изменения | Дата и время | Нет | Последнее изменение в IDENT |
| 23 | Отчество | Текст | Нет | Отчество пациента |
| 24 | Дополнительный телефон | Телефон | Нет | Дополнительный номер |
| 25 | Адрес | Текст | Нет | Адрес пациента |
| 26 | Источник | Текст | Нет | Источник привлечения |

#### 2.2. Получение ID полей

После создания полей необходимо получить их ID:

1. **Через API AmoCRM**:
```bash
curl -X GET "https://your-subdomain.amocrm.ru/api/v4/contacts/custom_fields" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

2. **Или через интерфейс**: В настройках полей наведите на поле - ID отобразится в URL

**Документация**: [Кастомные поля](https://www.amocrm.ru/developers/content/crm_platform/custom-fields)

### 3. Первичная OAuth авторизация

#### 3.1. Настройка .env файла

Скопируйте `.env_example` в `.env` и заполните:

```bash
cp .env_example .env
```

Отредактируйте `.env`:
```env
# AmoCRM Configuration
AMOCRM_SUBDOMAIN=your_subdomain
AMOCRM_CLIENT_ID=your_client_id_here
AMOCRM_CLIENT_SECRET=your_client_secret_here
AMOCRM_REDIRECT_URI=http://your-server.com:8080/callback

# Database Configuration
DB_HOST=your_ident_db_host
DB_PORT=1433
DB_NAME=PZ
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_DRIVER={ODBC Driver 18 for SQL Server}

# Other settings
USE_MOCK_AMOCRM=false
LOG_LEVEL=INFO
```

#### 3.2. Получение authorization code

1. **Запустите OAuth сервер**:
```bash
docker compose --profile auth up auth
```

2. **Откройте URL авторизации**:
```
https://your-subdomain.amocrm.ru/oauth?mode=request&client_id=YOUR_CLIENT_ID&redirect_uri=http://your-server.com:8080/callback&response_type=code
```

3. **Подтвердите доступ** в AmoCRM

4. **Получите код** - он будет передан на ваш redirect_uri

**Документация**: [OAuth авторизация](https://www.amocrm.ru/developers/content/oauth/step-by-step)

### 4. Обновление маппинга полей

#### 4.1. Обновите src/models.py

После получения ID кастомных полей обновите маппинг в `src/models.py`:

```python
def to_amocrm_format(self) -> Dict[str, Any]:
    """Convert patient to AmoCRM format."""
    custom_fields = [
        {'field_id': 123, 'values': [{'value': str(self.id_patient)}]},  # ID пациента IDENT
        {'field_id': 124, 'values': [{'value': self.person.age or 0}]},  # Возраст
        # ... добавьте все остальные поля с реальными ID
    ]
```

#### 4.2. Используйте готовую библиотеку (опционально)

Можно использовать готовую библиотеку [amocrm_api](https://github.com/Krukov/amocrm_api) от Krukov:

```bash
pip install amocrm_api
```

Пример использования:
```python
from amocrm.v2 import tokens, Contact

# Настройка токенов
tokens.default_token_manager(
    client_id="your-client-id",
    client_secret="your-client-secret",
    subdomain="your-subdomain",
    redirect_url="http://your-server.com:8080/callback",
    storage=tokens.FileTokensStorage(),
)

# Создание контакта
contact = Contact(
    first_name="Иван",
    last_name="Иванов",
    phone="+7 925 123-45-67"
)
contact.create()
```

**Документация библиотеки**: [amocrm_api на GitHub](https://github.com/Krukov/amocrm_api)

### 5. Настройка базы данных IDENT

#### 5.1. Установка ODBC драйверов

**На Ubuntu/Debian**:
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/ubuntu/20.04/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update
ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

**На CentOS/RHEL**:
```bash
curl https://packages.microsoft.com/config/rhel/8/prod.repo > /etc/yum.repos.d/mssql-release.repo
yum remove unixODBC-utf16 unixODBC-utf16-devel
ACCEPT_EULA=Y yum install -y msodbcsql18
```

#### 5.2. Тестирование подключения

```bash
# Тест подключения к IDENT БД
docker compose exec sync python main.py test-db
```

### 6. Запуск в продакшене

#### 6.1. Сборка и запуск

```bash
# Сборка образа
docker compose build

# Запуск синхронизации
docker compose up -d sync

# Проверка логов
docker compose logs -f sync
```

#### 6.2. Тестирование отдельного пациента

```bash
# Тест синхронизации одного пациента
docker compose exec sync python main.py test --patient-id 1
```

#### 6.3. Мониторинг

```bash
# Просмотр логов
docker compose logs sync

# Проверка статуса
docker compose ps

# Перезапуск при необходимости
docker compose restart sync
```

### 7. Настройка расписания синхронизации

Интеграция уже настроена на:
- **Инкрементальная синхронизация**: каждые 2 минуты
- **Глубокая синхронизация**: дважды в день (8:00 и 20:00)

Изменить расписание можно в `.env`:
```env
SYNC_INTERVAL_MINUTES=5  # Изменить интервал
DEEP_SYNC_HOUR_MORNING=9  # Изменить утреннее время
DEEP_SYNC_HOUR_EVENING=21  # Изменить вечернее время
```

## 📚 Полезные ссылки

### Документация AmoCRM:
- [Главная страница для разработчиков](https://www.amocrm.ru/developers/)
- [OAuth 2.0 авторизация](https://www.amocrm.ru/developers/content/oauth/step-by-step)
- [API контактов](https://www.amocrm.ru/developers/content/crm_platform/contacts-api)
- [Кастомные поля](https://www.amocrm.ru/developers/content/crm_platform/custom-fields)
- [Лимиты API](https://www.amocrm.ru/developers/content/crm_platform/rate-limits)

### Готовые библиотеки:
- [amocrm_api (Krukov)](https://github.com/Krukov/amocrm_api) - Рекомендуемая библиотека
- [PyPI: amocrm-api](https://pypi.org/project/amocrm-api/) - Установка через pip

### Microsoft SQL Server:
- [Установка ODBC драйверов](https://docs.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)

## 🔧 Решение проблем

### Проблема: "Invalid grant" при OAuth
**Решение**: Проверьте правильность redirect_uri и повторите авторизацию

### Проблема: "Field not found" при создании контакта
**Решение**: Убедитесь, что все кастомные поля созданы и ID правильные

### Проблема: Подключение к БД IDENT
**Решение**: Проверьте ODBC драйверы и connection string

### Проблема: Rate limit exceeded
**Решение**: AmoCRM имеет лимит 7 запросов в секунду. Увеличьте BATCH_SIZE в .env

## ✅ Чек-лист готовности

- [ ] Создана интеграция в AmoCRM
- [ ] Получены client_id и client_secret
- [ ] Созданы 26 кастомных полей
- [ ] Получены ID всех полей
- [ ] Обновлен маппинг в src/models.py
- [ ] Настроен .env файл
- [ ] Выполнена OAuth авторизация
- [ ] Установлены ODBC драйверы
- [ ] Настроено подключение к IDENT БД
- [ ] Протестирована синхронизация одного пациента
- [ ] Запущена полная синхронизация
- [ ] Настроен мониторинг логов

## 🎉 Заключение

После выполнения всех шагов интеграция будет полностью готова к работе в продакшене. Все пациенты из IDENT будут автоматически синхронизироваться с AmoCRM согласно настроенному расписанию.

**Время на настройку**: 2-4 часа  
**Сложность**: Средняя  
**Поддержка**: Все компоненты протестированы и готовы к работе 