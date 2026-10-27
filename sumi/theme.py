import tkinter as tk
import customtkinter as ctk

# Sumi palette: paper, ink indigo and a vermilion seal accent.
COLORS={'shell':'#f6f2eb','panel':'#fffdf9','surface':'#ece6db','line':'#ddd5c7',
        'text':'#161b2e','muted':'#5c6275','accent':'#2e4a9e','accent_hover':'#253d85',
        'ink':'#ffffff','preview':'#0b1630','live':'#28765e','danger':'#b3261e','seal':'#d7322a'}

def apply_theme(root:tk.Tk) -> None:
    ctk.set_appearance_mode('light')
    if isinstance(root,ctk.CTk): root.configure(fg_color=COLORS['shell'])
    else: root.configure(background=COLORS['shell'])
