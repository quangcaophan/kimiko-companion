from groq import Groq
from dotenv import load_dotenv
import os
import sounddevice as sd
import soundfile as sf
import numpy as np

load_dotenv()

class GroqASR:
    def __init__(self, api_key: str, context_prompt: str = "") -> None:
        self.api_key = api_key
        self.context_prompt = context_prompt
        self.client = self.get_groq_client()
        
    def get_groq_client(self):
        if not self.api_key:
            raise EnvironmentError("GROQ_API_KEY not set")
        return Groq(api_key=self.api_key)

    def record(self, output_file: str, samplerate: int = 44100, channels: int = 1,
               silence_threshold: float = 0.02, silence_duration: float = 1.0,
               device: int | str | None = None) -> bool:
        # return True nếu ghi thành công, False nếu lỗi (KHÁC bản gốc — không im lặng nuốt lỗi)
        try:
            chunk_duration = 0.1
            block_size = int(samplerate * chunk_duration)

            recored_frames = []
            has_spoken = False
            silence_frames = 0
            wait_time = 0.0
            silence_time = 0.0       
            max_wait_timeout = 15

            with sd.InputStream(samplerate = samplerate, channels = channels, blocksize = block_size,
                                device= device, dtype="float32") as stream:
                print("Listening...Speak now (press Enter to stop)...")

                while True:
                    data, overflowed = stream.read(block_size)
                    if overflowed: print("⚠️ audio overflow, có thể mất dữ liệu")

                    volume = np.sqrt(np.mean(data**2))
                    
                    if not has_spoken:
                        if volume > silence_threshold:
                            has_spoken = True
                            print("Detected voice, started recording")
                            recored_frames.append(data)
                        else:
                            wait_time += chunk_duration
                            if wait_time >= max_wait_timeout:
                                print("No speech detected after 15 seconds")
                                break
                    else:
                        recored_frames.append(data)
                        if volume < silence_threshold:
                            silence_frames += chunk_duration
                            if silence_frames >= silence_duration:
                                print("Silence detected, ending recording")
                                break
                        else:
                            silence_frames = 0 # reset
            
            if not recored_frames or not has_spoken:
                print("No speech detected")
                return False
            
            audio_data = np.concatenate(recored_frames, axis=0)
            sf.write(output_file, audio_data,samplerate)
            return True

        except Exception as e:
            print(f"Error recording audio: {e}")
            return False
        except KeyboardInterrupt:
            print("Recording stopped by user")
            return False


    def transcribe(self, aud_path: str) -> str:
        """Transcribe a WAV via Groq Whisper-large-v3. Returns the spoken text."""

        if not aud_path:
            return "There is no Audio path"

        with open(aud_path, "rb") as file:
            transcription = self.client.audio.transcriptions.create(
                file=(aud_path, file.read()),
                model="whisper-large-v3",
                response_format="verbose_json",
                prompt=self.context_prompt
            )
        text = transcription.text
        print(f"[asr.transcribe] {text!r}")
        return text


# if __name__ == "__main__":
#     asr = GroqASR(api_key=os.getenv("GROQ_API_KEY"), context_prompt="Cuộc trò chuyện giữa Kimiko và người dùng")

#     ok = asr.record("test_delay.wav", silence_duration=1.5,device=2)
#     if ok:
#         duration = sf.info("test_delay.wav").duration
#         print("Duration:", duration)
#         text = asr.transcribe("test_delay.wav")
#         print("Nội dung nói:", text)
#     else:
#         print("Ghi âm thất bại (chưa kịp nói hoặc mic không có tín hiệu)")
