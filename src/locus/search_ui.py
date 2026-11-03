
"""Graphical file-search interface for Locus."""

import json
import queue
import subprocess
import threading
import tkinter as tk
import urllib.error
import urllib.request

from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any


API_BASE = "http://127.0.0.1:8765"
SEARCH_ENDPOINT = f"{API_BASE}/v1/search"
HEALTH_ENDPOINT = f"{API_BASE}/health"

SEARCH_LIMIT = 20
REQUEST_TIMEOUT = 15


class SearchWindow:
    """Interactive file-search window backed by the Locus API."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.result_queue: queue.Queue = queue.Queue()
        self.searching = False

        self.root.title("Locus Search")
        self.root.geometry("1000x600")
        self.root.minsize(650, 400)

        self._configure_theme()
        self._build_ui()

        self.root.bind("<Escape>", lambda event: self.root.destroy())
        self.root.bind("<Control-c>", self._copy_selected)
        self.root.bind("<Control-C>", self._copy_selected)

        self.root.after(100, self._process_queue)

        self.query_entry.focus_set()
        self._check_service()

    def _configure_theme(self) -> None:
        """Apply a near-black theme inspired by ChatGPT dark mode."""

        background = "#212121"
        surface = "#2f2f2f"
        foreground = "#ececec"
        muted = "#b4b4b4"
        border = "#424242"
        selected = "#444444"

        self.root.configure(bg=background)

        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(
            ".",
            background=background,
            foreground=foreground,
            font=("Sans", 10),
        )

        style.configure(
            "TFrame",
            background=background,
        )

        style.configure(
            "TLabel",
            background=background,
            foreground=foreground,
        )

        style.configure(
            "TButton",
            background=surface,
            foreground=foreground,
            padding=(12, 7),
            borderwidth=1,
            bordercolor=border,
            relief="flat",
        )

        style.map(
            "TButton",
            background=[
                ("active", selected),
                ("disabled", background),
            ],
            foreground=[
                ("disabled", muted),
            ],
        )

        style.configure(
            "TEntry",
            fieldbackground=surface,
            foreground=foreground,
            insertcolor=foreground,
            bordercolor=border,
            padding=10,
            relief="flat",
        )

        style.map(
            "TEntry",
            bordercolor=[("focus", muted)],
        )

        style.configure(
            "Treeview",
            background=surface,
            foreground=foreground,
            fieldbackground=surface,
            rowheight=30,
            borderwidth=0,
            relief="flat",
        )

        style.map(
            "Treeview",
            background=[("selected", selected)],
            foreground=[("selected", foreground)],
        )

        style.configure(
            "Treeview.Heading",
            background=background,
            foreground=muted,
            padding=9,
            relief="flat",
            font=("Sans", 10, "bold"),
        )

        style.map(
            "Treeview.Heading",
            background=[("active", selected)],
        )

        style.configure(
            "Vertical.TScrollbar",
            background=surface,
            troughcolor=background,
            borderwidth=0,
            arrowsize=12,
        )

        style.configure(
            "Horizontal.TScrollbar",
            background=surface,
            troughcolor=background,
            borderwidth=0,
            arrowsize=12,
        )

    def _build_ui(self) -> None:
        """Construct the search interface."""

        container = ttk.Frame(self.root, padding=14)
        container.pack(fill="both", expand=True)

        header = ttk.Frame(container)
        header.pack(fill="x", pady=(0, 14))

        ttk.Label(
            header,
            text="Locus Search",
            font=("Sans", 18, "bold"),
        ).pack(side="left")

        self.service_label = ttk.Label(
            header,
            text="Checking service...",
            foreground="#b4b4b4",
        )
        self.service_label.pack(side="right")

        search_frame = ttk.Frame(container)
        search_frame.pack(fill="x", pady=(0, 14))

        self.query_var = tk.StringVar()

        self.query_entry = ttk.Entry(
            search_frame,
            textvariable=self.query_var,
            font=("Sans", 12),
        )
        self.query_entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=5,
        )

        self.query_entry.bind(
            "<Return>",
            lambda event: self.search(),
        )

        self.search_button = ttk.Button(
            search_frame,
            text="Search",
            command=self.search,
        )
        self.search_button.pack(side="left", padx=(8, 0))

        results_frame = ttk.Frame(container)
        results_frame.pack(fill="both", expand=True)

        columns = (
            "name",
            "extension",
            "sources",
            "relevance",
        )

        self.results = ttk.Treeview(
            results_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        self.results.heading("name", text="File")
        self.results.heading("extension", text="Type")
        self.results.heading("sources", text="Matched By")
        self.results.heading("relevance", text="Relevance")

        self.results.column(
            "name",
            width=450,
            minwidth=180,
            anchor="w",
        )
        self.results.column(
            "extension",
            width=100,
            minwidth=70,
            anchor="center",
        )
        self.results.column(
            "sources",
            width=180,
            minwidth=100,
            anchor="center",
        )
        self.results.column(
            "relevance",
            width=120,
            minwidth=90,
            anchor="center",
        )

        vertical_scrollbar = ttk.Scrollbar(
            results_frame,
            orient="vertical",
            command=self.results.yview,
        )

        horizontal_scrollbar = ttk.Scrollbar(
            results_frame,
            orient="horizontal",
            command=self.results.xview,
        )

        self.results.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )

        self.results.grid(row=0, column=0, sticky="nsew")
        vertical_scrollbar.grid(row=0, column=1, sticky="ns")
        horizontal_scrollbar.grid(row=1, column=0, sticky="ew")

        results_frame.rowconfigure(0, weight=1)
        results_frame.columnconfigure(0, weight=1)

        self.results.bind(
            "<Double-1>",
            self._open_selected,
        )

        footer = ttk.Frame(container)
        footer.pack(fill="x", pady=(12, 0))

        self.status_label = ttk.Label(
            footer,
            text="Enter a search query.",
        )
        self.status_label.pack(side="left")

        ttk.Label(
            footer,
            text="Double-click: Open  |  Ctrl+C: Copy path  |  Esc: Close",
            foreground="#b4b4b4",
        ).pack(side="right")

    def _request(
        self,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send an HTTP request to the local Locus service."""

        data = None
        headers = {"Accept": "application/json"}

        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(
            url,
            data=data,
            headers=headers,
            method="POST" if payload is not None else "GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=REQUEST_TIMEOUT,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        if not isinstance(result, dict):
            raise ValueError("Invalid response from Locus service")

        return result

    def _check_service(self) -> None:
        """Check whether the local API is available."""

        def worker() -> None:
            try:
                response = self._request(HEALTH_ENDPOINT)
                self.result_queue.put(("health", response))
            except (
                OSError,
                ValueError,
                urllib.error.URLError,
            ) as error:
                self.result_queue.put(
                    ("health_error", str(error))
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def search(self) -> None:
        """Start a search without blocking the UI."""

        query = self.query_var.get().strip()

        if not query:
            self.status_label.config(
                text="Enter a search query."
            )
            return

        if self.searching:
            return

        self.searching = True
        self.search_button.config(state="disabled")
        self.status_label.config(text="Searching...")

        for item in self.results.get_children():
            self.results.delete(item)

        def worker() -> None:
            try:
                response = self._request(
                    SEARCH_ENDPOINT,
                    {
                        "query": query,
                        "limit": SEARCH_LIMIT,
                    },
                )

                self.result_queue.put(("search", response))

            except (
                OSError,
                ValueError,
                urllib.error.URLError,
            ) as error:
                self.result_queue.put(
                    ("search_error", str(error))
                )

        threading.Thread(
            target=worker,
            daemon=True,
        ).start()

    def _process_queue(self) -> None:
        """Process background results on the Tkinter main thread."""

        while True:
            try:
                event, payload = self.result_queue.get_nowait()
            except queue.Empty:
                break

            if event == "health":
                if payload.get("status") == "ok":
                    self.service_label.config(
                        text="Service: Running"
                    )
                else:
                    self.service_label.config(
                        text="Service: Unexpected response"
                    )

            elif event == "health_error":
                self.service_label.config(
                    text="Service: Unavailable"
                )

            elif event == "search":
                self.searching = False
                self.search_button.config(state="normal")
                self._display_results(payload)

            elif event == "search_error":
                self.searching = False
                self.search_button.config(state="normal")
                self.status_label.config(text="Search failed.")

                messagebox.showerror(
                    "Locus Search",
                    f"Unable to search:\n{payload}",
                    parent=self.root,
                )

        self.root.after(100, self._process_queue)

    def _display_results(
        self,
        response: dict[str, Any],
    ) -> None:
        """Display results with relative relevance percentages."""

        results = response.get("results", [])

        max_score = max(
            (
                result["rrf_score"]
                for result in results
            ),
            default=0.0,
        )

        for result in results:
            sources = ", ".join(
                result.get("sources", [])
            )

            extension = result.get("extension") or "(none)"

            relative_relevance = (
                result["rrf_score"] / max_score * 100
                if max_score > 0
                else 0.0
            )

            self.results.insert(
                "",
                "end",
                iid=result["path"],
                values=(
                    result["name"],
                    extension,
                    sources,
                    f"{relative_relevance:.1f}%",
                ),
            )

        count = response.get("count", len(results))

        if count == 0:
            self.status_label.config(
                text="No matching files found."
            )
        else:
            self.status_label.config(
                text=f"{count} matching files found."
            )

    def _selected_path(self) -> str | None:
        """Return the selected file path."""

        selected = self.results.selection()

        if not selected:
            return None

        return selected[0]

    def _open_selected(self, event: Any = None) -> None:
        """Open the selected file with its default application."""

        path = self._selected_path()

        if path is None:
            return

        file_path = Path(path)

        if not file_path.is_file():
            messagebox.showerror(
                "Locus Search",
                f"File no longer exists:\n{path}",
                parent=self.root,
            )
            return

        try:
            subprocess.Popen(
                ["xdg-open", str(file_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            messagebox.showerror(
                "Unable to open file",
                str(error),
                parent=self.root,
            )

    def _copy_selected(self, event: Any = None) -> str:
        """Copy the selected file path to the clipboard."""

        path = self._selected_path()

        if path is None:
            return "break"

        self.root.clipboard_clear()
        self.root.clipboard_append(path)

        self.status_label.config(
            text="File path copied."
        )

        return "break"


def open_search_window() -> None:
    """Open the Locus search interface."""

    root = tk.Tk()
    SearchWindow(root)
    root.mainloop()

