"""
Android audio recording and playback helpers using pyjnius.
Only functional on Android.
"""

from kivy.utils import platform


if platform == 'android':
    from jnius import autoclass
    
    # Android classes
    MediaRecorder = autoclass('android.media.MediaRecorder')
    AudioManager = autoclass('android.media.AudioManager')
    Environment = autoclass('android.os.Environment')
    File = autoclass('java.io.File')
    PythonActivity = autoclass('org.kivy.android.PythonActivity')
    
    # MediaPlayer for playback
    MediaPlayer = autoclass('android.media.MediaPlayer')
    
    class AndroidAudioRecorder:
        """Wraps MediaRecorder for WAV recording on Android"""
        
        def __init__(self, output_path: str):
            self.recorder = MediaRecorder()
            self.output_path = output_path
            self.is_recording = False
        
        def start_record(self):
            """Start recording audio"""
            try:
                self.recorder.setAudioSource(MediaRecorder.AudioSource.MIC)
                self.recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)  # or AMR_NB
                self.recorder.setAudioEncoder(MediaRecorder.AudioEncoder.AMR_NB)
                self.recorder.setOutputFile(self.output_path)
                self.recorder.prepare()
                self.recorder.start()
                self.is_recording = True
                return True
            except Exception as e:
                print(f"Failed to start recording: {e}")
                return False
        
        def stop_record(self):
            """Stop recording"""
            try:
                if self.is_recording:
                    self.recorder.stop()
                    self.recorder.release()
                    self.is_recording = False
                    return True
            except Exception as e:
                print(f"Failed to stop recording: {e}")
            return False
    
    class AndroidAudioPlayer:
        """Wraps MediaPlayer for audio playback on Android"""
        
        def __init__(self, audio_path: str):
            self.player = MediaPlayer()
            self.audio_path = audio_path
        
        def play(self):
            """Play audio file"""
            try:
                self.player.setDataSource(self.audio_path)
                self.player.prepare()
                self.player.start()
                return True
            except Exception as e:
                print(f"Failed to play audio: {e}")
                return False
        
        def stop(self):
            """Stop playback"""
            try:
                if self.player.isPlaying():
                    self.player.stop()
                    self.player.release()
                return True
            except Exception as e:
                print(f"Failed to stop playback: {e}")
            return False

else:
    # Dummy classes for non-Android platforms
    class AndroidAudioRecorder:
        def __init__(self, output_path: str):
            pass
        
        def start_record(self):
            print("Recording only available on Android")
            return False
        
        def stop_record(self):
            return False
    
    class AndroidAudioPlayer:
        def __init__(self, audio_path: str):
            pass
        
        def play(self):
            print("Playback only available on Android")
            return False
        
        def stop(self):
            return False
