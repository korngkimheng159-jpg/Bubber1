import sys, os, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FROZEN = getattr(sys, "frozen", False)
if FROZEN:                                           # packaged .exe: use the ffmpeg shipped next to it, no console
    base = os.path.dirname(sys.executable)
    for d in (os.path.join(base, "ffmpeg"), base):
        if os.path.exists(os.path.join(d, "ffmpeg.exe")):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            break
    if sys.stdout is None: sys.stdout = open(os.devnull, "w")
    if sys.stderr is None: sys.stderr = open(os.devnull, "w")


def crash(msg):
    try:
        log = os.path.join(os.path.expanduser("~"), ".khmer_dubber", "crash.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        open(log, "a", encoding="utf-8").write(msg + "\n")
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Dubber ខ្មែរ", msg[-1500:])
    except Exception:
        print(msg)


if __name__ == "__main__":
    try:
        from ui.main_window import main
        main()
    except ImportError as e:
        crash(f"❌ ខ្វះ package: {e}\n   សូមរត់:  pip install -r requirements.txt")
        sys.exit(1)
    except Exception:
        crash(traceback.format_exc())
        sys.exit(1)
