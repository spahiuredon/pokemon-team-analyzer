"""Save-Synchronisation zwischen gemoddetem 3DS und PC-Emulatoren.

Unterstützte Spiele: Pokemon Platin bis Pokemon Ultra Sonne/Ultra Mond.

Zwei Welten:

- **NDS-Spiele** (Platin, HeartGold/SoulSilver, Schwarz/Weiss, Schwarz 2/
  Weiss 2): laufen auf dem 3DS über TWiLight Menu++. Der Spielstand ist
  eine rohe ``.sav``-Datei auf der SD-Karte (meist neben dem ROM oder im
  ``saves``-Unterordner). melonDS am PC nutzt exakt dasselbe rohe Format -
  die Datei kann 1:1 kopiert werden.

- **3DS-Spiele** (X/Y, OR/AS, Sonne/Mond, Ultra Sonne/Ultra Mond): der
  Spielstand liegt verschlüsselt im System und ist per FTP nicht direkt
  erreichbar. Stattdessen wird Checkpoint benutzt: Checkpoint exportiert
  den Save als rohe Dateien nach ``/3ds/Checkpoint/saves/...`` auf der SD.
  Diese rohe ``main``-Datei ist identisch mit dem, was Azahar (der
  Citra-Nachfolger) in seinem virtuellen SD-Ordner ablegt. Workflow:
  auf dem 3DS einmal Checkpoint-Backup machen -> syncen -> am PC spielen
  -> syncen -> auf dem 3DS mit Checkpoint wiederherstellen.

Transportweg ist FTP: auf dem 3DS läuft ``ftpd`` (Standard-Port 5000).
Zusätzlich kann ein Cloud-Ordner (z.B. der lokale Google-Drive- oder
Dropbox-Ordner) als dritte Quelle eingebunden werden - so synchronisieren
sich mehrere PCs untereinander über die Cloud.

Konfliktstrategie: **neuester Stand gewinnt**, alles was überschrieben
wird, landet vorher als Backup in ``~/.pokemon_team_analyzer/backups``.
Identische Inhalte (gleicher SHA-256) werden erkannt und nicht unnötig
kopiert.
"""

from __future__ import annotations

import hashlib
import json
import socket
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from ftplib import FTP, error_perm
from pathlib import Path
from typing import Callable


# --------------------------------------------------------------------- #
# Spiele-Registry
# --------------------------------------------------------------------- #

@dataclass(frozen=True)
class GameInfo:
    """Beschreibt ein unterstütztes Spiel."""

    key: str               # interner Schlüssel, z.B. "platinum"
    title: str             # Anzeigename
    platform: str          # "nds" oder "3ds"
    generation: int
    # Nur für 3DS-Spiele: Title-ID (low word) wie sie Azahar/Checkpoint
    # verwenden. Für NDS-Spiele leer.
    title_id_low: str = ""
    # Erwartete Save-Grösse(n) in Bytes (zur Plausibilitätsprüfung).
    save_sizes: tuple[int, ...] = ()

    @property
    def checkpoint_hex(self) -> str:
        """Unique-ID im Checkpoint-Ordnerformat, z.B. '0x01B50'.

        Checkpoint benennt Ordner als ``0x%05X <Titel>`` wobei die Zahl
        die Title-ID-Low >> 8 ist.
        """
        if not self.title_id_low:
            return ""
        return f"0x{int(self.title_id_low, 16) >> 8:05X}"


# Rohe NDS-Saves der Gen-4/5-Pokemon-Spiele sind 512 KiB.
_NDS_SIZE = (512 * 1024, 256 * 1024)

GAMES: tuple[GameInfo, ...] = (
    GameInfo("platinum", "Pokemon Platin", "nds", 4, save_sizes=_NDS_SIZE),
    GameInfo("heartgold", "Pokemon HeartGold", "nds", 4, save_sizes=_NDS_SIZE),
    GameInfo("soulsilver", "Pokemon SoulSilver", "nds", 4, save_sizes=_NDS_SIZE),
    GameInfo("black", "Pokemon Schwarz", "nds", 5, save_sizes=_NDS_SIZE),
    GameInfo("white", "Pokemon Weiss", "nds", 5, save_sizes=_NDS_SIZE),
    GameInfo("black2", "Pokemon Schwarz 2", "nds", 5, save_sizes=_NDS_SIZE),
    GameInfo("white2", "Pokemon Weiss 2", "nds", 5, save_sizes=_NDS_SIZE),
    GameInfo("x", "Pokemon X", "3ds", 6, "00055D00", (415232,)),
    GameInfo("y", "Pokemon Y", "3ds", 6, "00055E00", (415232,)),
    GameInfo("omega-ruby", "Pokemon Omega Rubin", "3ds", 6, "0011C400", (483328,)),
    GameInfo("alpha-sapphire", "Pokemon Alpha Saphir", "3ds", 6, "0011C500", (483328,)),
    GameInfo("sun", "Pokemon Sonne", "3ds", 7, "00164800", (441856,)),
    GameInfo("moon", "Pokemon Mond", "3ds", 7, "00175E00", (441856,)),
    GameInfo("ultra-sun", "Pokemon Ultra Sonne", "3ds", 7, "001B5000", (441856,)),
    GameInfo("ultra-moon", "Pokemon Ultra Mond", "3ds", 7, "001B5100", (441856,)),
)

GAMES_BY_KEY: dict[str, GameInfo] = {g.key: g for g in GAMES}


# --------------------------------------------------------------------- #
# Konfiguration & Zustand
# --------------------------------------------------------------------- #

def default_config_dir() -> Path:
    """Ordner für Konfiguration, Sync-Zustand und Backups."""
    return Path.home() / ".pokemon_team_analyzer"


def azahar_candidate_dirs() -> list[Path]:
    """Mögliche Azahar/Citra-Datenordner auf dieser Plattform."""
    home = Path.home()
    candidates: list[Path] = []
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support"
        candidates += [base / "Azahar", base / "azahar-emu",
                       base / "Citra", base / "Lime3DS"]
    elif sys.platform.startswith("win"):
        import os
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        candidates += [appdata / "Azahar", appdata / "azahar-emu",
                       appdata / "Citra", appdata / "Lime3DS"]
    else:
        base = home / ".local" / "share"
        candidates += [base / "azahar-emu", base / "citra-emu", base / "lime3ds-emu"]
    return [c for c in candidates if c.exists()]


def find_azahar_save(game: GameInfo) -> Path | None:
    """Sucht die 'main'-Savedatei eines 3DS-Spiels im Azahar/Citra-sdmc.

    Pfadschema:
    <datadir>/sdmc/Nintendo 3DS/<id0>/<id1>/title/00040000/<tidlow>/data/00000001/main
    """
    if game.platform != "3ds" or not game.title_id_low:
        return None
    tid = game.title_id_low.lower()
    for base in azahar_candidate_dirs():
        sdmc = base / "sdmc"
        if not sdmc.exists():
            continue
        hits = list(sdmc.glob(
            f"Nintendo 3DS/*/*/title/00040000/{tid}/data/00000001/main"))
        if hits:
            return hits[0]
    return None


@dataclass
class GameSyncConfig:
    """Pro-Spiel-Konfiguration: wo liegt der Save lokal und auf dem 3DS."""

    local_path: str = ""    # Pfad zur Save-Datei am PC (melonDS .sav / Azahar main)
    remote_path: str = ""   # FTP-Pfad auf der 3DS-SD-Karte
    enabled: bool = True


@dataclass
class SyncConfig:
    """Gesamte Sync-Konfiguration, als JSON persistiert."""

    ftp_host: str = ""
    ftp_port: int = 5000
    ftp_user: str = "anonymous"
    ftp_password: str = ""
    cloud_dir: str = ""     # optionaler Cloud-Ordner (Google Drive etc.)
    games: dict[str, GameSyncConfig] = field(default_factory=dict)

    # ----- Persistenz ----- #
    @classmethod
    def load(cls, config_dir: Path | None = None) -> "SyncConfig":
        path = (config_dir or default_config_dir()) / "sync_config.json"
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        cfg = cls(
            ftp_host=raw.get("ftp_host", ""),
            ftp_port=int(raw.get("ftp_port", 5000)),
            ftp_user=raw.get("ftp_user", "anonymous"),
            ftp_password=raw.get("ftp_password", ""),
            cloud_dir=raw.get("cloud_dir", ""),
        )
        for key, g in raw.get("games", {}).items():
            cfg.games[key] = GameSyncConfig(
                local_path=g.get("local_path", ""),
                remote_path=g.get("remote_path", ""),
                enabled=bool(g.get("enabled", True)),
            )
        return cfg

    def save(self, config_dir: Path | None = None) -> None:
        directory = config_dir or default_config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        data = {
            "ftp_host": self.ftp_host,
            "ftp_port": self.ftp_port,
            "ftp_user": self.ftp_user,
            "ftp_password": self.ftp_password,
            "cloud_dir": self.cloud_dir,
            "games": {
                key: {"local_path": g.local_path,
                      "remote_path": g.remote_path,
                      "enabled": g.enabled}
                for key, g in self.games.items()
            },
        }
        (directory / "sync_config.json").write_text(
            json.dumps(data, indent=2), encoding="utf-8")

    def game(self, key: str) -> GameSyncConfig:
        if key not in self.games:
            self.games[key] = GameSyncConfig()
        return self.games[key]


# --------------------------------------------------------------------- #
# FTP-Client für ftpd auf dem 3DS
# --------------------------------------------------------------------- #

class FTPError(Exception):
    """Eigene Fehlerklasse für FTP-Probleme (freundliche Meldungen)."""


class ThreeDSFTP:
    """Dünner Wrapper um ftplib.FTP, zugeschnitten auf ftpd (3DS).

    ftpd ist ein minimaler Server: kein TLS, anonymer Login, MDTM wird
    unterstützt. Pfade sind UNIX-artig relativ zur SD-Wurzel.
    """

    def __init__(self, host: str, port: int = 5000,
                 user: str = "anonymous", password: str = "",
                 timeout: float = 10.0) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self._ftp: FTP | None = None

    # ----- Verbindung ----- #
    def connect(self) -> None:
        ftp = FTP()
        try:
            ftp.connect(self.host, self.port, timeout=self.timeout)
            ftp.login(self.user, self.password)
        except (OSError, socket.timeout, error_perm) as exc:
            raise FTPError(
                f"Keine Verbindung zu {self.host}:{self.port} - läuft ftpd "
                f"auf dem 3DS und sind beide Geräte im selben WLAN? ({exc})"
            ) from exc
        self._ftp = ftp

    def close(self) -> None:
        if self._ftp is not None:
            try:
                self._ftp.quit()
            except Exception:
                pass
            self._ftp = None

    def __enter__(self) -> "ThreeDSFTP":
        self.connect()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @property
    def ftp(self) -> FTP:
        if self._ftp is None:
            raise FTPError("Nicht verbunden - zuerst connect() aufrufen.")
        return self._ftp

    # ----- Operationen ----- #
    def list_dir(self, path: str) -> list[tuple[str, bool]]:
        """Listet ein Verzeichnis: [(name, is_dir), ...]."""
        entries: list[tuple[str, bool]] = []
        try:
            for name, facts in self.ftp.mlsd(path):
                if name in (".", ".."):
                    continue
                entries.append((name, facts.get("type") == "dir"))
        except (error_perm, OSError):
            # Fallback ohne MLSD: NLST + cwd-Probe
            try:
                names = self.ftp.nlst(path)
            except (error_perm, OSError) as exc:
                raise FTPError(f"Verzeichnis nicht lesbar: {path} ({exc})") from exc
            for full in names:
                name = full.rsplit("/", 1)[-1]
                if name in (".", ".."):
                    continue
                is_dir = False
                try:
                    self.ftp.cwd(full if full.startswith("/") else f"{path.rstrip('/')}/{name}")
                    self.ftp.cwd("/")
                    is_dir = True
                except (error_perm, OSError):
                    pass
                entries.append((name, is_dir))
        return sorted(entries, key=lambda e: (not e[1], e[0].lower()))

    def mtime(self, path: str) -> float | None:
        """Änderungszeit (Unix-Timestamp, UTC) via MDTM, oder None."""
        try:
            resp = self.ftp.sendcmd(f"MDTM {path}")
        except (error_perm, OSError):
            return None
        # Antwort: "213 YYYYMMDDHHMMSS"
        stamp = resp.split()[-1].strip()
        try:
            dt = datetime.strptime(stamp[:14], "%Y%m%d%H%M%S")
            return dt.replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            return None

    def exists(self, path: str) -> bool:
        try:
            self.ftp.size(path)
            return True
        except (error_perm, OSError):
            return self.mtime(path) is not None

    def download(self, path: str) -> bytes:
        chunks: list[bytes] = []
        try:
            self.ftp.retrbinary(f"RETR {path}", chunks.append)
        except (error_perm, OSError) as exc:
            raise FTPError(f"Download fehlgeschlagen: {path} ({exc})") from exc
        return b"".join(chunks)

    def upload(self, path: str, data: bytes) -> None:
        import io
        # Zielordner ggf. anlegen (rekursiv).
        parent = path.rsplit("/", 1)[0]
        if parent:
            self._makedirs(parent)
        try:
            self.ftp.storbinary(f"STOR {path}", io.BytesIO(data))
        except (error_perm, OSError) as exc:
            raise FTPError(f"Upload fehlgeschlagen: {path} ({exc})") from exc

    def _makedirs(self, path: str) -> None:
        parts = [p for p in path.split("/") if p]
        current = ""
        for part in parts:
            current += "/" + part
            try:
                self.ftp.mkd(current)
            except (error_perm, OSError):
                pass  # existiert vermutlich schon

    def find_checkpoint_dir(self, game: GameInfo,
                            base: str = "/3ds/Checkpoint/saves") -> str | None:
        """Sucht den Checkpoint-Ordner eines 3DS-Spiels (z.B. '0x01B50 ...')."""
        hexid = game.checkpoint_hex.lower()
        if not hexid:
            return None
        try:
            for name, is_dir in self.list_dir(base):
                if is_dir and name.lower().startswith(hexid):
                    return f"{base}/{name}"
        except FTPError:
            return None
        return None

    def newest_checkpoint_backup(self, game_dir: str) -> str | None:
        """Neuester Backup-Unterordner, der eine 'main'-Datei enthält."""
        best: tuple[float, str] | None = None
        for name, is_dir in self.list_dir(game_dir):
            if not is_dir:
                continue
            main_path = f"{game_dir}/{name}/main"
            ts = self.mtime(main_path)
            if ts is None:
                continue
            if best is None or ts > best[0]:
                best = (ts, main_path)
        return best[1] if best else None


# --------------------------------------------------------------------- #
# Sync-Engine: Quellen abstrahieren, neuester gewinnt, Backups
# --------------------------------------------------------------------- #

@dataclass
class SaveSource:
    """Eine Seite der Synchronisation (PC, 3DS oder Cloud).

    Die Engine arbeitet nur mit dieser Abstraktion - dadurch ist die
    Konfliktlogik ohne FTP/Dateisystem testbar.
    """

    name: str
    read: Callable[[], bytes | None]      # None = existiert (noch) nicht
    write: Callable[[bytes], None]
    get_mtime: Callable[[], float | None]


@dataclass
class SyncResult:
    """Ergebnis eines Sync-Vorgangs für die Anzeige im GUI."""

    game_key: str
    winner: str = ""                 # Name der neuesten Quelle
    updated: list[str] = field(default_factory=list)
    backed_up: list[str] = field(default_factory=list)
    skipped: bool = False            # True wenn alles identisch war
    messages: list[str] = field(default_factory=list)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SyncEngine:
    """Führt die eigentliche Synchronisation durch.

    Strategie: alle Quellen lesen, Inhalte per SHA-256 vergleichen.
    Sind alle identisch -> nichts tun. Sonst gewinnt die Quelle mit dem
    neuesten Zeitstempel; jede abweichende Quelle wird vor dem
    Überschreiben gesichert.
    """

    def __init__(self, backup_dir: Path | None = None,
                 log: Callable[[str], None] | None = None) -> None:
        self.backup_dir = backup_dir or (default_config_dir() / "backups")
        self.log = log or (lambda _msg: None)

    def sync(self, game: GameInfo, sources: list[SaveSource],
             force_winner: str | None = None) -> SyncResult:
        """Synchronisiert die gegebenen Quellen.

        ``force_winner``: Name einer Quelle, die unabhängig vom
        Zeitstempel gewinnen soll (für "nur holen"/"nur senden").
        """
        result = SyncResult(game_key=game.key)

        # 1. Alle Quellen einlesen.
        contents: dict[str, bytes | None] = {}
        for src in sources:
            try:
                contents[src.name] = src.read()
            except Exception as exc:
                result.messages.append(f"{src.name}: Lesefehler ({exc})")
                contents[src.name] = None

        existing = {n: c for n, c in contents.items() if c is not None}
        if not existing:
            result.messages.append("Keine Quelle hat einen Spielstand.")
            result.skipped = True
            return result

        # Plausibilitätscheck: bekannte Save-Grössen.
        for name, data in existing.items():
            if game.save_sizes and len(data) not in game.save_sizes:
                result.messages.append(
                    f"Warnung: {name} hat unerwartete Grösse "
                    f"({len(data)} Bytes) - Sync wird trotzdem versucht.")

        # 2. Identisch? Dann fertig.
        hashes = {name: _sha256(data) for name, data in existing.items()}
        if len(set(hashes.values())) == 1 and len(existing) == len(sources):
            result.skipped = True
            result.messages.append("Alle Seiten sind bereits identisch.")
            return result

        # 3. Gewinner bestimmen.
        if force_winner is not None:
            if force_winner not in existing:
                result.messages.append(
                    f"Erzwungene Quelle '{force_winner}' hat keinen Spielstand.")
                result.skipped = True
                return result
            winner_name = force_winner
        else:
            by_name = {s.name: s for s in sources}
            def sort_key(name: str) -> float:
                ts = by_name[name].get_mtime()
                return ts if ts is not None else 0.0
            winner_name = max(existing, key=sort_key)
        winner_data = existing[winner_name]
        result.winner = winner_name
        self.log(f"[{game.title}] Neuester Stand: {winner_name}")

        # 4. Verteilen, mit Backup der Verlierer.
        for src in sources:
            if src.name == winner_name:
                continue
            current = contents.get(src.name)
            if current is not None and _sha256(current) == hashes[winner_name]:
                continue  # schon identisch
            if current is not None:
                backup_path = self._backup(game, src.name, current)
                result.backed_up.append(src.name)
                self.log(f"[{game.title}] Backup von {src.name}: {backup_path.name}")
            try:
                src.write(winner_data)
                result.updated.append(src.name)
                self.log(f"[{game.title}] {src.name} aktualisiert.")
            except Exception as exc:
                result.messages.append(f"{src.name}: Schreibfehler ({exc})")
        return result

    def _backup(self, game: GameInfo, source_name: str, data: bytes) -> Path:
        directory = self.backup_dir / game.key
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe = source_name.replace(" ", "_").replace("/", "_")
        path = directory / f"{stamp}_{safe}.sav"
        path.write_bytes(data)
        return path


# --------------------------------------------------------------------- #
# Quellen-Fabriken: Datei, Cloud, FTP
# --------------------------------------------------------------------- #

def file_source(name: str, path: Path) -> SaveSource:
    """Quelle für eine lokale Datei (melonDS .sav, Azahar main, Cloud-Kopie)."""

    def read() -> bytes | None:
        return path.read_bytes() if path.exists() else None

    def write(data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get_mtime() -> float | None:
        return path.stat().st_mtime if path.exists() else None

    return SaveSource(name=name, read=read, write=write, get_mtime=get_mtime)


def cloud_source(game: GameInfo, cloud_dir: Path) -> SaveSource:
    """Quelle im Cloud-Ordner (z.B. Google Drive Desktop-Ordner)."""
    return file_source("Cloud", cloud_dir / "pokemon_saves" / f"{game.key}.sav")


def ftp_source(game: GameInfo, ftp: ThreeDSFTP, remote_path: str,
               push_as_new_backup: bool = False) -> SaveSource:
    """Quelle auf der 3DS-SD-Karte via FTP.

    ``push_as_new_backup``: für 3DS-Spiele (Checkpoint) wird beim
    Hochladen ein NEUER Backup-Ordner ``PCSYNC_<zeit>`` angelegt statt
    das bestehende Backup zu überschreiben - so taucht der Stand in
    Checkpoint als eigener Eintrag auf und kann restored werden.
    """

    def read() -> bytes | None:
        if not ftp.exists(remote_path):
            return None
        return ftp.download(remote_path)

    def write(data: bytes) -> None:
        if push_as_new_backup:
            # remote_path zeigt auf .../<spielordner>/<backup>/main
            game_dir = remote_path.rsplit("/", 2)[0]
            stamp = time.strftime("%Y%m%d-%H%M%S")
            target = f"{game_dir}/PCSYNC_{stamp}/main"
        else:
            target = remote_path
        ftp.upload(target, data)

    def get_mtime() -> float | None:
        return ftp.mtime(remote_path)

    return SaveSource(name="3DS", read=read, write=write, get_mtime=get_mtime)


# --------------------------------------------------------------------- #
# Komfort: kompletten Sync für ein Spiel aus der Konfiguration aufbauen
# --------------------------------------------------------------------- #

def build_sources(game: GameInfo, cfg: SyncConfig,
                  ftp: ThreeDSFTP | None) -> list[SaveSource]:
    """Baut die Quellen-Liste für ein Spiel gemäss Konfiguration.

    Reihenfolge: PC (Emulator), 3DS (falls verbunden), Cloud (falls
    konfiguriert). Fehlende Konfiguration löst ValueError aus.
    """
    game_cfg = cfg.game(game.key)
    sources: list[SaveSource] = []

    if not game_cfg.local_path:
        # Für 3DS-Spiele: Azahar-Save automatisch suchen.
        auto = find_azahar_save(game)
        if auto is not None:
            game_cfg.local_path = str(auto)
    if not game_cfg.local_path:
        raise ValueError(
            f"{game.title}: kein lokaler Save-Pfad konfiguriert "
            "(im Sync-Tab unter 'Einrichten' setzen).")
    sources.append(file_source("PC", Path(game_cfg.local_path)))

    if ftp is not None:
        remote = game_cfg.remote_path
        if not remote and game.platform == "3ds":
            game_dir = ftp.find_checkpoint_dir(game)
            if game_dir:
                remote = ftp.newest_checkpoint_backup(game_dir) or ""
                game_cfg.remote_path = remote
        if not remote:
            raise ValueError(
                f"{game.title}: kein 3DS-Pfad konfiguriert. NDS-Spiele: Pfad "
                "zur .sav-Datei (TWiLight). 3DS-Spiele: zuerst in Checkpoint "
                "ein Backup anlegen, dann erneut versuchen.")
        sources.append(ftp_source(game, ftp, remote,
                                  push_as_new_backup=(game.platform == "3ds")))

    if cfg.cloud_dir:
        sources.append(cloud_source(game, Path(cfg.cloud_dir)))

    return sources


def sync_game(game_key: str, cfg: SyncConfig,
              use_ftp: bool = True,
              force_winner: str | None = None,
              log: Callable[[str], None] | None = None,
              backup_dir: Path | None = None) -> SyncResult:
    """High-Level-Einstieg: synchronisiert EIN Spiel komplett.

    Öffnet bei Bedarf die FTP-Verbindung, baut die Quellen und lässt die
    Engine laufen. Wird vom GUI (im Worker-Thread) aufgerufen.
    """
    game = GAMES_BY_KEY[game_key]
    engine = SyncEngine(backup_dir=backup_dir, log=log)

    if use_ftp and cfg.ftp_host:
        with ThreeDSFTP(cfg.ftp_host, cfg.ftp_port,
                        cfg.ftp_user, cfg.ftp_password) as ftp:
            sources = build_sources(game, cfg, ftp)
            return engine.sync(game, sources, force_winner=force_winner)
    sources = build_sources(game, cfg, None)
    return engine.sync(game, sources, force_winner=force_winner)
