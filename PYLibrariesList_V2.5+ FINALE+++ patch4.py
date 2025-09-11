#!/usr/bin/env python3
"""
PYLibrariesList V2.5+ (FINALE+++): A high-performance Python package manager.

This major update introduces support for the 'uv' backend for massive speed
gains, adds a new 'Tools' tab with professional features (orphaned package
finder, requirements compiler), and integrates virtual environment management.
Dependencies are now optional for easier setup, and stability is enhanced
by ensuring background tasks terminate correctly.

patch2 adds advanced venv creation: specify a Python version (uv-only) and
pre-install packages right from the creation dialog.

patch3 (Refactor, Robustness & Security): The codebase is refactored into logical
helper classes. Adds tools to find/fix corrupted packages and scan for known
vulnerabilities using pip-audit. Introduces a self-restart mechanism for safely
uninstalling in-use packages.

patch4 adds new "force reinstall" checkbox to Install Packages tab, improved "Damaged Packages" tool and reliability of initial packet scanning.
"""

# === Imports ===
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import os
import subprocess
import sys
import datetime
import queue
import json
import webbrowser
import threading
import importlib.metadata
import re
from collections import defaultdict, namedtuple
import hashlib
import shutil

# === Optional Imports ===
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

try:
    from packaging.version import parse as parse_version, InvalidVersion
    PACKAGING_AVAILABLE = True
except ImportError:
    PACKAGING_AVAILABLE = False

try:
    import tomli
    TOMLI_AVAILABLE = True
except ImportError:
    TOMLI_AVAILABLE = False


# === Constants & NamedTuples ===
CACHE_FILE_TEMPLATE = os.path.join(os.path.expanduser("~"), ".pylibs_manager_cache_{env_hash}.json")
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), ".pylibs_manager_settings.json")
CACHE_VERSION = 4
APP_VERSION = "2.5+ FINALE+++ patch4"
BUILD_NUMBER = "2025.07.06"

VenvConfig = namedtuple("VenvConfig", ["path", "python_version", "packages"])


# === Utils ===
class PackageUtils:
    """A collection of static utility functions for handling package data."""
    @staticmethod
    def format_size(num_bytes):
        """Converts bytes to a human-readable string (KB, MB, GB)."""
        if num_bytes is None or num_bytes < 1: return "N/A"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if num_bytes < 1024.0: return f"{num_bytes:.2f} {unit}"
            num_bytes /= 1024.0
        return f"{num_bytes:.2f} PB"

    @staticmethod
    def format_date(date_obj):
        """Formats a datetime object into a YYYY-MM-DD string."""
        if date_obj is None: return "unknown"
        return date_obj.strftime("%Y-%m-%d")

    @staticmethod
    def get_package_info_modern(dist: importlib.metadata.Distribution):
        """Gathers detailed information for a single package using importlib.metadata."""
        name = dist.metadata.get("Name", "N/A")
        version = dist.version
        size, install_date_ts, location = 0, None, ""
        try:
            if dist.files:
                size = sum(f.size for f in dist.files if f.size is not None)

            if hasattr(dist, '_path') and dist._path and os.path.exists(dist._path):
                location = str(dist._path)
                install_date_ts = os.path.getmtime(location)
            else:
                path_to_metadata = dist.locate_file('')
                if path_to_metadata:
                    location = str(path_to_metadata.parent)
                    install_date_ts = os.path.getmtime(location)
        except Exception:
            pass

        installer = "unknown"
        try:
            installer_file_content = dist.read_text('INSTALLER')
            if installer_file_content:
                installer = installer_file_content.strip()
        except (FileNotFoundError, TypeError, AttributeError):
            pass

        return {
            "name": name,
            "version": version,
            "size": size,
            "install_date_ts": install_date_ts,
            "location": location,
            "installer": installer,
            "metadata": {k: v for k, v in dist.metadata.items()},
            "requires": dist.requires or []
        }

    @staticmethod
    def get_version_sort_key(version_string):
        """Extracts the first version from a string and parses it for proper sorting."""
        base_version_str = version_string.split("→")[0].strip()
        if PACKAGING_AVAILABLE:
            try:
                return parse_version(base_version_str)
            except InvalidVersion:
                return parse_version("0.0.0")
        else:
            return base_version_str


# === GUI Helpers ===
class Tooltip:
    """Creates a tooltip for a given widget."""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event):
        x = event.x_root + 10
        y = event.y_root + 10

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        label = tk.Label(self.tooltip_window, text=self.text, justify='left',
                         background="#ffffe0", relief='solid', borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)

    def hide_tooltip(self, event):
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None


class CreateVenvDialog(tk.Toplevel):
    """A dialog for configuring and creating a new virtual environment."""
    def __init__(self, parent, package_manager, current_interpreter_path):
        super().__init__(parent)
        self.title("Create New Virtual Environment")
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.package_manager = package_manager
        self.current_interpreter_path = current_interpreter_path

        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        path_frame = ttk.Frame(main_frame)
        path_frame.pack(fill=tk.X, expand=True, pady=(0, 10))
        ttk.Label(path_frame, text="Environment Folder:", width=18).pack(side=tk.LEFT)
        self.path_var = tk.StringVar()
        path_entry = ttk.Entry(path_frame, textvariable=self.path_var)
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        browse_btn = ttk.Button(path_frame, text="Browse...", command=self._browse_path)
        browse_btn.pack(side=tk.LEFT)

        self.version_var = tk.StringVar()
        if self.package_manager == 'uv':
            version_frame = ttk.Frame(main_frame)
            version_frame.pack(fill=tk.X, expand=True, pady=(0, 15))
            label = ttk.Label(version_frame, text="Python Version:", width=18)
            label.pack(side=tk.LEFT)
            Tooltip(label, "Specify a Python version for `uv` to install (e.g., 3.11, 3.12.1).\nLeave blank to use the current base interpreter.")
            version_entry = ttk.Entry(version_frame, textvariable=self.version_var)
            version_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        packages_lf = ttk.LabelFrame(main_frame, text="Initial Packages (optional, one per line)", padding=10)
        packages_lf.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        self.packages_text = scrolledtext.ScrolledText(packages_lf, height=6, wrap=tk.WORD, font=("Segoe UI", 9))
        self.packages_text.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_frame, text="Create", command=self._on_create).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=(0, 5))

        self.wait_window()

    def _browse_path(self):
        path = filedialog.askdirectory(title="Select Folder for New Environment")
        if path:
            self.path_var.set(path)

    def _on_create(self):
        path = self.path_var.get().strip()
        if not path:
            messagebox.showerror("Input Required", "Please specify a location for the environment.", parent=self)
            return

        packages_str = self.packages_text.get("1.0", tk.END).strip()
        packages = [line.strip() for line in packages_str.splitlines() if line.strip()]

        self.result = VenvConfig(
            path=path,
            python_version=self.version_var.get().strip(),
            packages=packages
        )
        self.destroy()


class PyProjectInstallDialog(tk.Toplevel):
    """Dialog to select dependency groups from a pyproject.toml."""
    def __init__(self, parent, dependencies):
        super().__init__(parent)
        self.title("Install from pyproject.toml")
        self.transient(parent)
        self.grab_set()
        self.result = None
        self.dependencies = dependencies
        self.option_vars = {}

        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Select dependency groups to install:", font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(0, 10))

        main_deps_lf = ttk.LabelFrame(main_frame, text=f"Main Dependencies ({len(self.dependencies['main'])})", padding=10)
        main_deps_lf.pack(fill=tk.BOTH, expand=True, pady=5)
        main_text = scrolledtext.ScrolledText(main_deps_lf, height=5, wrap=tk.WORD, font=("Segoe UI", 9))
        main_text.pack(fill=tk.BOTH, expand=True)
        main_text.insert(tk.END, "\n".join(self.dependencies['main']) or "None")
        main_text.config(state=tk.DISABLED)

        if self.dependencies['optional']:
            opt_deps_lf = ttk.LabelFrame(main_frame, text="Optional Dependencies", padding=10)
            opt_deps_lf.pack(fill=tk.BOTH, expand=True, pady=5)
            
            for group_name in sorted(self.dependencies['optional'].keys()):
                self.option_vars[group_name] = tk.BooleanVar()
                group_size = len(self.dependencies['optional'][group_name])
                cb = ttk.Checkbutton(opt_deps_lf, text=f"{group_name} ({group_size} packages)", variable=self.option_vars[group_name])
                cb.pack(anchor='w')

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Install", command=self._on_install).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side=tk.RIGHT, padx=(0, 5))

        self.wait_window()
        
    def _on_install(self):
        packages_to_install = list(self.dependencies['main'])
        for group_name, var in self.option_vars.items():
            if var.get():
                packages_to_install.extend(self.dependencies['optional'][group_name])
        
        self.result = list(set(packages_to_install)) # Use set to remove duplicates
        self.destroy()

# === Logic Helpers ===
class SettingsManager:
    """Handles loading and saving application settings."""
    def __init__(self, file_path):
        self.file_path = file_path
        self.defaults = {
            'auto_check_updates': True,
            'cache_expiry_hours': 24,
            'interpreters': [sys.executable]
        }

    def load(self):
        """Loads settings from JSON, applying defaults for missing keys."""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r') as f:
                    settings = json.load(f)
                for key, value in self.defaults.items():
                    settings.setdefault(key, value)
            except (json.JSONDecodeError, TypeError):
                settings = self.defaults
        else:
            settings = self.defaults

        if sys.executable not in settings['interpreters']:
            settings['interpreters'].insert(0, sys.executable)

        seen = set()
        unique_interpreters = [x for x in settings['interpreters'] if not (x in seen or seen.add(x))]
        unique_interpreters.sort(key=lambda x: x == sys.executable, reverse=True)
        settings['interpreters'] = unique_interpreters

        return settings

    def save(self, settings):
        """Saves the provided settings dictionary to the JSON file."""
        with open(self.file_path, 'w') as f:
            json.dump(settings, f, indent=2)


class CacheManager:
    """Handles reading from and writing to the package cache files."""
    def __init__(self, template_path):
        self.template_path = template_path

    def _get_path(self, interpreter_path):
        """Generates a unique cache file path for the current interpreter."""
        env_hash = hashlib.sha1(interpreter_path.encode()).hexdigest()[:10]
        return self.template_path.format(env_hash=env_hash)

    def load(self, interpreter_path, expiry_hours):
        """Loads packages from the cache if it exists and is not expired."""
        cache_path = self._get_path(interpreter_path)
        if not os.path.exists(cache_path): return None
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            if cache_data.get("version") != CACHE_VERSION: return None

            if expiry_hours > 0:
                cache_time = datetime.datetime.fromisoformat(cache_data.get("timestamp"))
                if datetime.datetime.now() - cache_time > datetime.timedelta(hours=expiry_hours):
                    return None

            return cache_data
        except Exception as e:
            print(f"Error loading or validating cache: {e}")
            return None

    def save(self, interpreter_path, data):
        """Saves data to a JSON cache file."""
        cache_path = self._get_path(interpreter_path)
        try:
            data_to_save = {
                "version": CACHE_VERSION,
                "timestamp": datetime.datetime.now().isoformat(),
                **data
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f)
        except Exception as e:
            print(f"Error saving cache: {e}")

    def clear_all(self):
        """Deletes ALL package cache files across all known environments."""
        cache_dir = os.path.dirname(self.template_path)
        base_name = os.path.basename(self.template_path).split('{')[0]
        cleared_count = 0

        if not os.path.isdir(cache_dir):
            return 0, "No cache directory found."

        for filename in os.listdir(cache_dir):
            if filename.startswith(base_name) and filename.endswith(".json"):
                try:
                    os.remove(os.path.join(cache_dir, filename))
                    cleared_count += 1
                except OSError as e:
                    return cleared_count, f"Failed to clear cache file {filename}: {e}"
        return cleared_count, None


class StatusManager:
    """Manages updates to the action status bar to reduce code repetition."""
    def __init__(self, root, action_status_var):
        self.root = root
        self.action_status_var = action_status_var

    def update(self, message, clear_after_ms=3000):
        """Sets a status message that clears automatically."""
        self.action_status_var.set(message)
        if clear_after_ms:
            self.root.after(clear_after_ms, lambda: self._clear_if_matches(message))

    def set_persistent(self, message):
        """Sets a status message that does not clear automatically."""
        self.action_status_var.set(message)

    def _clear_if_matches(self, message):
        """Clears the status bar only if the message hasn't changed."""
        if self.action_status_var.get() == message:
            self.action_status_var.set("")


# === Main Application Class ===
class PackageManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Python Package Manager 2.5+")
        self.root.geometry("950x650")

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("Outdated.TButton", foreground="darkorange", font=('Segoe UI', 9, 'bold'))
        self.style.configure("Action.TLabel", foreground="gray")
        self.style.configure("UV.TLabel", foreground="#4B0082", font=('Segoe UI', 9, 'bold'))

        self.all_packages = []
        self.outdated_packages = {}
        self.reverse_deps = defaultdict(list)
        self.orphaned_packages_cache = []
        self.damaged_packages_cache = []
        self.vulnerabilities_cache = {}
        self.current_interpreter = sys.executable
        self.task_queue = queue.Queue()
        self.current_scan_id = 0
        self.last_sort_column = 'Name'
        self.last_sort_reverse = False
        self.force_reinstall_var = tk.BooleanVar()
        self.package_manager = 'pip'
        self.package_manager_path = None

        self.process_lock = threading.Lock()
        self.active_process = None

        self.RESTART_REQUIRED_PACKAGES = {'tkinterdnd2', 'packaging'}

        self.check_deps_var = tk.BooleanVar(value=True)
        self.check_hashes_var = tk.BooleanVar(value=False)
        self.check_import_var = tk.BooleanVar(value=False)
        self.check_metadata_files_var = tk.BooleanVar(value=False)

        self.settings_manager = SettingsManager(SETTINGS_FILE)
        self.cache_manager = CacheManager(CACHE_FILE_TEMPLATE)
        self.settings = self.settings_manager.load()

        self._create_widgets()

        self.status_manager = StatusManager(self.root, self.action_status_var)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.after(100, self._process_queue)
        self.status_manager.set_persistent("Initializing...")
        self.root.after(150, self.initial_load)
        self.root.after(200, self._validate_interpreters_on_startup)
        self.root.after(250, self._detect_package_manager)
        self.root.after(300, lambda: self._show_tool('vulnerabilities'))

    def on_closing(self):
        """Handles the window closing event to shut down background processes."""
        self.status_manager.set_persistent("Shutting down...")
        self._terminate_active_process()
        self.root.destroy()

    def _detect_package_manager(self):
        """Checks for `uv` and sets the package manager preference."""
        uv_path = shutil.which("uv")
        try:
            if uv_path:
                subprocess.run([uv_path, "--version"], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
                self.package_manager = 'uv'
                self.package_manager_path = uv_path
                self.manager_indicator_label.config(text="UV ⚡ (Faster)", style="UV.TLabel")
                Tooltip(self.manager_indicator_label, f"Using 'uv' package manager found at:\n{uv_path}")
                self.create_venv_btn.config(state=tk.NORMAL)
                return
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        self.package_manager = 'pip'
        self.package_manager_path = None
        self.manager_indicator_label.config(text="pip (Default)", style="TLabel")
        Tooltip(self.manager_indicator_label, "Using the standard 'pip' module for the selected environment.")
        self.create_venv_btn.config(state=tk.NORMAL)

    def _terminate_active_process(self):
        """Terminates the currently running subprocess, if any. Thread-safe."""
        proc_to_kill = None
        with self.process_lock:
            if self.active_process:
                proc_to_kill = self.active_process

        if proc_to_kill and proc_to_kill.poll() is None:
            try:
                print(f"Terminating active process {proc_to_kill.pid}...")
                proc_to_kill.terminate()
                proc_to_kill.wait(timeout=1)
                print("Active process terminated.")
            except Exception as e:
                print(f"Error terminating active process: {e}")

    def _save_settings(self, *args):
        """Saves current settings to the JSON file."""
        self.settings['auto_check_updates'] = self.auto_check_var.get()
        try:
            self.settings['cache_expiry_hours'] = int(self.cache_expiry_var.get())
        except (ValueError, tk.TclError):
            self.settings['cache_expiry_hours'] = 24

        if hasattr(self, 'interpreter_combo'):
            self.settings['interpreters'] = list(self.interpreter_combo['values'])

        self.settings_manager.save(self.settings)
        self.status_manager.update("Settings saved.")

    def initial_load(self):
        """Performs the initial package load, using cache if available and valid."""
        run_update_check = self.settings.get('auto_check_updates', True)

        cache_data = self.cache_manager.load(self.current_interpreter, self.settings.get('cache_expiry_hours', 24))
        if cache_data:
            self.all_packages = cache_data.get("packages", [])
            self.reverse_deps = defaultdict(list, cache_data.get("reverse_deps", {}))
            self.damaged_packages_cache = cache_data.get("damaged_packages", [])
            self._populate_tree()
            self._filter_packages()
            self._start_full_refresh_chain(run_update_check=run_update_check)
        else:
            self._start_full_refresh_chain(run_update_check=run_update_check)

        self.notebook.select(self.manage_frame)

    def refresh_installed_only(self):
        """Refreshes only the list of installed packages without checking for updates."""
        self._start_full_refresh_chain(run_update_check=False)

    def refresh_and_check_updates(self):
        """Performs a full refresh of installed packages and checks for updates."""
        self._start_full_refresh_chain(run_update_check=True)

    def check_for_updates_only(self):
        """Checks for outdated packages without rescanning the installed list."""
        if not self.all_packages:
            messagebox.showinfo("Info", "Load a package list first with a refresh.")
            return
        self._update_ui_state(True)
        scan_id = self.current_scan_id + 1
        self.current_scan_id = scan_id
        self._queue_status_update("Checking for outdated packages...", scan_id)
        self._run_in_thread(self._check_for_outdated_packages_task, scan_id, on_complete=lambda res: self._on_outdated_checked(res, scan_id))

    def _start_full_refresh_chain(self, run_update_check=True):
        """Initiates the package loading process in a background thread."""
        self._terminate_active_process()
        self._update_ui_state(True)
        scan_id = self.current_scan_id + 1
        self.current_scan_id = scan_id
        on_complete_callback = (lambda res: self._on_packages_loaded_then_check(res, scan_id)) if run_update_check else (lambda res: self._on_installed_loaded(res, scan_id))
        self._run_in_thread(self._load_packages_task, scan_id, on_complete=on_complete_callback)

    def _create_widgets(self):
        """Creates and arranges all GUI widgets."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self.manage_frame = ttk.Frame(self.notebook, padding="5")
        self.notebook.add(self.manage_frame, text="Manage Packages")
        self._create_manage_tab()

        self.install_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(self.install_frame, text="Install Packages")
        self._create_install_tab(self.install_frame)

        self.tools_tab_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(self.tools_tab_frame, text="Tools")
        self._create_tools_tab(self.tools_tab_frame)

        settings_frame = ttk.Frame(self.notebook, padding="20")
        self.notebook.add(settings_frame, text="Settings")
        self._create_settings_tab(settings_frame)

        status_frame = tk.Frame(main_frame, relief=tk.SUNKEN, bd=1)
        status_frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var = tk.StringVar(value="Welcome!")
        self.action_status_var = tk.StringVar(value="Initializing...")

        ttk.Label(status_frame, textvariable=self.status_var, anchor=tk.W, padding=(5, 2, 5, 0)).pack(fill=tk.X)
        ttk.Label(status_frame, textvariable=self.action_status_var, anchor=tk.W, padding=(5, 0, 5, 2), style="Action.TLabel").pack(fill=tk.X)

    def _create_manage_tab(self):
        """Creates the widgets for the 'Manage Packages' tab."""
        controls_frame = ttk.Frame(self.manage_frame)
        controls_frame.pack(fill=tk.X, pady=5)

        self.refresh_menubtn = ttk.Menubutton(controls_frame, text="🔄 Refresh", style="TButton")
        self.refresh_menubtn.pack(side=tk.LEFT, padx=(0, 10))
        refresh_menu = tk.Menu(self.refresh_menubtn, tearoff=0)
        refresh_menu.add_command(label="Refresh Installed List", command=self.refresh_installed_only)
        refresh_menu.add_command(label="Check For Updates Only", command=self.check_for_updates_only)
        refresh_menu.add_separator()
        refresh_menu.add_command(label="Full Refresh & Update Check", command=self.refresh_and_check_updates)
        self.refresh_menubtn['menu'] = refresh_menu

        self.upgrade_all_btn = ttk.Button(controls_frame, text="Upgrade All Outdated", command=self.upgrade_all_outdated, state=tk.DISABLED)
        self.upgrade_all_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.show_outdated_var = tk.BooleanVar()
        ttk.Checkbutton(controls_frame, text="Show only outdated", variable=self.show_outdated_var, command=self._filter_packages).pack(side=tk.LEFT, padx=(5, 5))

        ttk.Label(controls_frame, text="Search:").pack(side=tk.LEFT, padx=(10, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._filter_packages)
        self.search_entry = ttk.Entry(controls_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tree_frame = ttk.Frame(self.manage_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("Name", "Version", "Size", "Date")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="extended")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for col in columns:
            self.tree.heading(col, text=col.replace("_", " "), command=lambda c=col: self._sort_column(c, False))

        self.tree.column("Name", width=250)
        self.tree.column("Version", width=150, anchor=tk.CENTER)
        self.tree.column("Size", width=100, anchor=tk.E)
        self.tree.column("Date", width=120, anchor=tk.CENTER)

        self.tree.tag_configure('outdated', background='#FFFACD')
        self.tree.tag_configure('vulnerable', foreground='red')

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.bind('<<TreeviewSelect>>', lambda e: self._update_status_bar())
        self.tree.bind("<Button-3>", self._show_context_menu)
        self._create_context_menu()

    def _create_install_tab(self, parent_frame):
        """Creates the widgets for the 'Install Packages' tab."""
        # --- Install from PyPI ---
        pypi_lf = ttk.LabelFrame(parent_frame, text="Install from PyPI", padding=10)
        pypi_lf.pack(fill=tk.X, expand=False, pady=(0, 10), anchor='n')
        ttk.Label(pypi_lf, text="Package name (e.g., 'requests' or 'requests==2.25.1'):").pack(anchor='w')
        
        install_entry_frame = ttk.Frame(pypi_lf)
        install_entry_frame.pack(fill=tk.X, pady=5)
        self.package_entry = ttk.Entry(install_entry_frame, width=50)
        self.package_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        
        install_btn_frame = ttk.Frame(pypi_lf)
        install_btn_frame.pack(fill=tk.X)
        self.force_reinstall_check = ttk.Checkbutton(install_btn_frame, text="Force Reinstall", variable=self.force_reinstall_var)
        self.force_reinstall_check.pack(side=tk.LEFT, anchor='w')
        Tooltip(self.force_reinstall_check, "Forces a complete reinstall by ignoring caches and existing files.\nAdds --force-reinstall --no-cache-dir (pip)\nor --reinstall --no-cache (uv).")
        self.install_btn = ttk.Button(install_btn_frame, text="Install Package", command=self.install_package)
        self.install_btn.pack(side=tk.RIGHT, anchor='e')
        find_versions_btn = ttk.Button(install_btn_frame, text="Find Versions...", command=self.show_version_selector)
        find_versions_btn.pack(side=tk.RIGHT, anchor='e', padx=(0, 5))

        # --- Install from File (container) ---
        from_file_lf = ttk.LabelFrame(parent_frame, text="Install from File", padding=10)
        from_file_lf.pack(fill=tk.X, expand=False, pady=(0, 10), anchor='n')

        if DND_AVAILABLE:
            from_file_lf.drop_target_register(DND_FILES)
            from_file_lf.dnd_bind('<<Drop>>', self.handle_file_drop)
            hint_label = ttk.Label(from_file_lf, text="(Or drop a requirements.txt / pyproject.toml file here)", style="Action.TLabel")
            hint_label.pack(pady=(5, 0))

        # --- Sub-frames for each file type ---
        req_frame = ttk.Frame(from_file_lf)
        req_frame.pack(fill=tk.X, pady=2)
        ttk.Button(req_frame, text="Install from requirements.txt...", command=self.install_from_file).pack()

        toml_frame = ttk.Frame(from_file_lf)
        toml_frame.pack(fill=tk.X, pady=2)
        ttk.Button(toml_frame, text="Install from pyproject.toml...", command=self.install_from_pyproject).pack()

        # --- Optional Components ---
        if not all([DND_AVAILABLE, PACKAGING_AVAILABLE, TOMLI_AVAILABLE]):
            components_lf = ttk.LabelFrame(parent_frame, text="Additional Components", padding=10)
            components_lf.pack(fill=tk.X, expand=False, anchor='n')

            if not PACKAGING_AVAILABLE:
                pkg_frame = ttk.Frame(components_lf)
                pkg_frame.pack(fill=tk.X, pady=2)
                pkg_btn = ttk.Button(pkg_frame, text="Install 'packaging'", command=lambda: self._install_optional_dependency(package_name='packaging', frame_widget=pkg_frame))
                pkg_btn.pack(side=tk.LEFT)
                Tooltip(pkg_btn, "Provides accurate version sorting in the package list.\nA restart is required after installation.")
                ttk.Label(pkg_frame, text="- for accurate version sorting").pack(side=tk.LEFT, padx=5)

            if not DND_AVAILABLE:
                dnd_frame = ttk.Frame(components_lf)
                dnd_frame.pack(fill=tk.X, pady=2)
                dnd_btn = ttk.Button(dnd_frame, text="Install 'tkinterdnd2'", command=lambda: self._install_optional_dependency(package_name='tkinterdnd2', frame_widget=dnd_frame))
                dnd_btn.pack(side=tk.LEFT)
                Tooltip(dnd_btn, "Enables drag-and-drop support for requirements files.\nA restart is required after installation.")
                ttk.Label(dnd_frame, text="- for drag-and-drop support").pack(side=tk.LEFT, padx=5)

            if not TOMLI_AVAILABLE:
                toml_frame_install = ttk.Frame(components_lf)
                toml_frame_install.pack(fill=tk.X, pady=2)
                toml_btn = ttk.Button(toml_frame_install, text="Install 'tomli'", command=lambda: self._install_optional_dependency(package_name='tomli', frame_widget=toml_frame_install))
                toml_btn.pack(side=tk.LEFT)
                Tooltip(toml_btn, "Enables reading dependencies from pyproject.toml files.")
                ttk.Label(toml_frame_install, text="- to read pyproject.toml files").pack(side=tk.LEFT, padx=5)

    def _install_optional_dependency(self, package_name, target_interpreter=None, frame_widget=None, on_success=None):
        """Installs an optional dependency into a specified environment."""
        target_env = target_interpreter or sys.executable

        env_name = "the selected environment" if target_interpreter else "the application's own environment"
        msg = (f"This feature requires the '{package_name}' library. "
               f"It will be installed into {env_name}.\n\n"
               "Do you want to proceed?")

        if messagebox.askyesno(f"Install Optional Component", msg):
            if frame_widget:
                for widget in frame_widget.winfo_children():
                    widget.config(state=tk.DISABLED)

            def on_complete():
                self.status_manager.update(f"'{package_name}' installed successfully.")
                if on_success:
                    # A small trick to make the import available in the current run
                    if package_name == 'tomli':
                        global TOMLI_AVAILABLE, tomli
                        try:
                           import tomli
                           TOMLI_AVAILABLE = True
                        except ImportError:
                           pass
                    on_success()
                elif not target_interpreter:
                    messagebox.showinfo("Installation Successful",
                                        f"'{package_name}' has been installed.\n\nPlease restart the application to use the new functionality.")

            if self.package_manager == 'uv' and self.package_manager_path:
                command = [self.package_manager_path, "pip", "install", package_name, "-p", target_env]
            else:
                command = [target_env, "-m", "pip", "install", package_name]

            self._run_pip_command(command, f"Installing {package_name}", on_complete)

    def _create_tools_tab(self, parent_frame):
        """Creates the widgets for the Tools tab with a switcher."""
        controls_frame = ttk.Frame(parent_frame)
        controls_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))

        ttk.Button(controls_frame, text="Vulnerability Scan", command=lambda: self._show_tool('vulnerabilities')).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls_frame, text="Damaged Packages", command=lambda: self._show_tool('damaged')).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls_frame, text="Orphaned Packages", command=lambda: self._show_tool('orphans')).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls_frame, text="Compiler", command=lambda: self._show_tool('compiler')).pack(side=tk.LEFT, padx=2)

        self.tools_content_frame = ttk.Frame(parent_frame)
        self.tools_content_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.vulnerabilities_frame = self._create_vulnerability_tool()
        self.damaged_frame = self._create_damaged_packages_tool()
        self.orphans_frame = self._create_orphans_tool()
        self.compiler_frame = self._create_compiler_tool()

        self.tool_frames = {
            'vulnerabilities': self.vulnerabilities_frame,
            'damaged': self.damaged_frame,
            'orphans': self.orphans_frame,
            'compiler': self.compiler_frame,
        }

    def _show_tool(self, tool_name):
        """Hides all tool frames and shows the selected one."""
        for frame in self.tool_frames.values():
            frame.pack_forget()

        frame_to_show = self.tool_frames.get(tool_name)
        if frame_to_show:
            frame_to_show.pack(fill=tk.BOTH, expand=True)

    def _create_generic_treeview(self, parent, columns_config, selectmode='extended'):
        """
        Creates a generic Treeview with a scrollbar inside a frame.
        
        :param parent: The parent widget for the treeview frame.
        :param columns_config: A dictionary mapping column names to their properties (e.g., width, anchor).
        :param selectmode: The selection mode for the treeview ('extended', 'browse', etc.).
        :return: The created ttk.Treeview widget.
        """
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = tuple(columns_config.keys())
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode=selectmode)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for col_name, col_props in columns_config.items():
            tree.heading(col_name, text=col_name)
            if col_props:
                tree.column(col_name, **col_props)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scrollbar.set)
        
        return tree

    def _create_vulnerability_tool(self):
        """Creates the UI for the vulnerability scanner."""
        vuln_lf = ttk.LabelFrame(self.tools_content_frame, text="Vulnerability Scanner (via pip-audit)", padding=10)

        controls = ttk.Frame(vuln_lf)
        controls.pack(fill=tk.X, pady=5)
        self.run_vuln_scan_btn = ttk.Button(controls, text="Run Vulnerability Scan", command=self.run_vulnerability_scan)
        self.run_vuln_scan_btn.pack(side=tk.LEFT)
        self.vuln_status_label = ttk.Label(controls, text="Check the selected environment for known vulnerabilities.")
        self.vuln_status_label.pack(side=tk.LEFT, padx=10)

        columns_config = {
            "Package": {"width": 120},
            "Version": {"width": 80},
            "ID": {"width": 120},
            "Description": {"width": 300},
            "Fixed In": {"width": 100}
        }
        self.vuln_tree = self._create_generic_treeview(vuln_lf, columns_config, selectmode='browse')

        return vuln_lf

    def _create_damaged_packages_tool(self):
        """Creates the UI for the damaged package finder tool."""
        damaged_lf = ttk.LabelFrame(self.tools_content_frame, text="Analysis of Damaged Packages", padding=10)

        controls = ttk.Frame(damaged_lf)
        controls.pack(fill=tk.X, pady=5)

        self.find_damaged_btn = ttk.Button(controls, text="Find Damaged Packages", command=self.find_damaged_packages)
        self.find_damaged_btn.pack(side=tk.LEFT)

        self.reinstall_damaged_btn = ttk.Button(controls, text="Reinstall Selected", command=self.reinstall_selected_damaged, state=tk.DISABLED)
        self.reinstall_damaged_btn.pack(side=tk.LEFT, padx=10)
        Tooltip(self.reinstall_damaged_btn, "Attempt a force-reinstall of the selected package(s).\nThis can fix dependency issues, corrupted files, and failed imports.")

        self.damaged_status_label = ttk.Label(controls, text="Select checks and click 'Find' to scan the environment.")
        self.damaged_status_label.pack(side=tk.LEFT, padx=5)

        checks_frame = ttk.Frame(damaged_lf, padding=(0, 5, 0, 10))
        checks_frame.pack(fill=tk.X)

        c1 = ttk.Checkbutton(checks_frame, text="Dependency conflicts (pip check)", variable=self.check_deps_var)
        c1.grid(row=0, column=0, sticky='w', padx=5)
        Tooltip(c1, "Runs 'pip check' to find packages with incompatible or missing dependencies.")

        c2 = ttk.Checkbutton(checks_frame, text="File integrity (hashes)", variable=self.check_hashes_var)
        c2.grid(row=0, column=1, sticky='w', padx=5)
        Tooltip(c2, "Verifies SHA256 hashes of installed files against the package's RECORD file.\n(Can be slow)")

        c3 = ttk.Checkbutton(checks_frame, text="Test import", variable=self.check_import_var)
        c3.grid(row=1, column=0, sticky='w', padx=5)
        Tooltip(c3, "Attempts to import each package in a subprocess to catch basic runtime errors.\n(Can be slow)")

        c4 = ttk.Checkbutton(checks_frame, text="Missing metadata files", variable=self.check_metadata_files_var)
        c4.grid(row=1, column=1, sticky='w', padx=5)
        Tooltip(c4, "Checks if all files listed in the package metadata actually exist on disk.")

        columns_config = {
            "Package": {"width": 150},
            "Problem": {"width": 180},
            "Details": {"width": 350}
        }
        self.damaged_tree = self._create_generic_treeview(damaged_lf, columns_config, selectmode='extended')
        self.damaged_tree.bind("<<TreeviewSelect>>", self._on_damaged_selection_changed)

        return damaged_lf

    def _create_orphans_tool(self):
        """Creates the UI for the orphaned package finder tool."""
        orphan_lf = ttk.LabelFrame(self.tools_content_frame, text="Orphaned Packages Analysis", padding=10)

        orphan_controls_frame = ttk.Frame(orphan_lf)
        orphan_controls_frame.pack(fill=tk.X, pady=5)

        self.find_orphans_btn = ttk.Button(orphan_controls_frame, text="Find Orphaned Packages", command=self.find_orphaned_packages)
        self.find_orphans_btn.pack(side=tk.LEFT)

        self.uninstall_orphans_btn = ttk.Button(orphan_controls_frame, text="Uninstall Selected", command=self.uninstall_selected_orphans, state=tk.DISABLED)
        self.uninstall_orphans_btn.pack(side=tk.LEFT, padx=10)

        self.orphan_status_label = ttk.Label(orphan_controls_frame, text="Click 'Find' to scan for orphaned packages.")
        self.orphan_status_label.pack(side=tk.LEFT, padx=5)

        columns_config = {
            "Name": {"width": 250},
            "Version": {"width": 150, "anchor": tk.CENTER},
            "Size": {"width": 100, "anchor": tk.E},
            "Date": {"width": 120, "anchor": tk.CENTER}
        }
        self.orphan_tree = self._create_generic_treeview(orphan_lf, columns_config, selectmode='extended')
        self.orphan_tree.bind('<<TreeviewSelect>>', self._on_orphan_selection_changed)

        return orphan_lf

    def _create_compiler_tool(self):
        """Creates the UI for the requirements compiler tool."""
        compile_lf = ttk.LabelFrame(self.tools_content_frame, text="Compile requirements.in (via pip-tools)", padding=10)
        if DND_AVAILABLE:
            compile_lf.drop_target_register(DND_FILES)
            compile_lf.dnd_bind('<<Drop>>', self._handle_req_in_drop)

        in_frame = ttk.Frame(compile_lf)
        in_frame.pack(fill=tk.X, expand=True, pady=2)
        ttk.Label(in_frame, text="Input (.in):", width=12).pack(side=tk.LEFT)
        self.req_in_path = tk.StringVar()
        in_entry = ttk.Entry(in_frame, textvariable=self.req_in_path)
        in_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        in_btn = ttk.Button(in_frame, text="Browse...", command=self._browse_for_req_in_file)
        in_btn.pack(side=tk.LEFT)

        out_frame = ttk.Frame(compile_lf)
        out_frame.pack(fill=tk.X, expand=True, pady=2)
        ttk.Label(out_frame, text="Output (.txt):", width=12).pack(side=tk.LEFT)
        self.req_out_path = tk.StringVar()
        out_entry = ttk.Entry(out_frame, textvariable=self.req_out_path)
        out_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        out_btn = ttk.Button(out_frame, text="Browse...", command=self._browse_for_req_out_file)
        out_btn.pack(side=tk.LEFT)

        compile_btn_frame = ttk.Frame(compile_lf)
        compile_btn_frame.pack(fill=tk.X, pady=(10, 0))
        self.compile_reqs_btn = ttk.Button(compile_lf, text="Compile", command=self.compile_requirements)
        self.compile_reqs_btn.pack(side=tk.RIGHT)
        return compile_lf

    def _create_settings_tab(self, parent_frame):
        """Creates the widgets for the 'Settings' tab."""
        env_frame = ttk.LabelFrame(parent_frame, text="Python Environment Management", padding=10)
        env_frame.pack(fill=tk.X, pady=5)

        combo_frame = ttk.Frame(env_frame)
        combo_frame.pack(fill=tk.X, pady=(0, 5))
        self.interpreter_var = tk.StringVar(value=self.current_interpreter)
        self.interpreter_combo = ttk.Combobox(combo_frame, textvariable=self.interpreter_var, values=self.settings.get('interpreters', []), state='readonly')
        self.interpreter_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.interpreter_combo.bind('<<ComboboxSelected>>', self._on_interpreter_selected)

        browse_btn = ttk.Button(combo_frame, text="...", command=self._browse_for_interpreter, width=4)
        browse_btn.pack(side=tk.LEFT)
        Tooltip(browse_btn, "Add an existing Python interpreter (e.g., from a venv)")

        env_actions_frame = ttk.Frame(env_frame)
        env_actions_frame.pack(fill=tk.X, pady=(5, 0))

        self.remove_interpreter_btn = ttk.Button(env_actions_frame, text="Remove Selected", command=self._remove_interpreter)
        self.remove_interpreter_btn.pack(side=tk.RIGHT, padx=(5, 0))
        Tooltip(self.remove_interpreter_btn, "Remove the selected interpreter from the list.\nThe currently active interpreter cannot be removed.")

        self.create_venv_btn = ttk.Button(env_actions_frame, text="Create venv", command=self._create_venv, state=tk.DISABLED)
        self.create_venv_btn.pack(side=tk.RIGHT)
        Tooltip(self.create_venv_btn, "Create a new virtual environment.\n(Advanced options available if 'uv' is detected)")


        startup_lf = ttk.LabelFrame(parent_frame, text="Startup & Refresh", padding=10)
        startup_lf.pack(fill=tk.X, pady=5)
        self.auto_check_var = tk.BooleanVar(value=self.settings.get('auto_check_updates', True))
        auto_check_btn = ttk.Checkbutton(startup_lf, text="Automatically check for outdated packages on startup", variable=self.auto_check_var)
        auto_check_btn.pack(anchor='w')
        self.auto_check_var.trace_add("write", self._save_settings)
        Tooltip(auto_check_btn, "If enabled, the app will check for updates online automatically on startup.\nDisabling this leads to a faster, offline startup.")

        cache_lf = ttk.LabelFrame(parent_frame, text="Cache Management", padding=10)
        cache_lf.pack(fill=tk.X, pady=10)
        expiry_frame = ttk.Frame(cache_lf)
        expiry_frame.pack(fill=tk.X)
        self.cache_expiry_var = tk.StringVar(value=str(self.settings.get('cache_expiry_hours', 24)))
        cache_expiry_label = ttk.Label(expiry_frame, text="Cache expiry (hours):")
        cache_expiry_label.pack(side=tk.LEFT)
        cache_expiry_entry = ttk.Entry(expiry_frame, textvariable=self.cache_expiry_var, width=5)
        cache_expiry_entry.pack(side=tk.LEFT, padx=5)
        cache_expiry_entry.bind("<FocusOut>", self._save_settings)
        Tooltip(cache_expiry_label, "How long package data is cached before a full refresh is required on startup.\nSet to 0 to always refresh on startup.")
        clear_cache_btn = ttk.Button(cache_lf, text="Clear All Package Caches Now", command=self._clear_cache)
        clear_cache_btn.pack(pady=(10, 0))
        Tooltip(clear_cache_btn, "Deletes all cached package lists for all environments.\nThe next startup for each will perform a full, fresh scan.")

        about_lf = ttk.LabelFrame(parent_frame, text="About", padding=10)
        about_lf.pack(fill=tk.X, pady=10)
        ttk.Label(about_lf, text=f"Version: {APP_VERSION}").pack(anchor='w')
        ttk.Label(about_lf, text=f"Build: {BUILD_NUMBER}").pack(anchor='w')
        ttk.Label(about_lf, text="Author: Olexandr_43").pack(anchor='w')

        tool_frame = ttk.Frame(about_lf)
        tool_frame.pack(fill=tk.X, anchor='w', pady=(5,0))
        ttk.Label(tool_frame, text="Active Tool:").pack(side=tk.LEFT)
        self.manager_indicator_label = ttk.Label(tool_frame, text="Detecting...")
        self.manager_indicator_label.pack(side=tk.LEFT, padx=(5,0))

        link = ttk.Label(about_lf, text="GitHub Repository", foreground="blue", cursor="hand2")
        link.pack(anchor='w', pady=(5,0))
        link.bind("<Button-1>", lambda e: webbrowser.open_new_tab("https://github.com/Olexandr43/Python-Package-Manager"))


    def _get_subprocess_env(self):
        """Creates a safe environment for subprocesses to run in."""
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _validate_interpreters_on_startup(self):
        """Checks for invalid interpreter paths and offers to remove them."""
        interpreters = self.settings.get('interpreters', [])
        valid_interpreters = []
        invalid_interpreters = []

        for interp_path in interpreters:
            if interp_path == sys.executable or os.path.exists(interp_path):
                valid_interpreters.append(interp_path)
            else:
                invalid_interpreters.append(interp_path)

        if invalid_interpreters:
            msg = "The following Python interpreters could not be found and may have been deleted:\n\n"
            msg += "\n".join(f"- {p}" for p in invalid_interpreters)
            msg += "\n\nWould you like to remove them from the list?"

            if messagebox.askyesno("Invalid Interpreters Found", msg):
                self.settings['interpreters'] = valid_interpreters
                self.interpreter_combo['values'] = valid_interpreters
                if self.current_interpreter in invalid_interpreters:
                    self.current_interpreter = sys.executable
                    self.interpreter_var.set(sys.executable)
                self._save_settings()

    def handle_file_drop(self, event):
        """Handles the drop event for installing from a requirements.txt file."""
        filepath = event.data.strip('{}')
        if filepath.lower().endswith(".txt"):
            self.confirm_and_install_from_file(filepath)
        elif filepath.lower().endswith(".toml"):
            self.confirm_and_install_from_pyproject(filepath)
        else:
            messagebox.showwarning("Invalid File", "Please drop a valid '.txt' or '.toml' file.")

    def _handle_req_in_drop(self, event):
        """Handles the drop event for a requirements.in file."""
        filepath = event.data.strip('{}')
        if filepath.lower().endswith(".in"):
            self.req_in_path.set(filepath)
            if not self.req_out_path.get():
                out_path = os.path.splitext(filepath)[0] + ".txt"
                self.req_out_path.set(out_path)
        else:
            messagebox.showwarning("Invalid File", "Please drop a valid '.in' file.")

    def _browse_for_interpreter(self):
        filepath = filedialog.askopenfilename(
            title="Select Python Interpreter",
            filetypes=[("Python Executable", "python.exe"), ("Python", "python"), ("All files", "*.*")]
        )
        if filepath and os.path.exists(filepath):
            try:
                result_proc = subprocess.run(
                    [filepath, "--version"], capture_output=True, check=True, timeout=5, env=self._get_subprocess_env(),
                    text=True, encoding='utf-8', errors='replace'
                )
                stdout = result_proc.stdout
                stderr = result_proc.stderr
                if "Python" not in stdout and "Python" not in stderr:
                    messagebox.showerror("Invalid", "This does not appear to be a valid Python interpreter.")
                    return
            except Exception as e:
                messagebox.showerror("Error", f"Failed to validate interpreter: {e}")
                return

            current_interpreters = list(self.interpreter_combo['values'])
            if filepath not in current_interpreters:
                current_interpreters.append(filepath)
                self.interpreter_combo['values'] = current_interpreters
                self._save_settings()

            self.interpreter_combo.set(filepath)
            self._on_interpreter_selected(None)

    def _remove_interpreter(self):
        """Removes the selected interpreter from the list."""
        selected = self.interpreter_var.get()
        if not selected:
            return
        if selected == sys.executable:
            messagebox.showerror("Action Denied", "Cannot remove the interpreter currently running this application.")
            return

        if messagebox.askyesno("Confirm Removal", f"Are you sure you want to remove this interpreter from the list?\n\n{selected}"):
            current_interpreters = list(self.interpreter_combo['values'])
            if selected in current_interpreters:
                current_interpreters.remove(selected)
            self.interpreter_combo['values'] = current_interpreters
            if self.interpreter_var.get() == selected:
                self.interpreter_var.set(self.current_interpreter)
            self._save_settings()
            self._update_interpreter_buttons_state()

    def _create_venv(self):
        """Opens a dialog to configure and create a new Python virtual environment."""
        dialog = CreateVenvDialog(self.root, self.package_manager, self.interpreter_var.get())
        config = dialog.result

        if not config:
            return

        if os.path.exists(config.path) and os.listdir(config.path):
             if not messagebox.askyesno("Warning", "The selected directory is not empty. It is recommended to use an empty directory.\n\nContinue anyway?"):
                return

        self._execute_venv_creation(config)

    def _execute_venv_creation(self, config: VenvConfig):
        """Handles the logic of creating the venv and installing packages."""

        base_python = config.python_version or self.interpreter_var.get()
        if self.package_manager == 'uv':
            create_command = [self.package_manager_path, "venv", "-p", base_python, config.path]
        else:
            create_command = [base_python, "-m", "venv", config.path]

        def on_creation_complete():
            if config.packages:
                self.status_manager.set_persistent(f"Installing {len(config.packages)} packages...")
                new_python_path = self._get_python_path_for_venv(config.path)

                if self.package_manager == 'uv':
                    install_command = [self.package_manager_path, "pip", "install", *config.packages, "-p", new_python_path]
                else:
                    install_command = [new_python_path, "-m", "pip", "install", *config.packages]

                self._run_pip_command(install_command, "Installing Initial Packages", on_complete=lambda: self._finalize_venv_creation(config.path))
            else:
                self._finalize_venv_creation(config.path)

        self.status_manager.set_persistent(f"Creating venv in {os.path.basename(config.path)}...")
        self._run_pip_command(create_command, "Creating Virtual Environment", on_complete=on_creation_complete)

    def _get_python_path_for_venv(self, venv_path):
        """Gets the path to the python executable in a new venv."""
        if sys.platform == "win32":
            return os.path.join(venv_path, "Scripts", "python.exe")
        else:
            return os.path.join(venv_path, "bin", "python")

    def _finalize_venv_creation(self, venv_path):
        """Final step after all creation/installation is done."""
        new_python_path = self._get_python_path_for_venv(venv_path)

        if os.path.exists(new_python_path):
            msg = "Virtual environment created successfully.\n\nAdd it to the list and switch to it now?"
            if messagebox.askyesno("Success", msg):
                current_interpreters = list(self.interpreter_combo['values'])
                if new_python_path not in current_interpreters:
                    current_interpreters.append(new_python_path)
                    self.interpreter_combo['values'] = current_interpreters
                self.interpreter_combo.set(new_python_path)
                self._on_interpreter_selected(None)
        else:
            messagebox.showerror("Error", "Virtual environment was seemingly created, but the Python executable could not be found.")

    def _update_interpreter_buttons_state(self):
        """Updates the state of interpreter management buttons."""
        selected = self.interpreter_var.get()
        if selected == sys.executable:
            self.remove_interpreter_btn.config(state=tk.DISABLED)
        else:
            self.remove_interpreter_btn.config(state=tk.NORMAL)

    def _on_interpreter_selected(self, event=None):
        self._update_interpreter_buttons_state()
        new_interpreter = self.interpreter_var.get()
        if new_interpreter != self.current_interpreter:
            self.current_scan_id += 1
            self.current_interpreter = new_interpreter
            self.status_manager.update(f"Switched to environment: {os.path.basename(os.path.dirname(self.current_interpreter))}", clear_after_ms=None)
            self.all_packages = []
            self.outdated_packages = {}
            self.reverse_deps.clear()
            self._populate_tree()
            self._save_settings()
            self.root.after(100, self.initial_load)

    def _on_tab_changed(self, event):
        """Set focus to the notebook itself to prevent auto-focus on tab contents."""
        self.notebook.focus_set()
        if self.notebook.tab(self.notebook.select(), "text") == "Settings":
            self._update_interpreter_buttons_state()

    def _run_in_thread(self, target, *args, on_complete=None, **kwargs):
        """Submits a task to a daemon thread with an optional on_complete callback."""
        def task_wrapper():
            result = target(*args, **kwargs)
            if on_complete:
                self.task_queue.put((on_complete, (result,)))

        thread = threading.Thread(target=task_wrapper, daemon=True)
        thread.start()

    def _process_queue(self):
        """Processes tasks from the queue in the main GUI thread."""
        try:
            while True:
                task, args = self.task_queue.get_nowait()
                task(*args)
        except queue.Empty:
            self.root.after(100, self._process_queue)

    def _queue_status_update(self, message, scan_id):
        """Queues a status bar message to be set in the main thread, respecting the scan_id."""
        def update_task():
            if scan_id == self.current_scan_id:
                self.status_manager.set_persistent(message)
        self.task_queue.put((update_task, ()))

    def _update_ui_state(self, is_busy):
        """Enables or disables UI elements based on the busy state."""
        state = tk.DISABLED if is_busy else tk.NORMAL
        self.refresh_menubtn.config(state=state)
        self.install_btn.config(state=state)
        self.find_orphans_btn.config(state=state)
        self.compile_reqs_btn.config(state=state)
        self.find_damaged_btn.config(state=state)
        self.run_vuln_scan_btn.config(state=state)

        if self.outdated_packages and not is_busy:
            self.upgrade_all_btn.config(state=tk.NORMAL)
        else:
            self.upgrade_all_btn.config(state=tk.DISABLED)

        self._update_status_bar()
        self.root.config(cursor="wait" if is_busy else "")

    def _load_packages_task(self, scan_id):
        """Task to scan and gather information about all installed packages."""
        self._queue_status_update("Finding site-packages...", scan_id)
        try:
            cmd = [self.current_interpreter, "-c", "import sysconfig, json; print(json.dumps(list(set([p for p in (sysconfig.get_path('purelib'), sysconfig.get_path('platlib')) if p]))))"]
            result_proc = subprocess.run(
                cmd, capture_output=True, check=True, env=self._get_subprocess_env(),
                text=True, encoding='utf-8', errors='replace'
            )
            search_paths = [p for p in json.loads(result_proc.stdout) if os.path.isdir(p)]
        except Exception as e:
            msg = f"Failed to locate site-packages for:\n{self.current_interpreter}\n\nError: {e}"
            self.task_queue.put((messagebox.showerror, ("Environment Error", msg)))
            return [], {}, []

        self._queue_status_update("Scanning installed packages...", scan_id)
        packages = []
        damaged_packages = []

        all_dist_info_dirs = []
        for path in search_paths:
            try:
                all_dist_info_dirs.extend([os.path.join(path, d) for d in os.listdir(path) if d.endswith('.dist-info')])
            except OSError as e:
                print(f"Cannot list directory {path}: {e}")
                continue
        
        total = len(all_dist_info_dirs)
        for i, dist_path in enumerate(all_dist_info_dirs):
            try:
                dist = importlib.metadata.Distribution.at(dist_path)
                pkg_info = PackageUtils.get_package_info_modern(dist)
                if pkg_info and pkg_info['name'] != 'N/A':
                    packages.append(pkg_info)
                else:
                    damaged_packages.append(dist_path)
                
                self._queue_status_update(f"Scanning... ({i+1}/{total}) {dist.metadata.get('Name', '')}", scan_id)

            except Exception:
                damaged_packages.append(dist_path)
                self._queue_status_update(f"Scanning... ({i+1}/{total}) Found damaged package!", scan_id)


        reverse_deps = defaultdict(list)
        for pkg in packages:
            if pkg.get('requires'):
                for req_str in pkg['requires']:
                    req_name = re.split(r'[<>=!~ (]', req_str)[0].strip()
                    if req_name and req_name != pkg['name']:
                        reverse_deps[req_name].append(pkg['name'])

        return packages, reverse_deps, damaged_packages

    def _check_for_outdated_packages_task(self, scan_id):
        """Task to check for outdated packages by running 'pip list --outdated'."""
        try:
            if self.package_manager == 'uv':
                command = [self.package_manager_path, "pip", "list", "--outdated", "--format", "json", "-p", self.current_interpreter]
            else:
                command = [self.current_interpreter, "-m", "pip", "list", "--outdated", "--format", "json"]

            result_proc = subprocess.run(
                command, capture_output=True, check=True, env=self._get_subprocess_env(),
                text=True, encoding='utf-8', errors='replace'
            )
            return {item['name']: item for item in json.loads(result_proc.stdout)}
        except Exception as e:
            print(f"Could not check for outdated packages: {e}")
            self.task_queue.put((messagebox.showerror, ("Update Check Failed", f"Could not check for outdated packages.\n\nError: {e}")))
            return {}

    def _on_installed_loaded(self, result, scan_id):
        """Callback executed after only the installed list is loaded."""
        if scan_id != self.current_scan_id: return

        packages, reverse_deps, damaged = result
        if packages:
            self.all_packages = sorted(packages, key=lambda p: p['name'].lower())
            self.reverse_deps = reverse_deps
        self.damaged_packages_cache = damaged
        self.cache_manager.save(self.current_interpreter, {
            "packages": self.all_packages,
            "reverse_deps": self.reverse_deps,
            "damaged_packages": self.damaged_packages_cache
        })

        self._filter_packages()
        self._update_ui_state(False)
        self.status_manager.update("Ready.")

    def _on_packages_loaded_then_check(self, result, scan_id):
        """Callback executed after loading packages, which then triggers an update check."""
        if scan_id != self.current_scan_id: return

        packages, reverse_deps, damaged = result
        if packages:
            self.all_packages = sorted(packages, key=lambda p: p['name'].lower())
            self.reverse_deps = reverse_deps
        self.damaged_packages_cache = damaged
        self.cache_manager.save(self.current_interpreter, {
            "packages": self.all_packages,
            "reverse_deps": self.reverse_deps,
            "damaged_packages": self.damaged_packages_cache
        })

        self._filter_packages()
        self._queue_status_update("Checking for outdated packages...", scan_id)
        self._run_in_thread(self._check_for_outdated_packages_task, scan_id, on_complete=lambda res: self._on_outdated_checked(res, scan_id))

    def _on_outdated_checked(self, outdated_map, scan_id):
        """Callback executed after the outdated check is complete."""
        if scan_id != self.current_scan_id: return

        self.outdated_packages = outdated_map
        if outdated_map:
            self.upgrade_all_btn.config(state=tk.NORMAL, style="Outdated.TButton")
        else:
            self.upgrade_all_btn.config(state=tk.DISABLED, style="TButton")
        self._populate_tree()
        self._filter_packages()
        self._update_ui_state(False)

        num_outdated = len(self.outdated_packages)
        status = f"Found {num_outdated} outdated package(s)." if num_outdated > 0 else "All packages are up-to-date."
        self.status_manager.update(status)

    def _update_status_bar(self):
        """Updates the status bar with current package statistics."""
        total_count = len(self.all_packages)
        shown_count = len(self.tree.get_children())
        total_size = sum(p['size'] for p in self.all_packages)

        status_parts = [f"Total: {total_count}", f"Shown: {shown_count}", f"Size: {PackageUtils.format_size(total_size)}"]
        status_text = " | ".join(status_parts)

        selected_items = self.tree.selection()
        if selected_items:
            package_map = {p['name']: p for p in self.all_packages}
            selected_size = sum(package_map.get(name, {}).get('size', 0) for name in selected_items)
            status_text += f" || Selected: {len(selected_items)} ({PackageUtils.format_size(selected_size)})"
        self.status_var.set(status_text)

    def _is_package_outdated(self, pkg_name):
        """
        Checks if a package is outdated, accounting for name normalization
        discrepancies between tools like pip and uv.
        Returns the outdated info dict if found, otherwise None.
        """
        if pkg_name in self.outdated_packages:
            return self.outdated_packages[pkg_name]

        normalized_name = re.sub(r"[-.]+", "_", pkg_name).lower()

        for outdated_name, info in self.outdated_packages.items():
             normalized_outdated_name = re.sub(r"[-.]+", "_", outdated_name).lower()
             if normalized_name == normalized_outdated_name:
                 return info

        return None

    def _populate_tree(self, packages=None):
        """Populates the Treeview with package data."""
        selected_items = self.tree.selection()

        self.tree.delete(*self.tree.get_children())
        package_source = packages if packages is not None else self.all_packages

        for pkg in package_source:
            tags = []
            version_display = pkg["version"]
            outdated_info = self._is_package_outdated(pkg["name"])
            if outdated_info:
                tags.append('outdated')
                latest_ver = outdated_info.get('latest_version', '')
                version_display = f"{pkg['version']} → {latest_ver}"

            if pkg['name'].lower() in self.vulnerabilities_cache:
                tags.append('vulnerable')

            install_date = datetime.datetime.fromtimestamp(pkg["install_date_ts"]) if pkg["install_date_ts"] else None

            self.tree.insert(
                "", tk.END, iid=pkg["name"],
                values=(pkg["name"], version_display, PackageUtils.format_size(pkg["size"]), PackageUtils.format_date(install_date)),
                tags=tuple(tags)
            )

        if self.last_sort_column:
            self._sort_column(self.last_sort_column, self.last_sort_reverse)

        for item in selected_items:
            if self.tree.exists(item):
                self.tree.selection_add(item)

        self._update_status_bar()

    def _filter_packages(self, *args):
        """Filters the displayed packages based on search query and 'outdated' checkbox."""
        query = self.search_var.get().lower()
        show_outdated_only = self.show_outdated_var.get()

        filtered = [
            pkg for pkg in self.all_packages
            if query in pkg['name'].lower() and (not show_outdated_only or self._is_package_outdated(pkg['name']))
        ]
        self._populate_tree(filtered)

    def _sort_column(self, col, reverse):
        """Sorts the Treeview by the selected column."""
        key_func_map = {
            "Version": lambda iid: PackageUtils.get_version_sort_key(self.tree.set(iid, "Version")),
            "Size": lambda iid: next((p['size'] for p in self.all_packages if p['name'] == iid), 0),
            "Date": lambda iid: next((p['install_date_ts'] for p in self.all_packages if p['name'] == iid), 0),
        }
        key_func = key_func_map.get(col, lambda iid: self.tree.set(iid, col).lower())

        data = [(key_func(child), child) for child in self.tree.get_children('')]
        data.sort(key=lambda t: t[0], reverse=reverse)

        for index, (_, child) in enumerate(data):
            self.tree.move(child, '', index)

        for c in self.tree['columns']:
            text = self.tree.heading(c, 'text').replace(' ↑', '').replace(' ↓', '')
            self.tree.heading(c, text=text)

        new_text = f"{self.tree.heading(col, 'text')}{' ↓' if reverse else ' ↑'}"
        self.tree.heading(col, text=new_text, command=lambda: self._sort_column(col, not reverse))

        self.last_sort_column = col
        self.last_sort_reverse = reverse

    def _pip_action(self, action, packages, title, question, is_question=True, flags=None, on_complete_extra=None, packages_to_clear_from_outdated=None):
        """A generic handler for running pip commands."""
        self._terminate_active_process()
        if not packages and not (action == "install" and "-r" in (flags or [])):
            return

        display_packages = packages if "-r" not in (flags or []) else []
        question_str = f"{question} {len(display_packages)} package(s)?\n\n{', '.join(display_packages)}"

        if is_question and not messagebox.askyesno(title, question_str):
            return

        self._update_ui_state(True)
        status_msg_count = len(packages) if packages else "from file"
        self.status_manager.set_persistent(f"Running '{action}' on {status_msg_count} package(s)...")

        local_flags = list(flags) if flags else []

        if self.package_manager == 'uv':
            command = [self.package_manager_path, "pip", action, "-p", self.current_interpreter]
        else:
            command = [self.current_interpreter, "-m", "pip", action]
            if action == "uninstall":
                local_flags.append("--yes")

        command.extend(local_flags)
        command.extend(packages)

        def on_complete():
            if on_complete_extra:
                on_complete_extra()

            if packages_to_clear_from_outdated:
                for pkg_name in packages_to_clear_from_outdated:
                    self.outdated_packages.pop(pkg_name, None)

            if self.auto_check_var.get():
                self.refresh_and_check_updates()
            else:
                self.refresh_installed_only()

        self._run_pip_command(command, f"{title} Log", on_complete)

    def _run_pip_command(self, command, title, on_complete=None):
        """Executes a pip command in a separate thread and displays output in a log window."""
        log_window = tk.Toplevel(self.root)
        log_window.title(title)
        log_window.geometry("700x450")
        log_text = scrolledtext.ScrolledText(log_window, wrap=tk.WORD, state=tk.DISABLED, bg="black", fg="white", font=("Courier New", 9))
        log_text.pack(expand=True, fill=tk.BOTH)

        def write_to_log(message):
            log_text.config(state=tk.NORMAL)
            log_text.insert(tk.END, message)
            log_text.see(tk.END)
            log_text.config(state=tk.DISABLED)

        def task():
            proc = None
            try:
                proc = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    env=self._get_subprocess_env(),
                    text=True, encoding='utf-8', errors='replace'
                )
                with self.process_lock:
                    self.active_process = proc

                for line in iter(proc.stdout.readline, ''):
                    self.task_queue.put((write_to_log, (line,)))

                proc.wait()
                final_msg = f"\n--- Process finished with exit code {proc.returncode} ---\n"
                self.task_queue.put((write_to_log, (final_msg,)))
            except Exception as e:
                error_msg = f"\n--- An exception occurred: {e} ---\n"
                self.task_queue.put((write_to_log, (error_msg,)))
            finally:
                with self.process_lock:
                    if self.active_process is proc:
                        self.active_process = None
                if on_complete:
                    self.task_queue.put((on_complete, ()))

        self._run_in_thread(task)

    def delete_selected(self):
        """Uninstalls the selected packages."""
        selected = list(self.tree.selection())
        if not selected: return

        critical_to_uninstall = set(p.lower() for p in selected) & self.RESTART_REQUIRED_PACKAGES
        if critical_to_uninstall and self.current_interpreter == sys.executable:
            pkg_name = list(critical_to_uninstall)[0]
            msg = (f"To safely uninstall '{pkg_name}', which is currently in use, the application needs to restart.\n\n"
                   "The app will close, run the uninstallation, and then restart automatically. Continue?")
            if messagebox.askyesno("Restart Required for Uninstallation", msg, icon='warning'):
                args = [sys.executable, sys.argv[0], '--uninstall-on-startup', pkg_name]
                subprocess.Popen(args)
                self.root.destroy()
            return

        if 'pip' in [s.lower() for s in selected]:
            messagebox.showwarning(
                "Action Not Recommended",
                "Uninstalling 'pip' is a potentially destructive action and is not directly supported through this UI.")
            return

        self._pip_action("uninstall", selected, "Confirm Deletion", "Are you sure you want to delete",
                         packages_to_clear_from_outdated=selected)

    def upgrade_selected(self):
        """Upgrades the selected packages that are marked as outdated."""
        to_upgrade = [iid for iid in self.tree.selection() if self.tree.item(iid, 'tags') and 'outdated' in self.tree.item(iid, 'tags')]
        if not to_upgrade: return
        self._pip_action("install", to_upgrade, "Confirm Upgrade", "Are you sure you want to upgrade",
                         flags=["--upgrade"],
                         packages_to_clear_from_outdated=to_upgrade)

    def upgrade_all_outdated(self):
        """Upgrades all packages marked as outdated after showing a warning."""
        if self.package_manager == 'uv':
            allowed_installers = ['pip', 'uv']
        else:
            allowed_installers = ['pip']

        package_map = {p['name']: p for p in self.all_packages}
        all_outdated_names = list(self.outdated_packages.keys())
        packages_to_upgrade = [
            name for name in all_outdated_names
            if package_map.get(name, {}).get('installer') in allowed_installers
        ]

        if not packages_to_upgrade: return
        warning_message = (
            f"Are you sure you want to upgrade all {len(packages_to_upgrade)} manageable outdated packages?\n\n"
            "WARNING: This can potentially break dependencies.")
        if messagebox.askyesno("Confirm Upgrade All", warning_message, icon='warning'):
            self._pip_action("install", packages_to_upgrade, "Upgrade All Log", "Upgrading all outdated packages...",
                             is_question=False,
                             flags=["--upgrade"],
                             packages_to_clear_from_outdated=packages_to_upgrade)

    def install_package(self):
        """Installs new packages from the entry field."""
        packages_str = self.package_entry.get().strip()
        if not packages_str:
            return

        packages_to_install = packages_str.split()

        title = f"Installation of {len(packages_to_install)} package(s)"
        question = f"Installing {', '.join(packages_to_install)}"

        extra_flags = []
        if self.force_reinstall_var.get():
            if self.package_manager == 'uv':
                extra_flags.extend(['--reinstall', '--no-cache'])
            else:
                extra_flags.extend(['--force-reinstall', '--no-cache-dir'])

        self._pip_action("install", packages_to_install, title, question,
                         is_question=False,
                         flags=extra_flags,
                         on_complete_extra=lambda: self.package_entry.delete(0, tk.END))

    def install_from_file(self, filepath=None):
        """Opens a file dialog to select a requirements.txt file and then confirms the installation."""
        if not filepath:
            filepath = filedialog.askopenfilename(
                title="Select requirements.txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
            )
        if filepath:
            self.confirm_and_install_from_file(filepath)

    def confirm_and_install_from_file(self, filepath):
        """Reads a requirements file, asks for user confirmation, then installs."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

            if not lines:
                messagebox.showinfo("Empty File", "The selected requirements file is empty or only contains comments.")
                return

            packages_to_show = "\n".join(lines[:15])
            if len(lines) > 15:
                packages_to_show += f"\n...and {len(lines) - 15} more."

            question = (
                f"Are you sure you want to install {len(lines)} package(s) from {os.path.basename(filepath)}?\n\n"
                f"{packages_to_show}"
            )

            if messagebox.askyesno("Confirm Installation from File", question):
                self._pip_action("install", [], "Installation from File", "",
                                 is_question=False,
                                 flags=["-r", filepath])
        except Exception as e:
            messagebox.showerror("Error Reading File", f"Could not read the file: {e}")

    def install_from_pyproject(self, filepath=None):
        """Handles the logic for installing from a pyproject.toml file."""
        if not TOMLI_AVAILABLE:
            self._install_optional_dependency('tomli', on_success=self.install_from_pyproject)
            return

        if not filepath:
            filepath = filedialog.askopenfilename(
                title="Select pyproject.toml",
                filetypes=[("TOML files", "*.toml"), ("All files", "*.*")]
            )
        if filepath:
            self.confirm_and_install_from_pyproject(filepath)

    def confirm_and_install_from_pyproject(self, filepath):
        """Parses a pyproject.toml file, shows a selection dialog, and installs dependencies."""
        try:
            dependencies = self._parse_pyproject_toml(filepath)
            
            if not dependencies['main'] and not dependencies['optional']:
                messagebox.showinfo("No Dependencies Found", f"No dependencies found in {os.path.basename(filepath)} under the [project] table.")
                return

            dialog = PyProjectInstallDialog(self.root, dependencies)
            packages_to_install = dialog.result

            if packages_to_install:
                self._pip_action("install", packages_to_install, "Installing from pyproject.toml", "", is_question=False)

        except Exception as e:
            messagebox.showerror("Error Processing File", f"Could not process {os.path.basename(filepath)}:\n\n{e}")

    def _parse_pyproject_toml(self, filepath):
        """Parses a pyproject.toml file and extracts dependencies."""
        with open(filepath, "rb") as f:
            data = tomli.load(f)
        
        project_table = data.get("project", {})
        
        main_deps = project_table.get("dependencies", [])
        optional_deps = project_table.get("optional-dependencies", {})
        
        return {"main": main_deps, "optional": optional_deps}

    def _on_orphan_selection_changed(self, event=None):
        if self.orphan_tree.selection():
            self.uninstall_orphans_btn.config(state=tk.NORMAL)
        else:
            self.uninstall_orphans_btn.config(state=tk.DISABLED)

    def _queue_status_update_for_tool(self, label_widget, message):
        """Queues a status update for a specific label widget in a tool tab."""
        def update_task():
            label_widget.config(text=message)
        self.task_queue.put((update_task, ()))

    def find_damaged_packages(self):
        """Runs a suite of checks to find broken or corrupted packages."""
        if not self.all_packages:
             messagebox.showinfo("No Data", "Please perform a refresh from the 'Manage Packages' tab first to scan the environment.")
             return

        options = {
            "check_deps": self.check_deps_var.get(),
            "check_hashes": self.check_hashes_var.get(),
            "check_import": self.check_import_var.get(),
            "check_metadata_files": self.check_metadata_files_var.get(),
        }

        if not any(options.values()) and not self.damaged_packages_cache:
            messagebox.showinfo("No Checks Selected", "Please select at least one check to perform.")
            return

        self._update_ui_state(True)
        self.damaged_status_label.config(text="Scanning...")
        self.damaged_tree.delete(*self.damaged_tree.get_children())
        self.root.update_idletasks()

        self._run_in_thread(self._scan_for_damaged_packages_task, options, on_complete=self._on_damaged_scan_complete)

    def _scan_for_damaged_packages_task(self, options):
        """The background task that performs all the selected damage checks."""
        import base64
        from importlib.metadata import packages_distributions

        problems = []
        if self.damaged_packages_cache:
            for path in self.damaged_packages_cache:
                basename = os.path.basename(path).replace('.dist-info', '')
                try:
                    package_name = basename.rsplit('-', 1)[0]
                except IndexError:
                    package_name = basename
                problems.append({
                    "id": path,
                    "name": package_name,
                    "problem": "Unparseable metadata",
                    "details": f"Could not parse metadata from: {path}",
                    "type": "reinstallable"
                })

        # === Dependency Check (Check #1) ===
        if options["check_deps"]:
            self._queue_status_update_for_tool(self.damaged_status_label, "Running 'pip check'...")
            try:
                cmd = [self.current_interpreter, "-m", "pip", "check"]
                result_proc = subprocess.run(
                    cmd, capture_output=True, env=self._get_subprocess_env(), timeout=120,
                    text=True, encoding='utf-8', errors='replace'
                )
                output = result_proc.stdout
                for line in output.strip().splitlines():
                    parts = line.split(" has requirement ", 1)
                    if len(parts) == 2:
                        package_part, req_part = parts
                        package_name_from_check = package_part.split(' ')[0]
                        problems.append({"id": f"dep-{package_name_from_check}", "name": package_name_from_check, "problem": "Dependency conflict", "details": req_part, "type": "reinstallable"})
            except Exception as e:
                print(f"Failed to run pip check: {e}")

        dist_to_module_map = {}
        if options["check_import"]:
            self._queue_status_update_for_tool(self.damaged_status_label, "Building import map...")
            try:
                all_mappings = packages_distributions()
                for module, dists in all_mappings.items():
                    for dist_name in dists:
                        dist_to_module_map[dist_name] = module
            except Exception as e:
                print(f"Could not build package distribution map: {e}")

        total = len(self.all_packages)
        for i, pkg_data in enumerate(self.all_packages):
            pkg_name = pkg_data['name']
            self._queue_status_update_for_tool(self.damaged_status_label, f"Checking {pkg_name} ({i+1}/{total})...")

            try:
                dist = importlib.metadata.distribution(pkg_name)
            except Exception as e:
                problems.append({"id": f"dist-fail-{pkg_name}", "name": pkg_name, "problem": "Distribution lookup failed", "details": str(e), "type": "reinstallable"})
                continue

            # === Test Import (Check #3) ===
            if options["check_import"]:
                try:
                    import_name_to_test = dist_to_module_map.get(pkg_name)
                    if import_name_to_test:
                        cmd = [self.current_interpreter, "-c", f"__import__('{import_name_to_test}')"]
                        result = subprocess.run(
                            cmd, capture_output=True, env=self._get_subprocess_env(), timeout=15,
                            text=True, encoding='utf-8', errors='replace'
                        )
                        if result.returncode != 0:
                            error_details = (result.stderr or result.stdout).strip()
                            problems.append({"id": f"import-{pkg_name}", "name": pkg_name, "problem": "Import failed", "details": error_details.split('\n')[-1], "type": "reinstallable"})
                except Exception as e:
                    problems.append({"id": f"import-fail-{pkg_name}", "name": pkg_name, "problem": "Import check failed", "details": str(e), "type": "reinstallable"})

            # === File Checks (Hashes #2 and Missing #4) ===
            if options["check_hashes"] or options["check_metadata_files"]:
                try:
                    dist_files = dist.files
                    if not dist_files:
                        continue

                    for file_info in dist_files:
                        try:
                            file_path_str = str(file_info)
                            full_path = file_info.locate()

                            if options["check_metadata_files"]:
                                meta_dir = dist._path
                                for name in ("METADATA", "RECORD", "WHEEL"):
                                    meta_path = os.path.join(meta_dir, name)
                                    if not os.path.exists(meta_path):
                                        problems.append({"id": f"missing-meta-{pkg_name}-{name}", "name": pkg_name, "problem": "Missing metadata file", "details": f"Metadata file not found: {name}", "type": "reinstallable"})
                                        continue
                            
                            if options["check_hashes"] and file_info.hash is not None and os.path.isfile(full_path):
                                with open(full_path, 'rb') as f:
                                    digest_bytes = hashlib.sha256(f.read()).digest()
                                actual_hash_b64 = base64.urlsafe_b64encode(digest_bytes).rstrip(b'=').decode('ascii')
                                
                                if file_info.hash.value != actual_hash_b64:
                                    problems.append({"id": f"hash-{pkg_name}-{file_path_str}", "name": pkg_name, "problem": "File hash mismatch", "details": f"File: {file_path_str}", "type": "reinstallable"})

                        except Exception as e:
                            problems.append({"id": f"filecheck-fail-{pkg_name}-{str(file_info)}", "name": pkg_name, "problem": "File check failed", "details": f"Error checking file {str(file_info)}: {e}", "type": "reinstallable"})
                
                except (UnicodeDecodeError, Exception) as e:
                    problems.append({"id": f"record-read-fail-{pkg_name}", "name": pkg_name, "problem": "Corrupted RECORD file", "details": f"Could not parse file list. Error: {e}", "type": "reinstallable"})

        unique_problems = {p['id']: p for p in problems}.values()
        return list(unique_problems)

    def _on_damaged_scan_complete(self, problems):
        """Callback to populate the tree with results from the damage scan."""
        self._update_ui_state(False)
        for problem in problems:
            self.damaged_tree.insert("", tk.END, iid=problem['id'],
                                     values=(problem['name'], problem['problem'], problem['details']),
                                     tags=(problem['type'],))

        count = len(self.damaged_tree.get_children())
        self.damaged_status_label.config(text=f"Scan complete. Found {count} problem(s).")
        self._on_damaged_selection_changed()

    def _on_damaged_selection_changed(self, event=None):
        """Enables or disables the 'Reinstall' button based on selection."""
        selection = self.damaged_tree.selection()
        if not selection:
            self.reinstall_damaged_btn.config(state=tk.DISABLED)
            return

        all_reinstallable = True
        for item_id in selection:
            tags = self.damaged_tree.item(item_id, 'tags')
            if 'reinstallable' not in tags:
                all_reinstallable = False
                break

        if all_reinstallable:
            self.reinstall_damaged_btn.config(state=tk.NORMAL)
        else:
            self.reinstall_damaged_btn.config(state=tk.DISABLED)

    def reinstall_selected_damaged(self):
        """Force-reinstalls the packages selected in the damaged packages list."""
        selection = self.damaged_tree.selection()
        if not selection: return

        packages_to_reinstall = sorted(list({self.damaged_tree.item(item_id, 'values')[0] for item_id in selection}))

        msg = f"This will attempt to force-reinstall {len(packages_to_reinstall)} package(s):\n\n" \
              f"{', '.join(packages_to_reinstall)}\n\n" \
              "This is often effective for fixing the detected issues. Continue?"

        if messagebox.askyesno("Confirm Reinstallation", msg):
            if self.package_manager == 'uv':
                flags = ['--reinstall', '--no-cache']
            else:
                flags = ['--force-reinstall', '--no-cache-dir']

            self._pip_action(
                "install", packages_to_reinstall, "Reinstalling Damaged Packages",
                "Reinstalling...", is_question=False, flags=flags,
                on_complete_extra=self.find_damaged_packages
            )

    def find_orphaned_packages(self):
        if not self.all_packages:
            messagebox.showinfo("No Packages Loaded", "Please load a package list first via the 'Refresh' button on the 'Manage Packages' tab.")
            return

        self.orphan_status_label.config(text="Analyzing dependencies...")
        self.root.update_idletasks()

        all_installed_names = {pkg['name'] for pkg in self.all_packages}
        dependency_names = set(self.reverse_deps.keys())
        essential_packages = {'pip', 'setuptools', 'wheel'}

        orphan_names = all_installed_names - dependency_names - essential_packages
        self.orphaned_packages_cache = sorted([pkg for pkg in self.all_packages if pkg['name'] in orphan_names], key=lambda p: p['name'].lower())

        self.orphan_tree.delete(*self.orphan_tree.get_children())
        for pkg in self.orphaned_packages_cache:
            install_date = datetime.datetime.fromtimestamp(pkg["install_date_ts"]) if pkg["install_date_ts"] else None
            self.orphan_tree.insert(
                "", tk.END, iid=pkg["name"],
                values=(pkg["name"], pkg["version"], PackageUtils.format_size(pkg["size"]), PackageUtils.format_date(install_date))
            )

        count = len(self.orphaned_packages_cache)
        self.orphan_status_label.config(text=f"Found {count} potential orphaned package(s).")
        self._on_orphan_selection_changed()

    def uninstall_selected_orphans(self):
        selected = self.orphan_tree.selection()
        if not selected: return

        package_list = "\n".join(selected[:10])
        if len(selected) > 10:
            package_list += f"\n...and {len(selected) - 10} more."

        question = (
            f"Are you sure you want to uninstall these {len(selected)} selected package(s)?\n\n"
            "These are packages that do not appear to be required by any other installed package. "
            "Ensure they are not top-level tools you wish to keep (e.g., pytest, black, mypy).\n\n"
            f"{package_list}"
        )

        if messagebox.askyesno("Confirm Uninstall Orphans", question, icon='warning'):
            def on_uninstall_complete():
                self.orphan_tree.delete(*self.orphan_tree.get_children())
                self.orphaned_packages_cache = []
                self.orphan_status_label.config(text="Uninstall complete. Click 'Find' again to re-scan.")
                self._on_orphan_selection_changed()

            self._pip_action(
                "uninstall", list(selected), "Uninstalling Orphaned Packages", "Uninstalling...",
                is_question=False, on_complete_extra=on_uninstall_complete
            )

    def run_vulnerability_scan(self):
        """Checks if pip-audit is installed in the target env and then runs the scan."""
        try:
            check_command = [self.current_interpreter, "-m", "pip", "show", "pip-audit"]
            subprocess.run(check_command, check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)

            self._update_ui_state(True)
            self.vuln_status_label.config(text="Scanning for vulnerabilities...")
            self._run_in_thread(self._run_vulnerability_scan_task, on_complete=self._on_vulnerability_scan_complete)

        except (subprocess.CalledProcessError, FileNotFoundError):
            self._install_optional_dependency(
                'pip-audit',
                target_interpreter=self.current_interpreter,
                on_success=self.run_vulnerability_scan
            )

    def _run_vulnerability_scan_task(self):
        """Runs pip-audit in a background thread and parses the JSON output."""
        command = [self.current_interpreter, "-m", "pip_audit", "-f", "json"]
        try:
            result_proc = subprocess.run(
                command, capture_output=True, env=self._get_subprocess_env(),
                text=True, encoding='utf-8', errors='replace'
            )
            stdout = result_proc.stdout
            stderr = result_proc.stderr

            if not stdout:
                if stderr:
                    return {"error": stderr}
                return {}

            data = json.loads(stdout)

            vulns_by_pkg = defaultdict(list)
            for dep in data.get('dependencies', []):
                if dep.get('vulns'):
                    for v in dep['vulns']:
                        vulns_by_pkg[dep['name'].lower()].append(v)
            return vulns_by_pkg

        except Exception as e:
            return {"error": str(e)}

    def _on_vulnerability_scan_complete(self, result):
        """Callback to populate the vulnerability tree with scan results."""
        self._update_ui_state(False)
        self.vuln_tree.delete(*self.vuln_tree.get_children())
        self.vulnerabilities_cache.clear()

        if "error" in result:
            self.vuln_status_label.config(text="Scan failed. See console for details.")
            print(f"pip-audit error: {result['error']}")
            return

        self.vulnerabilities_cache = result

        total_vulns = 0
        for name, vulns in result.items():
            pkg_info = next((p for p in self.all_packages if p['name'].lower() == name.lower()), None)
            version = pkg_info['version'] if pkg_info else '?'
            for v in vulns:
                total_vulns += 1
                self.vuln_tree.insert("", "end", values=(
                    name,
                    version,
                    v.get('id', 'N/A'),
                    v.get('description', 'N/A'),
                    ', '.join(v.get('fix_versions', []))
                ))

        self.vuln_status_label.config(text=f"Scan complete. Found {total_vulns} vulnerabilit(y/ies).")
        self._populate_tree()

    def _browse_for_req_in_file(self):
        filepath = filedialog.askopenfilename(
            title="Select requirements.in file",
            filetypes=[("Requirements IN", "*.in"), ("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filepath:
            self.req_in_path.set(filepath)
            if not self.req_out_path.get():
                out_path = os.path.splitext(filepath)[0] + ".txt"
                self.req_out_path.set(out_path)

    def _browse_for_req_out_file(self):
        filepath = filedialog.asksaveasfilename(
            title="Save requirements.txt as",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="requirements.txt"
        )
        if filepath:
            self.req_out_path.set(filepath)

    def compile_requirements(self):
        in_path = self.req_in_path.get()
        out_path = self.req_out_path.get()

        if not in_path or not out_path:
            messagebox.showerror("Error", "Please specify both input and output files.")
            return

        if self.package_manager == 'pip':
            try:
                check_command = [self.current_interpreter, "-m", "pip", "show", "pip-tools"]
                subprocess.run(
                    check_command,
                    check=True, capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
                    env=self._get_subprocess_env()
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                self._install_optional_dependency(
                    'pip-tools',
                    target_interpreter=self.current_interpreter,
                    on_success=self.compile_requirements
                )
                return

        self._update_ui_state(True)
        self.status_manager.set_persistent("Compiling requirements...")

        if self.package_manager == 'uv':
            command = [
                self.package_manager_path, "pip", "compile",
                "--output-file", out_path, in_path,
                "-p", self.current_interpreter
            ]
        else:
            command = [
                self.current_interpreter, "-m", "piptools", "compile",
                "--output-file", out_path, in_path
            ]

        def on_complete():
            self._update_ui_state(False)
            self.status_manager.update(f"Compilation finished. Saved to {os.path.basename(out_path)}")

        self._run_pip_command(command, "Compilation Log", on_complete)

    def _create_context_menu(self):
        """Creates the right-click context menu for the package list."""
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="Upgrade Selected", command=self.upgrade_selected)
        self.context_menu.add_command(label="Uninstall Selected", command=self.delete_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="View Details...", command=self.view_package_details)
        self.context_menu.add_command(label="Open Package Location", command=self.open_package_location)
        self.context_menu.add_command(label="Find on PyPI", command=self.open_pypi_page)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Export to requirements.txt", command=self.export_to_requirements)
        self.context_menu.add_command(label="Copy Name(s)", command=lambda: self.copy_to_clipboard('name'))
        self.context_menu.add_command(label="Copy Name and Version(s)", command=lambda: self.copy_to_clipboard('name-version'))

    def _show_context_menu(self, event):
        """Shows the context menu and enables/disables items based on selection."""
        selection = self.tree.selection()
        if not selection: return

        if self.package_manager == 'uv':
            allowed_installers = ['pip', 'uv']
        else:
            allowed_installers = ['pip']

        all_manageable = True
        package_map = {p['name']: p for p in self.all_packages}
        for item_id in selection:
            pkg = package_map.get(item_id)
            if not pkg or pkg.get('installer') not in allowed_installers:
                all_manageable = False
                break

        is_single = len(selection) == 1
        is_outdated = any(self.tree.item(item, 'tags') and 'outdated' in self.tree.item(item, 'tags') for item in selection)

        self.context_menu.entryconfigure("Upgrade Selected", state=tk.NORMAL if is_outdated and all_manageable else tk.DISABLED)
        self.context_menu.entryconfigure("Uninstall Selected", state=tk.NORMAL if all_manageable else tk.DISABLED)
        self.context_menu.entryconfigure("View Details...", state=tk.NORMAL if is_single else tk.DISABLED)
        self.context_menu.entryconfigure("Open Package Location", state=tk.NORMAL if is_single else tk.DISABLED)
        self.context_menu.entryconfigure("Find on PyPI", state=tk.NORMAL if is_single else tk.DISABLED)
        self.context_menu.entryconfigure("Export to requirements.txt", state=tk.NORMAL if selection else tk.DISABLED)

        self.context_menu.post(event.x_root, event.y_root)

    def open_package_location(self):
        """Opens the selected package's installation directory in the file explorer."""
        selection = self.tree.selection()
        if not selection: return
        pkg = next((p for p in self.all_packages if p['name'] == selection[0]), None)
        if pkg and pkg['location']:
            try:
                if sys.platform == "win32":
                    os.startfile(pkg['location'])
                else:
                    opener = "open" if sys.platform == "darwin" else "xdg-open"
                    subprocess.run([opener, pkg['location']], check=True)
            except Exception as e:
                messagebox.showerror("Error", f"Could not open folder:\n{e}")

    def view_package_details(self):
        """Displays a window with detailed metadata for the selected package."""
        selection = self.tree.selection()
        if not selection: return
        pkg_name = selection[0]
        pkg = next((p for p in self.all_packages if p['name'] == pkg_name), None)
        if not pkg: return

        details_win = tk.Toplevel(self.root)
        details_win.title(f"Details for {pkg_name}")
        details_win.geometry("500x550")

        main_pane = ttk.PanedWindow(details_win, orient=tk.VERTICAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        desc_frame = ttk.Frame(main_pane)
        desc_text = scrolledtext.ScrolledText(desc_frame, wrap=tk.WORD, font=("Segoe UI", 9), relief=tk.SOLID, borderwidth=1)
        desc_text.pack(expand=True, fill=tk.BOTH)

        info_parts = []
        if pkg.get('metadata'):
            metadata_items = list(pkg['metadata'].items())
            description_item = None
            for i, (k, v) in enumerate(metadata_items):
                if k.lower() == 'description':
                    description_item = metadata_items.pop(i)
                    break

            for k, v in metadata_items:
                info_parts.append(f"{k}: {v}\n")

            if description_item:
                info_parts.append(f"\n{description_item[0]}:\n{description_item[1]}")

        if not info_parts:
             info_parts.append("No description or metadata provided.")

        full_info = "".join(info_parts)

        desc_text.insert(tk.END, full_info)
        desc_text.config(state=tk.DISABLED)
        main_pane.add(desc_frame, weight=1)

        bottom_pane = ttk.PanedWindow(main_pane, orient=tk.HORIZONTAL)
        main_pane.add(bottom_pane, weight=2)

        deps_lf = ttk.LabelFrame(bottom_pane, text="Dependencies", padding=5)
        deps_text = scrolledtext.ScrolledText(deps_lf, wrap=tk.WORD, font=("Segoe UI", 9), relief=tk.FLAT, borderwidth=0,
                                              background=details_win.cget('bg'))
        deps_text.pack(fill=tk.BOTH, expand=True)

        deps_content = "\n".join(sorted(pkg['requires'])) if pkg['requires'] else "None"
        deps_text.insert(tk.END, deps_content)
        deps_text.config(state=tk.DISABLED)
        bottom_pane.add(deps_lf, weight=1)

        req_by_lf = ttk.LabelFrame(bottom_pane, text="Required By", padding=5)
        req_by_text = scrolledtext.ScrolledText(req_by_lf, wrap=tk.WORD, font=("Segoe UI", 9), relief=tk.FLAT, borderwidth=0,
                                                background=details_win.cget('bg'))
        req_by_text.pack(fill=tk.BOTH, expand=True)

        required_by_list = sorted(self.reverse_deps.get(pkg['name'], []))
        if required_by_list:
            pkg_map = {p['name']: p for p in self.all_packages}
            lines = []
            for requirer_name in required_by_list:
                requirer_pkg = pkg_map.get(requirer_name)
                version = requirer_pkg['version'] if requirer_pkg else '?'
                lines.append(f"{requirer_name} ({version})")
            req_by_content = "\n".join(lines)
        else:
            req_by_content = "Nothing in this environment"

        req_by_text.insert(tk.END, req_by_content)
        req_by_text.config(state=tk.DISABLED)
        bottom_pane.add(req_by_lf, weight=1)

        if pkg_name.lower() in self.vulnerabilities_cache:
            vuln_lf = ttk.LabelFrame(main_pane, text="🚨 Vulnerabilities Found!", padding=5)
            vuln_text = scrolledtext.ScrolledText(vuln_lf, wrap=tk.WORD, font=("Segoe UI", 9), height=15,
                                                  relief=tk.FLAT, borderwidth=0, background=details_win.cget('bg'))
            vuln_text.pack(fill=tk.BOTH, expand=True)

            vuln_info = []
            for v in self.vulnerabilities_cache[pkg_name.lower()]:
                vuln_info.append(f"ID: {v['id']}\nDescription: {v['description']}\nFixed in: {', '.join(v.get('fix_versions', []))}\n")
            vuln_text.insert(tk.END, "\n".join(vuln_info))
            vuln_text.config(state=tk.DISABLED)

            main_pane.add(vuln_lf, weight=1)

    def open_pypi_page(self):
        """Opens the selected package's page on PyPI.org in a web browser."""
        selection = self.tree.selection()
        if selection:
            webbrowser.open_new_tab(f"https://pypi.org/project/{selection[0]}/")

    def copy_to_clipboard(self, format_type):
        """Copies the selected package names to the clipboard."""
        selection = self.tree.selection()
        if not selection: return

        self.root.clipboard_clear()
        if format_type == 'name':
            text_to_copy = "\n".join(selection)
        else:
            pkg_map = {p['name']: p for p in self.all_packages}
            lines = [f"{name}=={pkg_map[name]['version']}" for name in selection if name in pkg_map]
            text_to_copy = "\n".join(lines)

        self.root.clipboard_append(text_to_copy)
        self.status_manager.update(f"Copied {len(selection)} item(s) to clipboard.")

    def export_to_requirements(self):
        """Exports selected packages to a requirements.txt file."""
        selection = self.tree.selection()
        if not selection: return

        filepath = filedialog.asksaveasfilename(
            title="Export to requirements.txt",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile="requirements.txt"
        )

        if not filepath: return

        try:
            pkg_map = {p['name']: p for p in self.all_packages}
            lines = [f"{name}=={pkg_map[name]['version']}" for name in sorted(selection) if name in pkg_map]
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))
            self.status_manager.update(f"Exported {len(lines)} packages to {os.path.basename(filepath)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export file: {e}")

    def show_version_selector(self):
        """Shows a dialog to select a specific version of a package from PyPI."""
        pkg_name = self.package_entry.get().strip().split('==')[0]
        if not pkg_name:
            messagebox.showinfo("Input Needed", "Please enter a package name first.")
            return

        self._update_ui_state(True)
        self.status_manager.set_persistent(f"Finding versions for {pkg_name}...")
        self._run_in_thread(self._fetch_pypi_versions_task, pkg_name, on_complete=self._display_version_selector_dialog)

    def _fetch_pypi_versions_task(self, pkg_name):
        """Task to get available versions for a package from PyPI."""
        try:
            command = [self.current_interpreter, "-m", "pip", "index", "versions", pkg_name]

            result_proc = subprocess.run(
                command, capture_output=True, timeout=15, env=self._get_subprocess_env(),
                text=True, encoding='utf-8', errors='replace'
            )
            stdout = result_proc.stdout
            stderr = result_proc.stderr

            if result_proc.returncode != 0:
                error_lines = (stderr or stdout).strip().split('\n')
                last_line = error_lines[-1] if error_lines else "Unknown pip error."
                if "No matching distribution found" in last_line:
                    return f"Error: No matching distribution found for '{pkg_name}'"
                return f"Error fetching versions:\n{last_line}"

            versions = []
            for line in stdout.strip().split('\n'):
                if "Available versions:" in line:
                    versions_str = line.split(":", 1)[1]
                    versions = [v.strip() for v in versions_str.split(',')]
                    break
            return versions
        except Exception as e:
            return f"An exception occurred: {e}"

    def _display_version_selector_dialog(self, result):
        """Callback to show the version selector dialog window."""
        self._update_ui_state(False)
        self.status_manager.update("", clear_after_ms=0)
        pkg_name = self.package_entry.get().strip().split('==')[0]

        if isinstance(result, str):
            messagebox.showerror(f"Error for '{pkg_name}'", result)
            return
        if not result:
            messagebox.showinfo(f"No Versions Found", f"Could not find any versions for '{pkg_name}'.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(f"Select version for {pkg_name}")
        dialog.geometry("300x400")
        dialog.transient(self.root)
        dialog.grab_set()

        list_frame = ttk.Frame(dialog, padding=5)
        list_frame.pack(fill=tk.BOTH, expand=True)
        listbox = tk.Listbox(list_frame)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox.config(yscrollcommand=scrollbar.set)
        for version in result: listbox.insert(tk.END, version)

        def on_ok():
            if listbox.curselection():
                self.package_entry.delete(0, tk.END)
                self.package_entry.insert(0, f"{pkg_name}=={listbox.get(listbox.curselection()[0])}")
            dialog.destroy()

        listbox.bind("<Double-Button-1>", lambda e: on_ok())

        btn_frame = ttk.Frame(dialog, padding=(5,0,5,5))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="OK", command=on_ok).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.RIGHT, padx=(0, 5))
        dialog.wait_window()

    def _clear_cache(self):
        """Deletes ALL package cache files across all known environments."""
        if messagebox.askyesno("Confirm", "Clear ALL caches for ALL environments? The next startup for each environment will be slower."):
            cleared_count, error = self.cache_manager.clear_all()
            if error:
                messagebox.showerror("Error", error)
            elif cleared_count > 0:
                messagebox.showinfo("Success", f"{cleared_count} cache file(s) have been cleared.")
            else:
                messagebox.showinfo("Info", "No cache files found to clear.")

def handle_startup_uninstall(package_name):
    """
    A special 'headless' mode to uninstall a package and then restart the app.
    This is called when the app is launched with --uninstall-on-startup.
    """
    print(f"--- Running startup uninstaller for: {package_name} ---")
    try:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        command = [sys.executable, "-m", "pip", "uninstall", "--yes", package_name]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace', env=env)

        if result.returncode == 0:
            print(f"Successfully uninstalled {package_name}.")
        else:
            print(f"Failed to uninstall {package_name}. Pip output:")
            print(result.stdout)
            print(result.stderr)

    except Exception as e:
        print(f"An exception occurred during startup uninstall: {e}")

    finally:
        print("--- Relaunching application ---")
        subprocess.Popen([sys.executable, sys.argv[0]])

def main():
    """Initializes and runs the application."""
    if '--uninstall-on-startup' in sys.argv:
        try:
            idx = sys.argv.index('--uninstall-on-startup')
            package_to_uninstall = sys.argv[idx + 1]
            handle_startup_uninstall(package_to_uninstall)
        except IndexError:
            print("Error: --uninstall-on-startup flag found without a package name.")
        return

    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    app = PackageManagerApp(root)
    root.mainloop()

if __name__ == '__main__':
    main()