from .gui import LogisticsApp
import tkinter as tk 

# === Запуск ===
if __name__ == "__main__":
    root = tk.Tk()
    app = LogisticsApp(root)
    root.mainloop()