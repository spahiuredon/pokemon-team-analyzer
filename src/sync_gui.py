"""GUI-Tab für die 3DS<->PC Save-Synchronisation.

Wird von ``src.gui`` als zusätzlicher Tab in das Haupt-Notebook gehängt.
Folgt demselben Threading-Muster wie der Bulk-Download im Haupt-GUI:
FTP-Arbeit läuft in einem Worker-Thread, Ergebnisse wandern über eine
``queue.Queue`` zurück in den Tk-Main-Thread (``root.after``-Polling).
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .save_sync import (
    GAMES,
    GAMES_BY_KEY,
    FTPError,
    SyncConfig,
    ThreeDSFTP,
    find_azahar_save,
    sync_game,
)


class SyncTab:
    """Baut und verwaltet den '3DS Sync'-Tab."""

    def __init__(self, root: tk.Tk, parent: ttk.Frame) -> None:
        self.root = root
        self.frame = parent
        self.config = SyncConfig.load()
        self._queue: queue.Queue = queue.Queue()
        self._busy = False
        self._build()
        self._refresh_games()

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        # --- Verbindung --- #
        conn = ttk.LabelFrame(self.frame, text="3DS-Verbindung (ftpd)", padding=8)
        conn.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Label(conn, text="IP-Adresse:").grid(row=0, column=0, sticky=tk.W)
        self.host_var = tk.StringVar(value=self.config.ftp_host)
        ttk.Entry(conn, textvariable=self.host_var, width=16).grid(
            row=0, column=1, padx=4)
        ttk.Label(conn, text="Port:").grid(row=0, column=2, sticky=tk.W)
        self.port_var = tk.StringVar(value=str(self.config.ftp_port))
        ttk.Entry(conn, textvariable=self.port_var, width=6).grid(
            row=0, column=3, padx=4)
        ttk.Button(conn, text="Verbindung testen",
                   command=self._test_connection).grid(row=0, column=4, padx=8)
        ttk.Label(
            conn, foreground="#666666",
            text="Auf dem 3DS ftpd starten - die IP steht oben am Bildschirm.",
        ).grid(row=1, column=0, columnspan=5, sticky=tk.W, pady=(4, 0))

        # --- Cloud-Ordner --- #
        cloud = ttk.LabelFrame(
            self.frame, text="Cloud-Ordner (optional, z.B. Google Drive)",
            padding=8)
        cloud.pack(fill=tk.X, padx=8, pady=4)
        self.cloud_var = tk.StringVar(value=self.config.cloud_dir)
        ttk.Entry(cloud, textvariable=self.cloud_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(cloud, text="Wählen...",
                   command=self._pick_cloud_dir).pack(side=tk.LEFT, padx=4)
        ttk.Label(
            self.frame, foreground="#666666", wraplength=600, justify=tk.LEFT,
            text=("Tipp: Wähle hier deinen lokalen Google-Drive-/Dropbox-"
                  "Ordner. Die App legt darin 'pokemon_saves' an - so bleiben "
                  "mehrere PCs über die Cloud synchron."),
        ).pack(fill=tk.X, padx=12)

        # --- Spiele-Liste --- #
        games_frame = ttk.LabelFrame(self.frame, text="Spiele", padding=8)
        games_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        cols = ("platform", "local", "remote", "status")
        self.tree = ttk.Treeview(games_frame, columns=cols,
                                 show="tree headings", height=9)
        self.tree.heading("#0", text="Spiel")
        self.tree.heading("platform", text="System")
        self.tree.heading("local", text="PC-Save")
        self.tree.heading("remote", text="3DS-Pfad")
        self.tree.heading("status", text="Letzter Sync")
        self.tree.column("#0", width=190, anchor=tk.W)
        self.tree.column("platform", width=60, anchor=tk.CENTER)
        self.tree.column("local", width=90, anchor=tk.CENTER)
        self.tree.column("remote", width=90, anchor=tk.CENTER)
        self.tree.column("status", width=180, anchor=tk.W)
        scroll = ttk.Scrollbar(games_frame, orient=tk.VERTICAL,
                               command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-Button-1>", lambda _e: self._setup_game())

        # --- Buttons --- #
        btns = ttk.Frame(self.frame)
        btns.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(btns, text="Einrichten...",
                   command=self._setup_game).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Sync (neuester gewinnt)",
                   command=lambda: self._run_sync(None)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Nur 3DS → PC",
                   command=lambda: self._run_sync("3DS")).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Nur PC → 3DS",
                   command=lambda: self._run_sync("PC")).pack(side=tk.LEFT, padx=2)
        self.no_ftp_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(btns, text="Ohne 3DS (nur PC ↔ Cloud)",
                        variable=self.no_ftp_var).pack(side=tk.LEFT, padx=8)

        # --- Log --- #
        log_frame = ttk.LabelFrame(self.frame, text="Protokoll", padding=4)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=(4, 8))
        self.log_widget = tk.Text(log_frame, height=7, state=tk.DISABLED,
                                  font=("Courier", 10))
        self.log_widget.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------ #
    # Hilfen
    # ------------------------------------------------------------------ #
    def _log(self, msg: str) -> None:
        """Thread-sicher: aus Worker-Threads wird über die Queue geloggt."""
        self._queue.put(("log", msg))

    def _log_direct(self, msg: str) -> None:
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, msg + "\n")
        self.log_widget.see(tk.END)
        self.log_widget.configure(state=tk.DISABLED)

    def _save_connection_config(self) -> bool:
        self.config.ftp_host = self.host_var.get().strip()
        try:
            self.config.ftp_port = int(self.port_var.get().strip() or "5000")
        except ValueError:
            messagebox.showerror("Fehler", "Port muss eine Zahl sein.")
            return False
        self.config.cloud_dir = self.cloud_var.get().strip()
        self.config.save()
        return True

    def _refresh_games(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for game in GAMES:
            g = self.config.games.get(game.key)
            local_ok = "✓" if (g and g.local_path) or find_azahar_save(game) else "-"
            remote_ok = "✓" if (g and g.remote_path) else (
                "auto" if game.platform == "3ds" else "-")
            self.tree.insert(
                "", tk.END, iid=game.key, text=game.title,
                values=("3DS" if game.platform == "3ds" else "NDS",
                        local_ok, remote_ok, ""))

    def _selected_game_key(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Hinweis", "Bitte zuerst ein Spiel auswählen.")
            return None
        return sel[0]

    def _pick_cloud_dir(self) -> None:
        path = filedialog.askdirectory(title="Cloud-Ordner wählen")
        if path:
            self.cloud_var.set(path)

    # ------------------------------------------------------------------ #
    # Verbindungstest
    # ------------------------------------------------------------------ #
    def _test_connection(self) -> None:
        if not self._save_connection_config():
            return
        if not self.config.ftp_host:
            messagebox.showinfo("Hinweis", "Bitte zuerst die 3DS-IP eintragen.")
            return

        def worker() -> None:
            try:
                with ThreeDSFTP(self.config.ftp_host, self.config.ftp_port,
                                self.config.ftp_user, self.config.ftp_password):
                    self._queue.put(("info", "Verbindung zum 3DS steht!"))
            except FTPError as exc:
                self._queue.put(("error", str(exc)))

        self._start_worker(worker)

    # ------------------------------------------------------------------ #
    # Spiel einrichten (Pfade)
    # ------------------------------------------------------------------ #
    def _setup_game(self) -> None:
        key = self._selected_game_key()
        if key is None:
            return
        game = GAMES_BY_KEY[key]
        game_cfg = self.config.game(key)

        win = tk.Toplevel(self.root)
        win.title(f"Einrichten: {game.title}")
        win.geometry("620x260")
        win.transient(self.root)
        win.grab_set()

        if game.platform == "nds":
            local_hint = ("PC-Save: die .sav-Datei von melonDS "
                          "(liegt standardmässig neben dem ROM).")
            remote_hint = ("3DS-Pfad: die .sav-Datei auf der SD-Karte "
                           "(TWiLight Menu++, z.B. /roms/nds/saves/Spiel.sav).")
        else:
            local_hint = ("PC-Save: die 'main'-Datei von Azahar - wird "
                          "automatisch gesucht, sobald du das Spiel im "
                          "Emulator einmal gestartet hast.")
            remote_hint = ("3DS-Pfad: wird automatisch im Checkpoint-Ordner "
                           "gesucht. Voraussetzung: auf dem 3DS in Checkpoint "
                           "einmal ein Backup des Spiels anlegen.")

        ttk.Label(win, text=local_hint, wraplength=580,
                  justify=tk.LEFT).pack(anchor=tk.W, padx=10, pady=(10, 2))
        local_var = tk.StringVar(value=game_cfg.local_path)
        row1 = ttk.Frame(win)
        row1.pack(fill=tk.X, padx=10)
        ttk.Entry(row1, textvariable=local_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row1, text="Datei...", command=lambda: self._pick_file(
            local_var)).pack(side=tk.LEFT, padx=4)
        if game.platform == "3ds":
            def auto_local() -> None:
                found = find_azahar_save(game)
                if found:
                    local_var.set(str(found))
                else:
                    messagebox.showinfo(
                        "Nicht gefunden",
                        "Kein Azahar/Citra-Save gefunden. Spiel im Emulator "
                        "einmal starten und speichern, dann erneut suchen.",
                        parent=win)
            ttk.Button(row1, text="Auto", command=auto_local).pack(side=tk.LEFT)

        ttk.Label(win, text=remote_hint, wraplength=580,
                  justify=tk.LEFT).pack(anchor=tk.W, padx=10, pady=(12, 2))
        remote_var = tk.StringVar(value=game_cfg.remote_path)
        row2 = ttk.Frame(win)
        row2.pack(fill=tk.X, padx=10)
        ttk.Entry(row2, textvariable=remote_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row2, text="3DS durchsuchen...",
                   command=lambda: self._browse_remote(remote_var, win)).pack(
            side=tk.LEFT, padx=4)

        def save_and_close() -> None:
            game_cfg.local_path = local_var.get().strip()
            game_cfg.remote_path = remote_var.get().strip()
            self.config.save()
            self._refresh_games()
            win.destroy()

        ttk.Button(win, text="Speichern",
                   command=save_and_close).pack(pady=14)

    def _pick_file(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(title="Save-Datei wählen")
        if path:
            var.set(path)

    def _browse_remote(self, var: tk.StringVar, parent: tk.Toplevel) -> None:
        """Einfacher FTP-Datei-Browser für die 3DS-SD-Karte."""
        if not self._save_connection_config() or not self.config.ftp_host:
            messagebox.showinfo("Hinweis", "Bitte zuerst die 3DS-IP eintragen.",
                                parent=parent)
            return
        try:
            ftp = ThreeDSFTP(self.config.ftp_host, self.config.ftp_port,
                             self.config.ftp_user, self.config.ftp_password)
            ftp.connect()
        except FTPError as exc:
            messagebox.showerror("Fehler", str(exc), parent=parent)
            return

        win = tk.Toplevel(parent)
        win.title("3DS-SD-Karte durchsuchen")
        win.geometry("480x420")
        win.transient(parent)
        win.grab_set()

        path_var = tk.StringVar(value="/")
        ttk.Label(win, textvariable=path_var).pack(anchor=tk.W, padx=8, pady=4)
        listbox = tk.Listbox(win, font=("Courier", 11))
        listbox.pack(fill=tk.BOTH, expand=True, padx=8)

        entries: list[tuple[str, bool]] = []

        def load(path: str) -> None:
            nonlocal entries
            try:
                entries = ftp.list_dir(path)
            except FTPError as exc:
                messagebox.showerror("Fehler", str(exc), parent=win)
                return
            path_var.set(path)
            listbox.delete(0, tk.END)
            if path != "/":
                listbox.insert(tk.END, "[..]")
            for name, is_dir in entries:
                listbox.insert(tk.END, f"[{name}]" if is_dir else name)

        def on_open(_e=None) -> None:
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            current = path_var.get()
            offset = 0
            if current != "/":
                if idx == 0:  # [..]
                    parent_path = current.rsplit("/", 1)[0] or "/"
                    load(parent_path)
                    return
                offset = 1
            name, is_dir = entries[idx - offset]
            full = f"{current.rstrip('/')}/{name}"
            if is_dir:
                load(full)
            else:
                var.set(full)
                ftp.close()
                win.destroy()

        listbox.bind("<Double-Button-1>", on_open)
        ttk.Label(win, foreground="#666666",
                  text="Doppelklick: Ordner öffnen / Datei auswählen").pack(
            anchor=tk.W, padx=8, pady=4)
        win.protocol("WM_DELETE_WINDOW",
                     lambda: (ftp.close(), win.destroy()))
        load("/")

    # ------------------------------------------------------------------ #
    # Sync ausführen
    # ------------------------------------------------------------------ #
    def _run_sync(self, force_winner: str | None) -> None:
        key = self._selected_game_key()
        if key is None:
            return
        if self._busy:
            messagebox.showinfo("Hinweis", "Es läuft bereits ein Sync.")
            return
        if not self._save_connection_config():
            return
        use_ftp = not self.no_ftp_var.get()
        if use_ftp and not self.config.ftp_host:
            messagebox.showinfo(
                "Hinweis",
                "Bitte 3DS-IP eintragen - oder 'Ohne 3DS' anhaken, um nur "
                "PC und Cloud-Ordner zu synchronisieren.")
            return
        game = GAMES_BY_KEY[key]
        self._log_direct(f"--- Sync: {game.title} ---")

        def worker() -> None:
            try:
                result = sync_game(key, self.config, use_ftp=use_ftp,
                                   force_winner=force_winner, log=self._log)
                self.config.save()  # auto-erkannte Pfade persistieren
                self._queue.put(("result", key, result))
            except (FTPError, ValueError) as exc:
                self._queue.put(("error", str(exc)))
            except Exception as exc:  # pragma: no cover - GUI-Pfad
                self._queue.put(("error", f"Unerwarteter Fehler: {exc}"))

        self._start_worker(worker)

    # ------------------------------------------------------------------ #
    # Worker/Queue-Infrastruktur (Muster wie im Haupt-GUI)
    # ------------------------------------------------------------------ #
    def _start_worker(self, target) -> None:
        self._busy = True
        threading.Thread(target=target, daemon=True).start()
        self.root.after(100, self._poll_queue)

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log_direct(msg[1])
                elif kind == "info":
                    self._busy = False
                    self._log_direct(msg[1])
                    messagebox.showinfo("3DS Sync", msg[1])
                    return
                elif kind == "error":
                    self._busy = False
                    self._log_direct(f"FEHLER: {msg[1]}")
                    messagebox.showerror("3DS Sync", msg[1])
                    return
                elif kind == "result":
                    self._busy = False
                    _, key, result = msg
                    self._show_result(key, result)
                    return
        except queue.Empty:
            pass
        if self._busy:
            self.root.after(100, self._poll_queue)

    def _show_result(self, key: str, result) -> None:
        import time as _time
        stamp = _time.strftime("%H:%M:%S")
        if result.skipped:
            text = "aktuell" if not result.messages else result.messages[0]
        else:
            text = f"OK ({result.winner} → {', '.join(result.updated) or '-'})"
        try:
            self.tree.set(key, "status", f"{stamp} {text}")
        except tk.TclError:
            pass
        for m in result.messages:
            self._log_direct(m)
        if result.skipped:
            self._log_direct("Nichts zu tun - alles aktuell.")
        else:
            self._log_direct(
                f"Fertig. Neuester Stand: {result.winner}; aktualisiert: "
                f"{', '.join(result.updated) or 'nichts'}; Backups: "
                f"{', '.join(result.backed_up) or 'keine'}.")
        game = GAMES_BY_KEY[key]
        if not result.skipped and game.platform == "3ds" and "3DS" in result.updated:
            self._log_direct(
                "Hinweis: Auf dem 3DS jetzt Checkpoint öffnen und das neue "
                "'PCSYNC_...'-Backup wiederherstellen.")
        self._refresh_games()


def add_sync_tab(root: tk.Tk, notebook: ttk.Notebook) -> SyncTab:
    """Hängt den Sync-Tab an ein bestehendes Notebook an."""
    frame = ttk.Frame(notebook)
    notebook.add(frame, text="3DS Sync")
    return SyncTab(root, frame)
