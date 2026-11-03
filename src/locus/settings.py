"""Graphical settings window for Locus."""

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from locus.config import load_config, save_config


MODIFIER_MASKS = {
    "SHIFT": 0x01,
    "CTRL": 0x04,
    "ALT": 0x08,
    "SUPER": 0x40,
}

MODIFIER_KEYSYMS = {
    "Shift_L", "Shift_R",
    "Control_L", "Control_R",
    "Alt_L", "Alt_R",
    "Super_L", "Super_R",
}


def normalize_key(keysym: str) -> str:
    """Convert a Tk keysym into a Hyprland-compatible key name."""

    if len(keysym) == 1:
        return keysym.upper()

    if keysym == "space":
        return "SPACE"

    return keysym


def capture_keybind(event: Any) -> dict[str, Any] | None:
    """Convert a Tk keyboard event into a Locus keybind."""

    if event.keysym in MODIFIER_KEYSYMS:
        return None

    modifiers = [
        name
        for name, mask in MODIFIER_MASKS.items()
        if event.state & mask
    ]

    if not modifiers:
        return None

    key = normalize_key(event.keysym)

    if not key or key.upper() in MODIFIER_MASKS:
        return None

    return {
        "modifiers": modifiers,
        "key": key,
    }


class SettingsWindow:
    """Manage Locus keyboard shortcut settings."""

    def __init__(self, root: tk.Tk, config_path: Path):
        self.root = root
        self.config_path = config_path
        self.config = load_config(config_path)

        self.current_keybind = dict(self.config["keybind"])
        self.pending_keybind = dict(self.current_keybind)
        self.listening = False

        self.root.title("Locus Settings")
        self.root.geometry("440x300")
        self.root.resizable(False, False)

        self._build_ui()
        self._refresh_shortcut()

        self.root.bind("<KeyPress>", self._on_keypress)

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=20)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Locus Settings",
            font=("Sans", 17, "bold"),
        ).pack(anchor="w")

        ttk.Label(
            container,
            text="Keyboard Shortcut",
            font=("Sans", 11, "bold"),
        ).pack(anchor="w", pady=(22, 5))

        self.shortcut_label = ttk.Label(
            container,
            font=("Sans", 16),
            anchor="center",
        )
        self.shortcut_label.pack(fill="x", pady=8)

        self.status_label = ttk.Label(
            container,
            text="Shortcut used to launch Locus file search.",
            anchor="center",
        )
        self.status_label.pack(fill="x", pady=8)

        self.record_button = ttk.Button(
            container,
            text="Record Shortcut",
            command=self._start_recording,
        )
        self.record_button.pack(fill="x", pady=(12, 5))

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(18, 0))

        ttk.Button(
            actions,
            text="Cancel",
            command=self.root.destroy,
        ).pack(side="right")

        ttk.Button(
            actions,
            text="Save Shortcut",
            command=self._save,
        ).pack(side="right", padx=(0, 8))

    def _format_keybind(self, keybind: dict[str, Any]) -> str:
        parts = [
            modifier.title()
            for modifier in keybind["modifiers"]
        ]
        parts.append(keybind["key"])
        return " + ".join(parts)

    def _refresh_shortcut(self) -> None:
        self.shortcut_label.config(
            text=self._format_keybind(self.pending_keybind)
        )

    def _start_recording(self) -> None:
        self.listening = True
        self.record_button.config(state="disabled")
        self.status_label.config(
            text="Press a key combination. Escape cancels recording."
        )
        self.root.focus_force()

    def _stop_recording(self) -> None:
        self.listening = False
        self.record_button.config(state="normal")

    def _on_keypress(self, event: Any) -> None:
        if not self.listening:
            return

        if event.keysym == "Escape":
            self._stop_recording()
            self.status_label.config(text="Recording cancelled.")
            return

        keybind = capture_keybind(event)

        if keybind is None:
            return

        self.pending_keybind = keybind
        self._stop_recording()
        self._refresh_shortcut()

        self.status_label.config(
            text="Shortcut captured. Save to apply it."
        )

    def _save(self) -> None:
        if self.listening:
            self._stop_recording()

        updated_config = dict(self.config)
        updated_config["keybind"] = self.pending_keybind

        try:
            save_config(self.config_path, updated_config)
        except (OSError, ValueError, KeyError) as error:
            messagebox.showerror(
                "Unable to save shortcut",
                str(error),
                parent=self.root,
            )
            return

        messagebox.showinfo(
            "Shortcut saved",
            "The shortcut has been saved to your Locus configuration.\n\n"
            "Hyprland activation will be enabled after the Locus "
            "search launcher is implemented.",
            parent=self.root,
        )

        self.root.destroy()


def open_settings(config_path: Path) -> None:
    """Open the Locus settings window."""

    root = tk.Tk()
    SettingsWindow(root, config_path)
    root.mainloop()
