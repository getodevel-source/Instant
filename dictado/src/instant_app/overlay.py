"""Overlay: notificacion visual junto al cursor. Tkinter en su hilo (cross-platform)."""
import logging
import queue
import threading

log = logging.getLogger("instant")


class Overlay:
    def __init__(self):
        self.q = queue.Queue()
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        try:
            import tkinter as tk
            self.root = tk.Tk()
            self.root.withdraw()
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            try:
                self.root.attributes("-alpha", 0.92)
            except Exception:
                pass
            self.label = tk.Label(self.root, font=("Segoe UI", 11, "bold"),
                                  bg="#1e1e1e", padx=12, pady=6, wraplength=600,
                                  justify="left")
            self.label.pack()
            self.root.after(50, self._poll)
            self.root.mainloop()
        except Exception:
            log.exception("overlay thread muerto (sin Tk? instala python3-tk en linux)")

    def _poll(self):
        try:
            while True:
                cmd = self.q.get_nowait()
                if cmd[0] == "show":
                    _, text, color = cmd
                    self.label.config(text=text, fg=color)
                    x, y = self.root.winfo_pointerx() + 16, self.root.winfo_pointery() + 16
                    self.root.geometry(f"+{x}+{y}")
                    self.root.deiconify()
                    self.root.lift()
                elif cmd[0] == "hide":
                    self.root.withdraw()
        except queue.Empty:
            pass
        except Exception:
            log.exception("overlay poll fail")
        self.root.after(50, self._poll)

    def _push(self, cmd):
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        self.q.put(cmd)

    def show(self, text, color="#ff4444"):
        self._push(("show", text, color))

    def hide(self):
        self._push(("hide",))
