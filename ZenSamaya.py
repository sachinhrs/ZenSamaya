import tkinter as tk
from tkinter import messagebox, filedialog, simpledialog
from datetime import datetime, timedelta
import threading
import time
import os
import random
import json
import pygame
import subprocess
from PIL import Image, ImageTk  # Add this import at the top



script_dir = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(script_dir,".srvn_apps", 'settings.json') 
if not os.path.exists(SETTINGS_FILE):
    with open(SETTINGS_FILE, "w") as f:
        pass  # Just create the empty file

pygame_lock = threading.Lock()
global_start_time = 0.0


def play_mp3_for_duration(stop_event, file_path, duration, update_countdown_func, mute_state):
    global global_start_time
    with pygame_lock:
        try:
            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play(loops=-1)
            pygame.mixer.music.set_volume(0.0 if mute_state['muted'] else 1.0)
            print("Alarm Triggered at ")
            print(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
        except Exception as e:
            print(f"Error playing {file_path}: {e}")
            return

    global_start_time = time.time()
    while not stop_event.is_set():
        elapsed = time.time() - global_start_time
        remaining = max(0, duration - elapsed)
        update_countdown_func(remaining)
        if elapsed >= duration:
            break
        with pygame_lock:
            try:
                vol = 0.0 if mute_state['muted'] else 1.0
                pygame.mixer.music.set_volume(vol)
            except Exception as e:
                print(f"Error setting volume: {e}")
        time.sleep(0.1)

    with pygame_lock:
        try:
            pygame.mixer.music.fadeout(2000)
        except Exception as e:
            print(f"Error during fadeout: {e}")
    update_countdown_func(0)
    time.sleep(2)
    with pygame_lock:
        try:
            print("Alarm Ended at ")
            print(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
            pygame.mixer.music.stop()
        except Exception as e:
            print(f"Error stopping music: {e}")


montserrat_font = ("Montserrat", 12)
montserrat_font_bold = ("Montserrat", 12, "bold")
monospace_font = ("Monaco", 12)

class RoundedButton(tk.Canvas):
    def __init__(self, parent, width, height, cornerradius, padding, color, bg,text="", command=None):
        tk.Canvas.__init__(self, parent, borderwidth=0, 
            relief="flat", highlightthickness=0, bg=bg)
        self.command = command



        if cornerradius > 0.5*width:
            print("Error: cornerradius is greater than width.")
            return None

        if cornerradius > 0.5*height:
            print("Error: cornerradius is greater than height.")
            return None

        rad = 2*cornerradius
        def shape():
            self.create_polygon((padding,height-cornerradius-padding,padding,cornerradius+padding,padding+cornerradius,padding,width-padding-cornerradius,padding,width-padding,cornerradius+padding,width-padding,height-cornerradius-padding,width-padding-cornerradius,height-padding,padding+cornerradius,height-padding), fill=color, outline=color)
            self.create_arc((padding,padding+rad,padding+rad,padding), start=90, extent=90, fill=color, outline=color)
            self.create_arc((width-padding-rad,padding,width-padding,padding+rad), start=0, extent=90, fill=color, outline=color)
            self.create_arc((width-padding,height-rad-padding,width-padding-rad,height-padding), start=270, extent=90, fill=color, outline=color)
            self.create_arc((padding,height-padding-rad,padding+rad,height-padding), start=180, extent=90, fill=color, outline=color)

        id = shape()
        self.text_id = self.create_text(width/2,height/2,fill="black",font=montserrat_font_bold,
                        text=text)

        #self.move(text_id, 0, 10)
        (x0,y0,x1,y1)  = self.bbox("all")
        width = (x1-x0)
        height = (y1-y0)
        self.configure(width=width, height=height)

        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_press(self, event):
        self.configure(relief="sunken")

    def _on_release(self, event):
        self.configure(relief="raised")
        if self.command is not None:
            self.command()
    
    def set_text(self,text=""):
        self.itemconfig(self.text_id, text=text)


class ScrollingLabel(tk.Label):
    def __init__(self, master, text, width=20, delay=250, **kwargs):
        '''width: number of visible characters; delay: ms between shifts'''
        super().__init__(master, **kwargs)
        self.full_text = text
        self.display_width = width
        self.delay = delay
        self.position = 0
        self.after_id = None
        self._start_scroll()
        
    def _scroll_text(self):
        full_text = self.full_text + '   '  # spacing after end
        visible = (full_text + full_text)[self.position:self.position+self.display_width]
        self.config(text=visible)
        self.position = (self.position + 1) % len(full_text)
        self.after_id = self.after(self.delay, self._scroll_text)

    def _start_scroll(self):
        self.position = 0
        self._scroll_text()

    def set_text(self, new_text):
        self.full_text = new_text
        self.position = 0

    def stop(self):
        if self.after_id:
            self.after_cancel(self.after_id)
            self.after_id = None

class IntervalAlarmApp:
    def __init__(self, master):
        self.master = master
        self.bg_color = "white"
        master.title("Meditation Sessions 🧘")

        try:
            pygame.mixer.init()
        except Exception as e:
            messagebox.showerror("Audio Error", f"Pygame mixer initialization failed:\n{e}")
            master.destroy()
            return

        montserrat_font = ("Montserrat", 12)
        montserrat_font_bold = ("Montserrat", 12, "bold")
        monospace_font = ("Monaco", 12)


        self.frame_id = "load"
        # Alarm setup frame (NEW STYLE)
        self.setup_frame = tk.Frame(master,padx = 20,pady=10)
        self.setup_frame.grid(row=0, column=0, sticky='nsew')



        for i in range(3):
            self.setup_frame.grid_columnconfigure(i, weight=1)
        
        self.initialise_settings_vars()
        self.alarm_duration_seconds = 0
        row = 0

        # Start time
        self.start_time_label = tk.Label(self.setup_frame, text=self._format_time(self.start_hour, self.start_minute, self.start_second, self.start_ampm), font=montserrat_font)
        tk.Label(self.setup_frame, text="🕒", font=montserrat_font).grid(row=row, column=0, sticky='w')
        self.start_time_label.grid(row=row, column=1, sticky='w')
        self.start_edit_btn = tk.Label(self.setup_frame, text="🖊️")
        self.start_edit_btn.bind("<Button-1>", self.edit_start_time)        
        #tk.Button(self.setup_frame, text="🖊️", command=self.edit_start_time, font=montserrat_font_bold)
        self.start_edit_btn.grid(row=row, column=2,sticky="e")
        row += 1

        # End time
        self.end_time_label = tk.Label(self.setup_frame, text=self._format_time(self.end_hour, self.end_minute, self.end_second, self.end_ampm), font=montserrat_font)
        tk.Label(self.setup_frame, text="🕒", font=montserrat_font).grid(row=row, column=0, sticky='w')
        self.end_time_label.grid(row=row, column=1, sticky='w')

        self.end_edit_btn = tk.Label(self.setup_frame, text="🖊️")
        self.end_edit_btn.bind("<Button-1>", self.edit_end_time)   
        self.end_edit_btn.grid(row=row, column=2,sticky="e")
        row += 1

        # Alarm count
        self.count_label = tk.Label(self.setup_frame, text=str(self.num_alarms), font=montserrat_font)
        tk.Label(self.setup_frame, text="🔔", font=montserrat_font).grid(row=row, column=0, sticky='w')
        self.count_label.grid(row=row, column=1, sticky='w')
        self.count_edit_btn = tk.Label(self.setup_frame, text="🖊️")
        self.count_edit_btn.bind("<Button-1>", self.edit_count)   
        self.count_edit_btn.grid(row=row, column=2,sticky="e")
        row += 1

        # Folder
        self.folder_label = ScrollingLabel(self.setup_frame, text=self.sound_folder or "-", width=20, font=monospace_font)
        

        tk.Label(self.setup_frame, text="🎵", font=montserrat_font).grid(row=row, column=0, sticky='w')
        self.folder_label.grid(row=row, column=1, sticky='w')
        self.folder_edit_btn = tk.Label(self.setup_frame, text="📁")
        self.folder_edit_btn.bind("<Button-1>", self.edit_folder)   
        self.folder_edit_btn.grid(row=row, column=2,sticky="e")
        row += 1

        # Length
        self.length_label = tk.Label(self.setup_frame, text=self._format_length(self.alarm_length_minutes, self.alarm_length_seconds), font=montserrat_font)
        tk.Label(self.setup_frame, text="⏳", font=montserrat_font).grid(row=row, column=0, sticky='w')
        self.length_label.grid(row=row, column=1, sticky='w')
        self.length_edit_btn = tk.Label(self.setup_frame, text="🖊️")
        self.length_edit_btn.bind("<Button-1>", self.edit_length)   
        self.length_edit_btn.grid(row=row, column=2,sticky="e")
        row += 1

        spacer = tk.Label(self.setup_frame, text="")
        spacer.grid(row=row, column=0)
        row += 1


        self.set_button = RoundedButton(self.setup_frame, 200, 30, 10, 2, 'lightgray', 'systemWindowBackgroundColor',text ="⏰ Set", command=self.set_alarms)
        self.set_button.grid(row=row, column=0, columnspan=8)#, pady=(10, 10))



        for i in range(row):
            self.setup_frame.grid_rowconfigure(i, minsize=30)


        # Alarm running frame
        self.running_frame = tk.Frame(master, padx=20, pady=15)
        self.running_frame.grid(row=1, column=0, sticky='ew')
        self.running_frame.grid_remove()
        for i in range(7):
            self.running_frame.grid_columnconfigure(i, weight=1)

        row = 0
        round_btn_width = 130
        round_btn_height = 30

        self.next_file_label = ScrollingLabel(self.running_frame, text="", width=40, font=monospace_font)
       
        self.next_file_label.grid(row=row, column=0, columnspan=5,rowspan=2, sticky='ew', pady=(0,6))
        self.next_file_label.bind("<Button-1>", lambda e: self.toggle_test_play_pause())

        row += 2
        button_row=row
        self.trigger_now_btn =  RoundedButton(self.running_frame, round_btn_width, round_btn_height, 10, 2, 'lightgray', 'systemWindowBackgroundColor',text ="▶️ Start now", command=self.trigger_alarm_now)
        
        self.trigger_now_btn.grid(row=row, column=0, columnspan=1, sticky='w', padx=0, pady=(0, 0))

        #row += 1
        self.mute_btn = RoundedButton(self.running_frame, round_btn_width, round_btn_height, 10, 2, 'lightgray', 'systemWindowBackgroundColor',text ="🔇 Mute", command=self.toggle_mute)

        self.mute_btn.grid(row=row, column=1, columnspan=1, padx=0, pady=0)

        self.randomize_button =  RoundedButton(self.running_frame, round_btn_width, round_btn_height, 10, 2, 'lightgray', 'systemWindowBackgroundColor',text ="🔀", command=self.randomize_next_sound)

        self.randomize_button.grid(row=row, column=4, sticky='e')#, padx=5, pady=(0,6))



        # Add Play/Pause button next to Randomize button
        self.is_test_playing = False  # state for test audio playback




        row += 1
        self.countdown_to_next_label = tk.Label(self.running_frame, text="", font=montserrat_font)#("Montserrat", 14))
        self.countdown_to_next_label.grid(row=row, column=0, columnspan=2, sticky='w', padx=0)

        #row += 1
        self.countdown_label = tk.Label(self.running_frame, text="A", font=montserrat_font)#("Montserrat", 16))
        self.countdown_label.grid(row=row, column=3, columnspan=2, sticky='e', pady=(10, 10))

        row += 1
        self.prev_alarm_label = tk.Label(self.running_frame, text="⬅️ None", font=montserrat_font_bold)
        self.prev_alarm_label.grid(row=row, column=0, sticky='w', pady=(0,6))
        self.next_alarm_label = tk.Label(self.running_frame, text="None ➡️", font=montserrat_font_bold)
        self.next_alarm_label.grid(row=row, column=4, sticky='e', pady=(0,6))


        # Collapsible scheduled alarms area

        row += 1

        self.stop_all_btn =  RoundedButton(self.running_frame, round_btn_width, round_btn_height, 10, 2, 'lightgray', 'systemWindowBackgroundColor',text ="⏹️ Stop All", command=self.stop_all_alarms)

        self.stop_all_btn.grid(row=row, column=3, columnspan=2, sticky='ew', padx=0, pady=0)
        
        self.toggle_alarms_btn = RoundedButton(self.running_frame, round_btn_width*2, round_btn_height, 10, 2, 'lightgray', 'systemWindowBackgroundColor',text ="▼ Scheduled Sessions 🕗", command=self.toggle_alarms_list)

        self.toggle_alarms_btn.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(10, 10))
        
        for i in range(row):
            self.running_frame.grid_rowconfigure(i, minsize=30)

        self.running_frame.grid_rowconfigure(button_row, minsize=50)

        self.alarms_frame = tk.Frame(self.running_frame)
        self.alarms_frame.grid(row=row+1, column=0, columnspan=3, sticky='ew')

        self.alarms_frame.grid_remove()


        # Spinbox label and widget row below alarms_frame
        spinbox_row = 9 + 1

        self.arbitrary_integer_var = tk.IntVar(value=0)

        self.arbitrary_spinbox_label = tk.Label(self.running_frame, text="Set Value:", font=("Montserrat", 12))
        self.arbitrary_spinbox_label.grid(row=spinbox_row, column=0, sticky='w', padx=10, pady=(10, 0))

        self.arbitrary_spinbox = tk.Spinbox(
            self.running_frame,
            from_=-1000000,
            to=1000000,
            textvariable=self.arbitrary_integer_var,
            width=8,
            font=("Montserrat", 12),
            command=self.update_water_spin
        )
        self.arbitrary_spinbox.grid(row=spinbox_row, column=1, sticky='w', padx=0, pady=(10, 0))
        
        self.arbitrary_spinbox_label.grid_remove()
        self.arbitrary_spinbox.grid_remove()

        # Replace the simple Label with a frame to hold checkboxes
        self.alarms_checkboxes_frame = tk.Frame(self.alarms_frame)
        self.alarms_checkboxes_frame.pack(fill='x', padx=10, pady=5)

        # Store BooleanVar for each alarm checkbox to track state
        self.alarm_check_vars = []

        self.alarms_frame_visible = False

        # State variables
        self.alarm_times = []
        self.is_running = False
        self.stop_alarm_event = threading.Event()
        self.currently_ringing_index = None
        self.caffeinate_process = None
        self.sound_files = []
        self.next_sound_file = None
        self.mute_state = {'muted': False}
        self.last_set_time = None

        self.load_settings()
        self.update_water_spin(save=False)

        if(self.frame_id == "running"):
            self.master.after(100, self.set_alarms)

    def initialise_settings_vars(self):
        """Load initial values from file (or supply defaults)."""
        # add loading logic or assign defaults for first launch
        self.start_hour, self.start_minute, self.start_second, self.start_ampm = 6, 0, 0, "AM"
        self.end_hour, self.end_minute, self.end_second, self.end_ampm = 7, 0, 0, "AM"
        self.num_alarms = 5
        self.sound_folder = ""
        self.alarm_length_minutes = 0
        self.alarm_length_seconds = 10
        try:
            with open(SETTINGS_FILE) as f:
                s = json.load(f)
            self.start_hour     = int(s.get("start_hour", self.start_hour))
            self.start_minute   = int(s.get("start_minute", self.start_minute))
            self.start_second   = int(s.get("start_second", self.start_second))
            self.start_ampm     = s.get("start_ampm", self.start_ampm)
            self.end_hour       = int(s.get("end_hour", self.end_hour))
            self.end_minute     = int(s.get("end_minute", self.end_minute))
            self.end_second     = int(s.get("end_second", self.end_second))
            self.end_ampm       = s.get("end_ampm", self.end_ampm)
            self.num_alarms     = int(s.get("num_alarms", self.num_alarms))
            self.sound_folder   = s.get("sound_folder", self.sound_folder)
            self.frame_id = s.get("frame_id", self.frame_id)
            self.alarm_length_minutes = int(s.get("alarm_length_minutes", self.alarm_length_minutes))
            self.alarm_length_seconds = int(s.get("alarm_length_seconds", self.alarm_length_seconds))
        except Exception:
            pass


    def _format_time(self, hour, minute, second, ampm):
            return f"{hour:02}:{minute:02}:{second:02} {ampm}"

    def _format_length(self, minutes, seconds):
            return f"{minutes}m {seconds}s"

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.sound_folder_var.set(folder)

    def get_datetime(self, hour_box, min_box, sec_box, ampm_var):
        hour = int(hour_box)
        minute = int(min_box)
        second = int(sec_box)
        ampm = ampm_var
        if ampm == 'PM' and hour != 12:
            hour += 12
        elif ampm == 'AM' and hour == 12:
            hour = 0
        return datetime.combine(datetime.today(), datetime.min.time()).replace(hour=hour, minute=minute, second=second, microsecond=0)

    def update_water_spin(self,save = True):
        label = self.arbitrary_spinbox_label
        qty = round(self.arbitrary_integer_var.get()*.230,2)
        label.config(text=" 💧 "+str(qty)+" L")
        if(save):
            self.save_settings()

    def save_settings(self):
        settings = {
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
            # Save the checkboxes states as a list of bools mapped by index
            "alarm_check_statuses": [var.get() for var in self.alarm_check_vars] if hasattr(self, 'alarm_check_vars') else [],
            "arbitrary_integer": self.arbitrary_integer_var.get(),
            "frame_id": self.frame_id
        }
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w") as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def load_settings(self):
        try:
            with open(SETTINGS_FILE, "r") as f:
                settings = json.load(f)
            self.saved_alarm_check_statuses = settings.get("alarm_check_statuses", [])
            self.arbitrary_integer_var.set(settings.get("arbitrary_integer", 0))
        except Exception as e:
            print(f"Error loading settings: {e}")
            self.arbitrary_integer_var.set(0)
            self.saved_alarm_check_statuses = []

    def time_edit_popup(self, title, cur_hour, cur_min, cur_sec, cur_ampm, callback):
        popup = tk.Toplevel(self.master)
        popup.title(title)
        popup.resizable(False, False)

        tk.Label(popup, text="Hour:").grid(row=0, column=0)
        hour_var = tk.IntVar(value=cur_hour)
        tk.Spinbox(popup, from_=1, to=12, width=3, textvariable=hour_var).grid(row=0, column=1)

        tk.Label(popup, text="Minute:").grid(row=1, column=0)
        min_var = tk.IntVar(value=cur_min)
        tk.Spinbox(popup, from_=0, to=59, width=3, textvariable=min_var).grid(row=1, column=1)

        tk.Label(popup, text="Second:").grid(row=2, column=0)
        sec_var = tk.IntVar(value=cur_sec)
        tk.Spinbox(popup, from_=0, to=59, width=3, textvariable=sec_var).grid(row=2, column=1)

        tk.Label(popup, text="AM/PM:").grid(row=3, column=0)
        ampm_var = tk.StringVar(value=cur_ampm)
        tk.OptionMenu(popup, ampm_var, "AM", "PM").grid(row=3, column=1)

        def ok():
            h, m, s, a = hour_var.get(), min_var.get(), sec_var.get(), ampm_var.get()
            callback(h, m, s, a)
            popup.destroy()
        tk.Button(popup, text="OK", command=ok).grid(row=4, column=0)
        tk.Button(popup, text="Cancel", command=popup.destroy).grid(row=4, column=1)

        popup.transient(self.master)
        popup.grab_set()
        self.master.wait_window(popup)


    def edit_start_time(self,event=None):
        # pass in current values, lambda updates and saves:
        self.time_edit_popup("Edit Start Time", self.start_hour, self.start_minute, self.start_second, self.start_ampm,
                            lambda h, m, s, a: self._update_time('start', h, m, s, a))

    def edit_end_time(self,event=None):
        self.time_edit_popup("Edit End Time", self.end_hour, self.end_minute, self.end_second, self.end_ampm,
                            lambda h, m, s, a: self._update_time('end', h, m, s, a))

    def _update_time(self, which, hour, minute, second, ampm):
        if which == 'start':
            self.start_hour, self.start_minute, self.start_second, self.start_ampm = hour, minute, second, ampm
            self.start_time_label.config(text=self._format_time(hour, minute, second, ampm))
        else:
            self.end_hour, self.end_minute, self.end_second, self.end_ampm = hour, minute, second, ampm
            self.end_time_label.config(text=self._format_time(hour, minute, second, ampm))
        self.save_settings()

    def edit_count(self,event=None):
        new_count = simpledialog.askinteger("Edit Count", "Number of alarms:", initialvalue=self.num_alarms, minvalue=2, maxvalue=100)
        if new_count is not None:
            self.num_alarms = new_count
            self.count_label.config(text=str(new_count))
            self.save_settings()

    def edit_folder(self,event=None):
        folder = filedialog.askdirectory(title="Select sound folder")
        if folder:
            self.sound_folder = folder
            self.folder_label.set_text(folder)
            self.save_settings()

    def edit_length(self,event=None):
        # Could use a custom simple popup or two 'askinteger' dialogs for minutes and seconds:
        new_min = simpledialog.askinteger("Alarm Length", "Minutes:", initialvalue=self.alarm_length_minutes, minvalue=0, maxvalue=59)
        new_sec = simpledialog.askinteger("Alarm Length", "Seconds:", initialvalue=self.alarm_length_seconds, minvalue=0, maxvalue=59)
        if new_min is not None and new_sec is not None:
            self.alarm_length_minutes = new_min
            self.alarm_length_seconds = new_sec
            self.length_label.config(text=self._format_length(new_min, new_sec))
            self.save_settings()



    def start_caffeinate(self):
        if self.caffeinate_process is None:
            try:
                self.caffeinate_process = subprocess.Popen(['caffeinate','-i'])
            except Exception as e:
                print(f"Could not start caffeinate: {e}")

    def stop_caffeinate(self):
        if self.caffeinate_process:
            try:
                self.caffeinate_process.terminate()
            except Exception:
                pass
            self.caffeinate_process = None
    
    def set_alarms(self):
        try:
            # Construct datetime objects using updated internal variables, not widget.get()
            start = datetime.combine(
                datetime.today(),
                datetime.min.time()
            ).replace(
                hour=(
                    self.start_hour + 12 if self.start_ampm == 'PM' and self.start_hour != 12
                    else (0 if self.start_ampm == 'AM' and self.start_hour == 12 else self.start_hour)
                ),
                minute=self.start_minute,
                second=self.start_second,
                microsecond=0
            )
            end = datetime.combine(
                datetime.today(),
                datetime.min.time()
            ).replace(
                hour=(
                    self.end_hour + 12 if self.end_ampm == 'PM' and self.end_hour != 12
                    else (0 if self.end_ampm == 'AM' and self.end_hour == 12 else self.end_hour)
                ),
                minute=self.end_minute,
                second=self.end_second,
                microsecond=0
            )

            if end <= start:
                raise ValueError("End time must be after start time.")

            num_alarms = self.num_alarms
            if num_alarms < 2:
                raise ValueError("At least 2 alarms required.")

            sound_folder = self.sound_folder
            if not os.path.isdir(sound_folder):
                raise ValueError("Invalid sound folder.")

            sound_files = [f for f in os.listdir(sound_folder) if f.lower().endswith(('.mp3', '.wav'))]
            if not sound_files:
                raise ValueError("No mp3 or wav files found in sound folder.")

            self.sound_files = [os.path.join(sound_folder, f) for f in sound_files]

            minutes = self.alarm_length_minutes
            seconds = self.alarm_length_seconds
            duration = minutes * 60 + seconds
            if duration < 1:
                raise ValueError("Alarm duration must be at least 1 second.")

        except Exception as e:
            messagebox.showerror("Input Error", str(e))
            return

        # Set check statuses to unchecked initially or from saved, truncating or padding as necessary

        
        self.frame_id = "running"
        self.save_settings()

        self.alarm_duration_seconds = duration
        total_seconds = (end - start).total_seconds()
        interval_seconds = total_seconds / (num_alarms - 1)

        self.alarm_times.clear()
        curr = start
        for i in range(num_alarms):
            if i == 0:
                t = curr.time()
            else:
                curr = start + timedelta(seconds=interval_seconds * i)
                t = curr.time()
            self.alarm_times.append(t)

        self.setup_frame.grid_remove()
        self.running_frame.grid()


        self.countdown_label.config(text=self.format_seconds(self.alarm_duration_seconds))
        self.start_caffeinate()
        self.is_running = True
        self.stop_alarm_event.clear()
        self.mute_state['muted'] = False
        self.next_sound_file = random.choice(self.sound_files)
        self.update_next_sound_label()
        self.last_set_time = datetime.now()

        self.update_alarms_list()  # Refresh alarm list in the collapsible UI

        threading.Thread(target=self.alarm_thread, daemon=True).start()
        self.alarmsBox_initate = False

    def toggle_alarms_list(self):

        if self.alarms_frame_visible:
            self.alarms_frame.grid_remove()
            self.toggle_alarms_btn.set_text(text="▼ Scheduled Sessions 🕗")
            self.alarms_frame_visible = False
        else:

            self.alarms_frame.grid()
            self.toggle_alarms_btn.set_text(text="▲ Scheduled Sessions 🕗")
            self.alarms_frame_visible = True

    def update_alarms_list(self):
    # Clear existing widgets in the checkboxes frame
        for widget in self.alarms_checkboxes_frame.winfo_children():
            widget.destroy()
        self.alarm_check_vars = []

        num_alarms = len(self.alarm_times)

        if not self.alarm_times:
            label = tk.Label(self.alarms_checkboxes_frame, text="No scheduled alarms.")
            label.pack()
            return

        if hasattr(self, 'saved_alarm_check_statuses') and len(self.saved_alarm_check_statuses) == num_alarms:
            self.alarm_check_statuses = self.saved_alarm_check_statuses
        else:
            self.alarm_check_statuses = [False]*num_alarms

        for i, t in enumerate(self.alarm_times):
            var = tk.BooleanVar(value=self.alarm_check_statuses[i])
            cb = tk.Checkbutton(
                self.alarms_checkboxes_frame,
                text=f"{i+1:2d}. {t.strftime('%I:%M:%S %p')}",
                variable=var,
                command=self.save_settings
                ,state="active"
            )
            cb.pack(anchor='w')
            self.alarm_check_vars.append(var)
        self.save_settings()
        return


    def alarm_thread(self):
        notified = [False] * len(self.alarm_times)
        self.currently_ringing_index = None

        while self.is_running:
            now = datetime.now().replace(microsecond=0)

            # Skip triggering alarms if set_alarms was pressed less than 2 seconds ago
            last_set_delta = False
            if self.last_set_time and (datetime.now() - self.last_set_time).total_seconds() < 2:
                last_set_delta = True

            prev_alarm = None
            next_alarm = None

            for t in sorted(self.alarm_times):
                alarm_dt = datetime.combine(now.date(), t)
                if alarm_dt <= now:
                    prev_alarm = t
                elif alarm_dt > now and next_alarm is None:
                    next_alarm = t

            prev_text = f"⬅️ {prev_alarm.strftime('%I:%M:%S %p')}" if prev_alarm else "⬅️ None"
            next_text = f"➡️ {next_alarm.strftime('%I:%M:%S %p')}" if next_alarm else "➡️ None"

            self.prev_alarm_label.config(text=prev_text)
            self.next_alarm_label.config(text=next_text)
            if next_alarm:
                next_alarm_dt = datetime.combine(now.date(), next_alarm)
                remaining_seconds = (next_alarm_dt - now).total_seconds()
                if remaining_seconds < 0:
                    remaining_seconds = 0
                hours = int(remaining_seconds) // 3600
                minutes = (int(remaining_seconds) % 3600) // 60
                seconds = int(remaining_seconds) % 60
                if hours > 0:
                    countdown_text = f"⌛ {hours}:{minutes:02}:{seconds:02}"
                else:
                    countdown_text = f"⌛ {minutes:02}:{seconds:02}"
            else:
                countdown_text = ""

            self.countdown_to_next_label.config(text=countdown_text)

            for i, t in enumerate(self.alarm_times):
                alarm_dt = datetime.combine(now.date(), t)
                if not notified[i] and now >= alarm_dt:
                    if last_set_delta:
                        notified[i] = True
                        continue

                    self.start_alarm(i)
                    notified[i] = True
                    self.mute_state['muted'] = False

                    if i + 1 < len(self.alarm_times):
                        old_file = self.next_sound_file
                        choices = [f for f in self.sound_files if f != old_file]
                        self.next_sound_file = random.choice(choices) if choices else old_file
                        self.update_next_sound_label()
                    else:
                        self.next_sound_file = None
                        self.update_next_sound_label()
            time.sleep(1)

    def update_countdown_label(self, remaining_seconds):
        if remaining_seconds > 0:
            minutes = int(remaining_seconds) // 60
            seconds = int(remaining_seconds) % 60
            if minutes > 0:
                self.countdown_label.config(text=f"{minutes:02}:{seconds:02}")
            else:
                self.countdown_label.config(text=f"{seconds:02}")
        else:
            self.countdown_label.config(text=self.format_seconds(self.alarm_duration_seconds))

    def format_seconds(self,seconds):
            minutes = int(seconds) // 60
            seconds = int(seconds) % 60

            if minutes > 0:
                 return f"{minutes:02}:{seconds:02}"
            else:
                 return f"{seconds:02}"

    def start_alarm(self, idx):
        if self.currently_ringing_index is not None:
            # Only allow one alarm to ring at a time
            return

        def alarm_action():
            self.currently_ringing_index = idx
            file_path = self.next_sound_file if self.next_sound_file else random.choice(self.sound_files)
            play_mp3_for_duration(self.stop_alarm_event, file_path, self.alarm_duration_seconds, self.update_countdown_label, self.mute_state)
            self.countdown_label.config(text=self.format_seconds(self.alarm_duration_seconds))
            self.mute_state['muted'] = False
            self.currently_ringing_index = None

        threading.Thread(target=alarm_action, daemon=True).start()

    def update_next_sound_label(self):
        if self.next_sound_file:
            filename = os.path.basename(self.next_sound_file)
            self.next_file_label.set_text(filename)
        else:
            self.next_file_label.set_text("")

    def randomize_next_sound(self):
        playtest = True if self.is_test_playing else False
        if playtest:
            self.toggle_test_play_pause()
        if self.sound_files:
            old_file = self.next_sound_file
            choices = [f for f in self.sound_files if f != old_file]
            self.next_sound_file = random.choice(choices) if choices else old_file
            self.update_next_sound_label()
            if playtest:
                self.toggle_test_play_pause()

    def toggle_mute(self):
        self.mute_state['muted'] = not self.mute_state['muted']
        if self.mute_state['muted']:
            self.mute_btn.set_text(text="🔈 Unmute")
        else:
            self.mute_btn.set_text(text="🔇 Mute")

    def stop_all_alarms(self,save=True):
        self.is_running = False
        self.stop_alarm_event.set()
        self.stop_caffeinate()
        self.running_frame.grid_remove()
        self.setup_frame.grid()
        self.mute_btn.set_text(text="🔇 Mute")
        self.countdown_label.config(text=self.format_seconds(self.alarm_duration_seconds))
        self.next_file_label.set_text("")
        self.alarm_times.clear()
        self.prev_alarm_label.config(text="⬅️ None")
        self.next_alarm_label.config(text="➡️ None")
        self.countdown_to_next_label.config(text="")
        self.currently_ringing_index = None
        self.next_sound_file = None
        self.mute_state['muted'] = False
        self.alarms_frame.grid_remove()
        self.alarm_check_vars.clear()
        self.alarms_frame_visible = False
        self.toggle_alarms_btn.set_text(text="▼ Show Scheduled Sessions 🕗")
        self.frame_id = "setting"
        
        if(save):
            self.save_settings()

    def trigger_alarm_now(self):
        global global_start_time
        global_start_time = time.time()

        # Only trigger if no alarm is already ringing
        if self.currently_ringing_index is not None:
            messagebox.showinfo("Alarm Running", "An alarm is already playing.")
            return

        # Immediately trigger manual alarm with same behaviour
        if not self.sound_files:
            messagebox.showerror("No Sounds", "No sound files loaded for alarms.")
            return

        idx = -1  # Use -1 or another value to distinguish manual trigger
        self.start_alarm(idx)


    def toggle_test_play_pause(self):
        with pygame_lock:
            if not self.sound_files:
                messagebox.showerror("No Sounds", "No sound files loaded for testing.")
                return
            # Use the 'next_sound_file' or fallback to random sound for testing
            test_file = self.next_sound_file if self.next_sound_file else random.choice(self.sound_files)

            if not self.is_test_playing:
                # Play or unpause
                try:
                    if pygame.mixer.music.get_busy():
                        pygame.mixer.music.unpause()
                    else:
                        pygame.mixer.music.load(test_file)
                        pygame.mixer.music.play(loops=-1)
                    self.is_test_playing = True
                except Exception as e:
                    messagebox.showerror("Playback Error", f"Error playing sound: {e}")
            else:
                # Pause playback
                try:
                    pygame.mixer.music.pause()
                    self.is_test_playing = False
                except Exception as e:
                    messagebox.showerror("Playback Error", f"Error pausing sound: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    try:
        ico_file = os.path.join(script_dir, 'icon.png')
        icon = tk.PhotoImage(file=ico_file)
        root.iconphoto(True, icon)
    except Exception as e:
        print(f"Could not set icon: {e}")

    try:
        root.tk.call("font", "create", "Montserrat", "-family", "Montserrat")
        root.option_add("*Font", "Montserrat 12")
    except Exception:
        root.option_add("*Font", "Arial 12")

    app = IntervalAlarmApp(root)

    def on_close():
        app.stop_all_alarms(save=False)
        try:
            with pygame_lock:
                pygame.mixer.quit()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    
    root.mainloop()
