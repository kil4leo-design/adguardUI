#!/usr/bin/env python3
# ==================== ADGUARD VPN GUI ====================
# ВЕРСИЯ: 1.6.0 (фиксированная структура интерфейса)
# БЛОК ИМПОРТОВ
import gi
import sys
import subprocess
import threading
import re
import os
import tempfile
import select
import time
from getpass import getuser

gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib

# ==================== КОНФИГУРАЦИЯ ====================
VERSION = "1.6.0"
APP_ID = "com.example.AdGuardVPN"
ADGUARD_PATH = "/opt/adguardvpn_cli/adguardvpn-cli"
CURRENT_USER = getuser()
ADGUARD_CONFIG_DIR = os.path.expanduser("~/.local/share/adguardvpn-cli")

# ==================== Начало ГЛАВНОЕ ОКНО ====================
class AdGuardVPNWindow(Gtk.ApplicationWindow):
    def __init__(self, application):
        super().__init__(application=application, title=f"AdGuard VPN v{VERSION}")
        self.set_default_size(600, 700)
        
        # Устанавливаем правильную рабочую директорию и окружение
        os.chdir(os.path.expanduser("~"))
        os.environ['HOME'] = os.path.expanduser("~")
        
        print(f"=== ИНИЦИАЛИЗАЦИЯ ПРОГРАММЫ v{VERSION} ===")
        print(f"Рабочая директория: {os.getcwd()}")
        print(f"Пользователь: {CURRENT_USER}")
        print(f"Конфиг AdGuard: {ADGUARD_CONFIG_DIR}")
        print(f"Python: {sys.version}")
        
        self.vpn_status = "disconnected"
        self.current_location = None
        self.locations = []
        self.fast_locations = []
        self.is_authenticated = False
        self.sudo_password = None
        self.sudo_password_remembered = False
        self.account_info = {}
        
        self.setup_ui()
        self.check_adguard_installed()
        
        # При запуске программы: отдельно проверяем авторизацию и отдельно загружаем локации
        self.check_auth_status_only()  # Сначала проверяем авторизацию
        # После проверки авторизации загружаем локации (если авторизованы)
        GLib.timeout_add(1000, self.auto_load_locations_if_authenticated)  # Задержка 1 секунда
# ==================== Конец ГЛАВНОЕ ОКНО ====================

# ==================== Начало НАСТРОЙКА ИНТЕРФЕЙСА ====================
    def setup_ui(self):
        # Главный контейнер с вкладками
        self.notebook = Gtk.Notebook()
        self.set_child(self.notebook)
        
        # Вкладка Основные функции
        main_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_tab.set_margin_top(10)
        main_tab.set_margin_bottom(10)
        main_tab.set_margin_start(10)
        main_tab.set_margin_end(10)
        self.notebook.append_page(main_tab, Gtk.Label(label="Главная"))
        
        # Вкладка Авторизация (только создаем пустую вкладку)
        auth_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        auth_tab.set_margin_top(10)
        auth_tab.set_margin_bottom(10)
        auth_tab.set_margin_start(10)
        auth_tab.set_margin_end(10)
        self.notebook.append_page(auth_tab, Gtk.Label(label="Авторизация"))
        
        # Вкладка Настройки
        settings_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        settings_tab.set_margin_top(10)
        settings_tab.set_margin_bottom(10)
        settings_tab.set_margin_start(10)
        settings_tab.set_margin_end(10)
        self.notebook.append_page(settings_tab, Gtk.Label(label="Настройки"))
        
        # Вкладка Дополнительно
        extra_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        extra_tab.set_margin_top(10)
        extra_tab.set_margin_bottom(10)
        extra_tab.set_margin_start(10)
        extra_tab.set_margin_end(10)
        self.notebook.append_page(extra_tab, Gtk.Label(label="Дополнительно"))
        
        # ===== ГЛАВНАЯ ВКЛАДКА =====
        # Статус VPN
        self.status_frame = Gtk.Frame()
        self.status_frame.set_hexpand(True)
        main_tab.append(self.status_frame)
        
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        status_box.set_margin_top(15)
        status_box.set_margin_bottom(15)
        status_box.set_margin_start(15)
        status_box.set_margin_end(15)
        self.status_frame.set_child(status_box)
        
        self.status_icon = Gtk.Image.new_from_icon_name("network-vpn-disabled-symbolic")
        self.status_icon.set_pixel_size(64)
        status_box.append(self.status_icon)
        
        self.status_label = Gtk.Label(label="VPN отключен")
        self.status_label.add_css_class("title-1")
        status_box.append(self.status_label)
        
        self.location_label = Gtk.Label(label="Локация: не выбрана")
        self.location_label.add_css_class("dim-label")
        status_box.append(self.location_label)
        
        # Статус авторизации
        self.auth_status_label = Gtk.Label(label="Статус авторизации: Проверка...")
        self.auth_status_label.add_css_class("dim-label")
        status_box.append(self.auth_status_label)
        
        # Кнопка обновления локаций
        self.refresh_locations_btn = Gtk.Button(label="Обновить локации")
        self.refresh_locations_btn.connect("clicked", self.on_refresh_locations_clicked)
        main_tab.append(self.refresh_locations_btn)
        
        # Разделитель
        main_tab.append(Gtk.Separator())
        
        # Выбор локации
        location_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        main_tab.append(location_box)
        
        location_label = Gtk.Label(label="Доступные локации:")
        location_label.set_halign(Gtk.Align.START)
        location_box.append(location_label)
        
        self.location_spinner = Gtk.Spinner()
        location_box.append(self.location_spinner)
        
        self.location_dropdown = Gtk.DropDown()
        self.location_dropdown.set_sensitive(False)
        self.location_dropdown.connect("notify::selected", self.on_location_changed)
        location_box.append(self.location_dropdown)
        
        # Объединенная кнопка подключения/отключения
        self.vpn_action_btn = Gtk.Button(label="Подключить")
        self.vpn_action_btn.add_css_class("suggested-action")
        self.vpn_action_btn.set_hexpand(True)
        self.vpn_action_btn.set_sensitive(False)
        self.vpn_action_btn.connect("clicked", self.on_vpn_action_clicked)
        main_tab.append(self.vpn_action_btn)
        
        # Кнопка статуса
        self.status_btn = Gtk.Button(label="Проверить статус")
        self.status_btn.set_hexpand(True)
        self.status_btn.connect("clicked", self.on_status_clicked)
        main_tab.append(self.status_btn)
        
        # Разделитель
        main_tab.append(Gtk.Separator())
        
        # Статус и информация
        stats_frame = Gtk.Frame()
        stats_frame.set_hexpand(True)
        main_tab.append(stats_frame)
        
        stats_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        stats_box.set_margin_top(10)
        stats_box.set_margin_bottom(10)
        stats_box.set_margin_start(10)
        stats_box.set_margin_end(10)
        stats_frame.set_child(stats_box)
        
        stats_title = Gtk.Label(label="Информация о подключении")
        stats_title.add_css_class("heading")
        stats_box.append(stats_title)
        
        self.stats_label = Gtk.Label(label="Нажмите 'Проверить статус' для начала работы")
        self.stats_label.set_selectable(True)
        self.stats_label.set_wrap(True)
        stats_box.append(self.stats_label)
        
        # ===== ВКЛАДКА АВТОРИЗАЦИИ =====
        # Главный контейнер с фиксированной структурой
        main_auth_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_auth_box.set_margin_top(10)
        main_auth_box.set_margin_bottom(10)
        main_auth_box.set_margin_start(10)
        main_auth_box.set_margin_end(10)
        auth_tab.append(main_auth_box)

        # ЗАГОЛОВОК (фиксированный вверху)
        auth_title = Gtk.Label(label="Авторизация AdGuard VPN")
        auth_title.add_css_class("title-2")
        main_auth_box.append(auth_title)

        # КНОПКИ (фиксированные вверху)
        auth_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        auth_buttons_box.set_margin_top(10)
        auth_buttons_box.set_margin_bottom(10)
        main_auth_box.append(auth_buttons_box)

        self.check_auth_btn = Gtk.Button(label="Проверить авторизацию")
        self.check_auth_btn.connect("clicked", self.on_check_auth_clicked)
        auth_buttons_box.append(self.check_auth_btn)

        self.login_btn = Gtk.Button(label="Войти в AdGuard VPN")
        self.login_btn.connect("clicked", self.on_login_clicked)
        auth_buttons_box.append(self.login_btn)

        self.logout_btn = Gtk.Button(label="Выйти из AdGuard VPN")
        self.logout_btn.connect("clicked", self.on_logout_clicked)
        auth_buttons_box.append(self.logout_btn)

        # РАСШИРЯЕМЫЙ ПРОМЕЖУТОК (чтобы статус был внизу)
        expander_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        expander_box.set_vexpand(True)
        main_auth_box.append(expander_box)

        # СТАТУС (внизу)
        status_frame = Gtk.Frame()
        status_frame.set_hexpand(True)
        main_auth_box.append(status_frame)

        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        status_box.set_margin_top(15)
        status_box.set_margin_bottom(15)
        status_box.set_margin_start(15)
        status_box.set_margin_end(15)
        status_frame.set_child(status_box)

        status_title = Gtk.Label(label="Статус авторизации")
        status_title.add_css_class("heading")
        status_box.append(status_title)

        # Информация о статусе
        self.account_info_label = Gtk.Label(label="Нажмите 'Проверить авторизацию'")
        self.account_info_label.set_halign(Gtk.Align.START)
        self.account_info_label.set_wrap(True)
        self.account_info_label.set_selectable(True)
        status_box.append(self.account_info_label)

        # Версия программы (в самом низу)
        version_auth_label = Gtk.Label(label=f"Версия программы: {VERSION}")
        version_auth_label.add_css_class("dim-label")
        version_auth_label.set_halign(Gtk.Align.START)
        main_auth_box.append(version_auth_label)
        
        # ===== ВКЛАДКА НАСТРОЕК =====
        settings_title = Gtk.Label(label="Настройки VPN")
        settings_title.add_css_class("title-2")
        settings_tab.append(settings_title)
        
        # Исключения сайтов
        exclusions_frame = Gtk.Frame()
        exclusions_frame.set_hexpand(True)
        settings_tab.append(exclusions_frame)
        
        exclusions_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        exclusions_box.set_margin_top(15)
        exclusions_box.set_margin_bottom(15)
        exclusions_box.set_margin_start(15)
        exclusions_box.set_margin_end(15)
        exclusions_frame.set_child(exclusions_box)
        
        exclusions_title = Gtk.Label(label="Исключения сайтов")
        exclusions_title.add_css_class("heading")
        exclusions_box.append(exclusions_title)
        
        exclusions_info = Gtk.Label(label="Управление сайтами, которые будут обходить VPN")
        exclusions_info.set_wrap(True)
        exclusions_box.append(exclusions_info)
        
        exclusions_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        exclusions_box.append(exclusions_buttons_box)
        
        self.exclusions_list_btn = Gtk.Button(label="Показать исключения")
        self.exclusions_list_btn.connect("clicked", self.on_exclusions_list_clicked)
        exclusions_buttons_box.append(self.exclusions_list_btn)
        
        self.exclusions_add_btn = Gtk.Button(label="Добавить исключение")
        self.exclusions_add_btn.connect("clicked", self.on_exclusions_add_clicked)
        exclusions_buttons_box.append(self.exclusions_add_btn)
        
        self.exclusions_remove_btn = Gtk.Button(label="Удалить исключение")
        self.exclusions_remove_btn.connect("clicked", self.on_exclusions_remove_clicked)
        exclusions_buttons_box.append(self.exclusions_remove_btn)
        
        # Поле для отображения исключений
        self.exclusions_text = Gtk.TextView()
        self.exclusions_text.set_editable(False)
        self.exclusions_text.set_monospace(True)
        self.exclusions_text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        
        exclusions_scrolled = Gtk.ScrolledWindow()
        exclusions_scrolled.set_child(self.exclusions_text)
        exclusions_scrolled.set_hexpand(True)
        exclusions_scrolled.set_vexpand(True)
        exclusions_scrolled.set_min_content_height(150)
        exclusions_box.append(exclusions_scrolled)
        
        # ===== ВКЛАДКА ДОПОЛНИТЕЛЬНО =====
        extra_title = Gtk.Label(label="Дополнительные функции")
        extra_title.add_css_class("title-2")
        extra_tab.append(extra_title)
        
        # Обновления
        update_frame = Gtk.Frame()
        update_frame.set_hexpand(True)
        extra_tab.append(update_frame)
        
        update_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        update_box.set_margin_top(15)
        update_box.set_margin_bottom(15)
        update_box.set_margin_start(15)
        update_box.set_margin_end(15)
        update_frame.set_child(update_box)
        
        update_title = Gtk.Label(label="Обновления")
        update_title.add_css_class("heading")
        update_box.append(update_title)
        
        update_buttons_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        update_box.append(update_buttons_box)
        
        self.check_update_btn = Gtk.Button(label="Проверить обновления")
        self.check_update_btn.connect("clicked", self.on_check_update_clicked)
        update_buttons_box.append(self.check_update_btn)
        
        self.update_btn = Gtk.Button(label="Установить обновления")
        self.update_btn.connect("clicked", self.on_update_clicked)
        update_buttons_box.append(self.update_btn)
        
        self.update_status_label = Gtk.Label(label="Статус обновлений: Не проверен")
        self.update_status_label.set_wrap(True)
        update_box.append(self.update_status_label)
        
        # Разделитель
        extra_tab.append(Gtk.Separator())
        
        # Логи
        logs_frame = Gtk.Frame()
        logs_frame.set_hexpand(True)
        extra_tab.append(logs_frame)
        
        logs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        logs_box.set_margin_top(15)
        logs_box.set_margin_bottom(15)
        logs_box.set_margin_start(15)
        logs_box.set_margin_end(15)
        logs_frame.set_child(logs_box)
        
        logs_title = Gtk.Label(label="Логи программы")
        logs_title.add_css_class("heading")
        logs_box.append(logs_title)
        
        self.export_logs_btn = Gtk.Button(label="Экспортировать логи")
        self.export_logs_btn.connect("clicked", self.on_export_logs_clicked)
        logs_box.append(self.export_logs_btn)
        
        logs_info = Gtk.Label(label="Экспортирует все логи программы в zip-архив")
        logs_info.set_wrap(True)
        logs_box.append(logs_info)
        
        # Разделитель
        extra_tab.append(Gtk.Separator())
        
        # Версия программы
        version_label = Gtk.Label(label=f"Версия программы: {VERSION}")
        version_label.add_css_class("dim-label")
        extra_tab.append(version_label)
# ==================== Конец НАСТРОЙКА ИНТЕРФЕЙСА ====================

# ==================== Начало ОБРАБОТЧИКИ СОБЫТИЙ ====================
    def on_check_auth_clicked(self, button):
        """Проверка статуса авторизации (ТОЛЬКО проверка, без загрузки локаций)"""
        self.append_auth_log("=== ПРОВЕРКА АВТОРИЗАЦИИ ===")
        self.check_auth_btn.set_sensitive(False)
        GLib.idle_add(self.account_info_label.set_text, "Проверка авторизации...")
        threading.Thread(target=self.check_auth_status_only, daemon=True).start()

    def on_login_clicked(self, button):
        """Обработчик кнопки входа"""
        self.append_auth_log("=== ЗАПУСК ПРОЦЕССА АВТОРИЗАЦИИ ===")
        self.login_btn.set_sensitive(False)
        threading.Thread(target=self.execute_login, daemon=True).start()

    def on_logout_clicked(self, button):
        """Обработчик кнопки выхода"""
        self.append_auth_log("=== ВЫХОД ИЗ АККАУНТА ===")
        self.logout_btn.set_sensitive(False)
        threading.Thread(target=self.execute_logout, daemon=True).start()

    def on_refresh_locations_clicked(self, button):
        """Обновление списка локаций (отдельный блок)"""
        self.append_auth_log("=== ОБНОВЛЕНИЕ СПИСКА ЛОКАЦИЙ ===")
        self.location_spinner.start()
        self.location_spinner.set_visible(True)
        self.refresh_locations_btn.set_sensitive(False)
        threading.Thread(target=self.load_locations, daemon=True).start()

    def on_vpn_action_clicked(self, button):
        """Обработчик объединенной кнопки подключения/отключения"""
        if self.vpn_status == "disconnected":
            if not self.current_location:
                self.show_error("Выберите локацию")
                return
            
            if self.sudo_password_remembered and self.sudo_password:
                self.append_auth_log("Используем сохраненный пароль для подключения")
                threading.Thread(target=self.execute_connect, daemon=True).start()
            else:
                self.connect_vpn()
        else:
            if self.sudo_password_remembered and self.sudo_password:
                self.append_auth_log("Используем сохраненный пароль для отключения")
                threading.Thread(target=self.execute_disconnect, daemon=True).start()
            else:
                self.disconnect_vpn()

    def on_status_clicked(self, button):
        """Обработчик кнопки проверки статуса"""
        threading.Thread(target=self.check_status, daemon=True).start()

    def on_location_changed(self, dropdown, param):
        """Обработчик изменения локации"""
        selected = dropdown.get_selected()
        if 0 <= selected < len(self.fast_locations):
            location = self.fast_locations[selected]
            self.current_location = location['code']
            self.location_label.set_text(f"Локация: {location['name']}")
            
            if self.vpn_status == "disconnected":
                self.vpn_action_btn.set_sensitive(True)

    def on_exclusions_list_clicked(self, button):
        """Показать список исключений"""
        self.append_auth_log("=== ПОЛУЧЕНИЕ СПИСКА ИСКЛЮЧЕНИЙ ===")
        threading.Thread(target=self.execute_exclusions_list, daemon=True).start()

    def on_exclusions_add_clicked(self, button):
        """Добавить исключение"""
        self.show_exclusions_dialog("add")

    def on_exclusions_remove_clicked(self, button):
        """Удалить исключение"""
        self.show_exclusions_dialog("remove")

    def on_check_update_clicked(self, button):
        """Проверить обновления"""
        self.append_auth_log("=== ПРОВЕРКА ОБНОВЛЕНИЙ ===")
        self.check_update_btn.set_sensitive(False)
        threading.Thread(target=self.execute_check_update, daemon=True).start()

    def on_update_clicked(self, button):
        """Установить обновления"""
        self.append_auth_log("=== УСТАНОВКА ОБНОВЛЕНИЙ ===")
        self.update_btn.set_sensitive(False)
        threading.Thread(target=self.execute_update, daemon=True).start()

    def on_export_logs_clicked(self, button):
        """Экспорт логов"""
        self.append_auth_log("=== ЭКСПОРТ ЛОГОВ ===")
        self.export_logs_btn.set_sensitive(False)
        threading.Thread(target=self.execute_export_logs, daemon=True).start()
# ==================== Конец ОБРАБОТЧИКИ СОБЫТИЙ ====================

# ==================== Начало ЛОГИРОВАНИЕ ====================
    def append_auth_log(self, text):
        """Логировать сообщения авторизации и обновлять интерфейс"""
        # Список разрешенных сообщений для отображения
        allowed_messages = [
            "Выход выполнен успешно!",
            "Требуется авторизация", 
            "Ожидаем ссылку для авторизации в браузере...",
            "Отправлен ввод: b",
            "Аккаунт:",
            "Тариф:",
            "Устройств:",
            "Обновление:",
            "Авторизация успешно завершена!",
            "Авторизация AdGuard подтверждена",
            "=== ПРОВЕРКА АВТОРИЗАЦИИ ==="
        ]
        
        # Проверяем, содержит ли текст любое из разрешенных сообщений
        show_message = any(allowed_msg in text for allowed_msg in allowed_messages)
        
        if show_message:
            def update_display():
                current_text = self.account_info_label.get_text()
                if "Нажмите" in current_text or "Ошибка" in current_text or "Проверка" in current_text:
                    new_text = text
                else:
                    new_text = current_text + "\n" + text
                self.account_info_label.set_text(new_text)
            
            GLib.idle_add(update_display)
        
        # Всегда логируем в консоль для отладки
        print(f"AUTH: {text}")
# ==================== Конец ЛОГИРОВАНИЕ ====================

# ==================== Начало ВЫПОЛНЕНИЕ КОМАНД ====================
    def run_command_simple(self, command):
        """Простое выполнение команды без sudo (для диагностики)"""
        try:
            self.append_auth_log(f"Выполнение команды: {ADGUARD_PATH} {command}")
            
            result = subprocess.run(
                [ADGUARD_PATH] + command.split(),
                capture_output=True, text=True, timeout=30,
                cwd=os.path.expanduser("~")
            )
            
            self.append_auth_log(f"Код возврата: {result.returncode}")
            if result.stdout:
                self.append_auth_log(f"STDOUT: {result.stdout[:500]}...")
            if result.stderr:
                self.append_auth_log(f"STDERR: {result.stderr[:500]}...")
            
            return result
            
        except Exception as e:
            self.append_auth_log(f"ОШИБКА: {str(e)}")
            return None
# ==================== Конец ВЫПОЛНЕНИЕ КОМАНД ====================

# ==================== Начало АВТОРИЗАЦИЯ ====================
    def check_auth_status_only(self):
        """Проверка статуса авторизации (ТОЛЬКО проверка, без загрузки локаций)"""
        try:
            self.append_auth_log("=== ПРОВЕРКА АВТОРИЗАЦИИ ===")
            
            result = self.run_command_simple("license")
            
            if result and result.returncode == 0:
                self.is_authenticated = True
                self.account_info = self.parse_account_info(result.stdout)
                account_text = self.format_account_info(self.account_info)
                
                # Обновляем статус в главной вкладке
                GLib.idle_add(self.auth_status_label.set_text, "Статус авторизации: Авторизован")
                GLib.idle_add(self.stats_label.set_text, "Авторизация успешна!")
                GLib.idle_add(self.refresh_locations_btn.set_sensitive, True)
                GLib.idle_add(self.login_btn.set_sensitive, False)
                GLib.idle_add(self.logout_btn.set_sensitive, True)
                
                # Показываем информацию об аккаунте на вкладке авторизации
                GLib.idle_add(self.account_info_label.set_text, account_text)
                
                self.append_auth_log("Авторизация AdGuard подтверждена")
                
            else:
                self.is_authenticated = False
                self.account_info = {}
                
                GLib.idle_add(self.auth_status_label.set_text, "Статус авторизации: Не авторизован")
                GLib.idle_add(self.stats_label.set_text, "Требуется авторизация")
                GLib.idle_add(self.login_btn.set_sensitive, True)
                GLib.idle_add(self.logout_btn.set_sensitive, False)
                GLib.idle_add(self.account_info_label.set_text, "Требуется авторизация")
                
        except Exception as e:
            error_msg = f"Ошибка проверки авторизации: {str(e)}"
            GLib.idle_add(self.account_info_label.set_text, error_msg)
        
        # ВСЕГДА восстанавливаем кнопку после проверки
        GLib.idle_add(self.check_auth_btn.set_sensitive, True)

    def auto_load_locations_if_authenticated(self):
        """Автоматическая загрузка локаций при запуске, если пользователь авторизован"""
        if self.is_authenticated:
            self.append_auth_log("=== АВТОМАТИЧЕСКАЯ ЗАГРУЗКА ЛОКАЦИЙ ПРИ ЗАПУСКЕ ===")
            self.location_spinner.start()
            self.location_spinner.set_visible(True)
            threading.Thread(target=self.load_locations, daemon=True).start()
        else:
            self.append_auth_log("Пользователь не авторизован, автоматическая загрузка локаций пропущена")
        return False  # Останавливаем таймер

    def parse_account_info(self, output):
        """Парсим информацию об аккаунте из вывода команды license"""
        account_info = {}
        clean_output = self.clean_ansi_codes(output)
        
        # Парсим email
        email_match = re.search(r'Logged in as (.+)', clean_output)
        if email_match:
            account_info['email'] = email_match.group(1).strip()
        
        # Парсим тип подписки
        premium_match = re.search(r'You are using the (.+) version', clean_output)
        if premium_match:
            account_info['subscription'] = premium_match.group(1).strip()
        
        # Парсим количество устройств
        devices_match = re.search(r'Up to (\d+) devices simultaneously', clean_output)
        if devices_match:
            account_info['devices'] = devices_match.group(1).strip()
        
        # Парсим дату обновления
        renewal_match = re.search(r'Your subscription will be renewed on (.+)', clean_output)
        if renewal_match:
            account_info['renewal'] = renewal_match.group(1).strip()
        
        return account_info

    def format_account_info(self, account_info):
        """Форматируем информацию об аккаунте для простого отображения"""
        if not account_info:
            return "Информация об аккаунте не доступна"
        
        lines = []
        
        if 'email' in account_info:
            lines.append(f"Аккаунт: {account_info['email']}")
        
        if 'subscription' in account_info:
            sub_type = "PREMIUM" if account_info['subscription'].upper() == "PREMIUM" else account_info['subscription']
            lines.append(f"Тариф: {sub_type}")
        
        if 'devices' in account_info:
            lines.append(f"Устройств: {account_info['devices']} одновременно")
        
        if 'renewal' in account_info:
            lines.append(f"Обновление: {account_info['renewal']}")
        
        return "\n".join(lines)

    def execute_login(self):
        """Выполнение команды login с интерактивным вводом"""
        try:
            self.append_auth_log("Ожидаем ссылку для авторизации в браузере...")
            
            # Запускаем команду login в отдельном потоке
            return_code, output = self.run_command_interactive("login", "b")
            
            if return_code == 0:
                self.is_authenticated = True
                GLib.idle_add(self.login_btn.set_sensitive, False)
                GLib.idle_add(self.logout_btn.set_sensitive, True)
                self.append_auth_log("Авторизация успешно завершена!")
                
                # После успешного логина проверяем статус
                threading.Thread(target=self.check_auth_status_only, daemon=True).start()
            else:
                self.append_auth_log(f"Ошибка авторизации. Код возврата: {return_code}")
                
        except Exception as e:
            self.append_auth_log(f"Критическая ошибка при авторизации: {str(e)}")
        
        GLib.idle_add(self.login_btn.set_sensitive, True)

    def execute_logout(self):
        """Выполнение команды logout"""
        try:
            result = self.run_command_simple("logout")
            
            if result and result.returncode == 0:
                self.is_authenticated = False
                GLib.idle_add(self.login_btn.set_sensitive, True)
                GLib.idle_add(self.logout_btn.set_sensitive, False)
                self.append_auth_log("Выход выполнен успешно!")
                
                # После выхода проверяем статус
                threading.Thread(target=self.check_auth_status_only, daemon=True).start()
            else:
                self.append_auth_log("Ошибка выхода из аккаунта")
                
        except Exception as e:
            self.append_auth_log(f"Ошибка при выходе: {str(e)}")
        
        GLib.idle_add(self.logout_btn.set_sensitive, True)

    def run_command_interactive(self, command, input_text=None):
        """Выполнение команды с интерактивным вводом"""
        try:
            process = subprocess.Popen(
                [ADGUARD_PATH] + command.split(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            output = ""
            if input_text:
                process.stdin.write(input_text + "\n")
                process.stdin.flush()
                self.append_auth_log("Отправлен ввод: b")
            
            # Читаем вывод в реальном времени
            while True:
                if process.poll() is not None:
                    break
                time.sleep(0.1)
            
            # Читаем оставшийся вывод
            remaining_stdout, remaining_stderr = process.communicate()
            if remaining_stdout:
                output += remaining_stdout
            if remaining_stderr:
                output += remaining_stderr
            
            return_code = process.returncode
            return return_code, output
            
        except Exception as e:
            self.append_auth_log(f"ОШИБКА выполнения команды: {str(e)}")
            return -1, str(e)

    def clean_ansi_codes(self, text):
        """Очищает ANSI escape codes из текста"""
        return re.sub(r'\x1b\[[0-9;]*m', '', text)
# ==================== Конец АВТОРИЗАЦИЯ ====================


# ==================== Начало ЗАГРУЗКА ЛОКАЦИЙ ====================
    def load_locations(self):
        """Загрузка списка локаций (отдельный блок)"""
        try:
            self.append_auth_log("Загрузка списка локаций...")
            
            result = self.run_command_simple("list-locations")
            
            if result and result.returncode == 0:
                locations = self.parse_locations(result.stdout)
                if locations:
                    fast_locations = sorted(locations, key=lambda x: x.get('ping', 999))[:15]
                    GLib.idle_add(self.update_locations_ui, locations, fast_locations)
                    self.append_auth_log("Список локаций загружен")
                else:
                    GLib.idle_add(self.show_error, "Не удалось распарсить список локаций")
            else:
                error_msg = result.stderr if result and result.stderr else result.stdout
                GLib.idle_add(self.show_error, f"Ошибка загрузки локаций: {error_msg}")
                self.append_auth_log(f"Ошибка загрузки локаций: {error_msg}")
                
        except Exception as e:
            GLib.idle_add(self.show_error, f"Ошибка: {str(e)}")
            self.append_auth_log(f"Ошибка загрузки локаций: {str(e)}")
        
        GLib.idle_add(self.finish_loading)

    def finish_loading(self):
        """Завершение процесса загрузки"""
        self.location_spinner.stop()
        self.location_spinner.set_visible(False)
        self.refresh_locations_btn.set_sensitive(True)

    def parse_locations(self, output):
        """Парсим вывод команды list-locations"""
        locations = []
        clean_output = self.clean_ansi_codes(output)
        lines = clean_output.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line or 'ISO' in line or 'COUNTRY' in line or 'PING' in line or 'adguardvpn-cli' in line:
                continue
                
            parts = line.split()
            if len(parts) >= 4:
                try:
                    country_code = parts[0]
                    ping_index = -1
                    for i in range(len(parts)):
                        if parts[i].isdigit():
                            ping_index = i
                            break
                    
                    if ping_index != -1:
                        country_name = ' '.join(parts[1:ping_index])
                        ping = int(parts[ping_index])
                        
                        locations.append({
                            'code': country_code,
                            'name': country_name,
                            'ping': ping,
                            'display': f"{country_code} - {country_name} ({ping}ms)"
                        })
                except (ValueError, IndexError):
                    continue
        
        return locations

    def update_locations_ui(self, all_locations, fast_locations):
        """Обновляем UI с полученными локациями"""
        self.locations = all_locations
        self.fast_locations = fast_locations
        
        if fast_locations:
            locations_list = [loc['display'] for loc in fast_locations]
            string_list = Gtk.StringList.new(locations_list)
            self.location_dropdown.set_model(string_list)
            
            self.current_location = fast_locations[0]['code']
            self.location_label.set_text(f"Локация: {fast_locations[0]['name']}")
            self.location_dropdown.set_selected(0)
            self.location_dropdown.set_sensitive(True)
            
            self.vpn_action_btn.set_sensitive(True)
        
        self.stats_label.set_text("Выберите локацию и нажмите 'Подключить'")
# ==================== Конец ЗАГРУЗКА ЛОКАЦИЙ ====================

# ==================== Начало УПРАВЛЕНИЕ VPN ====================
    def connect_vpn(self):
        """Подключение к VPN"""
        try:
            self.vpn_status = "connecting"
            self.update_ui()
            self.show_sudo_dialog()
        except Exception as e:
            self.show_error(f"Ошибка подключения: {e}")

    def show_sudo_dialog(self):
        """Диалог для ввода пароля sudo"""
        dialog = Gtk.Window(transient_for=self, modal=True, title="Требуется пароль sudo")
        dialog.set_default_size(350, 250)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        dialog.set_child(main_box)
        
        action_text = "подключения" if self.vpn_status == "connecting" else "отключения"
        label = Gtk.Label(label=f"Введите пароль sudo для {action_text} VPN:")
        label.set_wrap(True)
        main_box.append(label)
        
        remember_checkbox = Gtk.CheckButton(label="Запомнить пароль для этой сессии")
        remember_checkbox.set_active(True)
        main_box.append(remember_checkbox)
        
        password_entry = Gtk.Entry()
        password_entry.set_visibility(False)
        password_entry.set_placeholder_text("Пароль sudo")
        main_box.append(password_entry)
        
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_box.append(button_box)
        
        cancel_btn = Gtk.Button(label="Отмена")
        cancel_btn.connect("clicked", lambda b: dialog.destroy())
        button_box.append(cancel_btn)
        
        action_btn = Gtk.Button(label="Подключить" if self.vpn_status == "connecting" else "Отключить")
        action_btn.add_css_class("suggested-action" if self.vpn_status == "connecting" else "destructive-action")
        action_btn.connect("clicked", lambda b: self.on_sudo_password_entered(
            dialog, password_entry.get_text(), remember_checkbox.get_active()))
        button_box.append(action_btn)
        
        password_entry.grab_focus()
        password_entry.connect("activate", lambda e: self.on_sudo_password_entered(
            dialog, password_entry.get_text(), remember_checkbox.get_active()))
        
        dialog.present()

    def on_sudo_password_entered(self, dialog, password, remember_password):
        """Обработчик ввода пароля sudo"""
        if not password:
            self.show_error("Пароль не введен")
            return
        
        self.append_auth_log("Получен пароль sudo")
        dialog.destroy()
        self.sudo_password = password
        self.sudo_password_remembered = remember_password
        
        if self.vpn_status == "connecting":
            threading.Thread(target=self.execute_connect, daemon=True).start()
        else:
            threading.Thread(target=self.execute_disconnect, daemon=True).start()

    def execute_connect(self):
        """Выполнение команды подключения"""
        try:
            self.append_auth_log("Выполнение подключения к VPN...")
            # Выполняем сам adguardvpn-cli под sudo и передаём пароль через stdin (-S)
            cmd = [
                "sudo", "-S",
                ADGUARD_PATH, "connect", "-l", str(self.current_location)
            ]
            result = subprocess.run(
                cmd,
                input=f"{self.sudo_password}\n",
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if not self.sudo_password_remembered:
                self.sudo_password = None
                self.sudo_password_remembered = False
            
            if result.returncode == 0:
                GLib.idle_add(self.set_vpn_status, "connected")
                GLib.idle_add(lambda: self.stats_label.set_text("Подключение установлено"))
                self.append_auth_log("Подключение успешно установлено")
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                GLib.idle_add(self.show_error, f"Ошибка подключения: {error_msg}")
                GLib.idle_add(self.set_vpn_status, "disconnected")
                
        except subprocess.TimeoutExpired:
            if not self.sudo_password_remembered:
                self.sudo_password = None
                self.sudo_password_remembered = False
            GLib.idle_add(self.show_error, "Таймаут подключения")
            GLib.idle_add(self.set_vpn_status, "disconnected")
        except Exception as e:
            if not self.sudo_password_remembered:
                self.sudo_password = None
                self.sudo_password_remembered = False
            GLib.idle_add(self.show_error, f"Ошибка: {str(e)}")
            GLib.idle_add(self.set_vpn_status, "disconnected")

    def disconnect_vpn(self):
        """Отключение VPN"""
        try:
            self.vpn_status = "disconnecting"
            self.update_ui()
            threading.Thread(target=self.execute_disconnect, daemon=True).start()
        except Exception as e:
            self.show_error(f"Ошибка отключения: {e}")

    def execute_disconnect(self):
        """Выполнение команды отключения"""
        try:
            self.append_auth_log("=== ОТКЛЮЧЕНИЕ VPN ===")
            # Выполняем команду отключения под sudo, пароль передаём через stdin
            cmd = [
                "sudo", "-S",
                ADGUARD_PATH, "disconnect"
            ]
            result = subprocess.run(
                cmd,
                input=f"{self.sudo_password}\n",
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if not self.sudo_password_remembered:
                self.sudo_password = None
                self.sudo_password_remembered = False
            
            if result.returncode == 0:
                GLib.idle_add(self.set_vpn_status, "disconnected")
                GLib.idle_add(lambda: self.stats_label.set_text("Отключено"))
                self.append_auth_log("VPN отключен")
            else:
                error_msg = result.stderr if result.stderr else result.stdout
                GLib.idle_add(self.show_error, f"Ошибка отключения: {error_msg}")
                
        except Exception as e:
            if not self.sudo_password_remembered:
                self.sudo_password = None
                self.sudo_password_remembered = False
            GLib.idle_add(self.show_error, f"Ошибка отключения: {str(e)}")
            GLib.idle_add(self.set_vpn_status, "disconnected")

    def check_status(self):
        """Проверка статуса VPN"""
        try:
            self.append_auth_log("=== ПРОВЕРКА СТАТУСА VPN ===")
            result = self.run_command_simple("status")
            
            if result and result.returncode == 0:
                if "Connected" in result.stdout:
                    GLib.idle_add(lambda: self.stats_label.set_text("Статус: Подключено"))
                    GLib.idle_add(self.set_vpn_status, "connected")
                else:
                    GLib.idle_add(lambda: self.stats_label.set_text("Статус: Отключено"))
                    GLib.idle_add(self.set_vpn_status, "disconnected")
            else:
                GLib.idle_add(lambda: self.stats_label.set_text("Ошибка проверки статуса"))
                
        except Exception as e:
            GLib.idle_add(lambda: self.stats_label.set_text(f"Ошибка: {str(e)}"))
# ==================== Конец УПРАВЛЕНИЕ VPN ====================


# ==================== Начало НОВЫЕ ФУНКЦИИ ====================
    def execute_exclusions_list(self):
        """Получение списка исключений"""
        try:
            self.append_auth_log("Запуск команды site-exclusions list...")
            result = self.run_command_simple("site-exclusions list")
            
            if result and result.returncode == 0:
                GLib.idle_add(self.update_exclusions_display, result.stdout)
            else:
                error_msg = result.stderr if result and result.stderr else "Ошибка получения списка исключений"
                GLib.idle_add(self.update_exclusions_display, f"Ошибка: {error_msg}")
                
        except Exception as e:
            GLib.idle_add(self.update_exclusions_display, f"Ошибка: {str(e)}")

    def update_exclusions_display(self, text):
        """Обновление отображения исключений"""
        buffer = self.exclusions_text.get_buffer()
        buffer.set_text(text)

    def show_exclusions_dialog(self, action_type):
        """Диалог для добавления/удаления исключений"""
        dialog = Gtk.Window(transient_for=self, modal=True, 
                           title="Добавить исключение" if action_type == "add" else "Удалить исключение")
        dialog.set_default_size(400, 200)
        
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(20)
        main_box.set_margin_bottom(20)
        main_box.set_margin_start(20)
        main_box.set_margin_end(20)
        dialog.set_child(main_box)
        
        label = Gtk.Label(label="Введите домен или сайт:" if action_type == "add" else "Введите домен для удаления:")
        label.set_wrap(True)
        main_box.append(label)
        
        entry = Gtk.Entry()
        entry.set_placeholder_text("example.com")
        main_box.append(entry)
        
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        main_box.append(button_box)
        
        cancel_btn = Gtk.Button(label="Отмена")
        cancel_btn.connect("clicked", lambda b: dialog.destroy())
        button_box.append(cancel_btn)
        
        action_btn = Gtk.Button(label="Добавить" if action_type == "add" else "Удалить")
        action_btn.add_css_class("suggested-action")
        action_btn.connect("clicked", lambda b: self.on_exclusions_action_confirm(
            dialog, entry.get_text(), action_type))
        button_box.append(action_btn)
        
        entry.grab_focus()
        entry.connect("activate", lambda e: self.on_exclusions_action_confirm(
            dialog, entry.get_text(), action_type))
        
        dialog.present()

    def on_exclusions_action_confirm(self, dialog, site, action_type):
        """Подтверждение действия с исключением"""
        if not site:
            self.show_error("Введите домен или сайт")
            return
        
        dialog.destroy()
        
        if action_type == "add":
            threading.Thread(target=self.execute_exclusions_add, args=(site,), daemon=True).start()
        else:
            threading.Thread(target=self.execute_exclusions_remove, args=(site,), daemon=True).start()

    def execute_exclusions_add(self, site):
        """Добавление исключения"""
        try:
            self.append_auth_log(f"Добавление исключения: {site}")
            result = self.run_command_simple(f"site-exclusions add {site}")
            
            if result and result.returncode == 0:
                self.append_auth_log(f"Исключение {site} добавлено")
                # Обновляем список исключений
                threading.Thread(target=self.execute_exclusions_list, daemon=True).start()
            else:
                error_msg = result.stderr if result and result.stderr else "Ошибка добавления исключения"
                self.show_error(f"Ошибка добавления: {error_msg}")
                
        except Exception as e:
            self.show_error(f"Ошибка добавления исключения: {str(e)}")

    def execute_exclusions_remove(self, site):
        """Удаление исключения"""
        try:
            self.append_auth_log(f"Удаление исключения: {site}")
            result = self.run_command_simple(f"site-exclusions remove {site}")
            
            if result and result.returncode == 0:
                self.append_auth_log(f"Исключение {site} удалено")
                # Обновляем список исключений
                threading.Thread(target=self.execute_exclusions_list, daemon=True).start()
            else:
                error_msg = result.stderr if result and result.stderr else "Ошибка удаления исключения"
                self.show_error(f"Ошибка удаления: {error_msg}")
                
        except Exception as e:
            self.show_error(f"Ошибка удаления исключения: {str(e)}")

    def execute_check_update(self):
        """Проверка обновлений"""
        try:
            self.append_auth_log("Проверка обновлений...")
            result = self.run_command_simple("check-update")
            
            if result:
                # Анализируем STDOUT, а не код возврата
                stdout_text = result.stdout.strip()
                
                if "You are using the latest version" in stdout_text:
                    status_text = "У вас новейшая версия"
                    self.append_auth_log("Обновлений не найдено - используется последняя версия")
                elif "new version" in stdout_text.lower() or "update" in stdout_text.lower():
                    status_text = f"Доступно обновление: {stdout_text}"
                    self.append_auth_log(f"Найдено обновление: {stdout_text}")
                else:
                    status_text = stdout_text if stdout_text else "Неизвестный статус"
                    self.append_auth_log(f"Результат проверки: {stdout_text}")
                
                GLib.idle_add(self.update_status_label.set_text, f"Статус обновлений: {status_text}")
            else:
                error_msg = "Ошибка выполнения команды check-update"
                GLib.idle_add(self.update_status_label.set_text, f"Ошибка: {error_msg}")
                self.append_auth_log(f"Ошибка проверки обновлений: {error_msg}")
                
        except Exception as e:
            error_text = f"Ошибка: {str(e)}"
            GLib.idle_add(self.update_status_label.set_text, error_text)
            self.append_auth_log(f"Ошибка проверки обновлений: {str(e)}")
        
        GLib.idle_add(self.check_update_btn.set_sensitive, True)

    def execute_update(self):
        """Установка обновлений"""
        try:
            self.append_auth_log("Установка обновлений...")
            result = self.run_command_simple("update")
            
            if result:
                stdout_text = result.stdout.strip()
                
                if "You are using the latest version" in stdout_text:
                    GLib.idle_add(self.update_status_label.set_text, "У вас новейшая версия, обновление не требуется")
                    self.append_auth_log("Обновление не требуется - используется последняя версия")
                elif "success" in stdout_text.lower() or "updated" in stdout_text.lower():
                    GLib.idle_add(self.update_status_label.set_text, "Обновление установлено успешно!")
                    self.append_auth_log("Обновление установлено")
                else:
                    # Показываем любой другой вывод
                    display_text = stdout_text if stdout_text else "Обновление завершено"
                    GLib.idle_add(self.update_status_label.set_text, display_text)
                    self.append_auth_log(f"Результат обновления: {stdout_text}")
            else:
                error_msg = "Ошибка выполнения команды update"
                GLib.idle_add(self.update_status_label.set_text, f"Ошибка: {error_msg}")
                self.append_auth_log(f"Ошибка установки обновлений: {error_msg}")
                
        except Exception as e:
            GLib.idle_add(self.update_status_label.set_text, f"Ошибка: {str(e)}")
            self.append_auth_log(f"Ошибка установки обновлений: {str(e)}")
        
        GLib.idle_add(self.update_btn.set_sensitive, True)

    def execute_export_logs(self):
        """Экспорт логов"""
        try:
            self.append_auth_log("Экспорт логов...")
            result = self.run_command_simple("export-logs")
            
            if result and result.returncode == 0:
                self.show_info("Экспорт логов", "Логи успешно экспортированы в zip-архив")
                self.append_auth_log("Логи экспортированы")
            else:
                error_msg = result.stderr if result and result.stderr else "Ошибка экспорта логов"
                self.show_error(f"Ошибка экспорта: {error_msg}")
                
        except Exception as e:
            self.show_error(f"Ошибка экспорта логов: {str(e)}")
        
        GLib.idle_add(self.export_logs_btn.set_sensitive, True)
# ==================== Конец НОВЫЕ ФУНКЦИИ ====================



# ==================== Начало УПРАВЛЕНИЕ СТАТУСОМ ====================
    def set_vpn_status(self, status):
        """Установка статуса VPN"""
        self.vpn_status = status
        self.update_ui()

    def update_ui(self):
        """Обновление интерфейса"""
        if self.vpn_status == "connected":
            self.status_icon.set_from_icon_name("network-vpn-symbolic")
            self.status_label.set_text("VPN подключен")
            self.vpn_action_btn.set_label("Отключить")
            self.vpn_action_btn.remove_css_class("suggested-action")
            self.vpn_action_btn.add_css_class("destructive-action")
            self.vpn_action_btn.set_sensitive(True)
            self.location_dropdown.set_sensitive(False)
            self.refresh_locations_btn.set_sensitive(False)
            
        elif self.vpn_status == "connecting":
            self.status_icon.set_from_icon_name("network-wireless-acquiring-symbolic")
            self.status_label.set_text("Подключение...")
            self.vpn_action_btn.set_sensitive(False)
            self.stats_label.set_text("Устанавливаем соединение...")
            
        elif self.vpn_status == "disconnecting":
            self.status_icon.set_from_icon_name("network-wireless-disconnecting-symbolic")
            self.status_label.set_text("Отключение...")
            self.vpn_action_btn.set_sensitive(False)
            self.stats_label.set_text("Разрываем соединение...")
            
        else:  # disconnected
            self.status_icon.set_from_icon_name("network-vpn-disabled-symbolic")
            self.status_label.set_text("VPN отключен")
            self.vpn_action_btn.set_label("Подключить")
            self.vpn_action_btn.remove_css_class("destructive-action")
            self.vpn_action_btn.add_css_class("suggested-action")
            self.vpn_action_btn.set_sensitive(bool(self.current_location and self.is_authenticated))
            self.location_dropdown.set_sensitive(True)
            self.refresh_locations_btn.set_sensitive(True)
# ==================== Конец УПРАВЛЕНИЕ СТАТУСОМ ====================

# ==================== Начало ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
    def check_adguard_installed(self):
        """Проверка установки AdGuard VPN"""
        if not os.path.exists(ADGUARD_PATH):
            self.show_error(f"AdGuard VPN не найден по пути: {ADGUARD_PATH}")
        else:
            print(f"AdGuard VPN найден: {ADGUARD_PATH}")

    def show_error(self, message):
        """Показать ошибку"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Ошибка"
        )
        dialog.set_property("secondary-text", message)
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()

    def show_info(self, title, message):
        """Показать информационное сообщение"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.set_property("secondary-text", message)
        dialog.connect("response", lambda d, r: d.destroy())
        dialog.present()
# ==================== Конец ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

# ==================== Начало ПРИЛОЖЕНИЕ ====================
class AdGuardVPNApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=0)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = AdGuardVPNWindow(application=self)
        win.present()
# ==================== Конец ПРИЛОЖЕНИЕ ====================

# ==================== Начало ЗАПУСК ====================
def main():
    app = AdGuardVPNApp()
    return app.run(sys.argv)

if __name__ == "__main__":
    sys.exit(main())
# ==================== Конец ЗАПУСК ====================
