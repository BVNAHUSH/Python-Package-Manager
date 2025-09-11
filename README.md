---

# Python Package Manager GUI

<p align="center">
  <strong>English</strong> | <a href="#-українська">Українська</a>
</p>

A powerful, high-performance GUI application for managing Python packages and virtual environments. Built with Tkinter, this tool provides a comprehensive and user-friendly interface for both novice and expert Python developers. It supports `pip` and the lightning-fast `uv` backend for incredible speed gains.


---

## ✨ Key Features

### Core Package Management
- **List & View:** See all installed packages in the current environment with details like version, size, and installation date.
- **Install:** Install packages from PyPI, `requirements.txt`, or `pyproject.toml`.
- **Update:** Easily identify and upgrade outdated packages, either individually or all at once.
- **Uninstall:** Remove packages with a simple click. The app can even safely restart itself to uninstall a dependency it's currently using.
- **Advanced Install:** Force reinstall packages, ignoring caches for a clean setup.
- **Search & Filter:** Instantly search your installed packages and filter to show only the outdated ones.

### 🚀 High-Performance Backend
- **Dual Backend Support:** Seamlessly uses `uv` if available for massive speed improvements in package installation, compilation, and environment creation. Falls back to `pip` if `uv` isn't found.
- **Intelligent Caching:** Caches package lists for near-instant startups.

### 🛠️ Professional Tools
- **Vulnerability Scanner:** Integrates `pip-audit` to scan your environment for packages with known security vulnerabilities.
- **Damaged Package Finder:** A powerful diagnostic tool that can find dependency conflicts, verify file integrity, test imports, and detect missing metadata.
- **Orphaned Package Finder:** Discover and remove packages that are no longer required by any other package, helping you keep your environment clean.
- **Requirements Compiler:** Use `pip-tools` to compile a `requirements.in` file into a fully-pinned `requirements.txt`.

### 🌐 Environment Management
- **Multi-Interpreter Support:** Easily switch between different Python interpreters and virtual environments.
- **Virtual Environment Creator:** Create new virtual environments directly from the UI. With `uv`, you can even specify a Python version and pre-install packages.
- **Drag & Drop:** Simply drop a `requirements.txt` or `pyproject.toml` file onto the window to start the installation process.

## 📜 Script Versions
There are 3 main versions of this script, representing its evolution:
- **V1 (Winter 2024):** The first, older script originally made for personal use.
- **V2 (Summer 2025):** A major update with a focus on improved architecture and new functionality.
- **V2.5 (FINALE+++):** The latest and most powerful version, designed to be the ultimate package management tool.

## 📋 Requirements

- **Python 3.x**
- **Tkinter:** Usually included with standard Python installations.
- **(Recommended) `uv`:** For the best performance. Install it with `pip install uv`. The application will detect it automatically.

### Optional Dependencies
The application will prompt you to install these when you use a feature that requires them:
- `tkinterdnd2`: For drag-and-drop support.
- `packaging`: For more accurate version sorting.
- `tomli`: To read `pyproject.toml` files.
- `pip-audit`: For the vulnerability scanner.
- `pip-tools`: For the requirements compiler.

## 🚀 How to Use

1.  Save the script as a `.py` file (e.g., `package_manager.py`).
2.  Run it from your terminal(or double-click):
    ```bash
    python package_manager.py
    ```
3.  Use the tabs to navigate:
    - **Manage Packages:** View, update, and uninstall your current packages.
    - **Install Packages:** Install new packages from PyPI or local files.
    - **Tools:** Access the vulnerability scanner, damaged/orphaned package finders, and requirements compiler.
    - **Settings:** Manage Python interpreters, configure cache settings, and see application info.

## 📄 License
This project is licensed under the MIT License.

---
---

# <a name="-українська"></a> 🇺🇦 Українська

## Графічний Менеджер Пакетів Python

<p align="center">
  <a href="#">English</a> | <strong>Українська</strong>
</p>

Потужний, високопродуктивний графічний застосунок для керування пакетами та віртуальними середовищами Python. Створений за допомогою Tkinter, цей інструмент надає комплексний та зручний інтерфейс як для початківців, так і для досвідчених розробників Python. Він підтримує `pip` та блискавичний `uv` для неймовірного приросту швидкості.


---

## ✨ Ключові можливості

### Основне керування пакетами
- **Список та перегляд:** Переглядайте всі встановлені пакети в поточному середовищі з деталями: версія, розмір, дата встановлення.
- **Встановлення:** Встановлюйте пакети з PyPI, `requirements.txt` або `pyproject.toml`.
- **Оновлення:** Легко знаходьте та оновлюйте застарілі пакети, окремо або всі разом.
- **Видалення:** Видаляйте пакети одним кліком. Застосунок може навіть безпечно перезапуститися, щоб видалити залежність, яку він використовує.
- **Розширене встановлення:** Примусово перевстановлюйте пакети, ігноруючи кеш, для чистого налаштування.
- **Пошук та фільтрація:** Миттєво шукайте серед встановлених пакетів та фільтруйте їх, щоб показати лише застарілі.

### 🚀 Високопродуктивний бекенд
- **Підтримка двох бекендів:** Автоматично використовує `uv`, якщо він доступний, для значного прискорення. Перемикається на `pip`, якщо `uv` не знайдено.
- **Розумне кешування:** Кешує списки пакетів для майже миттєвого запуску.

### 🛠️ Професійні інструменти
- **Сканер вразливостей:** Інтеграція з `pip-audit` для сканування вашого середовища на наявність пакетів з відомими вразливостями безпеки.
- **Пошук пошкоджених пакетів:** Потужний інструмент діагностики, який може знаходити конфлікти залежностей, перевіряти цілісність файлів, тестувати імпорти та виявляти відсутні метадані.
- **Пошук "осиротілих" пакетів:** Знаходьте та видаляйте пакети, які більше не потрібні жодному іншому пакету.
- **Компілятор залежностей:** Використовуйте `pip-tools` для компіляції файлу `requirements.in` у `requirements.txt`.

### 🌐 Керування середовищами
- **Підтримка кількох інтерпретаторів:** Легко перемикайтеся між різними інтерпретаторами Python та віртуальними середовищами.
- **Створення віртуальних середовищ:** Створюйте нові віртуальні середовища прямо з інтерфейсу. З `uv` можна навіть вказати версію Python.
- **Drag & Drop:** Просто перетягніть файл `requirements.txt` або `pyproject.toml` у вікно, щоб розпочати встановлення.

## 📜 Версії скрипту
Існує 3 основні версії цього скрипту, які відображають його еволюцію:
- **V1 (Зима 2024):** Перша, стара версія скрипту, спочатку створена для особистого використання.
- **V2 (Літо 2025):** Значне оновлення, орієнтоване на покращену архітектуру та нову функціональність.
- **V2.5 (FINALE+++):** Остання та найпотужніша версія, розроблена як ультимативний інструмент для керування пакетами.

## 📋 Вимоги

- **Python 3.x**
- **Tkinter:** Зазвичай входить до стандартної інсталяції Python.
- **(Рекомендовано) `uv`:** Для найкращої продуктивності. Встановіть його за допомогою `pip install uv`. Застосунок виявить його автоматично.

### Необов'язкові залежності
Застосунок запропонує встановити їх, коли ви скористаєтеся функцією, що їх вимагає:
- `tkinterdnd2`: Для підтримки drag-and-drop.
- `packaging`: Для більш точного сортування версій.
- `tomli`: Для читання файлів `pyproject.toml`.
- `pip-audit`: Для сканера вразливостей.
- `pip-tools`: Для компілятора залежностей.

## 🚀 Як використовувати

1.  Збережіть скрипт як файл `.py` (наприклад, `package_manager.py`).
2.  Запустіть його з термінала(фбо ж дабл-клік):
    ```bash
    python package_manager.py
    ```
3.  Використовуйте вкладки для навігації:
    - **Manage Packages:** Переглядайте, оновлюйте та видаляйте ваші поточні пакети.
    - **Install Packages:** Встановлюйте нові пакети з PyPI або локальних файлів.
    - **Tools:** Отримайте доступ до сканера вразливостей, інструментів пошуку пошкоджених/осиротілих пакетів та компілятора.
    - **Settings:** Керуйте інтерпретаторами Python, налаштовуйте параметри кешу та переглядайте інформацію про застосунок.

## 📄 Ліцензія
Цей проєкт ліцензовано за умовами ліцензії MIT.