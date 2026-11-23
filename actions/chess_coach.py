"""Treinador de xadrez do JARVIS.

Olha o tabuleiro na tela (captura rapida com mss), descobre a posicao por
reconhecimento de imagem, pede a melhor jogada ao Stockfish e FALA a jogada
exata ("Cavalo gê um para éfe três") assim que for a vez do jogador.

Nao precisa "treinar" modelo nenhum: na primeira vez o JARVIS aprende o visual
das pecas do site a partir da posicao inicial (perfil salvo em disco).

Uso pretendido: treino, analise e partidas contra o computador/bots.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

try:  # python-chess so e usado para as regras; instalado sob demanda
    import chess
except ImportError:  # pragma: no cover
    chess = None

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "memory" / "chess_coach"
CONFIG_PATH = DATA_DIR / "config.json"

SQ = 48            # tamanho normalizado de cada casa
_CORNER = 9        # cantos ignorados (coordenadas a-h / 1-8 desenhadas na casa)
_DIFF = 38         # diferenca minima em relacao ao fundo da casa
_MIN_AREA = 0.07   # fracao minima da casa ocupada para existir peca
_MIN_IOU = 0.50    # semelhanca minima com algum molde de peca
_FRAME_DELAY = 0.04
_RESYNC_AFTER = 1.5
_BACK_RANK = "rnbqkbnr"


# --------------------------------------------------------------------------
# Dependencias
# --------------------------------------------------------------------------

def _ensure_chess() -> bool:
    global chess
    if chess is not None:
        return True
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "chess", "--quiet",
             "--disable-pip-version-check"],
            capture_output=True, timeout=180,
        )
        import chess as _chess
        chess = _chess
        return True
    except Exception:
        return False


def _load_cfg() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cfg(cfg: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _find_engine() -> str | None:
    cfg = _load_cfg()
    candidates = [cfg.get("engine_path"), shutil.which("stockfish")]
    tools = ROOT / "tools" / "stockfish"
    if tools.exists():
        candidates += [str(p) for p in tools.rglob("stockfish*.exe")]
    for cand in candidates:
        if cand and Path(cand).exists():
            return str(cand)
    return None


# --------------------------------------------------------------------------
# Leitura do tabuleiro
# --------------------------------------------------------------------------

def _cell(img: np.ndarray, r: int, c: int) -> np.ndarray:
    h, w = img.shape[:2]
    return img[round(r * h / 8):round((r + 1) * h / 8),
               round(c * w / 8):round((c + 1) * w / 8)]


def _rc_to_fr(r: int, c: int, white_bottom: bool) -> tuple[int, int]:
    """(linha, coluna) na imagem -> (coluna a..h = 0..7, fileira 1..8 = 0..7)."""
    return (c, 7 - r) if white_bottom else (7 - c, r)


def _analyze_square(img: np.ndarray):
    """Silhueta da peca (independente da cor da casa), area e brilho interno."""
    img = cv2.resize(img, (SQ, SQ), interpolation=cv2.INTER_AREA)
    k = 4
    patches = np.concatenate([
        img[:k, :k].reshape(-1, 3), img[:k, -k:].reshape(-1, 3),
        img[-k:, :k].reshape(-1, 3), img[-k:, -k:].reshape(-1, 3),
    ])
    bg = np.median(patches, axis=0)
    diff = np.abs(img.astype(np.int16) - bg.astype(np.int16)).max(axis=2)
    mask = (diff > _DIFF).astype(np.uint8) * 255
    c = _CORNER
    mask[:c, :c] = 0
    mask[:c, -c:] = 0
    mask[-c:, :c] = 0
    mask[-c:, -c:] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    sil = np.zeros((SQ, SQ), np.uint8)
    for cnt in contours:
        if cv2.contourArea(cnt) >= 12:
            cv2.drawContours(sil, [cnt], -1, 255, -1)
    area = float((sil > 0).mean())
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    inner = cv2.erode(sil, np.ones((5, 5), np.uint8)) > 0
    if not inner.any():
        inner = sil > 0
    fill = float(gray[inner].mean()) if inner.any() else 0.0
    return sil.astype(np.float32) / 255.0, area, fill


def _start_piece(file_: int, rank: int) -> str | None:
    if rank == 0:
        return _BACK_RANK[file_].upper()
    if rank == 1:
        return "P"
    if rank == 6:
        return "p"
    if rank == 7:
        return _BACK_RANK[file_]
    return None


def learn_templates(board_img: np.ndarray, white_bottom: bool = True):
    """Aprende o visual das pecas a partir da posicao inicial na tela.

    Retorna (templates, mensagem_de_erro). Em sucesso a mensagem e ''.
    """
    sums = {t: np.zeros((SQ, SQ), np.float32) for t in "pnbrqk"}
    counts = {t: 0 for t in "pnbrqk"}
    white_fill, black_fill = [], []
    empty_ok = 0
    for r in range(8):
        for c in range(8):
            sil, area, fill = _analyze_square(_cell(board_img, r, c))
            file_, rank = _rc_to_fr(r, c, white_bottom)
            sym = _start_piece(file_, rank)
            if sym is None:
                if area < _MIN_AREA:
                    empty_ok += 1
                continue
            if area < _MIN_AREA:
                return None, ("Nao encontrei as pecas nas casas esperadas. "
                              "Confira se o tabuleiro esta na posicao inicial e "
                              "se a regiao marcada pega so o tabuleiro.")
            t = sym.lower()
            sums[t] += sil
            counts[t] += 1
            (white_fill if sym.isupper() else black_fill).append(fill)
    if empty_ok < 30:
        return None, ("As casas do meio nao estao vazias. Deixe o tabuleiro na "
                      "posicao inicial, sem setas ou marcacoes por cima.")
    types = np.stack([sums[t] / counts[t] for t in "pnbrqk"])
    tpl = {
        "types": types,
        "w": float(np.mean(white_fill)),
        "b": float(np.mean(black_fill)),
        "white_bottom": bool(white_bottom),
    }
    start = {sq: p for sq, p in chess.Board().piece_map().items()}
    if read_board(board_img, tpl, white_bottom) != start:
        return None, ("Nao consegui reconhecer as pecas desse tabuleiro. "
                      "Tente um tema de pecas mais simples ou marque a regiao de novo.")
    return tpl, ""


def read_board(img: np.ndarray, tpl: dict, white_bottom: bool = True) -> dict:
    pt = {"p": chess.PAWN, "n": chess.KNIGHT, "b": chess.BISHOP,
          "r": chess.ROOK, "q": chess.QUEEN, "k": chess.KING}
    order = "pnbrqk"
    pieces = {}
    for r in range(8):
        for c in range(8):
            sil, area, fill = _analyze_square(_cell(img, r, c))
            if area < _MIN_AREA:
                continue
            best_i, best = -1, 0.0
            for i, t in enumerate(tpl["types"]):
                union = float(np.maximum(sil, t).sum())
                score = float(np.minimum(sil, t).sum()) / union if union else 0.0
                if score > best:
                    best_i, best = i, score
            if best < _MIN_IOU:
                continue
            white = abs(fill - tpl["w"]) <= abs(fill - tpl["b"])
            file_, rank = _rc_to_fr(r, c, white_bottom)
            pieces[chess.square(file_, rank)] = chess.Piece(pt[order[best_i]], white)
    return pieces


def _save_tpl(profile: str, tpl: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    np.savez(DATA_DIR / f"templates_{profile}.npz", types=tpl["types"],
             w=tpl["w"], b=tpl["b"])


def _load_tpl(profile: str) -> dict | None:
    path = DATA_DIR / f"templates_{profile}.npz"
    if not path.exists():
        return None
    try:
        d = np.load(path)
        return {"types": d["types"], "w": float(d["w"]), "b": float(d["b"])}
    except Exception:
        return None


# --------------------------------------------------------------------------
# Acompanhamento da partida (independente de captura de tela)
# --------------------------------------------------------------------------

class Tracker:
    """Mantem a partida a partir de leituras sucessivas do tabuleiro."""

    def __init__(self, my_color: bool):
        self.color = my_color
        self.board = None
        self.bad_since = None

    def _resync(self, reading: dict) -> bool:
        kings = [p for p in reading.values() if p.piece_type == chess.KING]
        if sum(p.color for p in kings) != 1 or len(kings) != 2:
            return False
        nb = chess.Board(None)
        nb.set_piece_map(reading)
        nb.castling_rights = 0
        nb.turn = self.color
        if not nb.is_valid():
            nb.turn = not self.color
            if not nb.is_valid():
                return False
        self.board = nb
        self.bad_since = None
        return True

    @staticmethod
    def _match(b, reading: dict):
        for m in list(b.legal_moves):
            b.push(m)
            hit = b.piece_map() == reading
            b.pop()
            if hit:
                return [m]
        for m in list(b.legal_moves):
            b.push(m)
            for m2 in list(b.legal_moves):
                b.push(m2)
                hit = b.piece_map() == reading
                b.pop()
                if hit:
                    b.pop()
                    return [m, m2]
            b.pop()
        return None

    def feed(self, reading: dict, now: float) -> str:
        """'unchanged' | 'advanced' | 'pending'."""
        start = chess.Board().piece_map()
        b = self.board
        if b is None:
            if reading == start:
                self.board = chess.Board()
                return "advanced"
            return "advanced" if self._resync(reading) else "pending"
        if reading == b.piece_map():
            self.bad_since = None
            return "unchanged"
        if reading == start and b.move_stack:
            self.board = chess.Board()
            self.bad_since = None
            return "advanced"
        moves = self._match(b, reading)
        if moves:
            for m in moves:
                b.push(m)
            self.bad_since = None
            return "advanced"
        if self.bad_since is None:
            self.bad_since = now
        elif now - self.bad_since > _RESYNC_AFTER:
            return "advanced" if self._resync(reading) else "pending"
        return "pending"

    def my_turn(self) -> bool:
        return (self.board is not None and self.board.turn == self.color
                and not self.board.is_game_over())


# --------------------------------------------------------------------------
# Fala
# --------------------------------------------------------------------------

_FILE_SAY = dict(zip("abcdefgh", ["á", "bê", "cê", "dê", "ê", "éfe", "gê", "agá"]))
_RANK_SAY = ["um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito"]


def _piece_names():
    return {chess.PAWN: "peão", chess.KNIGHT: "cavalo", chess.BISHOP: "bispo",
            chess.ROOK: "torre", chess.QUEEN: "dama", chess.KING: "rei"}


def _sq_say(sq: int) -> str:
    name = chess.square_name(sq)
    return f"{_FILE_SAY[name[0]]} {_RANK_SAY[int(name[1]) - 1]}"


def describe(board, move) -> tuple[str, str]:
    """(texto falado, texto para o log) da jogada, antes de executa-la."""
    names = _piece_names()
    if board.is_castling(move):
        side = "pequeno" if board.is_kingside_castling(move) else "grande"
        spoken = text = f"Roque {side}"
    else:
        piece = board.piece_at(move.from_square)
        cap = board.is_capture(move)
        verb = "captura" if cap else "para"
        name = names[piece.piece_type].capitalize()
        spoken = f"{name} {_sq_say(move.from_square)} {verb} {_sq_say(move.to_square)}"
        text = (f"{name} {chess.square_name(move.from_square)} "
                f"{'x' if cap else '-'} {chess.square_name(move.to_square)}")
        if move.promotion:
            extra = f", promove a {names[move.promotion]}"
            spoken += extra
            text += extra
        if board.is_en_passant(move):
            spoken += ", en passant"
            text += " (en passant)"
    board.push(move)
    try:
        if board.is_checkmate():
            spoken += ", xeque-mate"
            text += " — xeque-mate"
        elif board.is_check():
            spoken += ", xeque"
            text += " — xeque"
    finally:
        board.pop()
    return spoken, text


_PS_SCRIPT = r"""
[Console]::InputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet,
      [System.Speech.Synthesis.VoiceAge]::NotSet, 0,
      [Globalization.CultureInfo]::GetCultureInfo('pt-BR')) } catch {}
$s.Rate = 3
while (($line = [Console]::In.ReadLine()) -ne $null) {
  if ($line.Length -eq 0) { continue }
  $s.SpeakAsyncCancelAll()
  $null = $s.SpeakAsync($line)
}
"""


class _Speaker:
    """Voz local persistente (SAPI): latencia de milissegundos, sem rede."""

    def __init__(self, mode: str = "local", gemini_speak=None):
        self.mode = mode
        self.gemini_speak = gemini_speak
        self.proc = None
        if mode == "local" and os.name == "nt":
            try:
                self.proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-NoLogo", "-NonInteractive",
                     "-Command", _PS_SCRIPT],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, creationflags=0x08000000,
                )
            except Exception:
                self.proc = None

    def say(self, text: str) -> None:
        if self.mode == "gemini" and callable(self.gemini_speak):
            try:
                self.gemini_speak(f"Diga em voz alta apenas isto, sem comentar: {text}")
            except Exception:
                pass
            return
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write((text + "\n").encode("utf-8"))
                self.proc.stdin.flush()
            except Exception:
                pass

    def close(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.close()
                self.proc.terminate()
            except Exception:
                pass


def _beep() -> None:
    try:
        import sounddevice as sd
        t = np.linspace(0, 0.12, int(44100 * 0.12), False)
        sd.play((0.25 * np.sin(2 * np.pi * 880 * t)).astype(np.float32), 44100)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Motor UCI minimo (sem asyncio, para nao brigar com o loop do JARVIS)
# --------------------------------------------------------------------------

class _UCI:
    def __init__(self, path: str, elo: int | None = None):
        flags = 0x08000000 if os.name == "nt" else 0
        self.p = subprocess.Popen(
            [path], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1, creationflags=flags,
        )
        self._send("uci")
        self._wait("uciok")
        cores = os.cpu_count() or 2
        self._send(f"setoption name Threads value {max(1, min(4, cores - 1))}")
        self._send("setoption name Hash value 64")
        if elo:
            self._send("setoption name UCI_LimitStrength value true")
            self._send(f"setoption name UCI_Elo value {int(elo)}")
        self._send("isready")
        self._wait("readyok")

    def _send(self, line: str) -> None:
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()

    def _wait(self, token: str) -> str:
        for line in self.p.stdout:
            if line.startswith(token):
                return line
        raise RuntimeError("motor de xadrez encerrou")

    def best(self, fen: str, movetime_ms: int):
        self._send(f"position fen {fen}")
        self._send(f"go movetime {int(movetime_ms)}")
        score = None
        for line in self.p.stdout:
            if line.startswith("info") and " score " in line:
                parts = line.split()
                try:
                    i = parts.index("score")
                    score = (parts[i + 1], int(parts[i + 2]))
                except (ValueError, IndexError):
                    pass
            elif line.startswith("bestmove"):
                mv = line.split()[1]
                return (None if mv == "(none)" else mv), score
        raise RuntimeError("motor de xadrez encerrou")

    def close(self) -> None:
        try:
            self._send("quit")
            self.p.wait(timeout=2)
        except Exception:
            try:
                self.p.kill()
            except Exception:
                pass


def _cursor() -> tuple[int, int]:
    import ctypes
    import ctypes.wintypes
    pt = ctypes.wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


# --------------------------------------------------------------------------
# Sessao
# --------------------------------------------------------------------------

class _Session(threading.Thread):
    def __init__(self, color, profile, think_ms, elo, voice, recalibrate,
                 player=None, gemini_speak=None):
        super().__init__(daemon=True, name="chess-coach")
        self.color = color
        self.profile = profile
        self.think_ms = think_ms
        self.elo = elo
        self.voice = voice
        self.recalibrate = recalibrate
        self.player = player
        self.stop_event = threading.Event()
        self.speaker = _Speaker(voice, gemini_speak)
        self.status = "iniciando"
        self.last_advice = ""

    def log(self, msg: str) -> None:
        if self.player is not None:
            try:
                self.player.write_log(f"JARVIS: {msg}")
            except Exception:
                pass

    def say(self, spoken: str, shown: str | None = None) -> None:
        self.speaker.say(spoken)
        self.log(shown or spoken)

    def _fail(self, msg: str) -> None:
        self.status = "erro: " + msg
        self.say(msg)

    def _wait_point(self, timeout: float = 60.0):
        """Espera o mouse se mover e depois ficar parado ~1,8 s."""
        origin = _cursor()
        anchor, since = origin, time.monotonic()
        moved = False
        t0 = time.monotonic()
        time.sleep(0.8)
        while time.monotonic() - t0 < timeout and not self.stop_event.is_set():
            cur = _cursor()
            if not moved and (abs(cur[0] - origin[0]) > 25 or abs(cur[1] - origin[1]) > 25):
                moved = True
            if abs(cur[0] - anchor[0]) > 4 or abs(cur[1] - anchor[1]) > 4:
                anchor, since = cur, time.monotonic()
            elif moved and time.monotonic() - since >= 1.8:
                return cur
            time.sleep(0.05)
        return None

    def _calibrate_region(self, cfg: dict):
        self.say("Ponha o mouse no canto superior esquerdo do tabuleiro e deixe parado.",
                 "Marque o canto superior esquerdo do tabuleiro.")
        p1 = self._wait_point()
        if p1 is None:
            return None
        _beep()
        self.say("Agora no canto inferior direito.", "Marque o canto inferior direito.")
        p2 = self._wait_point()
        if p2 is None:
            return None
        _beep()
        left, top = min(p1[0], p2[0]), min(p1[1], p2[1])
        w, h = abs(p2[0] - p1[0]), abs(p2[1] - p1[1])
        if min(w, h) < 200:
            return None
        side = (w + h) // 2
        region = [left, top, side, side]
        cfg.setdefault("regions", {})[self.profile] = region
        _save_cfg(cfg)
        return region

    def run(self) -> None:
        try:
            self._run()
        except Exception as exc:  # nunca derrubar o JARVIS
            self._fail(f"O treinador de xadrez parou: {exc}")
        finally:
            self.speaker.close()
            if not self.status.startswith("erro"):
                self.status = "parado"

    def _run(self) -> None:
        import mss
        if not _ensure_chess():
            return self._fail("Não consegui instalar a biblioteca de xadrez.")
        engine_path = _find_engine()
        if not engine_path:
            return self._fail("Não encontrei o Stockfish. Coloque o stockfish ponto exe "
                              "na pasta tools stockfish do Jarvis.")
        cfg = _load_cfg()
        region = (cfg.get("regions") or {}).get(self.profile)
        tpl = None if self.recalibrate else _load_tpl(self.profile)
        white_bottom = self.color == chess.WHITE
        if self.recalibrate or not region:
            self.status = "calibrando"
            region = self._calibrate_region(cfg)
            if region is None:
                return self._fail("Não consegui marcar o tabuleiro. Tente de novo.")
            tpl = None
        sct = mss.mss()
        mon = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}

        def grab():
            return np.ascontiguousarray(np.asarray(sct.grab(mon))[:, :, :3])

        if tpl is None:
            self.status = "aprendendo"
            self.say("Deixe o tabuleiro na posição inicial. Aprendendo as peças.")
            time.sleep(1.2)
            tpl, err = learn_templates(grab(), white_bottom)
            if tpl is None:
                return self._fail(err)
            _save_tpl(self.profile, tpl)
        engine = _UCI(engine_path, self.elo)
        tracker = Tracker(self.color)
        try:
            side = "brancas" if self.color == chess.WHITE else "pretas"
            self.status = "ativo"
            self.say(f"Pronto. Você joga de {side}.")
            prev_small, last_key, last_reading, stable = None, None, {}, 0
            handled, pending, spoken_fen = None, False, None
            while not self.stop_event.is_set():
                shot = grab()
                small = cv2.resize(shot, (64, 64), interpolation=cv2.INTER_AREA).astype(np.int16)
                if (prev_small is not None and last_key is not None
                        and float(np.abs(small - prev_small).mean()) < 0.5):
                    stable += 1
                else:
                    last_reading = read_board(shot, tpl, white_bottom)
                    key = frozenset((s, p.symbol()) for s, p in last_reading.items())
                    stable = stable + 1 if key == last_key else 1
                    last_key = key
                prev_small = small
                if stable >= 2 and (last_key != handled or pending):
                    handled = last_key
                    result = tracker.feed(last_reading, time.monotonic())
                    pending = result == "pending"
                    if result == "advanced" and tracker.my_turn():
                        fen = tracker.board.fen()
                        if fen != spoken_fen:
                            spoken_fen = fen
                            self._advise(engine, tracker.board)
                    elif (result == "advanced" and tracker.board is not None
                          and tracker.board.is_checkmate()):
                        self.say("Xeque-mate. Fim de jogo.")
                time.sleep(_FRAME_DELAY)
        finally:
            engine.close()

    def _advise(self, engine, board) -> None:
        t0 = time.monotonic()
        uci, score = engine.best(board.fen(), self.think_ms)
        if not uci:
            return
        move = chess.Move.from_uci(uci)
        if move not in board.legal_moves:
            return
        spoken, text = describe(board, move)
        self.last_advice = text
        extra = ""
        if score:
            kind, val = score
            extra = f" (mate em {abs(val)})" if kind == "mate" else f" ({val / 100:+.2f})"
        self.say(spoken, f"Jogue: {text}{extra}  [{time.monotonic() - t0:.2f}s]")


_SESSION: _Session | None = None
_LOCK = threading.Lock()


def _hint_once(color, profile, think_ms, elo, voice, player, gemini_speak) -> str:
    import mss
    if not _ensure_chess():
        return "Não consegui instalar a biblioteca de xadrez."
    engine_path = _find_engine()
    cfg = _load_cfg()
    region = (cfg.get("regions") or {}).get(profile)
    tpl = _load_tpl(profile)
    if not engine_path or not region or tpl is None:
        return "Ainda não calibrei o tabuleiro. Use a ação start primeiro."
    white_bottom = color == chess.WHITE
    mon = {"left": region[0], "top": region[1], "width": region[2], "height": region[3]}
    with mss.mss() as sct:
        img = np.ascontiguousarray(np.asarray(sct.grab(mon))[:, :, :3])
    reading = read_board(img, tpl, white_bottom)
    tracker = Tracker(color)
    tracker.board = None
    if tracker.feed(reading, time.monotonic()) == "pending" or tracker.board is None:
        return "Não consegui ler uma posição válida no tabuleiro."
    tracker.board.turn = color
    engine = _UCI(engine_path, elo)
    try:
        uci, _ = engine.best(tracker.board.fen(), think_ms)
    finally:
        engine.close()
    if not uci:
        return "Não há jogada possível nessa posição."
    spoken, text = describe(tracker.board, chess.Move.from_uci(uci))
    _Speaker(voice, gemini_speak).say(spoken)
    return f"Melhor jogada: {text}."


def chess_coach(parameters: dict | None = None, player=None, speak=None) -> str:
    global _SESSION
    params = parameters or {}
    action = str(params.get("action") or "start").lower()
    if not _ensure_chess():
        return "Não consegui instalar a biblioteca python-chess (pip install chess)."
    color = chess.BLACK if str(params.get("color") or "white").lower() in ("black", "pretas", "preto") else chess.WHITE
    profile = (str(params.get("profile") or "default").strip() or "default")[:32]
    think_ms = int(max(50, min(3000, float(params.get("think_ms") or 150))))
    elo = params.get("elo")
    elo = int(max(1320, min(3190, float(elo)))) if elo else None
    voice = "gemini" if str(params.get("voice") or "local").lower() == "gemini" else "local"

    with _LOCK:
        if action == "stop":
            if _SESSION and _SESSION.is_alive():
                _SESSION.stop_event.set()
                return "Treinador de xadrez desligado."
            return "O treinador de xadrez não estava ligado."
        if action == "status":
            if _SESSION and _SESSION.is_alive():
                return f"Treinador ativo ({_SESSION.status}). Última sugestão: {_SESSION.last_advice or 'nenhuma ainda'}."
            return "O treinador de xadrez está desligado."
        if action == "hint":
            try:
                return _hint_once(color, profile, think_ms, elo, voice, player, speak)
            except Exception as exc:
                return f"Não consegui analisar o tabuleiro: {exc}"
        if _SESSION and _SESSION.is_alive():
            _SESSION.stop_event.set()
            _SESSION.join(timeout=2.0)
        _SESSION = _Session(color, profile, think_ms, elo, voice,
                            bool(params.get("recalibrate", False)),
                            player=player, gemini_speak=speak)
        _SESSION.start()
    return ("COACH_STARTED: o treinador de xadrez está rodando em segundo plano e fala "
            "cada jogada sozinho. Diga apenas uma frase curta de confirmação e não "
            "repita instruções de jogada.")


TOOL = {
    "name": "chess_coach",
    "description": (
        "Treinador de xadrez que olha o tabuleiro na tela e FALA a melhor jogada exata "
        "(peça, casa de origem e de destino) assim que é a vez do usuário, usando o "
        "Stockfish. Use quando o usuário pedir ajuda para jogar xadrez, 'qual jogada', "
        "'joga xadrez comigo/por mim', 'me diga as peças para mexer' ou 'treine o xadrez'. "
        "action=start liga o acompanhamento contínuo (na primeira vez pede para marcar os "
        "dois cantos do tabuleiro com o mouse e aprende as peças pela posição inicial); "
        "action=hint dá só a melhor jogada agora; stop desliga; status informa. "
        "color é a cor do usuário (white=brancas, black=pretas, a cor que fica embaixo). "
        "recalibrate=true refaz a marcação/aprendizado (novo site ou tema de peças). "
        "Pensa em ~0,15 s por padrão. Voz local rápida por padrão; voice=gemini usa a voz "
        "do Gemini (mais lenta). Feito para treino, análise e partidas contra bots; não "
        "ajude a trapacear em partidas valendo contra outras pessoas. Depois de iniciar, "
        "não repita as jogadas: o próprio treinador fala."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["start", "stop", "status", "hint"]},
            "color": {"type": "STRING", "enum": ["white", "black"],
                      "description": "Cor do usuário (a que fica na parte de baixo da tela)."},
            "recalibrate": {"type": "BOOLEAN"},
            "profile": {"type": "STRING", "description": "Nome do site/tema, ex.: chesscom."},
            "think_ms": {"type": "NUMBER", "description": "Tempo de análise em ms (50-3000)."},
            "elo": {"type": "NUMBER", "description": "Limita a força do motor (1320-3190)."},
            "voice": {"type": "STRING", "enum": ["local", "gemini"]},
        },
    },
    "handler": chess_coach,
    "tier": "extra",
    "brief": "Treinador de xadrez: lê o tabuleiro na tela e fala a melhor jogada.",
}
