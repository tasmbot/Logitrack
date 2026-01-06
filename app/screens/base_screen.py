# app/screens/base_screen.py
import tkinter as tk

class BaseScreen:
    def __init__(self, root, app):
        self.root = root
        self.app = app
        self.create_widgets()

    def create_widgets(self):
        raise NotImplementedError