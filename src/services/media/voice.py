#!/usr/bin/env python3
"""
Voice-to-Text transcription using Google Speech Recognition (free)
Supports continuous recording that saves to file for hold-to-talk
"""

import sys
import json
import os
import tempfile
import atexit
import wave
import pyaudio
import speech_recognition as sr

# Temp file for continuous recording
TEMP_AUDIO_FILE = os.path.join(tempfile.gettempdir(), 'voice_recording.wav')

def cleanup():
    """Clean up temp file on exit"""
    try:
        if os.path.exists(TEMP_AUDIO_FILE):
            os.remove(TEMP_AUDIO_FILE)
    except:
        pass

atexit.register(cleanup)

def transcribe_audio(audio, recognizer):
    """Transcribe audio data using Google Speech Recognition"""
    try:
        text = recognizer.recognize_google(audio)
        return {"text": text}
    except sr.UnknownValueError:
        return {"error": "Could not understand audio. Please speak clearly."}
    except sr.RequestError as e:
        return {"error": f"Speech recognition service error: {e}"}
    except Exception as e:
        return {"error": f"Transcription error: {str(e)}"}

def transcribe_file(audio_path):
    """Transcribe from an audio file"""
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(audio_path) as source:
            audio = recognizer.record(source)
        return transcribe_audio(audio, recognizer)
    except Exception as e:
        return {"error": f"File transcription error: {str(e)}"}

def record_continuous():
    """Record continuously until killed, saving to temp file periodically"""
    try:
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024
        )

        print("Recording started...", file=sys.stderr)
        frames = []

        # Record continuously, saving periodically
        try:
            while True:
                data = stream.read(1024, exception_on_overflow=False)
                frames.append(data)

                # Save to file every 0.5 seconds (8 chunks at 16000/1024)
                if len(frames) % 8 == 0:
                    save_audio(frames)

        except (KeyboardInterrupt, SystemExit):
            pass
        finally:
            # Save final audio
            if frames:
                save_audio(frames)

            stream.stop_stream()
            stream.close()
            p.terminate()

            print(f"Recording stopped. Saved {len(frames)} chunks.", file=sys.stderr)

    except OSError as e:
        if "No Default Input Device" in str(e) or "-9996" in str(e):
            print(json.dumps({"error": "No microphone found. Please connect a microphone."}))
        else:
            print(json.dumps({"error": f"Microphone error: {str(e)}"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Recording error: {str(e)}"}))
        sys.exit(1)

def save_audio(frames):
    """Save frames to temp WAV file"""
    try:
        with wave.open(TEMP_AUDIO_FILE, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(16000)
            wf.writeframes(b''.join(frames))
    except Exception as e:
        print(f"Save error: {e}", file=sys.stderr)

def transcribe_recording():
    """Transcribe the saved recording"""
    if not os.path.exists(TEMP_AUDIO_FILE):
        return {"error": "No recording found"}

    file_size = os.path.getsize(TEMP_AUDIO_FILE)
    if file_size < 1000:  # Less than 1KB = too short
        return {"error": "Recording too short. Hold longer and speak."}

    print(f"Transcribing recording ({file_size} bytes)...", file=sys.stderr)
    result = transcribe_file(TEMP_AUDIO_FILE)

    # Clean up
    try:
        os.remove(TEMP_AUDIO_FILE)
    except:
        pass

    return result

def transcribe_live(timeout=30, phrase_timeout=20):
    """Record from microphone and transcribe (click-to-record method)"""
    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold = 1.5

    try:
        with sr.Microphone() as source:
            print("Adjusting for ambient noise...", file=sys.stderr)
            recognizer.adjust_for_ambient_noise(source, duration=0.5)

            print(f"Listening (max {phrase_timeout}s)...", file=sys.stderr)
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_timeout)

        print("Processing speech...", file=sys.stderr)
        return transcribe_audio(audio, recognizer)

    except sr.WaitTimeoutError:
        return {"error": "No speech detected. Please try again."}
    except OSError as e:
        if "No Default Input Device" in str(e):
            return {"error": "No microphone found. Please connect a microphone."}
        return {"error": f"Microphone error: {str(e)}"}
    except Exception as e:
        return {"error": f"Transcription error: {str(e)}"}

def main():
    if len(sys.argv) > 1:
        arg = sys.argv[1]

        if arg == "--record":
            # Just record (for hold-to-talk)
            record_continuous()
        elif arg == "--transcribe":
            # Transcribe saved recording
            result = transcribe_recording()
            print(json.dumps(result))
        elif arg == "--live":
            # Click-to-record mode
            timeout = int(sys.argv[2]) if len(sys.argv) > 2 else 30
            phrase_timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 20
            result = transcribe_live(timeout, phrase_timeout)
            print(json.dumps(result))
        else:
            print(json.dumps({"error": f"Unknown argument: {arg}"}))
    else:
        # Default: live recording
        result = transcribe_live()
        print(json.dumps(result))

if __name__ == "__main__":
    main()
