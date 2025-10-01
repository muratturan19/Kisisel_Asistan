"""Speech-to-text utilities built on faster-whisper."""
from __future__ import annotations

import queue
import time
from typing import Optional

import numpy as np

class WhisperTranscriber:
    """Offline STT wrapper using faster-whisper and WebRTC VAD."""

    def __init__(self, model_size: str = "medium", device: str = "cpu") -> None:
        from faster_whisper import WhisperModel  # type: ignore
        import webrtcvad  # type: ignore

        self.model = WhisperModel(model_size, device=device, compute_type="int8")
        self.vad = webrtcvad.Vad(2)
        self.samplerate = 16000
        self.channels = 1

    def listen_and_transcribe(self, silence_ms: int = 800, timeout_seconds: int = 30) -> str:
        import sounddevice as sd  # type: ignore

        frame_duration = 30  # ms
        frame_samples = int(self.samplerate * frame_duration / 1000)
        audio_frames: list[bytes] = []
        silence_frames_required = max(1, int(silence_ms / frame_duration))
        silence_counter = 0
        stream_queue: "queue.Queue[bytes]" = queue.Queue()
        start_time = time.time()

        def callback(indata, frames, time_info, status):  # type: ignore[no-untyped-def]
            if status:
                pass
            stream_queue.put(bytes(indata))

        try:
            with sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=frame_samples,
                dtype="int16",
                channels=self.channels,
                callback=callback,
            ):
                while True:
                    if time.time() - start_time > timeout_seconds:
                        if not audio_frames:
                            raise TimeoutError(
                                f"Ses kaydı {timeout_seconds} saniye içinde tamamlanamadı"
                            )
                        break

                    try:
                        data = stream_queue.get(timeout=1.0)
                    except queue.Empty:
                        continue

                    try:
                        is_speech = self.vad.is_speech(data, self.samplerate)
                    except Exception:
                        continue

                    if is_speech:
                        audio_frames.append(data)
                        silence_counter = 0
                    else:
                        silence_counter += 1

                    if audio_frames and silence_counter >= silence_frames_required:
                        break
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"Ses kaydı hatası: {str(e)}") from e
        if not audio_frames:
            return ""
        audio_bytes = b"".join(audio_frames)
        return self._transcribe_bytes(audio_bytes)

    def transcribe_file(self, path: str, *, language: Optional[str] = "tr") -> str:
        segments, _ = self.model.transcribe(path, language=language, beam_size=1)
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _transcribe_bytes(self, audio_bytes: bytes, *, language: Optional[str] = "tr") -> str:
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        segments, _ = self.model.transcribe(audio_array, language=language, beam_size=1)
        return " ".join(segment.text.strip() for segment in segments).strip()


__all__ = ["WhisperTranscriber"]
