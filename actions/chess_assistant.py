"""
Chess assistant: Jarvis olha o tabuleiro na tela, acha a melhor jogada com o
Stockfish local, FALA a jogada e desenha uma seta sobre o tabuleiro.

Tudo roda localmente (sem chamada de modelo): leitura por comparação de imagens
(OpenCV), jogada pelo Stockfish (python-chess) e voz pelo SAPI do Windows.

Uso (o Jarvis chama a ferramenta `chess_assistant`):
    action="calibrate"  bottom_color="white"|"black"   1x por site/tema de peças
    action="start"                                    fica olhando a tela
    action="stop" / "status"

Use contra bots, treino ou análise. Contra pessoas em sites online isso é
trapaça e leva a banimento.
"""
from __future__ import annotations

import io
import json
import os
import queue
import shutil
import threading
import time
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "memory" / "chess_assistant"
_CFG = _DATA / "config.json"
_TPL = _DATA / "templates.npz"

CELL = 64     # cada casa é reduzida para 64x64
PAD = 6       # borda cortada de cada casa (tira coordenadas/bordas)
SIZE = 32     # tamanho do vetor de comparação

_NOMES = {1: "peão", 2: "cavalo", 3: "bispo", 4: "torre", 5: "dama", 6: "rei"}


def _chess():
    import chess
    import chess.engine
    return chess


# --------------------------------------------------------------------------- visão
def sq_from_rc(r, c, white_bottom):
    ch = _chess()
    return ch.square(c, 7 - r) if white_bottom else ch.square(7 - c, r)


def rc_from_sq(sq, white_bottom):
    ch = _chess()
    f, rk = ch.square_file(sq), ch.square_rank(sq)
    return (7 - rk, f) if white_bottom else (rk, 7 - f)


def cells(board_bgr):
    """Imagem do tabuleiro (qualquer tamanho) -> 64 recortes em cinza (índice r*8+c)."""
    import cv2
    img = cv2.resize(board_bgr, (8 * CELL, 8 * CELL), interpolation=cv2.INTER_AREA)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return [g[r * CELL + PAD:(r + 1) * CELL - PAD, c * CELL + PAD:(c + 1) * CELL - PAD]
            for r in range(8) for c in range(8)]


def feat(patch):
    import cv2
    p = cv2.resize(patch, (SIZE, SIZE), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    p -= p.mean()
    return p / (np.linalg.norm(p) + 1e-6)


def energy(patch):
    import cv2
    inner = patch[10:-10, 10:-10]
    gx = cv2.Sobel(inner, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(inner, cv2.CV_32F, 0, 1)
    return float(np.mean(np.abs(gx) + np.abs(gy)))


def build_templates(board_bgr, white_bottom):
    """Aprende a aparência das 12 peças a partir da posição INICIAL visível."""
    import cv2
    ch = _chess()
    cs = cells(board_bgr)
    start = ch.Board()
    pieces, empties = [], {0: [], 1: []}
    for r in range(8):
        for c in range(8):
            sq = sq_from_rc(r, c, white_bottom)
            col = (ch.square_file(sq) + ch.square_rank(sq)) % 2  # 0 escura, 1 clara
            p = start.piece_at(sq)
            patch = cs[r * 8 + c]
            if p:
                pieces.append((p.symbol(), patch, col))
            elif 2 <= ch.square_rank(sq) <= 5:
                empties[col].append(patch)
    bg = {k: np.median(np.stack(v), axis=0).astype(np.uint8) for k, v in empties.items()}
    e_empty = max(energy(p) for v in empties.values() for p in v)
    e_piece = min(energy(p) for _, p, _ in pieces)
    thr = (e_empty + e_piece) / 2 if e_piece > e_empty else e_piece * 0.5

    labels, vecs = [], []
    for sym, patch, col in pieces:
        labels.append(sym)
        vecs.append(feat(patch))
        # variante da mesma peça sobre a cor de casa oposta (rei/dama só aparecem em uma cor)
        mask = (np.abs(patch.astype(int) - bg[col].astype(int)) > 20).astype(np.uint8)
        mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
        var = np.where(mask > 0, patch, bg[1 - col]).astype(np.uint8)
        labels.append(sym)
        vecs.append(feat(var))
    return np.stack(vecs), np.array(labels), thr


def read_position(board_bgr, T, L, thr, white_bottom):
    cs = cells(board_bgr)
    F = np.stack([feat(p) for p in cs])
    best = (F @ T.T).argmax(1)
    out = {}
    for i, p in enumerate(cs):
        if energy(p) >= thr:
            r, c = divmod(i, 8)
            out[sq_from_rc(r, c, white_bottom)] = str(L[best[i]])
    return out


def guess_white_bottom(board_bgr):
    """Palpite (só para avisar): peças de baixo mais claras que as de cima => brancas embaixo."""
    cs = cells(board_bgr)

    def corpo(rows):
        vals = []
        for r in rows:
            for c in range(8):
                p = cs[r * 8 + c]
                h, w = p.shape
                vals.append(float(p[int(h * .3):int(h * .7), int(w * .3):int(w * .7)].mean()))
        return sum(vals) / len(vals)

    return corpo((6, 7)) > corpo((0, 1))


# --------------------------------------------------------------------------- jogo
def symmap(board):
    return {sq: p.symbol() for sq, p in board.piece_map().items()}


class Tracker:
    def __init__(self):
        self.board = None

    def init_from(self, placement, turn):
        ch = _chess()
        b = ch.Board(None)
        for sq, s in placement.items():
            b.set_piece_at(sq, ch.Piece.from_symbol(s))
        b.turn = turn
        rights = ""
        if placement.get(ch.E1) == "K":
            rights += "K" if placement.get(ch.H1) == "R" else ""
            rights += "Q" if placement.get(ch.A1) == "R" else ""
        if placement.get(ch.E8) == "k":
            rights += "k" if placement.get(ch.H8) == "r" else ""
            rights += "q" if placement.get(ch.A8) == "r" else ""
        b.set_castling_fen(rights or "-")
        self.board = b

    def _try(self, board, placement):
        for m in list(board.legal_moves):
            board.push(m)
            if symmap(board) == placement:
                return True
            board.pop()
        return False

    def update(self, placement):
        """Acha qual(is) lance(s) levam a posição anterior à da tela."""
        b = self.board
        if symmap(b) == placement:
            return "igual"
        if self._try(b, placement):
            return "mov"
        # dois lances (eu joguei e o adversário respondeu entre duas leituras)
        for m1 in list(b.legal_moves):
            b.push(m1)
            if self._try(b, placement):
                return "mov"
            b.pop()
        # talvez a vez estivesse errada na inicialização
        alt = b.copy()
        alt.turn = not alt.turn
        if self._try(alt, placement):
            self.board = alt
            return "mov"
        return "desconhecido"


def _casa(sq):
    n = _chess().square_name(sq)
    return f"{n[0]} {n[1]}"


def frase(board, m):
    if board.is_castling(m):
        return "roque pequeno" if _chess().square_file(m.to_square) > _chess().square_file(m.from_square) else "roque grande"
    p = board.piece_at(m.from_square)
    s = f"{_NOMES[p.piece_type]}, {_casa(m.from_square)} para {_casa(m.to_square)}"
    if board.is_capture(m):
        s += ", captura"
    if m.promotion:
        s += f", promove a {_NOMES[m.promotion]}"
    board.push(m)
    if board.is_checkmate():
        s += ", xeque-mate"
    elif board.is_check():
        s += ", xeque"
    board.pop()
    return s


# --------------------------------------------------------------------------- voz (SAPI do Windows)
class Voz:
    """Fala só a jogada mais recente; uma jogada nova corta a anterior."""

    def __init__(self):
        self.q: "queue.Queue[str]" = queue.Queue()
        self.ok = False
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            v = win32com.client.Dispatch("SAPI.SpVoice")
            try:
                for i in range(v.GetVoices().Count):
                    tok = v.GetVoices().Item(i)
                    d = tok.GetDescription().lower()
                    if "portug" in d or "pt-br" in d or "brazil" in d:
                        v.Voice = tok
                        break
                v.Rate = 4
            except Exception:
                pass
            self.ok = True
        except Exception as exc:
            print(f"[chess] voz indisponível: {exc}")
            return
        while True:
            t = self.q.get()
            while not self.q.empty():
                t = self.q.get_nowait()
            try:
                v.Speak(t, 3)  # assíncrono + corta a fala anterior
                while self.q.empty() and not v.WaitUntilDone(80):
                    pass
            except Exception:
                pass

    def falar(self, texto):
        print(f"[chess] >> {texto}", flush=True)
        self.q.put(texto)


# --------------------------------------------------------------------------- tela
def _monitor():
    """Monitor primário, em coordenadas de mouse (mesmo espaço do overlay do Jarvis)."""
    try:
        from core import screenview
        m = screenview._primary_monitor(screenview.monitors())
        if m and m.get("width") and m.get("height"):
            return dict(m)
    except Exception:
        pass
    import mss
    with mss.mss() as s:
        m = s.monitors[1]
        return {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}


def _grab(sct, area):
    return np.array(sct.grab(area))[:, :, :3]


def _achar_stockfish(extra=None):
    cands = [extra, os.environ.get("STOCKFISH_PATH")]
    base = _ROOT / "tools" / "stockfish"
    if base.exists():
        exes = sorted(base.rglob("*.exe"), key=lambda p: (("stockfish" not in p.name.lower()), len(str(p))))
        cands += [str(p) for p in exes if "stockfish" in p.name.lower()]
    cands.append(shutil.which("stockfish"))
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


# --------------------------------------------------------------------------- sessão
class _Sessao:
    def __init__(self):
        self.thread = None
        self.parar = threading.Event()
        self.engine = None
        self.ultimo = ""
        self.erro = ""
        self.seta_ate = 0.0
        self.resync = None   # "me" | "opponent": pedido manual de ressincronização

    @property
    def ativa(self):
        return bool(self.thread and self.thread.is_alive())


_S = _Sessao()
_LOCK = threading.Lock()


def _log(msg):
    try:
        _DATA.mkdir(parents=True, exist_ok=True)
        with open(_DATA / "log.txt", "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


def _cores_do_tabuleiro(live_bgr):
    """Cor (BGR) das casas escuras e claras, lida das casas vazias da posição inicial."""
    import cv2
    img = cv2.resize(live_bgr, (8 * CELL, 8 * CELL), interpolation=cv2.INTER_AREA)
    por = {0: [], 1: []}
    for r in range(2, 6):
        for c in range(8):
            patch = img[r * CELL + 16:(r + 1) * CELL - 16, c * CELL + 16:(c + 1) * CELL - 16]
            por[(r + c) % 2].append(np.median(patch.reshape(-1, 3), axis=0))
    return [np.median(np.stack(v), axis=0).astype(int).tolist() for v in por.values()]


def _maior_trecho(v, lim, folga=3):
    """Maior trecho contínuo (índices inclusivos) onde v > lim, tolerando buracos de até `folga` posições."""
    melhor = (0, -1)
    ini = fim = None
    buraco = 0
    for i, ok in enumerate(v > lim):
        if ok:
            if ini is None:
                ini = i
            fim = i
            buraco = 0
        elif ini is not None:
            buraco += 1
            if buraco > folga:
                if fim - ini > melhor[1] - melhor[0]:
                    melhor = (ini, fim)
                ini = None
                buraco = 0
    if ini is not None and fim - ini > melhor[1] - melhor[0]:
        melhor = (ini, fim)
    return melhor


def _achar_tabuleiro(full_bgr, cores, lado=None):
    """Acha o tabuleiro numa captura da tela inteira pelas duas cores das casas.
    Devolve (x, y, w, h) em pixels da captura, ou None."""
    import cv2
    full = np.ascontiguousarray(full_bgr)
    tol = 16
    m = np.zeros(full.shape[:2], np.uint8)
    for c in cores:
        c = np.array(c)
        m |= cv2.inRange(full, np.clip(c - tol, 0, 255).astype(np.uint8),
                         np.clip(c + tol, 0, 255).astype(np.uint8))
    casa = (lado or 640) / 8.0
    k = int(casa * 0.9) | 1
    fechado = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    cnts, _ = cv2.findContours(fechado, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for cnt in cnts:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 4 * casa or h < 4 * casa:
            continue
        # o contorno pode ter engolido barras/elementos vizinhos: recorta pelo trecho denso (o tabuleiro)
        reg = m[y:y + h, x:x + w] > 0
        r0, r1 = _maior_trecho(reg.mean(1), 0.30)
        if r1 < r0:
            continue
        c0, c1 = _maior_trecho(reg[r0:r1 + 1].mean(0), 0.30)
        if c1 < c0:
            continue
        r0, r1 = _maior_trecho(reg[:, c0:c1 + 1].mean(1), 0.30)
        bw, bh = c1 - c0 + 1, r1 - r0 + 1
        if bw < 4 * casa or bh < 4 * casa or abs(bw - bh) > 0.04 * max(bw, bh):
            continue
        if lado and not (0.6 * lado <= bw <= 1.6 * lado):
            continue
        bx, by = x + c0, y + r0
        if m[by:by + bh, bx:bx + bw].mean() / 255.0 < 0.45:
            continue
        if best is None or bw * bh > best[2] * best[3]:
            best = (bx, by, bw, bh)
    return best


def _remap(raw, wb):
    """raw = leitura com 'brancas embaixo' assumido; converte para as casas reais conforme a cor de baixo."""
    if wb:
        return raw
    out = {}
    for sq, sym in raw.items():
        r, c = rc_from_sq(sq, True)
        out[sq_from_rc(r, c, False)] = sym
    return out


def _detectar_wb(raw, atual):
    """Qual cor está EMBAIXO na tela? Reis valem mais; as demais peças desempatam."""
    reis = sorted(sym for sym in raw.values() if sym.lower() == "k")
    if reis != ["K", "k"]:
        return atual          # leitura duvidosa: mantém o que já sabia
    sc = 0
    for sq, sym in raw.items():
        r, _ = rc_from_sq(sq, True)
        peso = 4 if sym.lower() == "k" else 1
        sc += peso if (sym.isupper() == (r >= 4)) else -peso
    return atual if sc == 0 else sc > 0


def _dump(img, tag):
    """Guarda a imagem que o assistente leu (as 30 últimas) em memory/chess_assistant/debug."""
    try:
        import cv2
        d = _DATA / "debug"
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / (time.strftime("%H%M%S_") + tag + ".png")), img)
        for f in sorted(d.glob("*.png"))[:-30]:
            f.unlink()
    except Exception:
        pass


def _vez_provavel(antigo, pl, minha):
    """Depois de perder o fio: quem acabou de mexer? A vez é do outro lado."""
    if antigo is None:
        return minha
    mexeram = set()
    for sq, sym in pl.items():
        old = antigo.piece_at(sq)
        if old is None or old.symbol() != sym:
            mexeram.add(sym.isupper())   # True = peça branca apareceu numa casa nova
    if len(mexeram) == 1:
        return not mexeram.pop()
    return minha


def _esconder_jarvis(player):
    """Esconde o HUD do Jarvis (continua vivo na bandeja) para ele não cobrir o tabuleiro.
    Atenção: o Jarvis também apaga as marcas da tela ao esconder, então chame ANTES de desenhar a seta."""
    try:
        if player is not None and callable(getattr(player, "hide_window", None)):
            player.hide_window()
            time.sleep(0.4)
    except Exception as exc:
        _log(f"não consegui esconder o Jarvis: {exc}")


_SETA_Q = []
_SETA_LOCK = threading.Lock()
_SETA_EV = threading.Event()
_SETA_TH = [None]


def _seta_worker():
    while True:
        _SETA_EV.wait()
        while True:
            with _SETA_LOCK:
                if not _SETA_Q:
                    _SETA_EV.clear()
                    break
                label, fn = _SETA_Q.pop(0)
            t0 = time.time()
            try:
                fn()
            except Exception as exc:
                print(f"[chess] seta ({label}) falhou: {exc}")
            dt = time.time() - t0
            if dt > 1.5:
                _log(f"interface demorou {dt:.1f}s para {label} (a leitura do tabuleiro nao espera mais por isso)")


def _seta_async(label, fn):
    """Desenha/limpa a seta numa thread propria: se a interface do Jarvis travar, a leitura do tabuleiro continua."""
    with _SETA_LOCK:
        if label == "desenhar":
            _SETA_Q[:] = [x for x in _SETA_Q if x[0] != "desenhar"]   # so a ultima seta importa
        _SETA_Q.append((label, fn))
        if _SETA_TH[0] is None or not _SETA_TH[0].is_alive():
            _SETA_TH[0] = threading.Thread(target=_seta_worker, daemon=True, name="chess-seta")
            _SETA_TH[0].start()
    _SETA_EV.set()


def _limpar_seta(player):
    if time.time() < _S.seta_ate and player is not None:
        try:
            _seta_async("limpar", player.clear_screen_marks)
        except Exception:
            pass
    _S.seta_ate = 0.0


def _desenhar_seta(player, mon, roi, wb, sq_a, sq_b):
    if player is None or not callable(getattr(player, "show_screen_marks", None)):
        return
    try:
        from gui.screen_marks import normalize_screen_marks
        x0, y0, w, h = roi
        cw, ch_ = w / 8.0, h / 8.0

        def centro(sq):
            r, c = rc_from_sq(sq, wb)
            px = x0 + (c + .5) * cw - mon["left"]
            py = y0 + (r + .5) * ch_ - mon["top"]
            return px * 1000.0 / mon["width"], py * 1000.0 / mon["height"]

        ax, ay = centro(sq_a)
        bx, by = centro(sq_b)
        raio = cw * .42 * 1000.0 / mon["width"]
        payload = normalize_screen_marks({
            "duration": 45,
            "marks": [
                {"kind": "ring", "x": ax, "y": ay, "r": raio, "tone": "lime"},
                {"kind": "arrow", "points": [[ax, ay], [bx, by]], "tone": "lime"},
                {"kind": "ring", "x": bx, "y": by, "r": raio, "tone": "lime"},
            ],
        })
        _seta_async("desenhar", lambda: player.show_screen_marks(payload, operation="replace"))
        _S.seta_ate = time.time() + 44
    except Exception as exc:
        print(f"[chess] seta falhou: {exc}")


_LOG_MOTOR = [False]


def _abrir_motor(ch, sf):
    """Abre o Stockfish sem janela e sem herdar stderr (o Jarvis roda em pythonw); loga avisos do motor."""
    import logging
    import subprocess as _sp
    if not _LOG_MOTOR[0]:
        _LOG_MOTOR[0] = True

        class _H(logging.Handler):
            def emit(self, rec):
                try:
                    _log("motor: " + rec.getMessage()[:300])
                except Exception:
                    pass
        h = _H()
        h.setLevel(logging.WARNING)
        lg = logging.getLogger("chess.engine")
        lg.addHandler(h)
        lg.setLevel(logging.WARNING)
    kw = {"stderr": _sp.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000   # CREATE_NO_WINDOW
    eng = ch.engine.SimpleEngine.popen_uci(sf, **kw)
    try:
        eng.configure({"Threads": max(1, (os.cpu_count() or 2) // 2), "Hash": 128})
    except Exception:
        pass
    return eng


def _plausivel(raw):
    """Leitura de tela que pode ser um tabuleiro de verdade (descarta lixo: pagina errada, animacao, tela de partida abortada)."""
    syms = list(raw.values())
    up = [x for x in syms if x.isupper()]
    lo = [x for x in syms if x.islower()]
    return (len(up) <= 16 and len(lo) <= 16 and syms.count("K") <= 1 and syms.count("k") <= 1
            and syms.count("P") <= 8 and syms.count("p") <= 8)


def _loop(player, cfg, T, L, thr, tempo, turno_inicial, voz, engine, sf):
    eng = [engine]   # lista para poder trocar o motor se ele cair
    ult_img = [None]
    import mss
    ch = _chess()
    wb = cfg["white_bottom"]
    roi = cfg["roi"]
    mon = cfg["monitor"]
    x0, y0, w, h = roi
    minha = ch.WHITE if wb else ch.BLACK
    area = {"left": x0, "top": y0, "width": w, "height": h}
    pat_w = symmap(ch.Board())   # posição inicial, brancas embaixo (leitura "raw")
    pat_b = {sq_from_rc(*rc_from_sq(sq, False), True): sym for sq, sym in pat_w.items()}   # idem, pretas embaixo

    cores = cfg.get("cores")
    lado_ref = roi[2]
    t_reloc = [0.0]

    def relocar(sct):
        """Reencontra o tabuleiro na tela (a página pode ter mudado de layout depois da calibração)."""
        nonlocal roi, area
        if not cores:
            return False
        full = _grab(sct, mon)
        bb = _achar_tabuleiro(full, cores, lado_ref)
        if not bb:
            return False
        sx = full.shape[1] / float(mon["width"])
        sy = full.shape[0] / float(mon["height"])
        novo = [mon["left"] + int(round(bb[0] / sx)), mon["top"] + int(round(bb[1] / sy)),
                int(round(bb[2] / sx)), int(round(bb[3] / sy))]
        if all(abs(a - b) <= 3 for a, b in zip(novo, roi)):
            return False
        _log(f"tabuleiro em outro lugar: {roi} -> {novo}")
        roi = novo
        area = {"left": roi[0], "top": roi[1], "width": roi[2], "height": roi[3]}
        return True

    def virar(raw):
        """A leitura só faz sentido com a orientação OPOSTA? (tabuleiro girou depois que começamos)"""
        nonlocal wb, minha
        t2 = Tracker()
        t2.board = tr.board.copy()
        if t2.update(_remap(raw, not wb)) == "desconhecido":
            return False
        wb = not wb
        minha = ch.WHITE if wb else ch.BLACK
        tr.board = t2.board
        _S.cor = "brancas" if wb else "pretas"
        _log(f"tabuleiro girou: agora você está de {_S.cor} (embaixo)")
        return True

    def sugerir(tr):
        b = tr.board
        if b.is_game_over():
            voz.falar("Fim de jogo")
            _limpar_seta(player)
            return
        if b.turn != minha:
            _limpar_seta(player)
            return
        if not b.is_valid():
            _log(f"posição lida inválida ({b.status()!r}); ignorando (o tabuleiro está na tela?)")
            if time.time() - getattr(_S, "t_dump", 0) > 2.0 and ult_img[0] is not None:
                _S.t_dump = time.time()
                _dump(ult_img[0], "invalida")
            _limpar_seta(player)
            return
        try:
            m = eng[0].play(b, ch.engine.Limit(time=tempo)).move
        except Exception as exc:
            _log(f"motor caiu ({type(exc).__name__}: {str(exc)[:200]}); reiniciando e tentando a mesma jogada")
            try:
                eng[0].close()
            except Exception:
                pass
            try:
                eng[0] = _abrir_motor(ch, sf)
                m = eng[0].play(b, ch.engine.Limit(time=tempo)).move
            except Exception as exc2:
                _log(f"motor caiu de novo ({type(exc2).__name__}: {str(exc2)[:200]}); sem sugestao nesta jogada")
                return
        txt = frase(b, m)
        _S.ultimo = txt
        _log(f"sugestão: {txt} | fen={b.fen()}")
        voz.falar(txt)
        _desenhar_seta(player, mon, roi, wb, m.from_square, m.to_square)

    tr = Tracker()
    ultimo, estavel, feito = None, 0, False
    try:
        with mss.mss() as s:
            if cores:
                relocar(s)
            else:
                _log("calibração sem as cores do tabuleiro: calibre 1x de novo para ele achar o tabuleiro sozinho")
            t_prev = time.time()
            while not _S.parar.is_set():
                _agora = time.time()
                if _agora - t_prev > 3.0:
                    _log(f"leitura ficou parada {_agora - t_prev:.1f}s (algo bloqueou o laco)")
                t_prev = _agora
                img = _grab(s, area)
                ult_img[0] = img
                raw = read_position(img, T, L, thr, True)
                pl = _remap(raw, wb)
                if len(raw) < 8 and cores and time.time() - t_reloc[0] > 1.5:
                    t_reloc[0] = time.time()
                    if relocar(s):
                        ultimo, estavel, feito = None, 0, False
                        tr.board = None
                        continue
                if not _plausivel(raw):
                    if time.time() < _S.seta_ate:
                        # a seta/circulo desenhado sobre uma peca pode estar confundindo a leitura: tira e le de novo
                        _limpar_seta(player)
                        _log("leitura impossivel com a seta na tela; tirando a seta e lendo de novo")
                        time.sleep(0.15)
                    else:
                        if time.time() - getattr(_S, "t_impl", 0) > 5.0:
                            _S.t_impl = time.time()
                            _log(f"leitura impossivel ({len(raw)} pecas lidas); aguardando um tabuleiro valido")
                            _dump(img, "implausivel")
                        time.sleep(0.05)
                    continue
                if pl == ultimo:
                    estavel += 1
                else:
                    ultimo, estavel, feito = pl, 1, False
                    time.sleep(0.03)
                    continue
                if estavel >= 2 and not feito:
                    if raw == pat_w or raw == pat_b:
                        nwb = (raw == pat_w)
                        if tr.board is None or nwb != wb or symmap(tr.board) != pat_w:
                            wb = nwb
                            minha = ch.WHITE if wb else ch.BLACK
                            tr.board = None
                            _limpar_seta(player)
                            _S.cor = "brancas" if wb else "pretas"
                            _log(f"partida nova: você está de {_S.cor} (embaixo)")
                            if not wb:
                                voz.falar("Voc\u00ea est\u00e1 de pretas. Aguardando as brancas jogarem.")
                            pl = _remap(raw, wb)
                            ultimo = pl
                    elif tr.board is None:
                        wb = _detectar_wb(raw, wb)
                        minha = ch.WHITE if wb else ch.BLACK
                        _S.cor = "brancas" if wb else "pretas"
                        _log(f"cor detectada (partida em andamento): {_S.cor} embaixo")
                        pl = _remap(raw, wb)
                        ultimo = pl
                if _S.resync and estavel >= 2:
                    nwb = _detectar_wb(raw, wb)
                    if nwb != wb:
                        wb = nwb
                        minha = ch.WHITE if wb else ch.BLACK
                        _S.cor = "brancas" if wb else "pretas"
                        _log(f"cor corrigida no resync manual: {_S.cor} embaixo")
                        pl = _remap(raw, wb)
                    vez = minha if _S.resync == "me" else (not minha)
                    _S.resync = None
                    _limpar_seta(player)
                    tr.init_from(pl, vez)
                    feito = True
                    _log("ressincronização manual")
                    sugerir(tr)
                    continue
                if estavel >= 2 and not feito:
                    if tr.board is None:
                        if pl == symmap(ch.Board()):
                            vez = ch.WHITE
                        else:
                            vez = minha if turno_inicial == "me" else (not minha)
                        tr.init_from(pl, vez)
                        feito = True
                        sugerir(tr)
                    else:
                        r = tr.update(pl)
                        if r == "mov":
                            feito = True
                            _log(f"lance detectado | fen={tr.board.fen()}")
                            sugerir(tr)
                        elif r == "igual":
                            feito = True
                        elif r == "desconhecido" and tr.board is not None and virar(raw):
                            feito = True
                            pl = _remap(raw, wb)
                            ultimo = pl
                            _limpar_seta(player)
                            sugerir(tr)
                        elif r == "desconhecido" and time.time() < _S.seta_ate:
                            # a própria seta pode estar tapando peças: tira e lê de novo
                            _limpar_seta(player)
                            time.sleep(0.1)
                            ultimo, estavel = None, 0
                            continue
                if estavel == 14 and not feito:      # nada bate: ressincroniza
                    if cores and relocar(s):         # talvez o tabuleiro tenha mudado de lugar
                        _limpar_seta(player)
                        ultimo, estavel, feito = None, 0, False
                        tr.board = None
                        continue
                    nwb = _detectar_wb(raw, wb)
                    if nwb != wb:
                        wb = nwb
                        minha = ch.WHITE if wb else ch.BLACK
                        _S.cor = "brancas" if wb else "pretas"
                        _log(f"cor corrigida na ressincronização: {_S.cor} embaixo")
                        pl = _remap(raw, wb)
                    vez = _vez_provavel(tr.board, pl, minha)
                    _log(f"leitura não bate com nenhum lance; ressincronizando (vez={'minha' if vez == minha else 'adversário'}) "
                         f"peças_lidas={len(pl)}")
                    try:
                        import cv2
                        cv2.imwrite(str(_DATA / "desync.png"), img)
                    except Exception:
                        pass
                    _dump(img, "desync")
                    tr.init_from(pl, vez)
                    _log(f"lido no desync: {tr.board.board_fen()}")
                    feito = True
                    sugerir(tr)
                time.sleep(0.03)
    except Exception as exc:
        _S.erro = f"{type(exc).__name__}: {exc}"
        print(f"[chess] loop parou: {_S.erro}")
    finally:
        _limpar_seta(player)
        try:
            eng[0].quit()
        except Exception:
            pass


# --------------------------------------------------------------------------- ações
def _calibrar_impl(parameters, player):
    import cv2
    import mss
    ch = _chess()
    cor = str(parameters.get("bottom_color") or "").strip().lower()
    if cor and cor not in {"white", "black", "branca", "brancas", "preta", "pretas"}:
        return "CHESS_BAD_COLOR: bottom_color deve ser white ou black (ou omita: é detectada sozinha)."
    wb = (cor in {"white", "branca", "brancas"}) if cor else None
    if player is None or not callable(getattr(player, "select_screen_area", None)):
        return "CHESS_UNAVAILABLE: a interface do Jarvis não está conectada (seletor de área)."
    try:
        sel = player.select_screen_area(timeout=90)
    except Exception as exc:
        return f"CHESS_CALIBRATION_CANCELLED: {type(exc).__name__}: {str(exc)[:120]}"

    crop = cv2.imdecode(np.frombuffer(sel["image"], np.uint8), cv2.IMREAD_COLOR)
    if crop is None or crop.shape[0] < 80 or crop.shape[1] < 80:
        return "CHESS_CALIBRATION_FAILED: seleção pequena demais. Selecione só as 64 casas."
    _esconder_jarvis(player)  # o seletor devolve a janela do Jarvis por cima do tabuleiro
    time.sleep(0.2)

    mon = _monitor()
    vp = sel["viewport"]
    with mss.mss() as s:
        full = _grab(s, mon)
        # posição exata: procura o recorte na captura ao vivo
        ch_, cw_ = crop.shape[:2]
        res = cv2.matchTemplate(full, crop, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score > 0.9:
            sx = full.shape[1] / float(mon["width"])
            sy = full.shape[0] / float(mon["height"])
            roi = [mon["left"] + int(round(loc[0] / sx)), mon["top"] + int(round(loc[1] / sy)),
                   int(round(cw_ / sx)), int(round(ch_ / sy))]
        else:  # fallback: grade 0-1000 do seletor
            roi = [mon["left"] + int(vp["x"] * mon["width"] / 1000.0),
                   mon["top"] + int(vp["y"] * mon["height"] / 1000.0),
                   int(vp["w"] * mon["width"] / 1000.0), int(vp["h"] * mon["height"] / 1000.0)]
        live = _grab(s, {"left": roi[0], "top": roi[1], "width": roi[2], "height": roi[3]})
    try:
        _DATA.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(_DATA / "calibrate_selected.png"), crop)
        cv2.imwrite(str(_DATA / "calibrate_live.png"), live)
        _log(f"calibrar: monitor={mon} roi={roi} match={score:.3f} crop={crop.shape[1]}x{crop.shape[0]}")
    except Exception:
        pass

    aviso = ""
    if wb is None:
        try:
            wb = guess_white_bottom(live)
        except Exception:
            wb = True
        aviso = " (cor de baixo detectada sozinha; no jogo ela é detectada a cada partida)"
    try:
        if cor and guess_white_bottom(live) != wb:
            aviso = (" ATENÇÃO: pela cor das peças parece que o lado de baixo é o OPOSTO do informado; "
                     "confirme com o usuário e refaça se estiver errado.")
    except Exception:
        pass
    try:
        T, L, thr = build_templates(live, wb)
    except Exception as exc:
        return f"CHESS_CALIBRATION_FAILED: não consegui aprender as peças ({exc}). A posição inicial estava visível?"
    lido = read_position(live, T, L, thr, wb)
    certo = symmap(ch.Board())
    erros = sum(1 for sq in set(lido) | set(certo) if lido.get(sq) != certo.get(sq))
    _DATA.mkdir(parents=True, exist_ok=True)
    np.savez(_TPL, T=T, L=L, thr=thr)
    try:
        cores = _cores_do_tabuleiro(live)
    except Exception:
        cores = None
    _CFG.write_text(json.dumps({"roi": roi, "white_bottom": wb, "monitor": mon, "cores": cores}), encoding="utf-8")
    if erros:
        return (f"CHESS_CALIBRATED_WITH_ERRORS: {erros} casa(s) lida(s) errado. Confira se selecionou só o "
                f"tabuleiro e se era a posição inicial, e calibre de novo.{aviso}")
    return f"CHESS_CALIBRATED: tabuleiro lido corretamente ({'brancas' if wb else 'pretas'} embaixo).{aviso}"


def _calibrar(parameters, player):
    """Roda a calibração e grava SEMPRE o resultado (ou o erro completo) em log.txt."""
    import traceback
    try:
        r = _calibrar_impl(parameters, player)
    except Exception:
        r = "CHESS_CALIBRATION_CRASH: " + traceback.format_exc()[-700:]
    _log("calibrar -> " + r)
    return r


def _iniciar_impl(parameters, player):
    ch = _chess()
    with _LOCK:
        if _S.ativa:
            return "CHESS_ALREADY_RUNNING: o assistente já está olhando a tela."
        if not (_CFG.exists() and _TPL.exists()):
            return "CHESS_NOT_CALIBRATED: calibre primeiro (action=calibrate) com a posição inicial na tela."
        cfg = json.loads(_CFG.read_text(encoding="utf-8"))
        d = np.load(_TPL)
        T, L, thr = d["T"], d["L"], float(d["thr"])
        sf = _achar_stockfish(parameters.get("stockfish_path"))
        if not sf:
            return "STOCKFISH_NOT_FOUND: coloque o .exe em tools\\stockfish ou passe stockfish_path."
        try:
            tempo = max(0.03, min(2.0, float(parameters.get("think_time") or 0.15)))
        except (TypeError, ValueError):
            tempo = 0.15
        turno = "opponent" if str(parameters.get("turn") or "me").lower().startswith("opp") else "me"
        try:
            engine = _abrir_motor(ch, sf)
        except Exception as exc:
            return f"STOCKFISH_FAILED: {type(exc).__name__}: {str(exc)[:160]}"
        _esconder_jarvis(player)
        _S.parar.clear()
        _S.erro = ""
        _S.ultimo = ""
        voz = Voz()
        _S.thread = threading.Thread(
            target=_loop, args=(player, cfg, T, L, thr, tempo, turno, voz, engine, sf),
            daemon=True, name="chess-assistant")
        _S.thread.start()
    return ("CHESS_STARTED: o assistente está olhando a tela e vai FALAR e desenhar cada jogada sozinho. "
            "O HUD do Jarvis foi escondido (volta pelo ícone da bandeja) para não cobrir o tabuleiro. "
            "Não repita as jogadas em voz alta; responda só com uma frase curta.")


def _iniciar(parameters, player):
    """Inicia o assistente e grava SEMPRE o resultado (ou o erro completo) em log.txt."""
    import traceback
    try:
        r = _iniciar_impl(parameters, player)
    except Exception:
        r = "CHESS_START_CRASH: " + traceback.format_exc()[-700:]
    _log("iniciar -> " + r)
    return r


def _parar(player):
    if not _S.ativa:
        return "CHESS_NOT_RUNNING: o assistente já estava parado."
    _S.parar.set()
    _S.thread.join(timeout=3)
    _limpar_seta(player)
    return "CHESS_STOPPED: assistente de xadrez parado."


def _status():
    if _S.ativa:
        return (f"CHESS_RUNNING: você está de {getattr(_S, 'cor', '') or 'cor ainda não detectada'}. "
                f"Última sugestão: {_S.ultimo or 'ainda nenhuma'}.")
    base = "CHESS_STOPPED"
    if _S.erro:
        base += f" (parou por erro: {_S.erro})"
    return base + f". Calibrado: {'sim' if (_CFG.exists() and _TPL.exists()) else 'não'}."


def chess_assistant(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    action = str(params.get("action") or "status").strip().lower()
    _log(f"chamada: action={action} params={ {k: v for k, v in params.items() if k != 'action'} }")
    try:
        if action == "calibrate":
            return _calibrar(params, player)
        if action == "start":
            return _iniciar(params, player)
        if action == "stop":
            return _parar(player)
        if action == "resync":
            if not _S.ativa:
                return "CHESS_NOT_RUNNING: inicie o assistente primeiro (action=start)."
            _S.resync = "opponent" if str(params.get("turn") or "me").lower().startswith("opp") else "me"
            return "CHESS_RESYNC_REQUESTED: relendo o tabuleiro agora; ele vai falar a jogada se for a vez do usuário."
        if action == "status":
            return _status()
        return "CHESS_INVALID_ACTION: use calibrate, start, stop, status ou resync."
    except ImportError as exc:
        _log(f"dependência faltando: {exc}")
        return f"CHESS_DEPENDENCY_MISSING: {exc}. Instale: pip install python-chess opencv-python mss pywin32"
    except Exception as exc:
        return f"CHESS_FAILED: {type(exc).__name__}: {str(exc)[:200]}"


TOOL = {
    "name": "chess_assistant",
    "description": (
        "Assistente de xadrez em tempo real. Lê o tabuleiro na tela, calcula a melhor jogada com o "
        "Stockfish local, FALA a jogada (ex.: 'cavalo, g 1 para f 3') e desenha uma seta verde sobre o "
        "tabuleiro, sozinho, a cada vez que for a vez do usuário. Fluxo: (1) action=calibrate com a "
        "posição inicial visível (NÃO pergunte a cor: ela é detectada sozinha em cada partida); "
        "o usuário arrasta o mouse sobre as 64 casas. Só é preciso refazer se trocar de site "
        "ou de tema de peças. (2) action=start para ficar olhando a tela. (3) action=stop para parar. "
        "action=status mostra o estado. action=resync (com turn=me/opponent) relê o tabuleiro se ele se perder ou o usuário errar um lance. Depois de start NÃO narre as jogadas: o assistente já fala. "
        "Use só contra bots, treino ou análise; contra pessoas em sites online é trapaça."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "enum": ["calibrate", "start", "stop", "status", "resync"],
                       "description": "calibrate, start, stop, status ou resync (releia o tabuleiro se ele se perdeu)."},
            "bottom_color": {"type": "STRING", "enum": ["white", "black"],
                             "description": "OPCIONAL, só em calibrate; normalmente NÃO informe (a cor é detectada sozinha)."},
            "think_time": {"type": "NUMBER",
                           "description": "Segundos de análise por jogada (0.03 a 2; padrão 0.15)."},
            "turn": {"type": "STRING", "enum": ["me", "opponent"],
                     "description": "Em start (partida em andamento) ou resync: de quem é a vez agora (padrão me)."},
            "stockfish_path": {"type": "STRING", "description": "Caminho do stockfish.exe, se não estiver em tools\\stockfish."},
        },
        "required": ["action"],
    },
    "handler": chess_assistant,
    "tier": "extra",
    "brief": "Chess coach: reads the board on screen, speaks and draws the best move.",
}
