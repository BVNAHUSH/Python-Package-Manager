#!/usr/bin/env python3
"""
скрипт для керування бібліотеками Python:
- Вкладка "Перегляд / Видалення пакетів" відображає список установлених пакетів з їх розмірами,
  датою встановлення та чекбоксами для видалення.
- Кнопка "Видалити вибрані" видаляє вибрані пакети (з прапорцем -y для pip uninstall).
- Вкладка "Встановлення пакетів" дозволяє встановити новий пакет, ввівши його назву.
- Реалізовано сортування за ім’ям, розміром і датою встановлення, а також показ загальної кількості пакетів.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import pkg_resources
import os
import subprocess
import sys
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

current_sort_key = "name"
sort_ascending = True
package_vars = {}
gl_package_list_frame = None
gl_total_size_label = None


def get_directory_size(path):
    """Рекурсивно обчислює розмір каталогу"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total_size += os.path.getsize(fp)
    return total_size


def get_package_size(dist):
    """
    Визначає розмір пакета за його метаданими top_level.txt.
    Якщо таких метаданих немає, намагається використати назву проєкту.
    """
    size = 0
    top_levels = []
    try:
        data = dist.get_metadata("top_level.txt")
        top_levels = [line.strip() for line in data.splitlines() if line.strip()]
    except Exception:
        pass

    if top_levels:
        for module in top_levels:
            module_path = os.path.join(dist.location, module)
            if os.path.exists(module_path):
                if os.path.isdir(module_path):
                    size += get_directory_size(module_path)
                else:
                    size += os.path.getsize(module_path)
            else:
                module_file = module_path + ".py"
                if os.path.exists(module_file):
                    size += os.path.getsize(module_file)
    else:
        module_path = os.path.join(dist.location, dist.project_name)
        if os.path.exists(module_path):
            if os.path.isdir(module_path):
                size += get_directory_size(module_path)
            else:
                size += os.path.getsize(module_path)
    return size


def get_install_date(dist):
    """
    Визначає дату встановлення пакета.
    Спочатку пробуємо отримати час зміни теки .egg-info або .dist-info,
    якщо не вийшло — використовуємо дату зміни одного з модулів.
    """
    try:
        metadata_path = dist.egg_info
        if os.path.exists(metadata_path):
            timestamp = os.path.getmtime(metadata_path)
            return datetime.datetime.fromtimestamp(timestamp)
    except Exception:
        pass

    try:
        data = dist.get_metadata("top_level.txt")
        top_levels = [line.strip() for line in data.splitlines() if line.strip()]
        if top_levels:
            module_path = os.path.join(dist.location, top_levels[0])
            if os.path.exists(module_path):
                timestamp = os.path.getmtime(module_path)
                return datetime.datetime.fromtimestamp(timestamp)
    except Exception:
        pass

    path = os.path.join(dist.location, dist.project_name)
    if os.path.exists(path):
        timestamp = os.path.getmtime(path)
        return datetime.datetime.fromtimestamp(timestamp)
    return None


def format_size(num):
    """Повертає рядок із зручним поданням розміру (B, KB, MB, GB)"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if num < 1024:
            return f"{num:.2f} {unit}"
        num /= 1024.0
    return f"{num:.2f} TB"


def format_date(date_obj):
    """Форматує дату в рядок 'РРРР-ММ-ДД' або 'невідомо', якщо дата відсутня"""
    if date_obj is None:
        return "невідомо"
    return date_obj.strftime("%Y-%m-%d")


def get_package_info(dist):
    """
    Отримує інформацію про пакет: назву, версію, розмір і дату встановлення.
    """
    try:
        size = get_package_size(dist)
        install_date = get_install_date(dist)
        return {
            "name": dist.project_name,
            "version": dist.version,
            "size": size,
            "install_date": install_date,
        }
    except Exception:
        return None


def refresh_packages():
    """
    Отримує список установлених пакетів з інформацією.
    Обчислення розмірів і дат встановлення виконуються паралельно.
    """
    packages = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_dist = {executor.submit(get_package_info, dist): dist for dist in pkg_resources.working_set}
        for future in as_completed(future_to_dist):
            pkg_info = future.result()
            if pkg_info:
                packages.append(pkg_info)
    return packages


def build_package_list(frame, total_label):
    """
    Заповнює переданий фрейм списком пакетів із можливістю сортування.
    Використовується Canvas + внутрішній Frame для скролінгу, а також додано можливість прокрутки коліщатком миші.
    """
    for widget in frame.winfo_children():
        widget.destroy()

    packages = refresh_packages()

    def sort_key(pkg):
        if current_sort_key == "install_date":
            return pkg["install_date"] if pkg["install_date"] is not None else datetime.datetime.min
        elif current_sort_key == "name":
            return pkg["name"].lower()
        elif current_sort_key == "size":
            return pkg["size"]
        else:
            return pkg["name"].lower()

    packages.sort(key=sort_key, reverse=not sort_ascending)

    total_size = sum(pkg["size"] for pkg in packages)
    total_count = len(packages)
    total_label.config(text=f"Загальний розмір пакетів: {format_size(total_size)}  |  Усього пакетів: {total_count}")

    canvas = tk.Canvas(frame)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
    scrollable_frame = ttk.Frame(canvas)

    scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    canvas.bind("<Enter>", lambda event: canvas.focus_set())
    canvas.bind("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1*(event.delta/120)), "units"))
    canvas.bind("<Button-4>", lambda event: canvas.yview_scroll(-1, "units"))
    canvas.bind("<Button-5>", lambda event: canvas.yview_scroll(1, "units"))

    def get_header_text(column_name, key):
        if current_sort_key == key:
            return f"{column_name} {'↑' if sort_ascending else '↓'}"
        return column_name

    header = ttk.Frame(scrollable_frame)
    header.grid(row=0, column=0, sticky="ew", padx=5, pady=3)
    ttk.Label(header, text="Вибір", width=6).grid(row=0, column=0, padx=2)
    btn_name = ttk.Button(header, text=get_header_text("Пакет", "name"), command=lambda: change_sort("name"))
    btn_name.grid(row=0, column=1, padx=2)
    ttk.Label(header, text="Версія", width=10).grid(row=0, column=2, padx=2)
    btn_size = ttk.Button(header, text=get_header_text("Розмір", "size"), command=lambda: change_sort("size"))
    btn_size.grid(row=0, column=3, padx=2)
    btn_date = ttk.Button(header, text=get_header_text("Дата встановлення", "install_date"), command=lambda: change_sort("install_date"))
    btn_date.grid(row=0, column=4, padx=2)

    global package_vars
    package_vars = {}
    for i, pkg in enumerate(packages, start=1):
        frame_row = ttk.Frame(scrollable_frame)
        frame_row.grid(row=i, column=0, sticky="ew", padx=5, pady=1)
        var = tk.BooleanVar()
        package_vars[pkg["name"]] = var
        chk = tk.Checkbutton(frame_row, variable=var)
        chk.grid(row=0, column=0, padx=2)
        ttk.Label(frame_row, text=pkg["name"], width=25, anchor="w").grid(row=0, column=1, padx=2)
        ttk.Label(frame_row, text=pkg["version"], width=10, anchor="center").grid(row=0, column=2, padx=2)
        ttk.Label(frame_row, text=format_size(pkg["size"]), width=10, anchor="e").grid(row=0, column=3, padx=2)
        ttk.Label(frame_row, text=format_date(pkg["install_date"]), width=12, anchor="e").grid(row=0, column=4, padx=2)


def change_sort(key):
    """
    Змінює критерій сортування. Якщо вибрано той самий ключ – змінюється порядок (зростання/спадання).
    Після зміни сортування відбувається оновлення списку пакетів.
    """
    global current_sort_key, sort_ascending, gl_package_list_frame, gl_total_size_label

    if current_sort_key == key:
        sort_ascending = not sort_ascending
    else:
        current_sort_key = key
        sort_ascending = True

    build_package_list(gl_package_list_frame, gl_total_size_label)


def delete_selected():
    """Видаляє вибрані пакети через pip uninstall"""
    selected = [pkg for pkg, var in package_vars.items() if var.get()]
    if not selected:
        messagebox.showinfo("Інформація", "Не вибрано жодного пакета для видалення.")
        return

    if not messagebox.askyesno("Підтвердження",
                               f"Видалити вибрані пакети:\n{', '.join(selected)}?"):
        return

    for pkg in selected:
        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "pip", "uninstall", "-y", pkg],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, stderr = proc.communicate()
            if proc.returncode != 0:
                messagebox.showerror("Помилка",
                                     f"Помилка під час видалення пакета {pkg}:\n{stderr.decode()}")
        except Exception as e:
            messagebox.showerror("Помилка", f"Помилка під час видалення пакета {pkg}:\n{str(e)}")
    messagebox.showinfo("Інформація", "Видалення завершено.\nЩоб оновити список, перезапустіть програму.")


def install_package(package_entry):
    """Встановлює пакет із введеною назвою через pip install"""
    pkg_name = package_entry.get().strip()
    if not pkg_name:
        messagebox.showinfo("Інформація", "Введіть назву пакета для встановлення.")
        return

    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", pkg_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            messagebox.showerror("Помилка",
                                 f"Помилка під час встановлення пакета {pkg_name}:\n{stderr.decode()}")
        else:
            messagebox.showinfo("Інформація", f"Пакет {pkg_name} успішно встановлено.\n"
                                               "Щоб оновити список, перезапустіть програму.")
    except Exception as e:
        messagebox.showerror("Помилка", f"Помилка під час встановлення пакета {pkg_name}:\n{str(e)}")


def main():
    root = tk.Tk()
    root.title("Керування пакетами Python")
    root.geometry("700x500")

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    manage_frame = ttk.Frame(notebook)
    notebook.add(manage_frame, text="Перегляд / Видалення пакетів")

    package_list_frame = ttk.Frame(manage_frame)
    package_list_frame.pack(fill="both", expand=True, padx=5, pady=5)
    total_size_label = ttk.Label(manage_frame, text="Загальний розмір пакетів:")
    total_size_label.pack(side="bottom", pady=5)

    global gl_package_list_frame, gl_total_size_label
    gl_package_list_frame = package_list_frame
    gl_total_size_label = total_size_label

    build_package_list(package_list_frame, total_size_label)

    delete_btn = ttk.Button(manage_frame, text="Видалити вибрані", command=delete_selected)
    delete_btn.pack(side="bottom", pady=5)

    install_frame = ttk.Frame(notebook)
    notebook.add(install_frame, text="Встановлення пакетів")

    install_lbl = ttk.Label(install_frame, text="Назва пакета:")
    install_lbl.pack(pady=10)
    package_entry = ttk.Entry(install_frame, width=30)
    package_entry.pack(pady=5)
    install_btn = ttk.Button(install_frame, text="Встановити",
                             command=lambda: install_package(package_entry))
    install_btn.pack(pady=5)

    root.mainloop()


if __name__ == '__main__':
    main() 