"""Einfaches Tkinter-GUI für den Pokemon Team-Analyzer.

Bietet eine grafische Oberfläche, in der man:
- Pokemon zum Team hinzufügt (Eingabefeld oder Auswahl aus Cache-Liste mit Bildchen)
- Pokemon wieder entfernt
- Die Stats-Tabelle (Pandas DataFrame) ansieht
- Die Typ-Coverage anzeigen lässt
- Drei Diagramme direkt im Fenster rendert (matplotlib eingebettet)

Sprites werden bevorzugt aus dem mitgelieferten Cache geladen
(typ-gefärbte Platzhalter), bei Bedarf vom Server der PokeAPI nachgezogen.

Tkinter ist Teil der Python-Standardbibliothek, also keine extra Installation.
Pillow (PIL) wird für Bildverarbeitung benötigt (steht in requirements.txt).

Aufruf:
    python -m src.gui
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:  # pragma: no cover - GUI braucht Pillow ohnehin
    HAS_PIL = False

from .analyzer import TeamAnalyzer
from .api_client import PokeAPIClient, PokeAPIError
from .pokemon import Pokemon
from .presets import available_presets, load_preset
from .team import Team
from .team_completer import GENERATION_RANGES, TeamCompleter


# Größe für Sprites in der Team-Übersicht und der Cache-Liste.
SPRITE_SIZE = 64


class PokemonTeamGUI:
    """Hauptfenster der Anwendung."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Pokemon Team-Analyzer")
        self.root.geometry("1200x780")

        # Cache-Ordner: derselbe wie für das Notebook (data/cache).
        project_root = Path(__file__).resolve().parent.parent
        self.client = PokeAPIClient(cache_dir=project_root / "data" / "cache",
                                    sprite_dir=project_root / "data" / "sprites")

        # App-Icon (Pokeball) für Fenster und Dock setzen.
        self._set_app_icon(project_root / "data" / "app_icon.png")
        self.team = Team("Mein Team")
        # Aktuell im rechten Bereich angezeigte matplotlib-Figur
        self._current_canvas: FigureCanvasTkAgg | None = None
        # Bilder dürfen NICHT vom Garbage Collector eingesammelt werden, sonst
        # zeigt Tk nur leere Felder. Referenzen werden in diesem Dict gehalten.
        self._photo_cache: dict[int, ImageTk.PhotoImage] = {}

        # ttk-Stil aufhübschen
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass  # Fallback auf Default

        self._build_layout()
        self._refresh_team_view()
        self._populate_cached_pokemon()

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _build_layout(self) -> None:
        # Linke Spalte: Team-Verwaltung
        left = ttk.Frame(self.root, padding=10)
        left.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left, text="Pokemon Team-Analyzer",
                  font=("Helvetica", 14, "bold")).pack(pady=(0, 10))

        # Eingabefeld
        ttk.Label(left, text="Pokemon-Name (oder ID):").pack(anchor=tk.W)
        self.name_var = tk.StringVar()
        entry = ttk.Entry(left, textvariable=self.name_var, width=30)
        entry.pack(fill=tk.X)
        entry.bind("<Return>", lambda _e: self._add_pokemon())

        ttk.Button(left, text="Zum Team hinzufügen",
                   command=self._add_pokemon).pack(fill=tk.X, pady=(4, 10))

        # Vorgefertigte Teams - Dropdown + Lade-Button
        ttk.Label(left, text="Vorgefertigtes Team:").pack(anchor=tk.W)
        self.preset_var = tk.StringVar()
        preset_combo = ttk.Combobox(left, textvariable=self.preset_var,
                                    values=available_presets(),
                                    state="readonly")
        preset_combo.pack(fill=tk.X)
        # Default: erstes Preset selektieren, damit der Button sofort etwas tut
        presets = available_presets()
        if presets:
            preset_combo.current(0)
        ttk.Button(left, text="Team laden (ersetzt aktuelles)",
                   command=self._load_preset).pack(fill=tk.X, pady=(4, 10))

        # Auto-Vervollständigung
        ttk.Label(left, text="Auto-Vervollständigung bis Gen:").pack(anchor=tk.W)
        # Werte: "Alle" + Gen-Nummern
        gen_values = ["Alle"] + [f"Gen {g}" for g in sorted(GENERATION_RANGES)]
        self.gen_var = tk.StringVar(value="Alle")
        gen_combo = ttk.Combobox(left, textvariable=self.gen_var,
                                 values=gen_values, state="readonly")
        gen_combo.pack(fill=tk.X)
        ttk.Button(left, text="Team auto-auffüllen",
                   command=self._auto_complete).pack(fill=tk.X, pady=(4, 4))
        ttk.Button(left, text="Alle Pokemon laden (PokeAPI)",
                   command=self._download_all_pokemon).pack(fill=tk.X, pady=(0, 10))

        # Cache-Liste mit Sprites: Treeview mit Bild + Name
        ttk.Label(left, text="Verfügbar (Doppelklick fügt hinzu):").pack(anchor=tk.W)
        # Suchfeld - filtert die Cache-Liste live nach Namen.
        self.cache_search_var = tk.StringVar()
        search_entry = ttk.Entry(left, textvariable=self.cache_search_var)
        search_entry.pack(fill=tk.X)
        # `trace_add("write", ...)` ruft die Filter-Funktion bei jedem Tastendruck.
        self.cache_search_var.trace_add("write", lambda *_: self._refresh_cache_view())
        # Hinweistext mit Trefferanzahl
        self.cache_info_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.cache_info_var,
                  foreground="#666666").pack(anchor=tk.W)
        cache_frame = ttk.Frame(left)
        cache_frame.pack(fill=tk.BOTH, expand=False)
        self.cache_tree = ttk.Treeview(cache_frame, columns=("types",),
                                       show="tree headings", height=8)
        self.cache_tree.heading("#0", text="Pokemon")
        self.cache_tree.heading("types", text="Typ(en)")
        self.cache_tree.column("#0", width=200, anchor=tk.W)
        self.cache_tree.column("types", width=120, anchor=tk.W)
        cache_scroll = ttk.Scrollbar(cache_frame, orient=tk.VERTICAL,
                                     command=self.cache_tree.yview)
        self.cache_tree.configure(yscrollcommand=cache_scroll.set)
        self.cache_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cache_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.cache_tree.bind("<Double-Button-1>", lambda _e: self._add_from_cache())

        ttk.Separator(left, orient="horizontal").pack(fill=tk.X, pady=10)

        # Aktionen
        ttk.Label(left, text="Analyse:").pack(anchor=tk.W)
        ttk.Button(left, text="Stats-Tabelle",
                   command=self._show_stats).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Typ-Coverage",
                   command=self._show_coverage).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Plot: Gesamt-Stats",
                   command=self._plot_totals).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Plot: Stats-Vergleich",
                   command=self._plot_stats).pack(fill=tk.X, pady=2)
        ttk.Button(left, text="Plot: Typ-Heatmap",
                   command=self._plot_heatmap).pack(fill=tk.X, pady=2)

        # Mitte: Team-Übersicht mit Sprites
        middle = ttk.LabelFrame(self.root, text="Aktuelles Team",
                                padding=10)
        middle.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 0), pady=10)
        self.team_inner = ttk.Frame(middle)
        self.team_inner.pack(fill=tk.BOTH, expand=True)
        # Buttons unter dem Team
        team_buttons = ttk.Frame(middle)
        team_buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(team_buttons, text="Ausgewähltes entfernen",
                   command=self._remove_selected).pack(side=tk.LEFT, padx=2)
        ttk.Button(team_buttons, text="Team leeren",
                   command=self._clear_team).pack(side=tk.LEFT, padx=2)

        # Aktuell selektiertes Team-Mitglied (über Klick gesetzt)
        self._selected_team_index: int | None = None

        # Rechte Spalte: Ausgabe
        right = ttk.Frame(self.root, padding=10)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.output_frame = right

        # Notebook-Widget für Tabs: "Tabelle" (Text) und "Plot" (Canvas)
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        self.text_tab = ttk.Frame(self.tabs)
        self.plot_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.text_tab, text="Tabelle / Text")
        self.tabs.add(self.plot_tab, text="Plot")

        self.text_widget = tk.Text(self.text_tab, font=("Courier", 10), wrap=tk.NONE)
        scroll_y = ttk.Scrollbar(self.text_tab, command=self.text_widget.yview)
        scroll_x = ttk.Scrollbar(self.text_tab, command=self.text_widget.xview,
                                 orient=tk.HORIZONTAL)
        self.text_widget.configure(yscrollcommand=scroll_y.set,
                                   xscrollcommand=scroll_x.set, state=tk.DISABLED)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.text_widget.pack(fill=tk.BOTH, expand=True)

        # Status-Zeile am unteren Rand
        self.status_var = tk.StringVar(value="Bereit.")
        ttk.Label(self.root, textvariable=self.status_var,
                  relief=tk.SUNKEN, anchor=tk.W).pack(side=tk.BOTTOM, fill=tk.X)

    # ------------------------------------------------------------------ #
    # App-Icon und Dock-Name
    # ------------------------------------------------------------------ #
    def _set_app_icon(self, icon_path: Path) -> None:
        """Setzt das Fenster-Icon (Pokeball) und versucht den Dock-Namen
        auf macOS auf den lesbaren Titel zu ändern.

        Fehler werden bewusst geschluckt, damit fehlende Bibliotheken
        oder ungewöhnliche Window-Manager das GUI nicht blockieren.
        """
        # 1) Fenster-Icon via Tk PhotoImage.
        if HAS_PIL and icon_path.exists():
            try:
                img = Image.open(icon_path).convert("RGBA")
                self._app_icon_photo = ImageTk.PhotoImage(img)
                # `True` heisst: gilt auch für neu geöffnete Toplevels.
                self.root.iconphoto(True, self._app_icon_photo)
            except (OSError, ValueError):
                pass

        # 2) macOS-Dock: Name auf "Pokemon Team-Analyzer" setzen.
        # Funktioniert nur, wenn `pyobjc` (Foundation) installiert ist.
        # Ohne pyobjc bleibt der Dock-Eintrag bei "python3.x" - das ist
        # Apple's Standardverhalten für Skripte ohne .app-Bundle.
        import sys as _sys
        if _sys.platform == "darwin":
            try:
                from Foundation import NSBundle  # type: ignore
                bundle = NSBundle.mainBundle()
                if bundle is not None:
                    info = (
                        bundle.localizedInfoDictionary()
                        or bundle.infoDictionary()
                    )
                    if info is not None:
                        info["CFBundleName"] = "Pokemon Team-Analyzer"
                        info["CFBundleDisplayName"] = "Pokemon Team-Analyzer"
            except ImportError:
                # pyobjc nicht installiert -> Dock-Name bleibt "python3.x".
                # Das Fenster-Icon und der Title-Bar zeigen aber den richtigen Namen.
                pass

    # ------------------------------------------------------------------ #
    # Sprite-Helfer
    # ------------------------------------------------------------------ #
    def _photo_for(
        self,
        pokemon: Pokemon,
        size: int = SPRITE_SIZE,
        allow_download: bool = True,
    ) -> tk.PhotoImage | None:
        """Liefert ein Tk-PhotoImage für ein Pokemon, oder None bei Fehler.

        Fertige Bilder werden im Dictionary gecached, damit
        1. das Resizen pro Pokemon nur einmal stattfindet und
        2. der Garbage Collector sie nicht einsammelt (Tk-Falle).

        Mit `allow_download=False` werden nur bereits lokal vorhandene
        Sprites genutzt - keine HTTP-Aufrufe. Das ist wichtig für die
        Cache-Liste, die viele Pokemon auf einmal rendert.
        """
        if not HAS_PIL:
            return None
        key = (pokemon.pokedex_id, size)
        if key in self._photo_cache:
            return self._photo_cache[key]

        sprite_path = self.client.get_sprite(
            pokemon.pokedex_id, pokemon.sprite_url,
            allow_download=allow_download,
        )
        if sprite_path is None:
            return None
        try:
            img = Image.open(sprite_path).convert("RGBA")
            img.thumbnail((size, size), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        except (OSError, ValueError) as exc:
            self._set_status(f"Sprite konnte nicht geladen werden: {exc}")
            return None
        self._photo_cache[key] = photo
        return photo

    # ------------------------------------------------------------------ #
    # Team-Aktionen
    # ------------------------------------------------------------------ #
    def _add_pokemon(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            return
        self._add_by_name(name)
        self.name_var.set("")

    def _add_from_cache(self) -> None:
        selection = self.cache_tree.selection()
        if not selection:
            return
        # Der Name wurde beim Einfügen als iid gesetzt.
        name = selection[0]
        self._add_by_name(name)

    def _add_by_name(self, name: str) -> None:
        try:
            data = self.client.get_pokemon(name)
            pokemon = Pokemon.from_api(data)
            self.team.add(pokemon)
        except (PokeAPIError, ValueError) as exc:
            # Fehler abfangen und freundlich anzeigen statt zu crashen.
            messagebox.showerror("Fehler", f"{exc}")
            self._set_status(f"Fehler: {exc}")
            return
        self._refresh_team_view()
        self._set_status(f"{pokemon.name.capitalize()} zum Team hinzugefügt.")

    def _remove_selected(self) -> None:
        if self._selected_team_index is None:
            messagebox.showinfo("Hinweis",
                                "Bitte zuerst ein Pokemon im Team anklicken.")
            return
        members = list(self.team.members)
        if self._selected_team_index >= len(members):
            return
        name = members[self._selected_team_index].name
        try:
            self.team.remove(name)
        except KeyError as exc:
            messagebox.showerror("Fehler", str(exc))
            return
        self._selected_team_index = None
        self._refresh_team_view()
        self._set_status(f"{name} entfernt.")

    def _clear_team(self) -> None:
        self.team = Team(self.team.name)
        self._selected_team_index = None
        self._refresh_team_view()
        self._clear_output()
        self._set_status("Team geleert.")

    def _download_all_pokemon(self) -> None:
        """Lädt alle Pokemon aus der PokeAPI in den Cache (mit Fortschrittsdialog).

        Der eigentliche Download läuft in einem Worker-Thread, damit die
        GUI während des Vorgangs reagierfähig bleibt. Über `root.after`
        werden die UI-Updates ins Haupt-Thread zurückgereicht.
        """
        if not messagebox.askyesno(
            "Alle Pokemon laden",
            "Lädt ca. 1300 Pokemon von der PokeAPI in den Cache.\n"
            "Das dauert je nach Verbindung 20-60 Sekunden.\n\n"
            "Fortfahren?",
        ):
            return

        # Fortschrittsdialog aufbauen.
        progress_win = tk.Toplevel(self.root)
        progress_win.title("Pokemon werden geladen ...")
        progress_win.geometry("420x120")
        progress_win.transient(self.root)
        progress_win.grab_set()
        progress_win.protocol("WM_DELETE_WINDOW", lambda: None)

        info_var = tk.StringVar(value="Hole Pokemon-Liste ...")
        ttk.Label(progress_win, textvariable=info_var,
                  padding=10).pack(fill=tk.X)
        bar = ttk.Progressbar(progress_win, mode="determinate",
                              length=380, maximum=100)
        bar.pack(padx=10, pady=4)

        # Lokaler Import - das fetch-Modul ist optional.
        from data.fetch_all_pokemon import bulk_fetch

        def _on_progress(done: int, total: int, name: str) -> None:
            # Wird aus einem Worker-Thread aufgerufen, deshalb der Umweg
            # über `after(0, ...)` zurück in den GUI-Thread.
            def _update():
                bar["maximum"] = total
                bar["value"] = done
                info_var.set(f"{done}/{total} - {name}")
            self.root.after(0, _update)

        def _worker():
            try:
                success, total = bulk_fetch(workers=16, progress=_on_progress)
                self.root.after(0, lambda: _finish_ok(success, total))
            except Exception as exc:  # pragma: no cover - GUI-Pfad
                self.root.after(0, lambda: _finish_error(str(exc)))

        def _finish_ok(success: int, total: int) -> None:
            # Erst das Fenster zerstören und ein Status-Update setzen.
            try:
                progress_win.grab_release()
            except tk.TclError:
                pass
            progress_win.destroy()
            self._set_status(f"Bulk-Download fertig: {success}/{total} Pokemon.")
            # Liste neu aufbauen und Info-Box - über `after` reihen wir das
            # in die Event-Loop ein, damit der Destroy-Aufruf zuerst greift.
            def _post():
                self._populate_cached_pokemon()
                messagebox.showinfo(
                    "Fertig",
                    f"{success} von {total} Pokemon im Cache. "
                    "Die Auto-Vervollständigung berücksichtigt jetzt alle.",
                )
            self.root.after(50, _post)

        def _finish_error(message: str) -> None:
            progress_win.grab_release()
            progress_win.destroy()
            messagebox.showerror("Fehler beim Download", message)
            self._set_status(f"Download-Fehler: {message}")

        threading.Thread(target=_worker, daemon=True).start()

    def _auto_complete(self) -> None:
        """Füllt das aktuelle Team mit besten verfügbaren Kandidaten auf."""
        # 1. Pool: alle Pokemon aus dem Cache laden.
        pool: list[Pokemon] = []
        for cache_file in self.client.cache_dir.glob("pokemon_*.json"):
            name = cache_file.stem.removeprefix("pokemon_")
            try:
                data = self.client.get_pokemon(name)
                pool.append(Pokemon.from_api(data))
            except (PokeAPIError, ValueError):
                continue  # defekte Cache-Datei einfach ignorieren
        if not pool:
            messagebox.showinfo(
                "Hinweis",
                "Kein Pokemon im Cache. Bitte zuerst ein paar hinzufügen.")
            return

        # 2. Generations-Filter umwandeln (Anzeige -> Zahl oder None).
        gen_label = self.gen_var.get()
        max_gen: int | None
        if gen_label == "Alle":
            max_gen = None
        else:
            try:
                max_gen = int(gen_label.removeprefix("Gen ").strip())
            except ValueError:
                max_gen = None

        # 3. Greedy-Vervollständigung anwenden.
        try:
            completer = TeamCompleter(pool)
            completer.complete(self.team, max_generation=max_gen)
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Fehler beim Auffüllen", str(exc))
            return

        self._refresh_team_view()
        gen_msg = "alle Generationen" if max_gen is None else f"bis Gen {max_gen}"
        self._set_status(
            f"Team auto-vervollständigt ({gen_msg}, Pool: {len(pool)} Pokemon)."
        )

    def _load_preset(self) -> None:
        """Lädt das im Dropdown ausgewählte Preset und ersetzt das aktuelle Team."""
        name = self.preset_var.get().strip()
        if not name:
            messagebox.showinfo("Hinweis", "Bitte zuerst ein Preset auswählen.")
            return
        try:
            self.team = load_preset(name, self.client)
        except (PokeAPIError, ValueError, KeyError) as exc:
            messagebox.showerror("Fehler beim Laden", str(exc))
            self._set_status(f"Preset-Fehler: {exc}")
            return
        self._selected_team_index = None
        self._refresh_team_view()
        self._set_status(f"Preset geladen: {name}")

    # ------------------------------------------------------------------ #
    # Analyse-Aktionen (unverändert gegenüber der vorherigen Version)
    # ------------------------------------------------------------------ #
    def _require_analyzer(self) -> TeamAnalyzer | None:
        if len(self.team) == 0:
            messagebox.showinfo("Hinweis",
                                "Bitte zuerst mindestens ein Pokemon hinzufügen.")
            return None
        return TeamAnalyzer(self.team)

    def _show_stats(self) -> None:
        analyzer = self._require_analyzer()
        if analyzer is None:
            return
        df = analyzer.to_stats_dataframe()
        summary = analyzer.summary()
        text = (
            "Stats pro Pokemon:\n"
            f"{df.to_string()}\n\n"
            "Aggregierte Statistik:\n"
            f"{summary.to_string()}"
        )
        self._show_text(text)

    def _show_coverage(self) -> None:
        analyzer = self._require_analyzer()
        if analyzer is None:
            return
        cov = analyzer.type_coverage()
        weakest = analyzer.biggest_weaknesses()
        text = (
            "Typ-Coverage (Anzahl Teammitglieder pro Kategorie):\n"
            f"{cov.to_string()}\n\n"
            "Grösste Schwächen (Top 5):\n"
            f"{weakest.to_string()}"
        )
        self._show_text(text)

    def _plot_totals(self) -> None:
        analyzer = self._require_analyzer()
        if analyzer is None:
            return
        self._show_plot(lambda ax: analyzer.plot_total_stats(ax=ax))

    def _plot_stats(self) -> None:
        analyzer = self._require_analyzer()
        if analyzer is None:
            return
        self._show_plot(lambda ax: analyzer.plot_stats_comparison(ax=ax),
                        figsize=(8, 5))

    def _plot_heatmap(self) -> None:
        analyzer = self._require_analyzer()
        if analyzer is None:
            return
        self._show_plot(lambda _ax: analyzer.plot_type_coverage_heatmap(),
                        from_method=True)

    # ------------------------------------------------------------------ #
    # Anzeige-Helfer
    # ------------------------------------------------------------------ #
    def _show_text(self, content: str) -> None:
        self.tabs.select(self.text_tab)
        self.text_widget.configure(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.insert("1.0", content)
        self.text_widget.configure(state=tk.DISABLED)

    def _show_plot(self, plot_fn, figsize=(7, 4), from_method: bool = False) -> None:
        self._clear_plot_tab()
        if from_method:
            ax = plot_fn(None)
            fig = ax.figure
        else:
            fig, ax = plt.subplots(figsize=figsize)
            plot_fn(ax)
        canvas = FigureCanvasTkAgg(fig, master=self.plot_tab)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._current_canvas = canvas
        self.tabs.select(self.plot_tab)

    def _clear_plot_tab(self) -> None:
        for child in self.plot_tab.winfo_children():
            child.destroy()
        if self._current_canvas is not None:
            plt.close(self._current_canvas.figure)
            self._current_canvas = None

    def _clear_output(self) -> None:
        self._clear_plot_tab()
        self.text_widget.configure(state=tk.NORMAL)
        self.text_widget.delete("1.0", tk.END)
        self.text_widget.configure(state=tk.DISABLED)

    # ------------------------------------------------------------------ #
    # Team-Anzeige neu rendern (mit Sprites)
    # ------------------------------------------------------------------ #
    def _refresh_team_view(self) -> None:
        # Alles entsorgen und neu aufbauen - das Team hat max. 6 Slots, daher
        # ist das auch performance-mässig vernachlässigbar.
        for child in self.team_inner.winfo_children():
            child.destroy()

        if len(self.team) == 0:
            ttk.Label(self.team_inner,
                      text="Noch leer. Pokemon links auswählen oder eingeben.",
                      foreground="#666666").pack(pady=20)
            return

        for i, pokemon in enumerate(self.team.members):
            row = ttk.Frame(self.team_inner, relief="ridge", padding=6)
            row.pack(fill=tk.X, pady=2)
            # Hervorhebung wenn ausgewählt
            if i == self._selected_team_index:
                row.configure(relief="solid")

            # Sprite
            photo = self._photo_for(pokemon)
            if photo is not None:
                lbl = ttk.Label(row, image=photo)
                lbl.image = photo  # zusätzliche Referenz: Tk-typische Falle vermeiden
                lbl.pack(side=tk.LEFT, padx=(0, 8))

            # Textblock
            types_str = " / ".join(t.capitalize() for t in pokemon.types)
            info = ttk.Frame(row)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Label(info, text=f"#{pokemon.pokedex_id} {pokemon.name.capitalize()}",
                      font=("Helvetica", 11, "bold")).pack(anchor=tk.W)
            ttk.Label(info, text=types_str, foreground="#444444").pack(anchor=tk.W)
            ttk.Label(info, text=f"Total: {pokemon.total_stats()}",
                      foreground="#1d4ed8").pack(anchor=tk.W)

            # Klick auf die Reihe wählt sie aus
            for widget in (row, info, *info.winfo_children()):
                widget.bind("<Button-1>",
                            lambda _e, idx=i: self._select_team_member(idx))

    def _select_team_member(self, index: int) -> None:
        self._selected_team_index = index
        self._refresh_team_view()
        member = self.team.members[index]
        self._set_status(f"Ausgewählt: {member.name.capitalize()}")

    # ------------------------------------------------------------------ #
    # Cache-Liste füllen
    # ------------------------------------------------------------------ #
    # Liste der bekannten Cache-Namen wird einmal eingelesen und dann nur
    # noch in `_refresh_cache_view` gefiltert. So bleibt die Suche flüssig
    # auch bei 1300+ Pokemon im Cache.
    CACHE_DISPLAY_LIMIT = 80

    def _populate_cached_pokemon(self) -> None:
        """Liest die Liste der Pokemon-Namen aus dem Cache (sehr günstig:
        nur Dateinamen, keine JSON-Parsen, keine Netz-Aufrufe).
        Die eigentliche Anzeige passiert in `_refresh_cache_view`.
        """
        cache_dir = self.client.cache_dir
        if not cache_dir.exists():
            self._cached_names: list[str] = []
        else:
            self._cached_names = sorted(
                f.stem.removeprefix("pokemon_")
                for f in cache_dir.glob("pokemon_*.json")
            )
        self._refresh_cache_view()

    def _refresh_cache_view(self) -> None:
        """Zeigt die Pokemon-Namen, die zum Suchfilter passen, in der Treeview.

        - Standardansicht (kein Suchtext): die ersten `CACHE_DISPLAY_LIMIT`
          Einträge, alphabetisch. Das hält die GUI flott bei grossen Caches.
        - Mit Suchtext wird nach Substring gefiltert; die Liste bleibt
          ebenfalls auf das Limit beschränkt.
        - Sprites werden nur angezeigt, wenn sie bereits lokal vorhanden
          sind (`allow_download=False`), sonst nur Name und Typen.
        """
        # Treeview leeren.
        for item in self.cache_tree.get_children():
            self.cache_tree.delete(item)

        query = self.cache_search_var.get().strip().lower()
        names_all = getattr(self, "_cached_names", [])
        if query:
            matches = [n for n in names_all if query in n]
        else:
            matches = list(names_all)
        total_matches = len(matches)
        shown = matches[: self.CACHE_DISPLAY_LIMIT]

        for name in shown:
            # JSON-Parse ist günstig (~1ms pro Pokemon), aber nur für die
            # tatsächlich gezeigten Einträge - nicht für alle 1300+.
            try:
                data = self.client.get_pokemon(name)
                pokemon = Pokemon.from_api(data)
            except (PokeAPIError, ValueError):
                continue
            types_str = "/".join(t.capitalize() for t in pokemon.types)
            photo = self._photo_for(pokemon, size=32, allow_download=False)
            kwargs = {"text": f"{pokemon.name.capitalize()}",
                      "values": (types_str,)}
            if photo is not None:
                kwargs["image"] = photo
            self.cache_tree.insert("", tk.END, iid=name, **kwargs)

        # Info-Zeile mit Anzahl Treffer und ggf. Limit-Hinweis aktualisieren.
        if total_matches == 0:
            self.cache_info_var.set("Keine Treffer.")
        elif total_matches > self.CACHE_DISPLAY_LIMIT:
            self.cache_info_var.set(
                f"{self.CACHE_DISPLAY_LIMIT} von {total_matches} angezeigt - "
                "Suche eingrenzen für mehr."
            )
        else:
            self.cache_info_var.set(f"{total_matches} im Cache.")

    def _set_status(self, msg: str) -> None:
        self.status_var.set(msg)


def main() -> None:
    """Startet die GUI."""
    root = tk.Tk()
    PokemonTeamGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
