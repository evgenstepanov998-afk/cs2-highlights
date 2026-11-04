"""Small always-visible window: shows that the helper runs, what it does, and closes it."""
import os
import tkinter as tk
import webbrowser
from tkinter import messagebox

from . import config, setup

BG, PANEL, TEXT, MUTED, ACCENT = "#0f1115", "#171a21", "#e7e9ee", "#8a91a0", "#ff5500"


def run(job, url, shutdown):
    """job: server.JOB dict (read-only here); shutdown(): stops CS2 if needed, restores settings, exits."""
    root = tk.Tk()
    root.title("CS2 Highlights")
    root.configure(bg=BG)
    root.resizable(False, False)
    root.geometry("380x210")

    tk.Label(root, text="▶ CS2 Highlights", bg=BG, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
    status = tk.Label(root, text="", bg=BG, fg=TEXT, font=("Segoe UI", 10), justify="left", wraplength=350, anchor="w")
    status.pack(fill="x", padx=16)
    hint = tk.Label(root, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9), justify="left", wraplength=350, anchor="w")
    hint.pack(fill="x", padx=16, pady=(4, 10))

    row = tk.Frame(root, bg=BG)
    row.pack(fill="x", padx=16, pady=(0, 14), side="bottom")

    def button(text, cmd, accent=False):
        b = tk.Button(row, text=text, command=cmd, relief="flat", padx=10, pady=5, cursor="hand2",
                      bg=ACCENT if accent else PANEL, fg="white" if accent else TEXT,
                      activebackground="#3b4250", activeforeground=TEXT, font=("Segoe UI", 9))
        b.pack(side="left", padx=(0, 8))
        return b

    button("Открыть сайт", lambda: webbrowser.open(url), accent=True)
    button("Папка с клипами", lambda: (os.makedirs(config.LIBRARY, exist_ok=True), os.startfile(config.LIBRARY)))

    def quit_app():
        if job["running"] and not messagebox.askyesno(
                "CS2 Highlights", "Сейчас идёт запись. Остановить её и выключить программу?\n"
                                  "Готовые клипы сохранятся, CS2 закроется, графика вернётся."):
            return
        status.config(text="Выключаюсь…")
        root.update()
        shutdown()

    button("Выключить", quit_app)
    root.protocol("WM_DELETE_WINDOW", quit_app)

    def refresh():
        s = setup.STATE
        if job["running"]:
            status.config(text=f"● Идёт запись: {job['done']} из {job['total'] or '…'} отрезков", fg=ACCENT)
            hint.config(text="CS2 работает в фоне без окна и звука. Не запускай CS2 и не закрывай Steam.")
        elif s["running"]:
            status.config(text=f"Устанавливаю инструменты… {int(s['progress'] * 100)}%", fg=TEXT)
            hint.config(text=s["step"])
        else:
            status.config(text="Работает. Управление — на сайте.", fg=TEXT)
            hint.config(text="Выключится сама через 2 минуты после того, как закроешь сайт, "
                             "или нажми «Выключить».")
        root.after(1000, refresh)

    refresh()
    root.mainloop()
