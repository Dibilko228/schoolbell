from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from datetime import datetime
from pathlib import Path
import json

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.gridlayout import MDGridLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDFloatingActionButton
from kivymd.uix.toolbar import MDTopAppBar
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.list import MDList, OneLineListItem


DEFAULT_SCHEDULE = [
    {"n": 1,  "start": "08:00", "end": "08:40"},
    {"n": 2,  "start": "08:45", "end": "09:25"},
    {"n": 3,  "start": "09:35", "end": "10:15"},
    {"n": 4,  "start": "10:20", "end": "11:00"},
    {"n": 5,  "start": "11:10", "end": "11:50"},
    {"n": 6,  "start": "12:00", "end": "12:40"},
    {"n": 7,  "start": "12:45", "end": "13:25"},
    {"n": 8,  "start": "13:35", "end": "14:15"},
    {"n": 9,  "start": "14:25", "end": "15:05"},
    {"n": 10, "start": "15:10", "end": "15:50"},
    {"n": 11, "start": "15:55", "end": "16:35"},
    {"n": 12, "start": "16:40", "end": "17:20"},
]


class ClockTab(MDBoxLayout):
    """Main tab with clock and current lesson display"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = 12
        self.spacing = 12
        
        self.time_label = MDLabel(
            text='00:00:00',
            font_style='H1',
            halign='center',
            size_hint_y=0.4
        )
        self.add_widget(self.time_label)
        
        self.date_label = MDLabel(
            text='01.01.2026',
            font_style='H4',
            halign='center',
            size_hint_y=0.15
        )
        self.add_widget(self.date_label)
        
        self.lesson_label = MDLabel(
            text='ДО 1 УРОКУ\n1h 23m',
            font_style='H3',
            halign='center',
            size_hint_y=0.45
        )
        self.add_widget(self.lesson_label)
        
        Clock.schedule_interval(self._update_clock, 1)
    
    def _update_clock(self, dt):
        now = datetime.now()
        self.time_label.text = now.strftime('%H:%M:%S')
        self.date_label.text = now.strftime('%d.%m.%Y')


class RecordingsTab(MDBoxLayout):
    """Recordings management tab"""
    def __init__(self, app_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.app = app_ref
        self.orientation = 'vertical'
        self.padding = 12
        self.spacing = 8
        
        self.add_widget(MDLabel(text='Мої записи', size_hint_y=0.08, font_style='H6'))
        
        btn_box = MDBoxLayout(size_hint_y=0.12, spacing=6)
        btn_box.add_widget(MDRaisedButton(text='▶ Start', on_release=self.on_start_record))
        btn_box.add_widget(MDRaisedButton(text='⏹ Save', on_release=self.on_stop_record))
        self.add_widget(btn_box)
        
        self.recordings_list = MDList()
        scroll = MDScrollView()
        scroll.add_widget(self.recordings_list)
        self.add_widget(scroll)
        
        self.refresh_recordings()
    
    def refresh_recordings(self):
        self.recordings_list.clear_widgets()
        recordings = self.app.custom_recordings if self.app else {}
        if not recordings:
            self.recordings_list.add_widget(OneLineListItem(text='(No recordings yet)'))
        else:
            for name in recordings.keys():
                self.recordings_list.add_widget(OneLineListItem(text=f'🎙 {name}'))
    
    def on_start_record(self, obj):
        from kivy.utils import platform
        if platform == 'android':
            # TODO: Call Android MediaRecorder via pyjnius
            pass
    
    def on_stop_record(self, obj):
        # TODO: Stop recording and save
        pass


class ScheduleTab(MDBoxLayout):
    """Schedule management tab"""
    def __init__(self, app_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.app = app_ref
        self.orientation = 'vertical'
        self.padding = 12
        self.spacing = 8
        
        self.add_widget(MDLabel(text='Розклад', size_hint_y=0.08, font_style='H6'))
        
        self.schedule_list = MDList()
        scroll = MDScrollView()
        scroll.add_widget(self.schedule_list)
        self.add_widget(scroll)
        
        btn_box = MDBoxLayout(size_hint_y=0.12, spacing=6)
        btn_box.add_widget(MDRaisedButton(text='+ Додати', on_release=self.on_add_lesson))
        btn_box.add_widget(MDRaisedButton(text='✔ Зберегти', on_release=self.on_save_schedule))
        self.add_widget(btn_box)
        
        self.refresh_schedule()
    
    def refresh_schedule(self):
        self.schedule_list.clear_widgets()
        schedule = self.app.schedule if self.app else DEFAULT_SCHEDULE
        for item in schedule:
            text = f"Урок {item['n']}: {item['start']} - {item['end']}"
            self.schedule_list.add_widget(OneLineListItem(text=text))
    
    def on_add_lesson(self, obj):
        # TODO: Open dialog to add lesson
        pass
    
    def on_save_schedule(self, obj):
        if self.app:
            self.app.save_config()


class SettingsTab(MDBoxLayout):
    """Settings tab"""
    def __init__(self, app_ref=None, **kwargs):
        super().__init__(**kwargs)
        self.app = app_ref
        self.orientation = 'vertical'
        self.padding = 12
        self.spacing = 8
        
        self.add_widget(MDLabel(text='Налаштування', size_hint_y=0.08, font_style='H6'))
        
        scroll = MDScrollView()
        settings_box = MDBoxLayout(orientation='vertical', size_hint_y=None, spacing=8, padding=8)
        settings_box.bind(minimum_height=settings_box.setter('height'))
        
        settings_box.add_widget(MDLabel(text='🔔 Звуки', size_hint_y=None, height=40, font_style='Subtitle1'))
        settings_box.add_widget(MDLabel(
            text='Звук на початок уроку\nЗвук на кінець уроку\nСирена тривоги',
            size_hint_y=None, height=100, font_style='Caption'
        ))
        
        settings_box.add_widget(MDLabel(text='⏰ Інше', size_hint_y=None, height=40, font_style='Subtitle1'))
        settings_box.add_widget(MDLabel(
            text='Тихий режим\nХвилина мовчання (09:00)\nВимкнення ПК',
            size_hint_y=None, height=100, font_style='Caption'
        ))
        
        scroll.add_widget(settings_box)
        self.add_widget(scroll)


class SchoolBellApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.title = 'SchoolBell'
        
        self.base_dir = Path.home() / 'SchoolBell'
        self.base_dir.mkdir(exist_ok=True)
        self.config_path = self.base_dir / 'config.json'
        
        self.schedule = DEFAULT_SCHEDULE.copy()
        self.custom_recordings = {}
        
        self.load_config()
    
    def build(self):
        root = MDBoxLayout(orientation='vertical')
        
        toolbar = MDTopAppBar(
            title='SchoolBell',
            elevation=10,
            size_hint_y=0.08
        )
        root.add_widget(toolbar)
        
        tabs = MDTabs(size_hint_y=0.92)
        
        # Clock tab
        clock_tab = ClockTab()
        clock_item = MDTabsBase(title='Час')
        clock_item.add_widget(clock_tab)
        tabs.add_widget(clock_item)
        
        # Recordings tab
        rec_tab = RecordingsTab(app_ref=self)
        rec_item = MDTabsBase(title='🎙')
        rec_item.add_widget(rec_tab)
        tabs.add_widget(rec_item)
        
        # Schedule tab
        sched_tab = ScheduleTab(app_ref=self)
        sched_item = MDTabsBase(title='≡')
        sched_item.add_widget(sched_tab)
        tabs.add_widget(sched_item)
        
        # Settings tab
        settings_tab = SettingsTab(app_ref=self)
        settings_item = MDTabsBase(title='⚙')
        settings_item.add_widget(settings_tab)
        tabs.add_widget(settings_item)
        
        root.add_widget(tabs)
        
        return root
    
    def load_config(self):
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text())
                self.schedule = data.get('schedule', DEFAULT_SCHEDULE.copy())
                self.custom_recordings = data.get('custom_recordings', {})
            except Exception:
                pass
    
    def save_config(self):
        try:
            data = {
                'schedule': self.schedule,
                'custom_recordings': self.custom_recordings,
            }
            self.config_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            pass


if __name__ == '__main__':
    SchoolBellApp().run()
