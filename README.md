# uvchat

Standalone desktop helper for Utherverse chat translation.

This project is intentionally separate from `cinema`.

Important:

- this app must run on the same PC as the Utherverse client
- for your real use case that means: run it on your Windows 10 machine
- the Ubuntu copy is only the project source and a prototype environment

## MVP

- small desktop window
- captures a configured screen region
- runs OCR on that region
- shows original text and translated text
- no sending, no bot, no Cinema integration

## Planned Flow

1. Open the app.
2. Enter the chat capture region (`x`, `y`, `width`, `height`).
3. Start scanning.
4. The app reads visible chat text from that region.
5. The app shows the OCR result and a translated version.

## Current Translation Mode

The app supports two modes:

- `echo`
  - no external translator
  - the translated pane mirrors OCR text
- `libretranslate`
  - sends text to a LibreTranslate-compatible endpoint

For the first MVP, `echo` is the safest default.

## Files

- [app.py](/home/ubuntu/uvchat/app.py)
- [config.example.json](/home/ubuntu/uvchat/config.example.json)
- [config.json](/home/ubuntu/uvchat/config.json)
- [requirements.txt](/home/ubuntu/uvchat/requirements.txt)
- [run_uvchat.sh](/home/ubuntu/uvchat/run_uvchat.sh)
- [run_uvchat.bat](/home/ubuntu/uvchat/run_uvchat.bat)

## Local Setup

Recommended packages:

- `python3-tk`
- `tesseract-ocr`
- Python packages from `requirements.txt`

Example:

```bash
cd /home/ubuntu/uvchat
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp config.example.json config.json
python app.py
```

## Windows 10 Setup

This is the setup you actually want for Utherverse.

### 1. Copy the folder to your Windows PC

Copy the whole `uvchat` folder to something like:

```text
C:\uvchat
```

### 2. Install Python for Windows

Install Python 3.12 or newer from:

- https://www.python.org/downloads/windows/

Important during install:

- enable `Add Python to PATH`

### 3. Install Tesseract OCR for Windows

Install Tesseract OCR on Windows.

After install, make sure `tesseract.exe` is available in your `PATH`.

If it is not in `PATH`, you can still add it later in Windows environment variables.

### 4. Open Command Prompt in the uvchat folder

Example:

```bat
cd C:\uvchat
```

### 5. Create a virtual environment

```bat
python -m venv .venv
```

### 6. Install Python packages

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 7. Start the app

Either double-click:

- `run_uvchat.bat`

or start manually:

```bat
.venv\Scripts\python.exe app.py
```

## First Windows Test

1. Start Utherverse on your Windows PC.
2. Open `uvchat`.
3. Leave the translation mode on `echo`.
4. Put the Utherverse chat window clearly on screen.
5. Enter the chat region:
   - `x`
   - `y`
   - `width`
   - `height`
6. Press `Start`.
7. Check whether the visible chat text appears in the `Original OCR` pane.

If OCR is still weak:

- make the chat text larger if possible
- reduce transparency
- increase contrast
- capture only the chat area, not the full client

## Region Coordinates On Windows

For the first test, the easiest way is:

- open `uvchat`
- guess a small region around the visible chat
- adjust the values until OCR starts reading text

If you want, the next improvement can be a simple Windows region-picker overlay so you do not have to enter coordinates manually.

## Notes

- OCR quality depends heavily on font size and contrast.
- Use a clearly visible chat area with minimal transparency if possible.
- The app stores settings in `config.json` if present.
