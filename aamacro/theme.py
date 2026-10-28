"""Colours and ttk styles shared by every window."""
import tkinter as tk
from tkinter import ttk

BG = "#1e1f24"
FIELD = "#2a2c33"
FG = "#e6e6e6"
MUTED = "#9aa0aa"
ACCENT = "#2f6fde"
OK = "#3ecf6e"
WARN = "#f0a43a"


def apply_style(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 9))
    style.configure("TButton", background="#2f323a", foreground=FG, borderwidth=0,
                    focusthickness=0, padding=(8, 5))
    style.map("TButton", background=[("disabled", "#26282e"), ("active", "#3b3f49")],
              foreground=[("disabled", "#5c6068")])
    style.configure("Accent.TButton", background=ACCENT)
    style.map("Accent.TButton", background=[("disabled", "#26282e"), ("active", "#3a7cf0")])
    style.configure("Danger.TButton", background="#6e2b2b")
    style.map("Danger.TButton", background=[("active", "#8a3434")])
    style.configure("Mode.TButton", background="#26282e", foreground=MUTED, padding=(6, 4))
    style.map("Mode.TButton", background=[("active", "#3b3f49")])
    style.configure("ModeOn.TButton", background=ACCENT, foreground=FG, padding=(6, 4))
    style.map("ModeOn.TButton", background=[("active", "#3a7cf0")])
    style.configure("TCheckbutton", background=BG, foreground=FG)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("Head.TLabel", font=("Segoe UI Semibold", 12))
    style.configure("Section.TLabel", foreground=MUTED, font=("Segoe UI Semibold", 8))
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("TEntry", fieldbackground=FIELD, foreground=FG, insertcolor=FG, borderwidth=0)
    style.configure("TCombobox", fieldbackground=FIELD, background="#2f323a", foreground=FG,
                    arrowcolor=FG, borderwidth=0)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", FG)],
              selectbackground=[("readonly", FIELD)], selectforeground=[("readonly", FG)])
    style.configure("TSeparator", background="#33363e")
    style.configure("Vertical.TScrollbar", background="#2f323a", troughcolor=BG, borderwidth=0,
                    arrowcolor=FG)
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", FG)


def listbox(parent, **options):
    return tk.Listbox(parent, bg=FIELD, fg=FG, selectbackground=ACCENT, selectforeground=FG,
                      highlightthickness=0, bd=0, activestyle="none", exportselection=False,
                      font=("Segoe UI", 9), **options)
