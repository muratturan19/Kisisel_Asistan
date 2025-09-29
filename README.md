# Mira Assistant

Windows odaklı, Türkçe destekli kişisel asistanın masaüstü MVP sürümü.

## Özellikler

- PySide6 tabanlı masaüstü arayüz: komut girişi, ajanda ve görev panelleri.
- STT için `faster-whisper` + `sounddevice` + `webrtcvad`.
- TTS için `edge-tts` öncelikli, `pyttsx3` yedek.
- SQLite + SQLModel veri katmanı, tüm tarih/saat değerleri UTC olarak saklanır.
- Belge ingest akışı (PDF/DOCX/PPTX/TXT/IMG) → chunk → embedding → Chroma vektör deposu.
- RAG tabanlı konu özetleri ve basit kural temelli uyarılar.

## Kurulum

```powershell
py -3.11 -m venv venv
./venv/Scripts/Activate.ps1
pip install -r requirements.txt
```

Windows bildirimleri için isteğe bağlı olarak `win10toast` kütüphanesini ayrıca yükleyebilirsiniz. Bu bağımlılık artık kurulumun
zorunlu bir parçası değildir; yüklenmediği durumda uygulama bildirim mesajlarını yalnızca günlük kayıtlarına yazar.

OCR için sistemde Tesseract kurulumu gerekir:

```powershell
winget install tesseract --source winget
```

## İlk Çalıştırma

```powershell
python .\app_ui.py
```

İlk açılışta `~/MiraData/` altında gerekli klasörler, `db/mira.sqlite` veritabanı ve `index/` vektör deposu oluşturulur.

## Notlar

- Uygulama çevrimdışı çalışacak şekilde tasarlanmıştır; dış API çağrısı yapılmaz.
- Ses ve bildirim özellikleri Windows ortamında test edilmelidir.
- Inbox klasörüne bırakılan belgeler UI üzerinden ingest edilerek arşivlenir.
