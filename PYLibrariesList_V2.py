#!/usr/bin/env python3
"""
An advanced script for managing Python libraries with a modern GUI.
This version uses the modern `importlib.metadata` library, making it faster
and removing deprecation warnings.

Features:
- "Manage Packages" Tab:
  - Displays installed packages in a sortable, searchable list (Treeview).
  - Shows package name, version, size, and installation date.
  - Real-time search/filter functionality.
  - Multi-selection of packages for deletion.
  - Status bar shows total packages, selected count/size, and ongoing actions.
- "Install Packages" Tab:
  - Allows installation of new packages by name.
- Asynchronous Operations & Auto-Refresh:
  - All slow operations run in the background, keeping the UI responsive.
  - The package list automatically updates after any installation or deletion.
  - Refreshing automatically switches view to the "Manage Packages" tab.
- Action Log:
  - A detailed log window shows the output from `pip`.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import os
import subprocess
import sys
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import importlib.metadata

# --- Helper Functions (Simplified and Modernized) ---

def format_size(num_bytes):
    """Returns a human-readable size string."""
    if num_bytes is None or num_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num_bytes < 1024.0:
            return f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} PB"

def format_date(date_obj):
    """Formats a date object to a string."""
    if date_obj is None:
        return "unknown"
    return date_obj.strftime("%Y-%m-%d")

def get_package_info_modern(dist: importlib.metadata.Distribution):
    """
    Gathers information for a single package using importlib.metadata.
    This is much faster than the old pkg_resources method.
    """
    name = dist.metadata.get("Name", "N/A")
    version = dist.version
    size = None
    install_date = None

    try:
        # Fast size calculation from metadata files
        if dist.files:
            size = sum(file.size for file in dist.files if file.size is not None)

        # Get install date from the modification time of the .dist-info directory
        path_to_metadata = dist.locate_file('')
        if path_to_metadata:
            dist_info_path = path_to_metadata / f"{name.replace('-', '_')}-{version}.dist-info"
            if os.path.exists(dist_info_path):
                timestamp = os.path.getmtime(dist_info_path)
                install_date = datetime.datetime.fromtimestamp(timestamp)

    except Exception:
        pass

    return {
        "name": name,
        "version": version,
        "size": size or 0, # Default to 0 if size calculation fails
        "install_date": install_date,
    }

# --- Main Application Class ---

class PackageManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Package Manager")
        self.root.geometry("850x600")

        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.all_packages = []
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        self.task_queue = queue.Queue()

        self._create_widgets()
        self.root.after(100, self._process_queue)
        self.refresh_packages()

    def _create_widgets(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # --- Tab 1: Manage Packages ---
        self.manage_frame = ttk.Frame(self.notebook, padding="5")
        self.notebook.add(self.manage_frame, text="Manage Packages")

        # Top controls frame
        controls_frame = ttk.Frame(self.manage_frame)
        controls_frame.pack(fill=tk.X, pady=5)

        self.refresh_btn = ttk.Button(controls_frame, text="🔄 Refresh", command=self.refresh_packages)
        self.refresh_btn.pack(side=tk.LEFT, padx=(0, 10))

        search_label = ttk.Label(controls_frame, text="Search:")
        search_label.pack(side=tk.LEFT, padx=(10, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._filter_packages)
        self.search_entry = ttk.Entry(controls_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Treeview for package list
        tree_frame = ttk.Frame(self.manage_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("Name", "Version", "Size", "Date"),
            show="headings",
            selectmode="extended"
        )
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Define headings and sorting commands
        self.tree.heading("Name", text="Package Name", command=lambda: self._sort_column("Name", False))
        self.tree.heading("Version", text="Version", command=lambda: self._sort_column("Version", False))
        self.tree.heading("Size", text="Size", command=lambda: self._sort_column("Size", False))
        self.tree.heading("Date", text="Installed", command=lambda: self._sort_column("Date", False))

        self.tree.column("Name", width=250, stretch=tk.YES)
        self.tree.column("Version", width=100, stretch=tk.YES)
        self.tree.column("Size", width=100, stretch=tk.YES, anchor=tk.E)
        self.tree.column("Date", width=120, stretch=tk.YES, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.bind('<<TreeviewSelect>>', self._update_status_bar)

        # Bottom controls (selection and deletion)
        bottom_frame = ttk.Frame(self.manage_frame)
        bottom_frame.pack(fill=tk.X, pady=(5,0))

        select_all_btn = ttk.Button(bottom_frame, text="Select All", command=self._select_all)
        select_all_btn.pack(side=tk.LEFT, padx=(0, 5))

        deselect_all_btn = ttk.Button(bottom_frame, text="Deselect All", command=self._deselect_all)
        deselect_all_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.delete_btn = ttk.Button(bottom_frame, text="Delete Selected", command=self.delete_selected, state=tk.DISABLED)
        self.delete_btn.pack(side=tk.RIGHT)

        # --- Tab 2: Install Packages ---
        install_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(install_frame, text="Install Packages")

        install_label = ttk.Label(install_frame, text="Enter package name to install (e.g., 'requests' or 'requests==2.25.1'):")
        install_label.pack(pady=(10, 5), anchor='w')
        self.package_entry = ttk.Entry(install_frame, width=50)
        self.package_entry.pack(fill=tk.X, pady=5, ipady=4)
        self.install_btn = ttk.Button(install_frame, text="Install Package", command=self.install_package)
        self.install_btn.pack(pady=10, anchor='e')

        # --- Status Bar ---
        self.status_var = tk.StringVar(value="Ready.")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, anchor=tk.W, relief=tk.SUNKEN, padding=5)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _run_in_thread(self, target, *args, **kwargs):
        self.thread_pool.submit(target, *args, **kwargs)

    def _process_queue(self):
        try:
            while True:
                task, args, kwargs = self.task_queue.get_nowait()
                task(*args, **kwargs)
        except queue.Empty:
            self.root.after(100, self._process_queue)

    def _update_ui_state(self, is_busy):
        state = tk.DISABLED if is_busy else tk.NORMAL
        try:
            for i in range(self.notebook.index("end")):
                self.notebook.tab(i, state=state)
        except tk.TclError:
            pass
        self.refresh_btn.configure(state=state)
        self.search_entry.configure(state=state)
        self.install_btn.configure(state=state)
        if is_busy:
            self.delete_btn.configure(state=tk.DISABLED)
        else:
            self._update_status_bar()
        self.root.config(cursor="wait" if is_busy else "")
        self.root.update_idletasks()

    def _load_packages_task(self):
        """Task to be run in a thread for loading package info."""
        dists = list(importlib.metadata.distributions())
        self.task_queue.put((self.status_var.set, (f"Loading {len(dists)} packages... Please wait.",), {}))
        
        packages = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_dist = {executor.submit(get_package_info_modern, dist): dist for dist in dists}
            for future in as_completed(future_to_dist):
                pkg_info = future.result()
                if pkg_info and pkg_info['name'] != 'N/A':
                    packages.append(pkg_info)
        
        self.task_queue.put((self._on_packages_loaded, (packages,), {}))

    # --- THIS IS THE CORRECTED METHOD ---
    def _on_packages_loaded(self, packages):
        """Callback executed in the main thread after packages are loaded."""
        self.all_packages = sorted(packages, key=lambda p: p['name'].lower())
        
        # 1. Populate the data in the tree (this is fast)
        self._populate_tree() 
        
        # 2. Re-enable the UI
        self._update_ui_state(is_busy=False) 
        
        # 3. NOW that the UI is enabled and stable, reliably select the correct tab.
        # This fixes the issue of the tab not changing on load/refresh.
        self.notebook.select(self.manage_frame)

    def refresh_packages(self):
        """Starts the process of refreshing the package list."""
        self._update_ui_state(is_busy=True)
        self.status_var.set("Scanning for installed packages...")
        self.tree.delete(*self.tree.get_children()) # Clear view immediately
        self._run_in_thread(self._load_packages_task)

    def _populate_tree(self, packages=None):
        """Fills the treeview with package data."""
        self.tree.delete(*self.tree.get_children())
        if packages is None:
            packages = self.all_packages
        
        for pkg in packages:
            self.tree.insert(
                "",
                tk.END,
                iid=pkg["name"],
                values=(
                    pkg["name"],
                    pkg["version"],
                    format_size(pkg["size"]),
                    format_date(pkg["install_date"])
                ),
                tags=(pkg["size"], str(pkg["install_date"] or ''))
            )
        self._update_status_bar()

    def _filter_packages(self, *args):
        query = self.search_var.get().lower()
        filtered_packages = [pkg for pkg in self.all_packages if query in pkg['name'].lower()]
        self._populate_tree(filtered_packages)

    def _sort_column(self, col, reverse):
        if col == "Size":
            key = lambda child: int(self.tree.item(child)["tags"][0])
        elif col == "Date":
            key = lambda child: self.tree.item(child)["tags"][1]
        else: # Sort by displayed value for Name and Version
            key = lambda child: self.tree.set(child, col).lower()
            
        data = list(self.tree.get_children(''))
        data.sort(key=key, reverse=reverse)
        
        for index, child in enumerate(data):
            self.tree.move(child, '', index)
            
        for c in self.tree['columns']:
            text = self.tree.heading(c, 'text').replace(' ↑', '').replace(' ↓', '')
            self.tree.heading(c, text=text)
            
        new_text = f"{self.tree.heading(col, 'text')}{' ↓' if reverse else ' ↑'}"
        self.tree.heading(col, text=new_text, command=lambda: self._sort_column(col, not reverse))

    def _select_all(self):
        self.tree.selection_set(self.tree.get_children())
    
    def _deselect_all(self):
        self.tree.selection_set()

    def _update_status_bar(self, event=None):
        selected_items = self.tree.selection()
        total_size = sum(pkg.get('size', 0) for pkg in self.all_packages)
        status_text = f"Total: {len(self.all_packages)} packages ({format_size(total_size)})"
        
        if selected_items:
            selected_size = sum(pkg.get('size', 0) for pkg in self.all_packages if pkg['name'] in selected_items)
            status_text += f" | Selected: {len(selected_items)} ({format_size(selected_size)})"
            self.delete_btn.config(state=tk.NORMAL)
        else:
            self.delete_btn.config(state=tk.DISABLED)
        self.status_var.set(status_text)

    def _run_pip_command(self, command, title, on_complete=None):
        log_window = tk.Toplevel(self.root)
        log_window.title(title)
        log_window.geometry("600x400")
        log_text = scrolledtext.ScrolledText(log_window, wrap=tk.WORD, state=tk.DISABLED, bg="black", fg="white")
        log_text.pack(expand=True, fill=tk.BOTH)
        
        def write_to_log(message):
            log_text.config(state=tk.NORMAL)
            log_text.insert(tk.END, message)
            log_text.see(tk.END)
            log_text.config(state=tk.DISABLED)

        def task():
            try:
                proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                for line in iter(proc.stdout.readline, ''):
                    self.task_queue.put((write_to_log, (line,), {}))
                
                proc.wait()
                final_message = f"\n--- Process finished with exit code {proc.returncode} ---\n"
                self.task_queue.put((write_to_log, (final_message,), {}))

            except Exception as e:
                error_message = f"\n--- An exception occurred: {e} ---\n"
                self.task_queue.put((write_to_log, (error_message,), {}))
            finally:
                if on_complete:
                    self.task_queue.put((on_complete, (), {}))

        self._run_in_thread(task)

    def delete_selected(self):
        selected_ids = self.tree.selection()
        if not selected_ids: return

        confirm = messagebox.askyesno(
            "Confirm Deletion",
            f"Are you sure you want to delete {len(selected_ids)} package(s)?\n\n{', '.join(selected_ids)}"
        )
        if not confirm: return

        self._update_ui_state(is_busy=True)
        self.status_var.set(f"Deleting {len(selected_ids)} packages...")
        command = [sys.executable, "-m", "pip", "uninstall", "-y"] + list(selected_ids)
        self._run_pip_command(command, "Deletion Log", self.refresh_packages)

    def install_package(self):
        pkg_name = self.package_entry.get().strip()
        if not pkg_name:
            messagebox.showinfo("Input Required", "Please enter a package name to install.")
            return

        self._update_ui_state(is_busy=True)
        self.status_var.set(f"Installing {pkg_name}...")
        command = [sys.executable, "-m", "pip", "install", pkg_name]

        def on_install_complete():
            self.package_entry.delete(0, tk.END)
            self.refresh_packages()

        self._run_pip_command(command, f"Installation Log for '{pkg_name}'", on_install_complete)

def main():
    root = tk.Tk()
    app = PackageManagerApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()
