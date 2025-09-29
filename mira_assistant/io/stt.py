"""Speech-to-text utilities built on faster-whisper."""
from __future__ import annotations

import queue
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

    def listen_and_transcribe(self, silence_ms: int = 800) -> str:
        import sounddevice as sd  # type: ignore

        frame_duration = 30  # ms
        frame_samples = int(self.samplerate * frame_duration / 1000)
        audio_frames: list[bytes] = []
        silence_frames_required = max(1, int(silence_ms / frame_duration))
        silence_counter = 0
        stream_queue: "queue.Queue[bytes]" = queue.Queue()

        def callback(indata, frames, time, status):  # type: ignore[no-untyped-def]
            if status:
                pass
            stream_queue.put(bytes(indata))

        with sd.RawInputStream(
            samplerate=self.samplerate,
            blocksize=frame_samples,
            dtype="int16",
            channels=self.channels,
            callback=callback,
        ):
            while True:
                data = stream_queue.get()
                if self.vad.is_speech(data, self.samplerate):
                    audio_frames.append(data)
                    silence_counter = 0
                else:
                    silence_counter += 1
                if audio_frames and silence_counter >= silence_frames_required:
                    break
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
