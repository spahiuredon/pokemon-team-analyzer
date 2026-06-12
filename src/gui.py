"""Modernes GUI für den Pokemon Team-Analyzer (CustomTkinter).

Aufbau:
- Links eine Sidebar: Suche + Pokemon-Liste, Hinzufügen, Presets,
  Auto-Vervollständigung.
- Mitte: das aktuelle Team als Karten (Sprite, Typ-Badges, Stats).
- Rechts: Tab-Ansicht mit Tabelle, Typ-Coverage, Plots und 3DS-Sync.

Das Farbschema folgt automatisch dem System (hell/dunkel).

Aufruf:
    python -m src.gui
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:  # pragma: no cover - GUI braucht Pillow ohnehin
    HAS_PIL = False

from .analyzer import TeamAnalyzer
from .api_client import PokeAPIClient, PokeAPIError
from .app_paths import app_icon_path, data_dir
from .pokemon import Pokemon
from .presets import available_presets, load_preset
from .team import Team
from .team_completer import GENERATION_RANGES, TeamCompleter
from .translations import display_name, matches_query, to_english

SPRITE_SIZE = 64

# Textfarbe für Buttons mit transparentem Hintergrund: das Theme-Default
# (helles Weiss) ist im Light Mode unsichtbar - daher explizit
# (hell-Modus-Farbe, dunkel-Modus-Farbe) setzen.
TEXT_ON_TRANSPARENT = ("gray10", "#DCE4EE")

# Offizielle Typ-Farben für die Badges auf den Team-Karten.
TYPE_COLORS: dict[str, str] = {
    "normal": "#A8A77A", "fire": "#EE8130", "water": "#6390F0",
    "electric": "#F7D02C", "grass": "#7AC74C", "ice": "#96D9D6",
    "fighting": "#C22E28", "poison": "#A33EA1", "ground": "#E2BF65",
    "flying": "#A98FF3", "psychic": "#F95587", "bug": "#A6B91A",
    "rock": "#B6A136", "ghost": "#735797", "dragon": "#6F35FC",
    "dark": "#705746", "steel": "#B7B7CE", "fairy": "#D685AD",
}

GERMAN_TYPES: dict[str, str] = {
    "normal": "Normal", "fire": "Feuer", "water": "Wasser",
    "electric": "Elektro", "grass": "Pflanze", "ice": "Eis",
    "fighting": "Kampf", "poison": "Gift", "ground": "Boden",
    "flying": "Flug", "psychic": "Psycho", "bug": "Käfer",
    "rock": "Gestein", "ghost": "Geist", "dragon": "Drache",
    "dark": "Unlicht", "steel": "Stahl", "fairy": "Fee",
}


class PokemonTeamGUI:
    """Hauptfenster der Anwendung."""

    CACHE_DISPLAY_LIMIT = 60

    def __init__(self, root: ctk.CTk) -> None:
        self.root = root
        self.root.title("Pokemon Team-Analyzer")
        self.root.geometry("1280x800")
        self.root.minsize(1080, 680)

        self.client = PokeAPIClient(cache_dir=data_dir() / "cache",
                                    sprite_dir=data_dir() / "sprites")
        self.team = Team("Mein Team")
        self._selected_team_index: int | None = None
        self._current_canvas: FigureCanvasTkAgg | None = None
        self._image_cache: dict[tuple[int, int], ctk.CTkImage] = {}
        self._cached_names: list[str] = []

        self._set_app_icon()
        self._build_layout()
        self._populate_cached_pokemon()
        self._refresh_team_view()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ #
    # Grund-Layout
    # ------------------------------------------------------------------ #
    def _build_layout(self) -> None:
        self.root.grid_columnconfigure(1, weight=0)
        self.root.grid_columnconfigure(2, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_team_panel()
        self._build_analysis_panel()
        self._build_statusbar()

    # ------------------------------------------------------------------ #
    # Sidebar (links): Suche, Liste, Hinzufügen, Presets
    # ------------------------------------------------------------------ #
    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self.root, width=290, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(4, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            sidebar, text="Pokemon\nTeam-Analyzer",
            font=ctk.CTkFont(size=20, weight="bold"), justify="left",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))

        # Suche + direkte Eingabe
        self.search_var = tk.StringVar()
        search = ctk.CTkEntry(sidebar, textvariable=self.search_var,
                              placeholder_text="Suchen (deutsch/englisch)...")
        search.grid(row=1, column=0, sticky="ew", padx=16)
        search.bind("<Return>", lambda _e: self._add_pokemon())
        self.search_var.trace_add("write", lambda *_: self._refresh_cache_view())

        ctk.CTkButton(sidebar, text="+  Zum Team hinzufügen",
                      command=self._add_pokemon).grid(
            row=2, column=0, sticky="ew", padx=16, pady=(8, 4))

        self.cache_info = ctk.CTkLabel(sidebar, text="",
                                       font=ctk.CTkFont(size=11),
                                       text_color=("gray40", "gray60"))
        self.cache_info.grid(row=3, column=0, sticky="w", padx=16)

        # Scrollbare Pokemon-Liste
        self.cache_list = ctk.CTkScrollableFrame(sidebar, label_text="")
        self.cache_list.grid(row=4, column=0, sticky="nsew", padx=10, pady=4)
        self.cache_list.grid_columnconfigure(0, weight=1)

        # Presets
        bottom = ctk.CTkFrame(sidebar, fg_color="transparent")
        bottom.grid(row=5, column=0, sticky="ew", padx=16, pady=(4, 16))
        bottom.grid_columnconfigure(0, weight=1)

        presets = available_presets()
        self.preset_var = tk.StringVar(value=presets[0] if presets else "")
        ctk.CTkLabel(bottom, text="Vorgefertigtes Team",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=0, sticky="w")
        ctk.CTkOptionMenu(bottom, variable=self.preset_var,
                          values=presets or ["-"]).grid(
            row=1, column=0, sticky="ew", pady=(2, 4))
        ctk.CTkButton(bottom, text="Team laden",
                      command=self._load_preset).grid(
            row=2, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(bottom, text="Auto-Vervollständigung",
                     font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=3, column=0, sticky="w")
        # "Bis Gen n" = alles bis einschliesslich Gen n;
        # "Nur Gen n" = ausschliesslich Pokemon dieser Generation
        # (z.B. ein reines Gen-5-Team passend zu Schwarz/Weiss).
        gens = sorted(GENERATION_RANGES)
        gen_values = (["Alle"] + [f"Bis Gen {g}" for g in gens]
                      + [f"Nur Gen {g}" for g in gens])
        self.gen_var = tk.StringVar(value="Alle")
        ctk.CTkOptionMenu(bottom, variable=self.gen_var,
                          values=gen_values).grid(
            row=4, column=0, sticky="ew", pady=(2, 4))
        self.legendary_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(bottom, variable=self.legendary_var,
                        text="Legendäre & Mythische erlauben",
                        font=ctk.CTkFont(size=12),
                        checkbox_width=18, checkbox_height=18).grid(
            row=5, column=0, sticky="w", pady=(2, 4))
        ctk.CTkButton(bottom, text="Team auto-auffüllen",
                      command=self._auto_complete).grid(
            row=6, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkButton(bottom, text="Alle Pokemon laden (PokeAPI)",
                      fg_color="transparent", border_width=1,
                      text_color=TEXT_ON_TRANSPARENT,
                      command=self._download_all_pokemon).grid(
            row=7, column=0, sticky="ew")
        ctk.CTkButton(bottom, text="Cache leeren...",
                      fg_color="transparent", border_width=1,
                      text_color=TEXT_ON_TRANSPARENT,
                      command=self._clear_cache_dialog).grid(
            row=8, column=0, sticky="ew", pady=(4, 0))

    # ------------------------------------------------------------------ #
    # Team-Panel (Mitte): Karten
    # ------------------------------------------------------------------ #
    def _build_team_panel(self) -> None:
        panel = ctk.CTkFrame(self.root, width=320, fg_color="transparent")
        panel.grid(row=0, column=1, sticky="nsew", padx=(12, 6), pady=12)
        panel.grid_propagate(False)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(panel, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="Aktuelles Team",
                     font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="Leeren", width=70,
                      fg_color="transparent", border_width=1,
                      text_color=TEXT_ON_TRANSPARENT,
                      command=self._clear_team).grid(row=0, column=1)

        self.team_frame = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.team_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.team_frame.grid_columnconfigure(0, weight=1)

    # ------------------------------------------------------------------ #
    # Analyse-Panel (rechts): Tabs
    # ------------------------------------------------------------------ #
    def _build_analysis_panel(self) -> None:
        self.tabs = ctk.CTkTabview(self.root, command=self._on_tab_change)
        self.tabs.grid(row=0, column=2, sticky="nsew", padx=(6, 12), pady=12)

        self.tab_stats = self.tabs.add("Tabelle")
        self.tab_coverage = self.tabs.add("Coverage")
        self.tab_plots = self.tabs.add("Plots")
        self.tab_sync = self.tabs.add("3DS Sync")

        # Tabelle
        self.stats_text = ctk.CTkTextbox(self.tab_stats,
                                         font=ctk.CTkFont(family="Courier",
                                                          size=12))
        self.stats_text.pack(fill="both", expand=True)
        self.stats_text.configure(state="disabled")

        # Coverage
        self.coverage_text = ctk.CTkTextbox(self.tab_coverage,
                                            font=ctk.CTkFont(family="Courier",
                                                             size=12))
        self.coverage_text.pack(fill="both", expand=True)
        self.coverage_text.configure(state="disabled")

        # Plots: Auswahl oben, Zeichenfläche darunter
        self.plot_choice = ctk.CTkSegmentedButton(
            self.tab_plots,
            values=["Gesamt-Stats", "Stats-Vergleich", "Typ-Heatmap"],
            command=lambda _v: self._render_plot())
        self.plot_choice.set("Gesamt-Stats")
        self.plot_choice.pack(pady=(4, 8))
        self.plot_area = ctk.CTkFrame(self.tab_plots, fg_color="transparent")
        self.plot_area.pack(fill="both", expand=True)

        # 3DS Sync (eigenes Modul)
        from .sync_gui import SyncTab
        self.sync_tab = SyncTab(self.root, self.tab_sync)

    def _build_statusbar(self) -> None:
        self.status_var = tk.StringVar(value="Bereit.")
        bar = ctk.CTkLabel(self.root, textvariable=self.status_var,
                           anchor="w", font=ctk.CTkFont(size=11),
                           text_color=("gray30", "gray70"))
        bar.grid(row=1, column=0, columnspan=3, sticky="ew", padx=14,
                 pady=(0, 4))

    # ------------------------------------------------------------------ #
    # Icon & Aufräumen
    # ------------------------------------------------------------------ #
    def _set_app_icon(self) -> None:
        icon = app_icon_path()
        if icon.exists():
            try:
                self._icon_photo = tk.PhotoImage(file=str(icon))
                self.root.iconphoto(True, self._icon_photo)
            except (OSError, ValueError, tk.TclError):
                pass
        import sys as _sys
        if _sys.platform == "darwin":
            try:
                from Foundation import NSBundle  # type: ignore
                bundle = NSBundle.mainBundle()
                if bundle is not None:
                    info = (bundle.localizedInfoDictionary()
                            or bundle.infoDictionary())
                    if info is not None:
                        info["CFBundleName"] = "Pokemon Team-Analyzer"
                        info["CFBundleDisplayName"] = "Pokemon Team-Analyzer"
            except ImportError:
                pass

    def _on_close(self) -> None:
        try:
            self._image_cache.clear()
        except Exception:
            pass
        try:
            self.root.quit()
        finally:
            self.root.destroy()

    # ------------------------------------------------------------------ #
    # Sprites als CTkImage
    # ------------------------------------------------------------------ #
    def _image_for(self, pokemon: Pokemon, size: int = SPRITE_SIZE,
                   allow_download: bool = True) -> ctk.CTkImage | None:
        if not HAS_PIL:
            return None
        key = (pokemon.pokedex_id, size)
        if key in self._image_cache:
            return self._image_cache[key]
        sprite_path = self.client.get_sprite(
            pokemon.pokedex_id, pokemon.sprite_url,
            allow_download=allow_download)
        if sprite_path is None:
            return None
        try:
            img = Image.open(sprite_path).convert("RGBA")
            image = ctk.CTkImage(light_image=img, dark_image=img,
                                 size=(size, size))
        except (OSError, ValueError):
            return None
        self._image_cache[key] = image
        return image

    # ------------------------------------------------------------------ #
    # Pokemon-Liste (Sidebar)
    # ------------------------------------------------------------------ #
    def _populate_cached_pokemon(self) -> None:
        cache_dir = self.client.cache_dir
        self._cached_names = sorted(
            f.stem.removeprefix("pokemon_")
            for f in cache_dir.glob("pokemon_*.json")
        ) if cache_dir.exists() else []
        self._refresh_cache_view()

    def _refresh_cache_view(self) -> None:
        for child in self.cache_list.winfo_children():
            child.destroy()

        query = self.search_var.get().strip().lower()
        # Suche matcht englische UND deutsche Namen ("Glurak" -> charizard).
        matches = ([n for n in self._cached_names if matches_query(n, query)]
                   if query else list(self._cached_names))
        total = len(matches)
        shown = matches[: self.CACHE_DISPLAY_LIMIT]

        for row, name in enumerate(shown):
            try:
                pokemon = Pokemon.from_api(self.client.get_pokemon(name))
            except (PokeAPIError, ValueError):
                continue
            item = ctk.CTkFrame(self.cache_list, fg_color="transparent")
            item.grid(row=row, column=0, sticky="ew", pady=1)
            item.grid_columnconfigure(1, weight=1)

            image = self._image_for(pokemon, size=28, allow_download=False)
            if image is not None:
                ctk.CTkLabel(item, image=image, text="").grid(
                    row=0, column=0, padx=(2, 6))
            types = "/".join(GERMAN_TYPES.get(t, t.capitalize())
                             for t in pokemon.types)
            ctk.CTkLabel(item, text=display_name(pokemon.name),
                         anchor="w").grid(row=0, column=1, sticky="w")
            ctk.CTkLabel(item, text=types, anchor="e",
                         font=ctk.CTkFont(size=10),
                         text_color=("gray40", "gray60")).grid(
                row=0, column=2, sticky="e", padx=4)
            ctk.CTkButton(item, text="+", width=26, height=22,
                          command=lambda n=name: self._add_by_name(n)).grid(
                row=0, column=3, padx=(2, 4))

        if total == 0:
            self.cache_info.configure(text="Keine Treffer.")
        elif total > self.CACHE_DISPLAY_LIMIT:
            self.cache_info.configure(
                text=f"{self.CACHE_DISPLAY_LIMIT} von {total} - Suche eingrenzen.")
        else:
            self.cache_info.configure(text=f"{total} Pokemon")

    # ------------------------------------------------------------------ #
    # Team-Aktionen
    # ------------------------------------------------------------------ #
    def _add_pokemon(self) -> None:
        name = self.search_var.get().strip()
        if not name:
            return
        if self._add_by_name(name):
            self.search_var.set("")

    def _add_by_name(self, name: str) -> bool:
        try:
            # Deutsche Namen ("Glurak") werden zu englischen übersetzt,
            # bevor Cache/API gefragt werden.
            pokemon = Pokemon.from_api(self.client.get_pokemon(to_english(name)))
            self.team.add(pokemon)
        except (PokeAPIError, ValueError) as exc:
            messagebox.showerror("Fehler", f"{exc}")
            self._set_status(f"Fehler: {exc}")
            return False
        self._refresh_team_view()
        self._refresh_analysis()
        self._set_status(f"{display_name(pokemon.name)} hinzugefügt.")
        return True

    def _remove_member(self, name: str) -> None:
        try:
            self.team.remove(name)
        except KeyError as exc:
            messagebox.showerror("Fehler", str(exc))
            return
        self._refresh_team_view()
        self._refresh_analysis()
        self._set_status(f"{display_name(name)} entfernt.")

    def _clear_team(self) -> None:
        self.team = Team(self.team.name)
        self._refresh_team_view()
        self._refresh_analysis()
        self._set_status("Team geleert.")

    def _load_preset(self) -> None:
        name = self.preset_var.get().strip()
        if not name or name == "-":
            return
        try:
            self.team = load_preset(name, self.client)
        except (PokeAPIError, ValueError, KeyError) as exc:
            messagebox.showerror("Fehler beim Laden", str(exc))
            return
        self._refresh_team_view()
        self._refresh_analysis()
        self._set_status(f"Preset geladen: {name}")

    def _auto_complete(self) -> None:
        if len(self.team) >= Team.MAX_SIZE:
            messagebox.showinfo(
                "Team ist voll",
                "Das Team hat schon 6 Pokemon. Entferne welche oder leere "
                "das Team, um eine neue Variante zu bekommen.")
            return
        pool: list[Pokemon] = []
        for cache_file in self.client.cache_dir.glob("pokemon_*.json"):
            try:
                pool.append(Pokemon.from_api(
                    self.client.get_pokemon(
                        cache_file.stem.removeprefix("pokemon_"))))
            except (PokeAPIError, ValueError):
                continue
        if not pool:
            messagebox.showinfo("Hinweis", "Kein Pokemon im Cache.")
            return
        gen_label = self.gen_var.get()
        max_gen: int | None = None
        exact_gen: int | None = None
        if gen_label.startswith("Bis Gen "):
            max_gen = int(gen_label.removeprefix("Bis Gen ").strip())
        elif gen_label.startswith("Nur Gen "):
            exact_gen = int(gen_label.removeprefix("Nur Gen ").strip())
        try:
            TeamCompleter(pool).complete(
                self.team, max_generation=max_gen,
                exact_generation=exact_gen,
                allow_legendary=self.legendary_var.get())
        except (ValueError, KeyError) as exc:
            messagebox.showerror("Fehler beim Auffüllen", str(exc))
            return
        self._refresh_team_view()
        self._refresh_analysis()
        self._set_status("Team auto-vervollständigt - nochmal klicken "
                         "ergibt eine neue Variante.")

    # ------------------------------------------------------------------ #
    # Team-Karten rendern
    # ------------------------------------------------------------------ #
    def _refresh_team_view(self) -> None:
        for child in self.team_frame.winfo_children():
            child.destroy()

        if len(self.team) == 0:
            ctk.CTkLabel(
                self.team_frame,
                text="Noch leer.\nLinks ein Pokemon suchen\nund mit + hinzufügen.",
                text_color=("gray40", "gray60"), justify="center",
            ).grid(row=0, column=0, pady=40)
            return

        for i, pokemon in enumerate(self.team.members):
            card = ctk.CTkFrame(self.team_frame, corner_radius=12)
            card.grid(row=i, column=0, sticky="ew", pady=4)
            card.grid_columnconfigure(1, weight=1)

            image = self._image_for(pokemon)
            if image is not None:
                ctk.CTkLabel(card, image=image, text="").grid(
                    row=0, column=0, rowspan=3, padx=10, pady=8)

            ctk.CTkLabel(
                card, text=display_name(pokemon.name),
                font=ctk.CTkFont(size=14, weight="bold"), anchor="w",
            ).grid(row=0, column=1, sticky="w", pady=(8, 0))
            ctk.CTkLabel(
                card, text=f"#{pokemon.pokedex_id} · Total {pokemon.total_stats()}",
                font=ctk.CTkFont(size=11),
                text_color=("gray40", "gray60"), anchor="w",
            ).grid(row=1, column=1, sticky="w")

            badges = ctk.CTkFrame(card, fg_color="transparent")
            badges.grid(row=2, column=1, sticky="w", pady=(2, 8))
            for j, t in enumerate(pokemon.types):
                ctk.CTkLabel(
                    badges, text=GERMAN_TYPES.get(t, t.capitalize()),
                    fg_color=TYPE_COLORS.get(t, "#777777"),
                    text_color="white", corner_radius=8,
                    font=ctk.CTkFont(size=11, weight="bold"),
                    padx=8, height=20,
                ).grid(row=0, column=j, padx=(0, 4))

            ctk.CTkButton(
                card, text="✕", width=28, height=28,
                fg_color="transparent", border_width=1,
                text_color=TEXT_ON_TRANSPARENT,
                hover_color=("#fca5a5", "#7f1d1d"),
                command=lambda n=pokemon.name: self._remove_member(n),
            ).grid(row=0, column=2, rowspan=3, padx=10)

    # ------------------------------------------------------------------ #
    # Analyse: Tabs füllen sich automatisch
    # ------------------------------------------------------------------ #
    def _on_tab_change(self) -> None:
        self._refresh_analysis()

    def _refresh_analysis(self) -> None:
        current = self.tabs.get()
        if current == "Tabelle":
            self._render_stats()
        elif current == "Coverage":
            self._render_coverage()
        elif current == "Plots":
            self._render_plot()

    def _analyzer(self) -> TeamAnalyzer | None:
        return TeamAnalyzer(self.team) if len(self.team) > 0 else None

    def _fill_textbox(self, box: ctk.CTkTextbox, content: str) -> None:
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", content)
        box.configure(state="disabled")

    def _render_stats(self) -> None:
        analyzer = self._analyzer()
        if analyzer is None:
            self._fill_textbox(self.stats_text,
                               "Füge zuerst Pokemon zum Team hinzu.")
            return
        df = analyzer.to_stats_dataframe()
        summary = analyzer.summary()
        self._fill_textbox(
            self.stats_text,
            f"Stats pro Pokemon:\n{df.to_string()}\n\n"
            f"Aggregierte Statistik:\n{summary.to_string()}")

    def _render_coverage(self) -> None:
        analyzer = self._analyzer()
        if analyzer is None:
            self._fill_textbox(self.coverage_text,
                               "Füge zuerst Pokemon zum Team hinzu.")
            return
        cov = analyzer.type_coverage()
        weakest = analyzer.biggest_weaknesses()
        self._fill_textbox(
            self.coverage_text,
            "Typ-Coverage (Teammitglieder pro Kategorie):\n"
            f"{cov.to_string()}\n\nGrösste Schwächen (Top 5):\n"
            f"{weakest.to_string()}")

    def _render_plot(self) -> None:
        self._clear_plot_area()
        analyzer = self._analyzer()
        if analyzer is None:
            ctk.CTkLabel(self.plot_area,
                         text="Füge zuerst Pokemon zum Team hinzu.",
                         text_color=("gray40", "gray60")).pack(pady=40)
            return
        choice = self.plot_choice.get()
        if choice == "Gesamt-Stats":
            fig, ax = plt.subplots(figsize=(7, 4))
            analyzer.plot_total_stats(ax=ax)
        elif choice == "Stats-Vergleich":
            fig, ax = plt.subplots(figsize=(8, 5))
            analyzer.plot_stats_comparison(ax=ax)
        else:
            ax = analyzer.plot_type_coverage_heatmap()
            fig = ax.figure
        self._style_figure(fig)
        canvas = FigureCanvasTkAgg(fig, master=self.plot_area)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)
        self._current_canvas = canvas

    def _style_figure(self, fig) -> None:
        """Passt die Plot-Farben an den Hell/Dunkel-Modus an."""
        if ctk.get_appearance_mode() != "Dark":
            return
        fg = "#e5e5e5"
        fig.patch.set_facecolor("#1f1f1f")
        for ax in fig.axes:
            ax.set_facecolor("#2a2a2a")
            ax.tick_params(colors=fg)
            ax.xaxis.label.set_color(fg)
            ax.yaxis.label.set_color(fg)
            ax.title.set_color(fg)
            for spine in ax.spines.values():
                spine.set_color("#555555")

    def _clear_plot_area(self) -> None:
        for child in self.plot_area.winfo_children():
            child.destroy()
        if self._current_canvas is not None:
            plt.close(self._current_canvas.figure)
            self._current_canvas = None

    # ------------------------------------------------------------------ #
    # Bulk-Download (Worker-Thread + Queue, wie gehabt)
    # ------------------------------------------------------------------ #
    def _download_all_pokemon(self) -> None:
        if not messagebox.askyesno(
            "Alle Pokemon laden",
            "Lädt etwa 1000 Pokemon von der PokeAPI (20-60 Sekunden).\n\n"
            "Fortfahren?",
        ):
            return

        win = ctk.CTkToplevel(self.root)
        win.title("Pokemon werden geladen ...")
        win.geometry("440x130")
        win.transient(self.root)
        win.grab_set()
        win.protocol("WM_DELETE_WINDOW", lambda: None)

        info_var = tk.StringVar(value="Hole Pokemon-Liste ...")
        ctk.CTkLabel(win, textvariable=info_var).pack(padx=14, pady=(16, 6))
        bar = ctk.CTkProgressBar(win, width=380)
        bar.set(0)
        bar.pack(padx=14, pady=4)

        update_queue: queue.Queue = queue.Queue()
        from data.fetch_all_pokemon import bulk_fetch

        def _worker() -> None:
            try:
                success, total, pruned = bulk_fetch(
                    workers=16, prune=True,
                    progress=lambda d, t, n: update_queue.put(
                        ("progress", d, t, n)))
                update_queue.put(("done", success, total, pruned))
            except Exception as exc:  # pragma: no cover - GUI-Pfad
                update_queue.put(("error", str(exc)))

        def _poll() -> None:
            try:
                while True:
                    msg = update_queue.get_nowait()
                    if msg[0] == "progress":
                        _, done, total, name = msg
                        bar.set(done / max(total, 1))
                        info_var.set(f"{done}/{total} - {name}")
                    elif msg[0] == "done":
                        _, success, total, _pruned = msg
                        win.grab_release()
                        win.destroy()
                        self._set_status(
                            f"Download fertig: {success}/{total} Pokemon.")
                        self._populate_cached_pokemon()
                        return
                    else:
                        win.grab_release()
                        win.destroy()
                        messagebox.showerror("Fehler beim Download", msg[1])
                        return
            except queue.Empty:
                pass
            self.root.after(50, _poll)

        threading.Thread(target=_worker, daemon=True).start()
        self.root.after(100, _poll)

    # ------------------------------------------------------------------ #
    # Cache leeren (Vorschaubilder / Pokemon-Daten)
    # ------------------------------------------------------------------ #
    def _clear_cache_dialog(self) -> None:
        """Kleiner Dialog: nur Bilder leeren oder alles."""
        win = ctk.CTkToplevel(self.root)
        win.title("Cache leeren")
        win.geometry("460x230")
        win.transient(self.root)
        win.grab_set()

        ctk.CTkLabel(
            win, wraplength=420, justify="left",
            text=("Vorschaubilder leeren behebt defekte oder nie geladene "
                  "Sprites - sie werden bei Bedarf automatisch neu von der "
                  "PokeAPI geholt.\n\n"
                  "Alles leeren entfernt zusätzlich die Pokemon-Daten: die "
                  "Liste ist danach leer, bis du 'Alle Pokemon laden' "
                  "ausführst (Internet nötig)."),
        ).pack(padx=16, pady=(16, 10))

        def clear_sprites() -> None:
            removed = self.client.clear_sprites()
            self._image_cache.clear()
            win.destroy()
            self._refresh_cache_view()
            self._refresh_team_view()
            self._set_status(
                f"{removed} Vorschaubilder gelöscht - werden bei Bedarf "
                "neu geladen.")

        def clear_all() -> None:
            if not messagebox.askyesno(
                "Wirklich alles leeren?",
                "Pokemon-Daten UND Bilder werden gelöscht. Die Liste ist "
                "danach leer, bis neu geladen wird. Fortfahren?",
                parent=win,
            ):
                return
            sprites = self.client.clear_sprites()
            data = self.client.clear_pokemon_cache()
            self._image_cache.clear()
            win.destroy()
            self._populate_cached_pokemon()
            self._refresh_team_view()
            self._set_status(
                f"Cache geleert ({data} Datensätze, {sprites} Bilder). "
                "'Alle Pokemon laden' füllt die Liste neu.")

        row = ctk.CTkFrame(win, fg_color="transparent")
        row.pack(pady=(0, 14))
        ctk.CTkButton(row, text="Nur Vorschaubilder leeren",
                      command=clear_sprites).pack(side="left", padx=4)
        ctk.CTkButton(row, text="Alles leeren",
                      fg_color="transparent", border_width=1,
                      text_color=TEXT_ON_TRANSPARENT,
                      hover_color=("#fca5a5", "#7f1d1d"),
                      command=clear_all).pack(side="left", padx=4)

    def _set_status(self, msg: str) -> None:
        self.status_var.set(msg)


def main() -> None:
    """Startet die GUI."""
    ctk.set_appearance_mode("system")   # hell/dunkel folgt dem OS
    ctk.set_default_color_theme("blue")
    root = ctk.CTk()
    PokemonTeamGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
