import sounddevice as sd
import numpy as np

print("=" * 60)
print("AUDIO DEVICES:")
print(sd.query_devices())
print()
print("DEFAULT:", sd.default.device)
print("=" * 60)

# Play a 440Hz beep for 1 second on default output
print("\nPlaying 440Hz beep for 1 second via sounddevice...")
try:
    fs = 44100
    t = np.linspace(0, 1.0, fs, endpoint=False)
    tone = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
    sd.play(tone, fs)
    sd.wait()
    print("✅ Beep finished — did you hear it?")
except Exception as e:
    print(f"❌ Playback failed: {e}")

# Try playing the last speech WAV if it exists
import glob, os
wavs = sorted(glob.glob(r"kimiko\assets\client\audio\temp\*.wav"))
if wavs:
    latest = wavs[-1]
    print(f"\nTrying to play latest WAV: {latest}")
    try:
        import soundfile as sf
        data, fs = sf.read(latest, dtype="float32")
        print(f"  Sample rate: {fs}, Duration: {len(data)/fs:.2f}s, Shape: {data.shape}")
        sd.play(data, fs)
        sd.wait()
        print("✅ WAV playback done — did you hear it?")
    except Exception as e:
        print(f"❌ WAV playback failed: {e}")
else:
    print("No WAV files found in audio/temp/")
