# Winestyle: экспорт результатов ИИ и создание чернового PR

GitHub не видит незакоммиченные файлы в рабочем окружении другого агента. Сначала сохраните результаты там, где они были собраны. Не считайте цену проверенной без конкретной карточки товара и даты наблюдения.

## 1. Формат импорта цен

Скрипт scripts/import_winestyle.py принимает JSON-массив, объект с ключом observations или JSONL (один объект в строке).

| Поле | Требование |
| --- | --- |
| url | Точная HTTPS-ссылка на товар из data/wines.json без параметров |
| source_url | Та же карточка WineStyle, на которой непосредственно проверена цена |
| currency | RUB |
| checked_at | Дата YYYY-MM-DD |
| price_rub | Целая цена в рублях |
| price_text | Текст видимой цены, например 3 490 ₽ |
| regular_price_rub | Явно показанная цена до скидки или null |
| regular_price_text | Текст обычной цены или null |

Синтетический пример **не для импорта**:

~~~json
{
  "observations": [
    {
      "url": "https://spb.winestyle.ru/products/Example-2021.html",
      "source_url": "https://spb.winestyle.ru/products/Example-2021.html",
      "currency": "RUB",
      "checked_at": "2026-11-22",
      "price_rub": 3490,
      "price_text": "3 490 ₽",
      "regular_price_rub": 4190,
      "regular_price_text": "4 190 ₽"
    }
  ]
}
~~~

Нельзя выводить обычную цену из процента скидки, смешивать регионы и винтажи или считать сниппет поисковика прямым доказательством цены. Не обходить блокировки, CAPTCHA, robots.txt и условия сайта. Рабочий регион каталога - Санкт-Петербург. Если обычная цена на карточке не указана, поля regular_price_* должны быть null.

## 2. Безопасный импорт

В корне репозитория:

~~~bash
python scripts/import_winestyle.py agent-output/winestyle-prices.json
python scripts/import_winestyle.py agent-output/winestyle-prices.json --apply
python scripts/validate_catalog.py
python scripts/validate_ratings.py
python -m unittest discover -s scripts -p 'test_import_winestyle.py'
git diff --check
git diff -- data/wines.json
~~~

Первая команда - read-only dry-run. Вторая изменяет data/wines.json после полной валидации. Принимаются только точные URL активного каталога, валюты RUB, даты не старше семи дней. Неподтверждённые, будущие, слишком старые, повторяющиеся или конфликтующие данные отвергаются. Ошибка любой строки отменяет весь импорт. Исторические reference_* сохраняются. При отсутствии явно указанной обычной цены не сохраняется старое предположение о скидке.

Исходные выгрузки агента храните локально в agent-output/ (каталог в .gitignore), а не в публичном репозитории. Проверка схемы не заменяет ручной сверки с первоисточником перед review.

## 3. Как создать PR из наработок уже работающего агента

В терминале именно того рабочего окружения, где находятся изменения:

~~~bash
git status --short
git branch --show-current
git remote -v
git fetch origin
~~~

Если вы ещё на main и изменения не закоммичены, сначала создайте отдельную ветку:

~~~bash
git switch -c data/winestyle-agent-2026-11-22
~~~

Если агент уже создал отдельную ветку, оставайтесь в ней. Когда данные проверены, добавьте только конкретные проверенные файлы:

~~~bash
git add data/wines.json
git diff --cached --check
git diff --cached --stat
git commit -m "data: import verified Winestyle price observations"
git push -u origin HEAD
~~~

Если агент собирал не цены, а другие атрибуты вина, добавляйте только действительно изменённые и проверенные файлы вместо data/wines.json. Не используйте без разбора git add .: исходные выгрузки и личные файлы в PR не нужны.

Откройте https://github.com/dancyuser/wine-atlas/compare/main... и выберите опубликованную ветку. Нажмите Create pull request и выберите Create draft pull request. Или примените GitHub CLI:

~~~bash
gh pr create --base main --head "$(git branch --show-current)" --draft \
  --title "data: импорт проверенных данных Winestyle" \
  --body "Точные URL, даты наблюдений, доказанные цены; неопределённые данные исключены."
~~~

GitHub Actions выполняет проверку только после Ready for review; черновики не расходуют минуты на тестовые задания. Не выполняйте merge до проверки диффа.

Если git status пуст и git log origin/main..HEAD --oneline ничего не показывает, в этом checkout нет новых изменений. Найдите прежнее рабочее окружение агента (Codex/IDE, другая копия репозитория), экспортируйте данные или diff/patch. Из текстового ответа ИИ GitHub автоматически PR не создаст.
