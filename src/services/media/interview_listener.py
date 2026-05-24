#!/usr/bin/env python3
"""
Interview Listener Service
- Long-lived subprocess controlled via stdin JSON commands
- Captures audio from microphone (MVP) and emits question events
- Supports force trigger command for immediate transcription
"""

import sys
import json
import threading
import queue
import time

import speech_recognition as sr

try:
    import pyaudiowpatch as pyaudio  # Windows loopback support
    LOOPBACK_AVAILABLE = True
except Exception:
    pyaudio = None
    LOOPBACK_AVAILABLE = False


def send(event):
    try:
        print(json.dumps(event), flush=True)
    except Exception:
        pass


class InterviewListener:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.running = True
        self.listening_enabled = False
        self.source_mode = "auto"  # auto | mic | loopback | index (int)
        self.device_index = None   # Specific index if source_mode is an index
        self.audio_queue = queue.Queue()
        self.listener_thread = None
        self.transcribe_thread = None

    def set_source(self, source):
        if isinstance(source, int):
            self.source_mode = "index"
            self.device_index = source
        elif source in ("auto", "mic", "loopback"):
            self.source_mode = source
            self.device_index = None
        else:
            self.source_mode = "auto"
            self.device_index = None

        if (self.source_mode == "loopback" or self.source_mode == "index") and not LOOPBACK_AVAILABLE:
            send({
                "event": "error",
                "message": "Loopback requested but pyaudiowpatch is unavailable. Falling back to microphone."
            })
            self.source_mode = "mic"
            self.device_index = None

    def list_devices(self):
        """Enumerate available WASAPI loopback devices."""
        if not LOOPBACK_AVAILABLE:
            send({"event": "devices", "devices": []})
            return

        pa = None
        try:
            pa = pyaudio.PyAudio()
            devices = []
            
            # On Windows with pyaudiowpatch, we look for loopback devices
            try:
                # get_default_wasapi_loopback check
                default = pa.get_default_wasapi_loopback()
                if default:
                    devices.append({
                        "index": default["index"],
                        "name": f"Default Loopback: {default['name']}",
                        "is_default": True
                    })
            except Exception:
                pass

            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                # Check if it's a loopback device (specific to pyaudiowpatch)
                if info.get('isLoopbackDevice') or 'loopback' in info.get('name', '').lower():
                    # Avoid duplicates with default if it's already there
                    if not any(d['index'] == i for d in devices):
                        devices.append({
                            "index": i,
                            "name": info.get('name'),
                            "is_default": False
                        })
            
            send({"event": "devices", "devices": devices})
        except Exception as e:
            send({"event": "error", "message": f"Failed to list devices: {e}"})
        finally:
            if pa:
                pa.terminate()

    def start(self):
        if self.listening_enabled:
            return

        self.listening_enabled = True
        if not self.listener_thread or not self.listener_thread.is_alive():
            self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listener_thread.start()
        if not self.transcribe_thread or not self.transcribe_thread.is_alive():
            self.transcribe_thread = threading.Thread(target=self._transcribe_loop, daemon=True)
            self.transcribe_thread.start()

        send({"event": "listening"})

    def stop(self):
        self.listening_enabled = False
        send({"event": "listening", "message": "paused"})

    def shutdown(self):
        self.running = False
        self.listening_enabled = False

    def force(self):
        """Force a quick capture and emit a question."""
        if not self.running:
            return
        try:
            use_loopback = self.source_mode in ("loopback", "index") or (self.source_mode == "auto" and LOOPBACK_AVAILABLE)
            if use_loopback:
                audio = self._capture_loopback_phrase(duration_sec=6)
                if audio:
                    self.audio_queue.put(audio)
                else:
                    send({"event": "partial", "text": "Loopback unavailable, using microphone..."})
                return
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                send({"event": "partial", "text": "Capturing question..."})
                audio = self.recognizer.listen(source, timeout=3, phrase_time_limit=12)
                self.audio_queue.put(audio)
        except Exception as e:
            send({"event": "error", "message": f"Force capture failed: {e}"})

    def _listen_loop(self):
        while self.running:
            if not self.listening_enabled:
                time.sleep(0.1)
                continue
            try:
                use_loopback = self.source_mode in ("loopback", "index") or (self.source_mode == "auto" and LOOPBACK_AVAILABLE)
                if use_loopback:
                    send({"event": "partial", "text": "Listening (meeting audio)..."})
                    audio = self._capture_loopback_phrase(duration_sec=8)
                    if audio:
                        self.audio_queue.put(audio)
                    else:
                        send({"event": "partial", "text": "Listening (microphone fallback)..."})
                        with sr.Microphone() as source:
                            self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                            audio = self.recognizer.listen(source, timeout=4, phrase_time_limit=14)
                            self.audio_queue.put(audio)
                    continue

                with sr.Microphone() as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
                    send({"event": "partial", "text": "Listening..."})
                    audio = self.recognizer.listen(source, timeout=4, phrase_time_limit=14)
                    self.audio_queue.put(audio)
            except sr.WaitTimeoutError:
                continue
            except Exception as e:
                send({"event": "error", "message": f"Listener error: {e}"})
                time.sleep(0.5)

    def _capture_loopback_phrase(self, duration_sec=8):
        """Capture desktop/meeting audio via WASAPI loopback and convert to SpeechRecognition AudioData."""
        if not LOOPBACK_AVAILABLE:
            return None
        pa = None
        stream = None
        try:
            pa = pyaudio.PyAudio()
            
            target_device = None
            if self.source_mode == "index" and self.device_index is not None:
                try:
                    target_device = pa.get_device_info_by_index(self.device_index)
                except Exception:
                    pass
            
            if not target_device:
                target_device = pa.get_default_wasapi_loopback()
                
            if not target_device:
                send({"event": "error", "message": "No loopback device found. Using microphone source is recommended."})
                return None

            channels = int(target_device.get("maxInputChannels") or 2)
            rate = int(target_device.get("defaultSampleRate") or 48000)
            frames_per_buffer = 1024

            stream = pa.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=rate,
                input=True,
                input_device_index=target_device["index"],
                frames_per_buffer=frames_per_buffer
            )

            chunks = []
            total_frames = int((rate * duration_sec) / frames_per_buffer)
            for _ in range(total_frames):
                if not self.running or not self.listening_enabled:
                    break
                data = stream.read(frames_per_buffer, exception_on_overflow=False)
                chunks.append(data)

            raw = b"".join(chunks)
            if not raw:
                return None
            # SpeechRecognition expects mono-like PCM bytes. For simplicity, pass raw bytes and sample width 2.
            return sr.AudioData(raw, rate, 2)
        except Exception as e:
            send({"event": "error", "message": f"Loopback capture failed: {e}"})
            return None
        finally:
            try:
                if stream:
                    stream.stop_stream()
                    stream.close()
            except Exception:
                pass
            try:
                if pa:
                    pa.terminate()
            except Exception:
                pass

    def _transcribe_loop(self):
        while self.running:
            try:
                audio = self.audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                send({"event": "partial", "text": "Transcribing..."})
                text = self.recognizer.recognize_google(audio)
                if text and text.strip():
                    send({"event": "question", "text": text.strip()})
            except sr.UnknownValueError:
                # Silence/unclear capture; ignore quietly
                continue
            except sr.RequestError as e:
                send({"event": "error", "message": f"Speech service error: {e}"})
            except Exception as e:
                send({"event": "error", "message": f"Transcription failed: {e}"})


def main():
    listener = InterviewListener()
    send({"event": "started", "success": True, "source": "mic"})

    while listener.running:
        line = sys.stdin.readline()
        if not line:
            break

        try:
            payload = json.loads(line.strip())
        except Exception:
            send({"event": "error", "message": "Invalid JSON command"})
            continue

        cmd = payload.get("cmd")
        if cmd == "start":
            listener.start()
        elif cmd == "stop":
            listener.stop()
        elif cmd == "force":
            listener.force()
        elif cmd == "get_devices":
            listener.list_devices()
        elif cmd == "set_source":
            listener.set_source(payload.get("source", "auto"))
        elif cmd == "shutdown":
            listener.shutdown()
            break
        else:
            send({"event": "error", "message": f"Unknown command: {cmd}"})

    send({"event": "stopped"})


if __name__ == "__main__":
    main()
