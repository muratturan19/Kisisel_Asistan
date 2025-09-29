# Mira Assistant

Windows odaklı, Türkçe destekli kişisel asistanın MVP kaynak kodu.

## Kurulum

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py init-db
```

## Çalıştırma

```powershell
python app.py process "22'si 10:00 toplantı"
```

## Test

```powershell
pytest
```

## Not

- Sesli özellikler için `faster-whisper` ve `edge-tts` entegrasyonu TODO.
- Tray arayüzü için `pystray` entegrasyonu TODO.
