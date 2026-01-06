# app/main.py
from app_core import LogisticsApp
import tkinter as tk

if __name__ == "__main__":
    root = tk.Tk()
    app = LogisticsApp(root)
    root.mainloop()