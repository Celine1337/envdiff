<p align="center"><img src="docs/style/hero.png" alt="envdiff — проверка дрейфа конфигурации .env" width="100%"></p>

<p align="center">
  <a href="README.md"><img src="docs/style/pill-en.png" alt="README EN" height="42"></a>
  <a href="https://github.com/Celine1337/envdiff/releases"><img src="docs/style/pill-release.png" alt="Releases" height="42"></a>
  <a href="https://github.com/Celine1337/envdiff/actions/workflows/ci.yml"><img src="docs/style/pill-ci.png" alt="CI" height="42"></a>
  <a href="LICENSE"><img src="docs/style/pill-license.png" alt="MIT" height="42"></a>
</p>

<img src="docs/style/sec-about-ru.png" alt="О проекте" width="100%">

`.env`-файлы расползаются: staging теряет ключ, production переименовывает
токен — и приложение падает в 3 ночи из-за отсутствующей настройки. envdiff
сравнивает два `.env`-файла семантически — порядок, комментарии и стиль
кавычек не важны — и показывает, что именно разъехалось:

- MISSING — ключи есть в `A.env`, но нет в `B.env`;
- EXTRA — ключи есть в `B.env`, но нет в `A.env`;
- CHANGED — ключи в обоих файлах, значения различаются.

Один файл, только стандартная библиотека, Python 3.9+, без сети.

<img src="docs/style/sec-features-ru.png" alt="Возможности" width="100%">

- Парсит строки `KEY=VALUE`: пустые строки и `#`-комментарии игнорируются,
  необязательный префикс `export `, одинарные/двойные кавычки, inline-комментарии
  вне кавычек.
- Ключи, похожие на секреты (имя содержит `SECRET`, `TOKEN`, `PASSWORD`,
  `PASSWD`, `KEY`, `API` или `CREDENTIAL`, без учёта регистра), маскируются как
  `****` и в тексте, и в JSON; `--show-values` раскрывает значения.
- `--ignore KEY[,KEY...]` (можно повторять) — пропустить шумные ключи.
- `--json` — машинный отчёт: `{missing, extra, changed:[{key,old,new}]}`.
- Коды возврата для CI-гейта: `0` — дрейфа нет, `1` — дрейф найден,
  `2` — плохой ввод/путь.
- Цветные ANSI-заголовки групп, `--no-color` и `NO_COLOR`.

<img src="docs/style/sec-checks-ru.png" alt="Проверки" width="100%">

| Группа | Смысл |
|--------|-------|
| MISSING | ключ есть в `A.env`, отсутствует в `B.env` |
| EXTRA | ключ есть в `B.env`, отсутствует в `A.env` |
| CHANGED | ключ в обоих файлах, значения различаются |

| Правило ввода | Поведение |
|---------------|-----------|
| пустые строки, `#`-комментарии | игнорируются |
| `export KEY=VALUE` | префикс `export ` снимается |
| `KEY="a b"`, `KEY='a b'` | кавычки снимаются, пробелы внутри сохраняются |
| `KEY=val # note` | inline-комментарий вне кавычек отбрасывается |
| повтор `KEY` в одном файле | побеждает последнее значение |
| строка без `KEY=`, незакрытая кавычка | ошибка, код `2` |
| нечитаемый путь / каталог | ошибка, код `2` |

<img src="docs/style/sec-stack-ru.png" alt="Технологии" width="100%">

<img src="docs/style/chips.png" alt="Python 3.9+, unittest, JSON; GitHub Actions, Pillow, argparse" width="100%">

<img src="docs/style/sec-quick-ru.png" alt="Быстрый старт" width="100%">

```console
$ python envdiff.py a.env b.env
$ python envdiff.py a.env b.env --ignore HOST,PORT
$ python envdiff.py a.env b.env --show-values
$ python envdiff.py a.env b.env --json
```

```
a.env -> b.env
MISSING (1)
  - LEGACY_FLAG
EXTRA (1)
  + NEW_RELIC
CHANGED (2)
  ~ API_TOKEN: **** -> ****
  ~ HOST: localhost -> 0.0.0.0
```

Коды возврата: `0` — дрейфа нет, `1` — дрейф найден, `2` — нечитаемый путь
или сломанная строка.

Ограничения сознательные: построчный парсер — без многострочных значений,
без раскрытия `${VAR}`, без пробелов вокруг `=`; всё после закрывающей
кавычки считается комментарием; поиск секретов — эвристика по подстроке
(`MONKEY` попадает под `KEY`); сравнение семантическое, не побайтовый diff.

<img src="docs/style/sec-shots-ru.png" alt="Скриншоты" width="100%">

![отчёт о дрейфе](docs/drift.png)

![чистый отчёт](docs/clean.png)

<img src="docs/style/sec-tests-ru.png" alt="Тесты" width="100%">

```console
$ python -m unittest discover -s tests -v
```

44 теста покрывают парсинг, группы дрейфа, маскировку секретов, форму JSON и
коды возврата. Фикстуры — крошечные временные файлы, все картинки
перегенерируются:

```console
$ pip install pillow
$ python tools/make_shots.py      # docs/drift.png, docs/clean.png
$ python tools/make_style.py tools/style.json docs/style
```

<img src="docs/style/stats.png" alt="44 теста, 3 ОС в CI, v1.0.0" width="100%">

[MIT](LICENSE) © Celine1337