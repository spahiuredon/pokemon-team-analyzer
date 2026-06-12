"""'3DS Sync'-Tab: Spielstände zwischen 3DS und PC-Emulator abgleichen.

Bewusst als geführter 3-Schritte-Ablauf aufgebaut:

    1. Mit dem 3DS verbinden (ftpd starten, IP eintragen)
    2. Spiel wählen und einmalig einrichten
    3. Synchronisieren - der neueste Stand gewinnt

FTP-Arbeit läuft in einem Worker-Thread; Ergebnisse wandern über eine
``queue.Queue`` zurück in den Tk-Main-Thread (``root.after``-Polling).
"""

from __future__ import annotations

import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .save_sync import (
    GAMES,
    GAMES_BY_KEY,
    FTPError,
    SyncConfig,
    ThreeDSFTP,
    find_azahar_save,
    sync_game,
)

# Textfarbe für Buttons mit transparentem Hintergrund (Theme-Default
# wäre im Light Mode unsichtbar - weiss auf weiss).
TEXT_ON_TRANSPARENT = ("gray10", "#DCE4EE")

HELP_TEXT = """\
So funktioniert der Sync - einmal lesen, danach ist es ein Klick:

WAS DU AUF DEM 3DS BRAUCHST (einmalig installieren, CFW vorausgesetzt):
• ftpd - macht den 3DS über WLAN für diese App erreichbar.
• Für DS-Spiele (Platin bis Weiss 2): TWiLight Menu++. Der Spielstand
  ist eine normale .sav-Datei auf der SD-Karte - melonDS am PC nutzt
  exakt dasselbe Format, es wird einfach die Datei abgeglichen.
• Für 3DS-Spiele (X/Y bis Ultra Mond): Checkpoint. 3DS-Spielstände
  liegen verschlüsselt in der Konsole - Checkpoint exportiert sie als
  normale Dateien auf die SD-Karte. Diese App gleicht dann das
  Checkpoint-Backup mit dem Azahar-Emulator am PC ab.

DER ABLAUF BEIM SPIELEN:
• 3DS -> PC: auf dem 3DS speichern (bei 3DS-Spielen zusätzlich kurz in
  Checkpoint ein Backup machen), dann hier "Synchronisieren".
• PC -> 3DS: im Emulator speichern, hier "Synchronisieren". Bei
  3DS-Spielen danach auf dem 3DS in Checkpoint das neue
  "PCSYNC_..."-Backup wiederherstellen - fertig.

SICHERHEIT:
• Es gewinnt immer der neuere Spielstand. Was überschrieben wird,
  sichert die App vorher automatisch (Ordner: ~/.pokemon_team_analyzer/
  backups). Es geht also nie etwas verloren.
• Tipp Cloud: Unter "Erweitert" kannst du deinen Google-Drive-/Dropbox-
  Ordner angeben - dann bleiben auch mehrere PCs untereinander synchron.
"""


class SyncTab:
    """Baut und verwaltet den Sync-Tab (geführter 3-Schritte-Ablauf)."""

    def __init__(self, root: ctk.CTk, parent) -> None:
        self.root = root
        self.config = SyncConfig.load()
        self._queue: queue.Queue = queue.Queue()
        self._busy = False
        self._help_visible = False
        self._advanced_visible = False
        self._connected = False

        self.frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)
        self.frame.grid_columnconfigure(0, weight=1)

        self._build()
        self._refresh_game_status()

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        row = 0

        # --- Hilfe --- #
        help_header = ctk.CTkFrame(self.frame, fg_color="transparent")
        help_header.grid(row=row, column=0, sticky="ew", pady=(4, 2))
        row += 1
        self.help_button = ctk.CTkButton(
            help_header, text="❓  Wie funktioniert der Sync?",
            fg_color="transparent", border_width=1, anchor="w",
            text_color=TEXT_ON_TRANSPARENT,
            command=self._toggle_help)
        self.help_button.pack(fill="x")

        self.help_box = ctk.CTkTextbox(self.frame, height=300,
                                       font=ctk.CTkFont(size=12), wrap="word")
        self.help_box.insert("1.0", HELP_TEXT)
        self.help_box.configure(state="disabled")
        self.help_row = row
        row += 1  # Platzhalter-Zeile, ein-/ausgeblendet in _toggle_help

        # --- Schritt 1: Verbindung --- #
        step1 = self._step_card("Schritt 1 - Mit dem 3DS verbinden")
        step1.grid(row=row, column=0, sticky="ew", pady=4)
        row += 1
        ctk.CTkLabel(
            step1, text="Auf dem 3DS die App 'ftpd' starten - die IP-Adresse "
                        "steht dort oben am Bildschirm.",
            font=ctk.CTkFont(size=12), text_color=("gray30", "gray70"),
            anchor="w", justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=12)

        self.host_var = tk.StringVar(value=self.config.ftp_host)
        self.port_var = tk.StringVar(value=str(self.config.ftp_port))
        ctk.CTkEntry(step1, textvariable=self.host_var, width=160,
                     placeholder_text="z.B. 192.168.1.42").grid(
            row=2, column=0, padx=(12, 4), pady=10, sticky="w")
        ctk.CTkEntry(step1, textvariable=self.port_var, width=70).grid(
            row=2, column=1, padx=4, pady=10, sticky="w")
        ctk.CTkButton(step1, text="Verbinden", width=110,
                      command=self._test_connection).grid(
            row=2, column=2, padx=4, pady=10, sticky="w")
        self.conn_status = ctk.CTkLabel(step1, text="●  nicht verbunden",
                                        text_color=("gray40", "gray60"))
        self.conn_status.grid(row=2, column=3, padx=8, sticky="w")

        # --- Schritt 2: Spiel --- #
        step2 = self._step_card("Schritt 2 - Spiel wählen")
        step2.grid(row=row, column=0, sticky="ew", pady=4)
        row += 1
        titles = [g.title for g in GAMES]
        self.game_var = tk.StringVar(value=titles[0])
        ctk.CTkOptionMenu(step2, variable=self.game_var, values=titles,
                          width=260,
                          command=lambda _v: self._refresh_game_status()).grid(
            row=1, column=0, padx=12, pady=(4, 2), sticky="w")
        ctk.CTkButton(step2, text="Einrichten...", width=110,
                      fg_color="transparent", border_width=1,
                      text_color=TEXT_ON_TRANSPARENT,
                      command=self._setup_game).grid(
            row=1, column=1, padx=4, pady=(4, 2), sticky="w")
        self.game_status = ctk.CTkLabel(step2, text="", anchor="w",
                                        justify="left",
                                        font=ctk.CTkFont(size=12),
                                        text_color=("gray30", "gray70"))
        self.game_status.grid(row=2, column=0, columnspan=2, sticky="w",
                              padx=12, pady=(0, 10))

        # --- Schritt 3: Sync --- #
        step3 = self._step_card("Schritt 3 - Synchronisieren")
        step3.grid(row=row, column=0, sticky="ew", pady=4)
        row += 1
        self.sync_button = ctk.CTkButton(
            step3, text="⟳   Jetzt synchronisieren",
            height=44, font=ctk.CTkFont(size=15, weight="bold"),
            command=lambda: self._run_sync(None))
        self.sync_button.grid(row=1, column=0, columnspan=2, sticky="ew",
                              padx=12, pady=(6, 4))
        ctk.CTkLabel(
            step3, text="Der neuere Spielstand gewinnt - die andere Seite "
                        "wird vorher automatisch gesichert.",
            font=ctk.CTkFont(size=11), text_color=("gray40", "gray60"),
        ).grid(row=2, column=0, columnspan=2, padx=12, sticky="w")

        ctk.CTkLabel(step3, text="Richtung erzwingen:",
                     font=ctk.CTkFont(size=12)).grid(
            row=3, column=0, padx=12, pady=(8, 10), sticky="w")
        direction = ctk.CTkFrame(step3, fg_color="transparent")
        direction.grid(row=3, column=1, sticky="w", pady=(8, 10))
        ctk.CTkButton(direction, text="Nur 3DS → PC", width=120,
                      fg_color="transparent", border_width=1,
                      text_color=TEXT_ON_TRANSPARENT,
                      command=lambda: self._run_sync("3DS")).pack(
            side="left", padx=2)
        ctk.CTkButton(direction, text="Nur PC → 3DS", width=120,
                      fg_color="transparent", border_width=1,
                      text_color=TEXT_ON_TRANSPARENT,
                      command=lambda: self._run_sync("PC")).pack(
            side="left", padx=2)

        # --- Erweitert (Cloud, ohne 3DS) --- #
        self.advanced_button = ctk.CTkButton(
            self.frame, text="▸  Erweitert (Cloud-Ordner, Sync ohne 3DS)",
            fg_color="transparent", border_width=1, anchor="w",
            text_color=TEXT_ON_TRANSPARENT,
            command=self._toggle_advanced)
        self.advanced_button.grid(row=row, column=0, sticky="ew", pady=(8, 2))
        row += 1

        self.advanced_box = ctk.CTkFrame(self.frame, corner_radius=10)
        self.advanced_row = row
        row += 1
        self.advanced_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.advanced_box,
            text="Cloud-Ordner: wähle deinen lokalen Google-Drive-/Dropbox-"
                 "Ordner. Die App legt darin 'pokemon_saves' an und nimmt "
                 "ihn als dritte Quelle in den Sync auf - so bleiben mehrere "
                 "PCs synchron.",
            font=ctk.CTkFont(size=12), text_color=("gray30", "gray70"),
            wraplength=560, justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 4))
        self.cloud_var = tk.StringVar(value=self.config.cloud_dir)
        ctk.CTkEntry(self.advanced_box, textvariable=self.cloud_var,
                     placeholder_text="(kein Cloud-Ordner)").grid(
            row=1, column=0, sticky="ew", padx=(12, 4), pady=4)
        ctk.CTkButton(self.advanced_box, text="Wählen...", width=90,
                      command=self._pick_cloud_dir).grid(
            row=1, column=1, padx=(0, 12), pady=4)
        self.no_ftp_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            self.advanced_box, variable=self.no_ftp_var,
            text="Ohne 3DS syncen (nur PC ↔ Cloud-Ordner)").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 10))

        # --- Protokoll --- #
        ctk.CTkLabel(self.frame, text="Protokoll",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     anchor="w").grid(row=row, column=0, sticky="w",
                                      pady=(8, 2))
        row += 1
        self.log_box = ctk.CTkTextbox(self.frame, height=120,
                                      font=ctk.CTkFont(family="Courier",
                                                       size=11))
        self.log_box.configure(state="disabled")
        self.log_box.grid(row=row, column=0, sticky="ew", pady=(0, 8))

    def _step_card(self, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self.frame, corner_radius=10)
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(card, text=title,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").grid(row=0, column=0, columnspan=4,
                                      sticky="w", padx=12, pady=(10, 2))
        return card

    # ------------------------------------------------------------------ #
    # Ein-/Ausklappen
    # ------------------------------------------------------------------ #
    def _toggle_help(self) -> None:
        self._help_visible = not self._help_visible
        if self._help_visible:
            self.help_box.grid(row=self.help_row, column=0, sticky="ew",
                               pady=(0, 6))
            self.help_button.configure(text="▾  Erklärung ausblenden")
        else:
            self.help_box.grid_forget()
            self.help_button.configure(text="❓  Wie funktioniert der Sync?")

    def _toggle_advanced(self) -> None:
        self._advanced_visible = not self._advanced_visible
        if self._advanced_visible:
            self.advanced_box.grid(row=self.advanced_row, column=0,
                                   sticky="ew", pady=(0, 4))
            self.advanced_button.configure(
                text="▾  Erweitert (Cloud-Ordner, Sync ohne 3DS)")
        else:
            self.advanced_box.grid_forget()
            self.advanced_button.configure(
                text="▸  Erweitert (Cloud-Ordner, Sync ohne 3DS)")

    # ------------------------------------------------------------------ #
    # Hilfen
    # ------------------------------------------------------------------ #
    def _log(self, msg: str) -> None:
        """Thread-sicher: aus Worker-Threads läuft das über die Queue."""
        self._queue.put(("log", msg))

    def _log_direct(self, msg: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

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

    def _current_game(self):
        title = self.game_var.get()
        for g in GAMES:
            if g.title == title:
                return g
        return GAMES[0]

    def _refresh_game_status(self) -> None:
        game = self._current_game()
        cfg = self.config.games.get(game.key)
        parts: list[str] = []
        # PC-Seite
        if cfg and cfg.local_path:
            parts.append("PC-Save: eingerichtet ✓")
        elif game.platform == "3ds" and find_azahar_save(game):
            parts.append("PC-Save: Azahar automatisch gefunden ✓")
        else:
            parts.append("PC-Save: noch nicht eingerichtet - 'Einrichten...'")
        # 3DS-Seite
        if cfg and cfg.remote_path:
            parts.append("3DS-Pfad: eingerichtet ✓")
        elif game.platform == "3ds":
            parts.append("3DS-Pfad: wird automatisch im Checkpoint-Ordner "
                         "gesucht (vorher dort 1x Backup anlegen)")
        else:
            parts.append("3DS-Pfad: .sav-Datei wählen - 'Einrichten...'")
        self.game_status.configure(text="\n".join(parts))

    def _pick_cloud_dir(self) -> None:
        path = filedialog.askdirectory(title="Cloud-Ordner wählen")
        if path:
            self.cloud_var.set(path)

    # ------------------------------------------------------------------ #
    # Schritt 1: Verbindung testen
    # ------------------------------------------------------------------ #
    def _test_connection(self) -> None:
        if not self._save_connection_config():
            return
        if not self.config.ftp_host:
            messagebox.showinfo("Hinweis", "Bitte zuerst die 3DS-IP eintragen.")
            return
        self.conn_status.configure(text="●  verbinde ...",
                                   text_color=("#b45309", "#fbbf24"))

        def worker() -> None:
            try:
                with ThreeDSFTP(self.config.ftp_host, self.config.ftp_port,
                                self.config.ftp_user, self.config.ftp_password):
                    self._queue.put(("conn_ok",))
            except FTPError as exc:
                self._queue.put(("conn_fail", str(exc)))

        self._start_worker(worker)

    # ------------------------------------------------------------------ #
    # Schritt 2: Spiel einrichten
    # ------------------------------------------------------------------ #
    def _setup_game(self) -> None:
        game = self._current_game()
        game_cfg = self.config.game(game.key)

        win = ctk.CTkToplevel(self.root)
        win.title(f"Einrichten: {game.title}")
        win.geometry("640x320")
        win.transient(self.root)
        win.grab_set()
        win.grid_columnconfigure(0, weight=1)

        if game.platform == "nds":
            local_hint = ("Save-Datei am PC: die .sav von melonDS "
                          "(liegt standardmässig neben dem ROM).")
            remote_hint = ("Save-Datei auf dem 3DS: die .sav auf der "
                           "SD-Karte (TWiLight Menu++, z.B. "
                           "/roms/nds/saves/Spiel.sav).")
        else:
            local_hint = ("Save am PC: die 'main'-Datei von Azahar. 'Auto' "
                          "findet sie selbst, sobald du das Spiel im "
                          "Emulator einmal gestartet und gespeichert hast.")
            remote_hint = ("Save auf dem 3DS: wird automatisch im "
                           "Checkpoint-Ordner gefunden - dafür auf dem 3DS "
                           "in Checkpoint einmal ein Backup anlegen. Nur "
                           "anpassen, wenn die Auto-Suche nichts findet.")

        ctk.CTkLabel(win, text=local_hint, wraplength=600,
                     justify="left").grid(row=0, column=0, columnspan=3,
                                          sticky="w", padx=14, pady=(14, 2))
        local_var = tk.StringVar(value=game_cfg.local_path)
        ctk.CTkEntry(win, textvariable=local_var).grid(
            row=1, column=0, sticky="ew", padx=(14, 4))
        ctk.CTkButton(win, text="Datei...", width=80,
                      command=lambda: self._pick_file(local_var)).grid(
            row=1, column=1, padx=2)
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
            ctk.CTkButton(win, text="Auto", width=60,
                          command=auto_local).grid(row=1, column=2,
                                                   padx=(2, 14))

        ctk.CTkLabel(win, text=remote_hint, wraplength=600,
                     justify="left").grid(row=2, column=0, columnspan=3,
                                          sticky="w", padx=14, pady=(16, 2))
        remote_var = tk.StringVar(value=game_cfg.remote_path)
        ctk.CTkEntry(win, textvariable=remote_var,
                     placeholder_text="(automatisch)" if game.platform == "3ds"
                     else "").grid(row=3, column=0, sticky="ew", padx=(14, 4))
        ctk.CTkButton(win, text="3DS durchsuchen...", width=140,
                      command=lambda: self._browse_remote(remote_var, win)).grid(
            row=3, column=1, columnspan=2, padx=(2, 14), sticky="w")

        def save_and_close() -> None:
            game_cfg.local_path = local_var.get().strip()
            game_cfg.remote_path = remote_var.get().strip()
            self.config.save()
            self._refresh_game_status()
            win.destroy()

        ctk.CTkButton(win, text="Speichern", width=140,
                      command=save_and_close).grid(
            row=4, column=0, columnspan=3, pady=20)

    def _pick_file(self, var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(title="Save-Datei wählen")
        if path:
            var.set(path)

    def _browse_remote(self, var: tk.StringVar, parent) -> None:
        """Einfacher Datei-Browser für die 3DS-SD-Karte (über FTP)."""
        if not self._save_connection_config() or not self.config.ftp_host:
            messagebox.showinfo("Hinweis", "Bitte zuerst die 3DS-IP eintragen "
                                           "(Schritt 1).", parent=parent)
            return
        try:
            ftp = ThreeDSFTP(self.config.ftp_host, self.config.ftp_port,
                             self.config.ftp_user, self.config.ftp_password)
            ftp.connect()
        except FTPError as exc:
            messagebox.showerror("Fehler", str(exc), parent=parent)
            return

        win = ctk.CTkToplevel(parent)
        win.title("3DS-SD-Karte durchsuchen")
        win.geometry("500x440")
        win.transient(parent)
        win.grab_set()

        path_var = tk.StringVar(value="/")
        ctk.CTkLabel(win, textvariable=path_var).pack(anchor="w",
                                                      padx=10, pady=4)
        listbox = tk.Listbox(win, font=("Courier", 12), borderwidth=0,
                             highlightthickness=0)
        listbox.pack(fill="both", expand=True, padx=10)

        entries: list[tuple[str, bool]] = []

        def load(path: str) -> None:
            nonlocal entries
            try:
                entries = ftp.list_dir(path)
            except FTPError as exc:
                messagebox.showerror("Fehler", str(exc), parent=win)
                return
            path_var.set(path)
            listbox.delete(0, "end")
            if path != "/":
                listbox.insert("end", "[..]")
            for name, is_dir in entries:
                listbox.insert("end", f"[{name}]" if is_dir else name)

        def on_open(_e=None) -> None:
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            current = path_var.get()
            offset = 0
            if current != "/":
                if idx == 0:  # [..]
                    load(current.rsplit("/", 1)[0] or "/")
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
        ctk.CTkLabel(win, text="Doppelklick: Ordner öffnen / Datei wählen",
                     font=ctk.CTkFont(size=11),
                     text_color=("gray40", "gray60")).pack(anchor="w",
                                                           padx=10, pady=4)
        win.protocol("WM_DELETE_WINDOW",
                     lambda: (ftp.close(), win.destroy()))
        load("/")

    # ------------------------------------------------------------------ #
    # Schritt 3: Sync ausführen
    # ------------------------------------------------------------------ #
    def _run_sync(self, force_winner: str | None) -> None:
        if self._busy:
            messagebox.showinfo("Hinweis", "Es läuft bereits ein Sync.")
            return
        if not self._save_connection_config():
            return
        use_ftp = not self.no_ftp_var.get()
        if use_ftp and not self.config.ftp_host:
            messagebox.showinfo(
                "Hinweis",
                "Bitte in Schritt 1 die 3DS-IP eintragen - oder unter "
                "'Erweitert' den Sync ohne 3DS aktivieren.")
            return
        game = self._current_game()
        self._log_direct(f"--- Sync: {game.title} ---")
        self.sync_button.configure(state="disabled", text="Synchronisiere ...")

        def worker() -> None:
            try:
                result = sync_game(game.key, self.config, use_ftp=use_ftp,
                                   force_winner=force_winner, log=self._log)
                self.config.save()  # auto-erkannte Pfade merken
                self._queue.put(("result", game.key, result))
            except (FTPError, ValueError) as exc:
                self._queue.put(("error", str(exc)))
            except Exception as exc:  # pragma: no cover - GUI-Pfad
                self._queue.put(("error", f"Unerwarteter Fehler: {exc}"))

        self._start_worker(worker)

    # ------------------------------------------------------------------ #
    # Worker/Queue-Infrastruktur
    # ------------------------------------------------------------------ #
    def _start_worker(self, target) -> None:
        self._busy = True
        threading.Thread(target=target, daemon=True).start()
        self.root.after(100, self._poll_queue)

    def _reset_sync_button(self) -> None:
        self.sync_button.configure(state="normal",
                                   text="⟳   Jetzt synchronisieren")

    def _poll_queue(self) -> None:
        try:
            while True:
                msg = self._queue.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log_direct(msg[1])
                elif kind == "conn_ok":
                    self._busy = False
                    self._connected = True
                    self.conn_status.configure(
                        text="●  verbunden ✓",
                        text_color=("#15803d", "#4ade80"))
                    self._log_direct("Verbindung zum 3DS steht.")
                    return
                elif kind == "conn_fail":
                    self._busy = False
                    self._connected = False
                    self.conn_status.configure(
                        text="●  keine Verbindung",
                        text_color=("#b91c1c", "#f87171"))
                    self._log_direct(f"FEHLER: {msg[1]}")
                    messagebox.showerror("3DS Sync", msg[1])
                    return
                elif kind == "error":
                    self._busy = False
                    self._reset_sync_button()
                    self._log_direct(f"FEHLER: {msg[1]}")
                    messagebox.showerror("3DS Sync", msg[1])
                    return
                elif kind == "result":
                    self._busy = False
                    self._reset_sync_button()
                    self._show_result(msg[1], msg[2])
                    return
        except queue.Empty:
            pass
        if self._busy:
            self.root.after(100, self._poll_queue)

    def _show_result(self, key: str, result) -> None:
        stamp = time.strftime("%H:%M:%S")
        for m in result.messages:
            self._log_direct(m)
        if result.skipped:
            self._log_direct(f"[{stamp}] Nichts zu tun - alles aktuell.")
        else:
            self._log_direct(
                f"[{stamp}] Fertig. Neuester Stand: {result.winner}; "
                f"aktualisiert: {', '.join(result.updated) or 'nichts'}; "
                f"Backups: {', '.join(result.backed_up) or 'keine'}.")
        game = GAMES_BY_KEY[key]
        if (not result.skipped and game.platform == "3ds"
                and "3DS" in result.updated):
            self._log_direct(
                "WICHTIG: Auf dem 3DS jetzt Checkpoint öffnen und das neue "
                "'PCSYNC_...'-Backup wiederherstellen.")
            messagebox.showinfo(
                "Fast fertig",
                "Der Spielstand liegt jetzt auf dem 3DS.\n\n"
                "Letzter Schritt: auf dem 3DS Checkpoint öffnen, das Spiel "
                "wählen und das Backup 'PCSYNC_...' wiederherstellen.")
        self._refresh_game_status()
