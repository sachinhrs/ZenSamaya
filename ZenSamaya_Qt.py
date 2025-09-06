# ZenSamaya_qt.py
import sys, os, json, time, random, threading, subprocess
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSpinBox,
    QGridLayout, QVBoxLayout, QHBoxLayout, QFileDialog, QInputDialog,
    QMessageBox, QCheckBox, QScrollArea, QSizePolicy
)
from PySide6.QtGui import QIcon

import pygame

script_dir = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(script_dir, ".srvn_apps", "settings.json")

pygame_lock = threading.Lock()
global_start_time = 0.0

class AlarmWorker(QObject):
    tick = Signal(int)            # remaining seconds
    finished = Signal()
    started = Signal()
    error = Signal(str)

    def __init__(self, file_path: str, duration_s: int, mute_state: dict):
        super().__init__()
        self.file_path = file_path
        self.duration_s = duration_s
        self.mute_state = mute_state
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def run(self):
        global global_start_time
        with pygame_lock:
            try:
                pygame.mixer.music.load(self.file_path)
                pygame.mixer.music.play(loops=-1)
                pygame.mixer.music.set_volume(0.0 if self.mute_state.get("muted") else 1.0)
            except Exception as e:
                self.error.emit(f"Error playing {self.file_path}: {e}")
                return
        self.started.emit()

        global_start_time = time.time()
        end_time = global_start_time + self.duration_s
        try:
            while not self._stop.is_set():
                now = time.time()
                remaining = max(0, int(end_time - now))
                self.tick.emit(remaining)
                if remaining <= 0:
                    break
                # refresh volume according to mute state
                with pygame_lock:
                    try:
                        vol = 0.0 if self.mute_state.get("muted") else 1.0
                        pygame.mixer.music.set_volume(vol)
                    except Exception:
                        pass
                time.sleep(0.1)
            with pygame_lock:
                try:
                    pygame.mixer.music.fadeout(2000)
                except Exception:
                    pass
            time.sleep(2)
            with pygame_lock:
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass
        finally:
            self.tick.emit(0)
            self.finished.emit()


class ScrollingLabel(QLabel):
    def __init__(self, text="", width_chars=30, delay_ms=250, parent=None):
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.full_text = text
        self.display_width = width_chars
        self.pos = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._scroll)
        self.timer.start(delay_ms)

    def set_text(self, t: str):
        self.full_text = t or ""
        self.pos = 0

    def _scroll(self):
        full = self.full_text + " "
        if not full:
            self.setText("")
            return
        doubled = full + full
        visible = doubled[self.pos:self.pos+self.display_width]
        self.setText(visible)
        self.pos = (self.pos + 1) % len(full)


class IntervalAlarmApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Meditation Sessions 🧘")
        # pygame init
        try:
            pygame.mixer.init()
        except Exception as e:
            QMessageBox.critical(self, "Audio Error", f"Pygame mixer initialization failed:\n{e}")
            sys.exit(1)

        # state
        self.frame_id = "load"
        self.alarm_duration_seconds = 0
        self.alarm_times = []
        self.is_running = False
        self.current_worker = None
        self.current_thread = None
        self.caffeinate_process = None
        self.sound_files = []
        self.next_sound_file = None
        self.mute_state = {"muted": False}
        self.last_set_time = None
        self.alarm_check_vars = []
        self.saved_alarm_check_statuses = []
        self.alarms_frame_visible = False

        # defaults + settings
        self._defaults()
        self._load_settings_min()

        # UI
        self._build_ui()
        if self.frame_id == "running":
            QTimer.singleShot(100, self.set_alarms)

        # next alarm countdown timer
        self.next_timer = QTimer(self)
        self.next_timer.timeout.connect(self._update_next_countdown)
        self.next_timer.start(1000)

    def _defaults(self):
        self.start_hour, self.start_minute, self.start_second, self.start_ampm = 6, 0, 0, "AM"
        self.end_hour, self.end_minute, self.end_second, self.end_ampm = 7, 0, 0, "AM"
        self.num_alarms = 5
        self.sound_folder = ""
        self.alarm_length_minutes = 0
        self.alarm_length_seconds = 10
        self.arbitrary_integer = 0

    def _load_settings_min(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, "r") as f:
                    s = json.load(f)
                self.start_hour = int(s.get("start_hour", self.start_hour))
                self.start_minute = int(s.get("start_minute", self.start_minute))
                self.start_second = int(s.get("start_second", self.start_second))
                self.start_ampm = s.get("start_ampm", self.start_ampm)
                self.end_hour = int(s.get("end_hour", self.end_hour))
                self.end_minute = int(s.get("end_minute", self.end_minute))
                self.end_second = int(s.get("end_second", self.end_second))
                self.end_ampm = s.get("end_ampm", self.end_ampm)
                self.num_alarms = int(s.get("num_alarms", self.num_alarms))
                self.sound_folder = s.get("sound_folder", self.sound_folder)
                self.alarm_length_minutes = int(s.get("alarm_length_minutes", self.alarm_length_minutes))
                self.alarm_length_seconds = int(s.get("alarm_length_seconds", self.alarm_length_seconds))
                self.saved_alarm_check_statuses = s.get("alarm_check_statuses", [])
                self.arbitrary_integer = int(s.get("arbitrary_integer", 0))
                self.frame_id = s.get("frame_id", "load")
        except Exception:
            pass

    def _save_settings(self):
        s = {
            "start_hour": self.start_hour,
            "start_minute": self.start_minute,
            "start_second": self.start_second,
            "start_ampm": self.start_ampm,
            "end_hour": self.end_hour,
            "end_minute": self.end_minute,
            "end_second": self.end_second,
            "end_ampm": self.end_ampm,
            "num_alarms": self.num_alarms,
            "sound_folder": self.sound_folder,
            "alarm_length_minutes": self.alarm_length_minutes,
            "alarm_length_seconds": self.alarm_length_seconds,
            "alarm_check_statuses": [cb.isChecked() for cb in self.alarm_check_vars],
            "arbitrary_integer": self.arbitrary_spin.value(),
            "frame_id": self.frame_id,
        }
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(s, f)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def _format_time(self, h, m, s, ap):
        return f"{h:02}:{m:02}:{s:02} {ap}"

    def _format_len(self, m, s):
        return f"{m}m {s}s"

    def _hms_ampm_to_24(self, h, m, s, ap):
        if ap == "PM" and h != 12:
            h += 12
        elif ap == "AM" and h == 12:
            h = 0
        return h, m, s

    def _build_ui(self):
        central = QWidget(self)
        outer = QVBoxLayout(central)
        self.setCentralWidget(central)

        # Setup frame
        self.setup_panel = QWidget()
        grid = QGridLayout(self.setup_panel)

        r = 0
        # Start time line
        grid.addWidget(QLabel("🕒"), r, 0)
        self.start_lbl = QLabel(self._format_time(self.start_hour, self.start_minute, self.start_second, self.start_ampm))
        grid.addWidget(self.start_lbl, r, 1)
        btn = QPushButton("🖊️")
        btn.clicked.connect(self.edit_start_time)
        grid.addWidget(btn, r, 2)
        r += 1

        grid.addWidget(QLabel("🕒"), r, 0)
        self.end_lbl = QLabel(self._format_time(self.end_hour, self.end_minute, self.end_second, self.end_ampm))
        grid.addWidget(self.end_lbl, r, 1)
        btn2 = QPushButton("🖊️")
        btn2.clicked.connect(self.edit_end_time)
        grid.addWidget(btn2, r, 2)
        r += 1

        grid.addWidget(QLabel("🔔"), r, 0)
        self.count_lbl = QLabel(str(self.num_alarms))
        grid.addWidget(self.count_lbl, r, 1)
        btn3 = QPushButton("🖊️")
        btn3.clicked.connect(self.edit_count)
        grid.addWidget(btn3, r, 2)
        r += 1

        grid.addWidget(QLabel("🎵"), r, 0)
        self.folder_lbl = ScrollingLabel(self.sound_folder or "-", width_chars=30)
        grid.addWidget(self.folder_lbl, r, 1)
        btn4 = QPushButton("📁")
        btn4.clicked.connect(self.edit_folder)
        grid.addWidget(btn4, r, 2)
        r += 1

        grid.addWidget(QLabel("⏳"), r, 0)
        self.length_lbl = QLabel(self._format_len(self.alarm_length_minutes, self.alarm_length_seconds))
        grid.addWidget(self.length_lbl, r, 1)
        btn5 = QPushButton("🖊️")
        btn5.clicked.connect(self.edit_length)
        grid.addWidget(btn5, r, 2)
        r += 1

        self.set_btn = QPushButton("⏰ Set")
        self.set_btn.clicked.connect(self.set_alarms)
        grid.addWidget(self.set_btn, r, 0, 1, 3)

        outer.addWidget(self.setup_panel)

        # Running frame
        self.running_panel = QWidget()
        self.running_panel.hide()
        rg = QGridLayout(self.running_panel)

        row = 0
        self.next_file_lbl = ScrollingLabel("", width_chars=40)
        rg.addWidget(self.next_file_lbl, row, 0, 2, 5)
        row += 2

        self.trigger_btn = QPushButton("▶️ Start now")
        self.trigger_btn.clicked.connect(self.trigger_alarm_now)
        rg.addWidget(self.trigger_btn, row, 0)

        self.mute_btn = QPushButton("🔇 Mute")
        self.mute_btn.clicked.connect(self.toggle_mute)
        rg.addWidget(self.mute_btn, row, 1)

        self.random_btn = QPushButton("🔀")
        self.random_btn.clicked.connect(self.randomize_next_sound)
        rg.addWidget(self.random_btn, row, 4)
        row += 1

        self.countdown_to_next = QLabel("")
        rg.addWidget(self.countdown_to_next, row, 0, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)

        self.countdown_lbl = QLabel("00")
        rg.addWidget(self.countdown_lbl, row, 3, 1, 2, alignment=Qt.AlignmentFlag.AlignRight)
        row += 1

        self.prev_alarm_lbl = QLabel("⬅️ None")
        rg.addWidget(self.prev_alarm_lbl, row, 0, alignment=Qt.AlignmentFlag.AlignLeft)
        self.next_alarm_lbl = QLabel("➡️ None")
        rg.addWidget(self.next_alarm_lbl, row, 4, alignment=Qt.AlignmentFlag.AlignRight)
        row += 1

        self.stop_all_btn = QPushButton("⏹️ Stop All")
        self.stop_all_btn.clicked.connect(self.stop_all_alarms)
        rg.addWidget(self.stop_all_btn, row, 3, 1, 2)

        self.toggle_alarms_btn = QPushButton("▼ Scheduled Sessions 🕗")
        self.toggle_alarms_btn.clicked.connect(self.toggle_alarms_list)
        rg.addWidget(self.toggle_alarms_btn, row, 0, 1, 2)
        row += 1

        # Alarms area
        self.alarms_area = QScrollArea()
        self.alarms_area.setWidgetResizable(True)
        self.alarms_inner = QWidget()
        self.alarms_v = QVBoxLayout(self.alarms_inner)
        self.alarms_inner.setLayout(self.alarms_v)
        self.alarms_area.setWidget(self.alarms_inner)
        self.alarms_area.hide()
        rg.addWidget(self.alarms_area, row, 0, 1, 3)
        row += 1

        # Spinbox row
        hbox = QHBoxLayout()
        self.arbitrary_label = QLabel("Set Value:")
        self.arbitrary_spin = QSpinBox()
        self.arbitrary_spin.setRange(-1_000_000, 1_000_000)
        self.arbitrary_spin.setValue(self.arbitrary_integer)
        self.arbitrary_spin.valueChanged.connect(self.update_water_spin)
        hbox.addWidget(self.arbitrary_label)
        hbox.addWidget(self.arbitrary_spin)
        rg.addLayout(hbox, row, 0, 1, 2)

        outer.addWidget(self.running_panel)

        # icon
        try:
            ico_file = os.path.join(script_dir, "icon.png")
            if os.path.exists(ico_file):
                self.setWindowIcon(QIcon(ico_file))
        except Exception:
            pass

    def closeEvent(self, e):
        self.stop_all_alarms(save=False)
        try:
            with pygame_lock:
                pygame.mixer.quit()
        except Exception:
            pass
        return super().closeEvent(e)

    # Dialog helpers
    def edit_start_time(self):
        self._edit_time("Edit Start Time", is_start=True)

    def edit_end_time(self):
        self._edit_time("Edit End Time", is_start=False)

    def _edit_time(self, title, is_start=True):
        h0 = self.start_hour if is_start else self.end_hour
        m0 = self.start_minute if is_start else self.end_minute
        s0 = self.start_second if is_start else self.end_second
        a0 = self.start_ampm if is_start else self.end_ampm

        h, ok = QInputDialog.getInt(self, title, "Hour (1-12):", h0, 1, 12, 1)
        if not ok: return
        m, ok = QInputDialog.getInt(self, title, "Minute (0-59):", m0, 0, 59, 1)
        if not ok: return
        s, ok = QInputDialog.getInt(self, title, "Second (0-59):", s0, 0, 59, 1)
        if not ok: return
        ap, ok = QInputDialog.getItem(self, title, "AM/PM:", ["AM","PM"], 0 if a0=="AM" else 1, False)
        if not ok: return
        if is_start:
            self.start_hour, self.start_minute, self.start_second, self.start_ampm = h, m, s, ap
            self.start_lbl.setText(self._format_time(h, m, s, ap))
        else:
            self.end_hour, self.end_minute, self.end_second, self.end_ampm = h, m, s, ap
            self.end_lbl.setText(self._format_time(h, m, s, ap))
        self._save_settings()

    def edit_count(self):
        n, ok = QInputDialog.getInt(self, "Edit Count", "Number of alarms:", self.num_alarms, 2, 100, 1)
        if ok:
            self.num_alarms = n
            self.count_lbl.setText(str(n))
            self._save_settings()

    def edit_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select sound folder", self.sound_folder or os.path.expanduser("~"))
        if folder:
            self.sound_folder = folder
            self.folder_lbl.set_text(folder)
            self._save_settings()

    def edit_length(self):
        m, ok = QInputDialog.getInt(self, "Alarm Length", "Minutes:", self.alarm_length_minutes, 0, 59, 1)
        if not ok: return
        s, ok = QInputDialog.getInt(self, "Alarm Length", "Seconds:", self.alarm_length_seconds, 0, 59, 1)
        if not ok: return
        self.alarm_length_minutes = m
        self.alarm_length_seconds = s
        self.length_lbl.setText(self._format_len(m, s))
        self._save_settings()

    def update_water_spin(self):
        qty = round(self.arbitrary_spin.value() * 0.230, 2)
        self.arbitrary_label.setText(f" 💧 {qty} L")
        self._save_settings()

    def _start_caffeinate(self):
        if self.caffeinate_process is None:
            try:
                self.caffeinate_process = subprocess.Popen(["caffeinate", "-i"])
            except Exception as e:
                print(f"Could not start caffeinate: {e}")

    def _stop_caffeinate(self):
        if self.caffeinate_process:
            try:
                self.caffeinate_process.terminate()
            except Exception:
                pass
            self.caffeinate_process = None

    def set_alarms(self):
        # validate
        try:
            sh, sm, ss = self._hms_ampm_to_24(self.start_hour, self.start_minute, self.start_second, self.start_ampm)
            eh, em, es = self._hms_ampm_to_24(self.end_hour, self.end_minute, self.end_second, self.end_ampm)
            start = datetime.combine(datetime.today(), datetime.min.time()).replace(hour=sh, minute=sm, second=ss, microsecond=0)
            end   = datetime.combine(datetime.today(), datetime.min.time()).replace(hour=eh, minute=em, second=es, microsecond=0)
            if end <= start:
                raise ValueError("End time must be after start time.")
            if self.num_alarms < 2:
                raise ValueError("At least 2 alarms required.")
            if not os.path.isdir(self.sound_folder):
                raise ValueError("Invalid sound folder.")
            sound_files = [f for f in os.listdir(self.sound_folder) if f.lower().endswith((".mp3", ".wav"))]
            if not sound_files:
                raise ValueError("No mp3 or wav files found in sound folder.")
            self.sound_files = [os.path.join(self.sound_folder, f) for f in sound_files]
            duration = self.alarm_length_minutes * 60 + self.alarm_length_seconds
            if duration < 1:
                raise ValueError("Alarm duration must be at least 1 second.")
        except Exception as e:
            QMessageBox.critical(self, "Input Error", str(e))
            return

        self.frame_id = "running"
        self._save_settings()
        self.alarm_duration_seconds = duration

        total_seconds = (end - start).total_seconds()
        interval = total_seconds / (self.num_alarms - 1)

        self.alarm_times.clear()
        for i in range(self.num_alarms):
            dt = start + timedelta(seconds=interval * i)
            self.alarm_times.append(dt.time())

        # switch panels
        self.setup_panel.hide()
        self.running_panel.show()

        self.countdown_lbl.setText(self._format_seconds(self.alarm_duration_seconds))
        self._start_caffeinate()
        self.is_running = True
        self.mute_state["muted"] = False
        self.last_set_time = datetime.now()
        self.next_sound_file = random.choice(self.sound_files)
        self._update_next_sound_label()
        self._rebuild_alarms_checklist()
        # start scheduler loop timer
        if not hasattr(self, "_scheduler_timer"):
            self._scheduler_timer = QTimer(self)
            self._scheduler_timer.timeout.connect(self._scheduler_tick)
        self._notified = [False] * len(self.alarm_times)
        self._scheduler_timer.start(1000)

    def _format_seconds(self, secs: int):
        m = int(secs) // 60
        s = int(secs) % 60
        return f"{m:02}:{s:02}" if m > 0 else f"{s:02}"

    def toggle_alarms_list(self):
        self.alarms_frame_visible = not self.alarms_frame_visible
        if self.alarms_frame_visible:
            self.toggle_alarms_btn.setText("▲ Scheduled Sessions 🕗")
            self.alarms_area.show()
        else:
            self.toggle_alarms_btn.setText("▼ Scheduled Sessions 🕗")
            self.alarms_area.hide()

    def _rebuild_alarms_checklist(self):
        # clear
        while self.alarms_v.count():
            item = self.alarms_v.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.alarm_check_vars = []

        if not self.alarm_times:
            self.alarms_v.addWidget(QLabel("No scheduled alarms."))
            return

        if len(self.saved_alarm_check_statuses) == len(self.alarm_times):
            states = self.saved_alarm_check_statuses
        else:
            states = [False] * len(self.alarm_times)

        for i, t in enumerate(self.alarm_times):
            text = f"{i+1:2d}. {t.strftime('%I:%M:%S %p')}"
            cb = QCheckBox(text)
            cb.setChecked(states[i])
            cb.stateChanged.connect(self._save_settings)
            self.alarms_v.addWidget(cb)
            self.alarm_check_vars.append(cb)
        self._save_settings()

    def _scheduler_tick(self):
        if not self.is_running:
            return
        now = datetime.now().replace(microsecond=0)

        # prev/next indicators
        prev_alarm = None
        next_alarm = None
        for t in sorted(self.alarm_times):
            alarm_dt = datetime.combine(now.date(), t)
            if alarm_dt <= now:
                prev_alarm = t
            elif alarm_dt > now and next_alarm is None:
                next_alarm = t
        self.prev_alarm_lbl.setText(f"⬅️ {prev_alarm.strftime('%I:%M:%S %p')}" if prev_alarm else "⬅️ None")
        self.next_alarm_lbl.setText(f"➡️ {next_alarm.strftime('%I:%M:%S %p')}" if next_alarm else "➡️ None")

        # trigger alarms
        last_set_delta = self.last_set_time and (datetime.now() - self.last_set_time).total_seconds() < 2
        for i, t in enumerate(self.alarm_times):
            alarm_dt = datetime.combine(now.date(), t)
            if not self._notified[i] and now >= alarm_dt:
                if last_set_delta:
                    self._notified[i] = True
                    continue
                self._start_alarm(i)
                self._notified[i] = True
                self.mute_state["muted"] = False
                if i + 1 < len(self.alarm_times):
                    old = self.next_sound_file
                    choices = [f for f in self.sound_files if f != old]
                    self.next_sound_file = random.choice(choices) if choices else old
                    self._update_next_sound_label()
                else:
                    self.next_sound_file = None
                    self._update_next_sound_label()
        # countdown-to-next updated by _update_next_countdown()

    def _update_next_countdown(self):
        if not self.is_running:
            self.countdown_to_next.setText("")
            return
        now = datetime.now().replace(microsecond=0)
        next_alarm = None
        for t in sorted(self.alarm_times):
            alarm_dt = datetime.combine(now.date(), t)
            if alarm_dt > now:
                next_alarm = t
                break
        if next_alarm:
            next_dt = datetime.combine(now.date(), next_alarm)
            remaining = (next_dt - now).total_seconds()
            if remaining < 0:
                remaining = 0
            hours = int(remaining) // 3600
            minutes = (int(remaining) % 3600) // 60
            seconds = int(remaining) % 60
            if hours > 0:
                text = f"⌛ {hours}:{minutes:02}:{seconds:02}"
            else:
                text = f"⌛ {minutes:02}:{seconds:02}"
        else:
            text = ""
        self.countdown_to_next.setText(text)

    def _start_alarm(self, idx):
        # only one at a time
        if self.current_worker is not None:
            return

        file_path = self.next_sound_file if self.next_sound_file else random.choice(self.sound_files)
        self.current_worker = AlarmWorker(file_path, self.alarm_duration_seconds, self.mute_state)

        # wire signals
        self.current_worker.tick.connect(self._on_alarm_tick)
        self.current_worker.finished.connect(self._on_alarm_finished)
        self.current_worker.started.connect(lambda: None)
        self.current_worker.error.connect(self._on_alarm_error)

        # launch in Python thread (Qt threads also possible)
        self.current_thread = threading.Thread(target=self.current_worker.run, daemon=True)
        self.current_thread.start()

    def _on_alarm_tick(self, remaining):
        if remaining > 0:
            self.countdown_lbl.setText(self._format_seconds(remaining))
        else:
            self.countdown_lbl.setText(self._format_seconds(self.alarm_duration_seconds))

    def _on_alarm_finished(self):
        self.mute_state["muted"] = False
        self.current_worker = None
        self.current_thread = None

    def _on_alarm_error(self, msg):
        QMessageBox.critical(self, "Playback Error", msg)
        self.current_worker = None
        self.current_thread = None

    def _update_next_sound_label(self):
        if self.next_sound_file:
            self.next_file_lbl.set_text(os.path.basename(self.next_sound_file))
        else:
            self.next_file_lbl.set_text("")

    def randomize_next_sound(self):
        if not self.sound_files:
            QMessageBox.critical(self, "No Sounds", "No sound files loaded for alarms.")
            return
        old = self.next_sound_file
        choices = [f for f in self.sound_files if f != old]
        self.next_sound_file = random.choice(choices) if choices else old
        self._update_next_sound_label()

    def toggle_mute(self):
        self.mute_state["muted"] = not self.mute_state.get("muted", False)
        self.mute_btn.setText("🔈 Unmute" if self.mute_state["muted"] else "🔇 Mute")

    def stop_all_alarms(self, save=True):
        self.is_running = False
        if self.current_worker:
            self.current_worker.stop()
        self._stop_caffeinate()
        self.running_panel.hide()
        self.setup_panel.show()
        self.mute_btn.setText("🔇 Mute")
        self.countdown_lbl.setText(self._format_seconds(self.alarm_duration_seconds))
        self.next_file_lbl.set_text("")
        self.alarm_times.clear()
        self.prev_alarm_lbl.setText("⬅️ None")
        self.next_alarm_lbl.setText("➡️ None")
        self.countdown_to_next.setText("")
        self.next_sound_file = None
        self.mute_state["muted"] = False
        self.alarms_area.hide()
        self.alarms_frame_visible = False
        self.toggle_alarms_btn.setText("▼ Scheduled Sessions 🕗")
        self.frame_id = "setting"
        if hasattr(self, "_scheduler_timer"):
            self._scheduler_timer.stop()
        if save:
            self._save_settings()

    def trigger_alarm_now(self):
        global global_start_time
        global_start_time = time.time()
        if self.current_worker is not None:
            QMessageBox.information(self, "Alarm Running", "An alarm is already playing.")
            return
        if not self.sound_files:
            QMessageBox.critical(self, "No Sounds", "No sound files loaded for alarms.")
            return
        self._start_alarm(-1)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = IntervalAlarmApp()
    w.resize(700, 520)
    w.show()
    sys.exit(app.exec())
