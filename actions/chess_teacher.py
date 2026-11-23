"""
Professor de xadrez do JARVIS (modulo SEPARADO do assistente de xadrez).

O assistente (actions/chess_assistant.py) so diz e desenha a melhor jogada.
O professor ENSINA: explica cada jogada em detalhe, diz por que jogar naquela casa,
o que o adversario deve responder, compara com as alternativas, avalia o lance que
o usuario realmente jogou e comenta o lance do adversario.

Nada aqui altera o assistente: o professor so LE as funcoes de leitura de tela dele
e a calibracao ja salva (memory/chess_assistant). Log e arquivos do professor ficam
em memory/chess_teacher.

Comandos (ferramenta `chess_teacher`):
    action="start"        aula ao vivo: olha a tela e ensina cada jogada
    action="stop" / "status"
    action="explain"      explica UMA vez a posicao que esta na tela
    action="explain_fen"  explica uma posicao dada por FEN (sem tela), com move= opcional
    action="why"          por que jogar (ou nao) um lance, na aula em andamento
    action="repeat"       repete a ultima explicacao
    action="level"        muda entre explicacao "detalhado" e "curto"
    action="calibrate"    usa a calibracao do assistente (1x por site/tema)
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import queue
import re
import threading
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "memory" / "chess_teacher"
_CA_DATA = _ROOT / "memory" / "chess_assistant"   # calibracao do assistente (somente leitura)
_CFG = _CA_DATA / "config.json"
_TPL = _CA_DATA / "templates.npz"

_NOMES = {1: "peão", 2: "cavalo", 3: "bispo", 4: "torre", 5: "dama", 6: "rei"}
_VALOR = {1: 1, 2: 3, 3: 3, 4: 5, 5: 9, 6: 99}
_FEM = (4, 5)


def _chess():
    import chess
    import chess.engine
    return chess


def _log(msg):
    try:
        _DATA.mkdir(parents=True, exist_ok=True)
        with open(_DATA / "log.txt", "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + msg + "\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- texto das jogadas
def _casa(sq):
    n = _chess().square_name(sq)
    return f"{n[0]} {n[1]}"


def _o(pt):
    return ("a " if pt in _FEM else "o ") + _NOMES[pt]


def _peca_de(pt, voce):
    """Peca-alvo: 'a torre adversária' (do adversário) ou 'a sua torre' (sua)."""
    fem = pt in _FEM
    art = "a" if fem else "o"
    if voce:
        return f"{art} {_NOMES[pt]} adversári{'a' if fem else 'o'}"
    return f"{art} {'sua' if fem else 'seu'} {_NOMES[pt]}"


def _lista(itens):
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def _pontos(cp):
    return f"{abs(cp) / 100.0:.1f}".replace(".", ",")


def descrever(board, m):
    """'cavalo, g 1 para f 3, xeque' (nao altera o tabuleiro)."""
    ch = _chess()
    if board.is_castling(m):
        base = "roque pequeno" if ch.square_file(m.to_square) > ch.square_file(m.from_square) else "roque grande"
    else:
        p = board.piece_at(m.from_square)
        base = f"{_NOMES[p.piece_type]}, {_casa(m.from_square)} para {_casa(m.to_square)}"
        if board.is_capture(m):
            base += ", captura"
        if m.promotion:
            base += f", promove a {_NOMES[m.promotion]}"
    board.push(m)
    if board.is_checkmate():
        base += ", xeque-mate"
    elif board.is_check():
        base += ", xeque"
    board.pop()
    return base


def _menor_atacante(b, color, sq):
    vals = [_VALOR[b.piece_type_at(s)] for s in b.attackers(color, sq)]
    return min(vals) if vals else None


def _seguro(b2, me, sq, val):
    """A peca em `sq` (depois do lance) esta a salvo ou so pode ser trocada de igual para igual?"""
    atk = _menor_atacante(b2, not me, sq)
    if atk is None:
        return True
    if not b2.is_attacked_by(me, sq):
        return False
    return atk >= val


def _controle_centro(b, color):
    ch = _chess()
    return sum(1 for s in (ch.D4, ch.E4, ch.D5, ch.E5) if b.is_attacked_by(color, s))


def _cravadas(b, color):
    return {s for s, p in b.piece_map().items() if p.color == color and p.piece_type != 6 and b.is_pinned(color, s)}


def motivos(board, m, voce=True):
    """Lista de frases com o PORQUE do lance (so fatos que o tabuleiro confirma).
    voce=True: lance do usuario; voce=False: lance do adversario."""
    ch = _chess()
    me = board.turn
    opp = not me
    p = board.piece_at(m.from_square)
    pt = p.piece_type
    val = _VALOR[pt]
    sq = m.to_square
    cap = board.piece_at(sq)
    if board.is_en_passant(m):
        cap = ch.Piece(ch.PAWN, opp)
    b2 = board.copy(stack=False)
    b2.push(m)
    if b2.is_checkmate():
        return ["Essa jogada dá xeque-mate: o rei não tem como escapar e a partida termina."]
    out = []
    roque = board.is_castling(m)

    if m.promotion:
        out.append(f"Promove o peão a {_NOMES[m.promotion]}, transformando-o numa peça muito mais forte.")
    if roque:
        out.append("O roque tira o rei do centro, onde ele corre mais risco, e ao mesmo tempo coloca a torre numa casa ativa.")
    if cap:
        base = f"Captura {_peca_de(cap.piece_type, voce)} em {_casa(sq)}"
        atk = _menor_atacante(b2, opp, sq)
        vc = _VALOR[cap.piece_type]
        if atk is None:
            base += ", ganhando material, e a peça que captura fica fora de perigo."
        elif vc > val:
            base += ", ganhando material: a peça capturada vale mais do que a que se arrisca."
        elif vc == val:
            base += ", uma troca de peças de mesmo valor, que simplifica a posição."
        else:
            base += ", e mesmo podendo ser recapturada, a troca compensa pelo que vem depois."
        out.append(base)
    if b2.is_check():
        out.append("Dá xeque, e o adversário é obrigado a responder, o que mantém a iniciativa." if voce
                   else "Dá xeque: é preciso responder a ele agora.")

    if not roque:
        back = 0 if me == ch.WHITE else 7
        if pt in (2, 3) and ch.square_rank(m.from_square) == back and board.fullmove_number <= 15 and not cap:
            out.append(f"Desenvolve {_o(pt)}, tirando-o da última fileira para entrar no jogo; peças ativas valem mais do que peças paradas.")
        centro = (ch.D4, ch.E4, ch.D5, ch.E5)
        if pt == 1 and sq in centro and not cap:
            out.append(f"O peão ocupa o centro, em {_casa(sq)}, ganhando espaço e controlando casas importantes.")
        elif pt != 1 and _controle_centro(b2, me) > _controle_centro(board, me):
            out.append("Aumenta o controle das casas centrais do tabuleiro, de onde as peças alcançam os dois lados.")
        if pt == 4 and ch.square_file(m.from_square) != ch.square_file(sq):
            f = ch.square_file(sq)
            sem_peao = all((b2.piece_type_at(ch.square(f, r)) != 1) for r in range(8))
            if sem_peao:
                out.append("Coloca a torre numa coluna aberta, sem peões, onde ela tem liberdade para agir.")
        if pt == 6 and len(board.piece_map()) <= 12:
            out.append("No final de jogo o rei vira uma peça de ataque: ativá-lo ajuda a vencer.")

        seguro = _seguro(b2, me, sq, val)
        # peca ameacada que sai do perigo
        atk_antes = _menor_atacante(board, opp, m.from_square)
        fraca_antes = atk_antes is not None and (not board.is_attacked_by(me, m.from_square) or atk_antes < val)
        if fraca_antes and seguro and not cap:
            out.append(f"Tira {_o(pt)} da casa {_casa(m.from_square)}, onde corria perigo, e leva para um lugar seguro.")
        # ameacas criadas
        if seguro:
            alvos = []
            for t in b2.attacks(sq):
                q = b2.piece_at(t)
                if q and q.color == opp and q.piece_type != 6:
                    sem_prot = not b2.is_attacked_by(opp, t)
                    if sem_prot or _VALOR[q.piece_type] > val:
                        alvos.append((t, q, sem_prot))
            if len(alvos) >= 2:
                lista = _lista([f"{_peca_de(q.piece_type, voce)} em {_casa(t)}" for t, q, _ in alvos])
                out.append(f"Cria um garfo: ataca ao mesmo tempo {lista}. Só dá para resolver uma das ameaças por vez.")
            elif len(alvos) == 1:
                t, q, sem = alvos[0]
                if sem:
                    fim = ("se não houver reação, essa peça é ganha de graça." if voce
                           else "se você não reagir, vai perder essa peça.")
                    out.append(f"Ataca {_peca_de(q.piece_type, voce)} em {_casa(t)}, que está sem nenhuma proteção; {fim}")
                else:
                    fim = ("é preciso mover a peça ou perder material." if voce
                           else "é preciso movê-la ou proteger melhor, senão você perde material.")
                    out.append(f"Ataca {_peca_de(q.piece_type, voce)} em {_casa(t)}, que vale mais do que a peça que ataca; {fim}")
        # defende peca ameacada
        for s, q in b2.piece_map().items():
            if q.color == me and s != sq and q.piece_type != 6 and b2.is_attacked_by(opp, s) \
                    and b2.is_attacked_by(me, s) and not board.is_attacked_by(me, s):
                out.append(f"Protege {_o(q.piece_type)} em {_casa(s)}, que estava ameaçada e sem defesa.")
                break
        # cravada nova
        novas = _cravadas(b2, opp) - _cravadas(board, opp)
        for s in novas:
            out.append(f"Crava {_o(b2.piece_type_at(s))} em {_casa(s)}: ela não pode sair do lugar sem expor o rei.")
            break

    if not out:
        out.append("Melhora a posição da peça, deixando-a mais ativa e mais bem coordenada com o resto do time.")
    return out


# --------------------------------------------------------------------------- avaliacao e explicacao
def _cp(score_pov):
    return score_pov.score(mate_score=10000)


def _aval(sc):
    """Frase sobre quem esta melhor (sc = Score do ponto de vista de quem joga)."""
    if sc.is_mate():
        n = sc.mate()
        if n > 0:
            return f"Há mate forçado em {abs(n)} para você"
        return f"Cuidado: o adversário tem mate forçado em {abs(n)}"
    cp = sc.score()
    a = abs(cp)
    if a < 30:
        return "A posição está equilibrada"
    grau = "pequena" if a < 100 else ("clara" if a < 300 else "decisiva")
    return f"Você tem vantagem {grau}" if cp > 0 else f"Você está em desvantagem {grau}"


def explicar(board, infos, nivel="detalhado"):
    """infos: [{move, score (de quem joga), pv}] melhor primeiro. Devolve {move, frases, texto}."""
    best = infos[0]
    m = best["move"]
    frases = [f"A melhor jogada é {descrever(board, m)}."]
    mot = motivos(board, m, True)
    frases += mot if nivel != "curto" else mot[:1]
    if nivel != "curto":
        pv = best.get("pv") or []
        if len(pv) >= 2:
            b = board.copy(stack=False)
            b.push(pv[0])
            if pv[1] in b.legal_moves:
                frases.append(f"O adversário deve responder com {descrever(b, pv[1])}.")
                b.push(pv[1])
                if len(pv) >= 3 and pv[2] in b.legal_moves:
                    frases.append(f"E então você continua com {descrever(b, pv[2])}.")
        frases.append(_aval(best["score"]) + ".")
        bcp = _cp(best["score"])
        for alt in infos[1:3]:
            perda = bcp - _cp(alt["score"])
            d = descrever(board, alt["move"])
            if perda <= 30:
                frases.append(f"Outra boa opção seria {d}, quase tão boa quanto.")
            else:
                frases.append(f"{d.capitalize()} seria pior: perderia cerca de {_pontos(perda)} pontos de vantagem.")
    return {"move": m, "frases": frases, "texto": " ".join(frases)}


def avaliar_lance(engine_fn, board, move, infos, saida=None):
    """Nota o lance que o usuario jogou. engine_fn(board) -> Score do ponto de vista de quem jogava.
    Devolve lista de frases."""
    best = infos[0]
    d = descrever(board, move)
    if move == best["move"]:
        if saida is not None:
            saida.update(perda=0, tema="", melhor=d)
        return [f"Excelente! Você jogou {d}, exatamente a melhor jogada."]
    achou = [i for i in infos if i["move"] == move]
    if achou:
        cp = _cp(achou[0]["score"])
    else:
        b2 = board.copy(stack=False)
        b2.push(move)
        if b2.is_checkmate():
            cp = 10000
        elif b2.is_game_over():
            cp = 0
        else:
            cp = _cp(engine_fn(b2))
    perda = max(0, _cp(best["score"]) - cp)
    melhor = descrever(board, best["move"])
    porque = motivos(board, best["move"], True)[0]
    if saida is not None:
        saida.update(perda=perda, tema=_tema(porque), melhor=melhor)
    if perda <= 20:
        return [f"Boa! Você jogou {d}, praticamente tão boa quanto a melhor."]
    if perda <= 60:
        return [f"Boa jogada, {d}. A melhor era {melhor}, só um pouco mais precisa."]
    if perda <= 150:
        return [f"Imprecisão: {d} perde cerca de {_pontos(perda)} pontos de vantagem.",
                f"A melhor era {melhor}. {porque}"]
    if perda <= 300:
        return [f"Erro: {d} perde cerca de {_pontos(perda)} pontos de vantagem.",
                f"A melhor era {melhor}. {porque}"]
    return [f"Erro grave: {d} perde cerca de {_pontos(perda)} pontos de vantagem, ou até a partida.",
            f"A melhor era {melhor}. {porque}"]


def comentar_lance(board, move):
    """Comenta o lance do ADVERSARIO (board = posicao antes do lance)."""
    frases = [f"O adversário jogou {descrever(board, move)}."]
    mot = motivos(board, move, False)
    frases += mot[:2]
    return frases


def achar_lance(board, texto):
    """Aceita 'Nf3', 'g1f3', 'g1 f3', 'e4'. Devolve Move legal ou None."""
    ch = _chess()
    s = str(texto or "").strip()
    if not s:
        return None
    for cand in (s, s.replace(" ", "").replace("-", "")):
        try:
            return board.parse_san(cand)
        except Exception:
            pass
        try:
            m = ch.Move.from_uci(cand.lower())
            if m in board.legal_moves:
                return m
        except Exception:
            pass
    return None


# --------------------------------------------------------------------------- motor (Stockfish)
def _achar_stockfish(extra=None):
    import shutil
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


class _Motor:
    """Stockfish com reinicio automatico se ele cair."""

    def __init__(self, caminho):
        self.caminho = caminho
        self.eng = None
        self._abrir()

    def _abrir(self):
        import subprocess as sp
        ch = _chess()
        kw = {"stderr": sp.DEVNULL}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000   # CREATE_NO_WINDOW
        self.eng = ch.engine.SimpleEngine.popen_uci(self.caminho, **kw)
        try:
            self.eng.configure({"Threads": max(1, (os.cpu_count() or 2) // 2), "Hash": 128})
        except Exception:
            pass

    def _com_retry(self, fn):
        try:
            return fn()
        except Exception as exc:
            _log(f"motor caiu ({type(exc).__name__}: {str(exc)[:160]}); reiniciando")
            try:
                self.eng.close()
            except Exception:
                pass
            self._abrir()
            return fn()

    def analisar(self, board, tempo, n=3):
        ch = _chess()
        n = max(1, min(n, board.legal_moves.count()))

        def fn():
            infos = self.eng.analyse(board, ch.engine.Limit(time=tempo), multipv=n)
            return [infos] if isinstance(infos, dict) else infos

        out = []
        for i in self._com_retry(fn):
            pv = list(i.get("pv") or [])
            if pv and "score" in i:
                out.append({"move": pv[0], "score": i["score"].pov(board.turn), "pv": pv})
        return out

    def nota(self, board, tempo, pov):
        """Score da posicao `board` do ponto de vista de `pov`."""
        ch = _chess()
        info = self._com_retry(lambda: self.eng.analyse(board, ch.engine.Limit(time=tempo)))
        return info["score"].pov(pov)

    def fechar(self):
        try:
            self.eng.quit()
        except Exception:
            pass


# --------------------------------------------------------------------------- voz (a MESMA voz do Jarvis)
_PCM_HZ = 24000     # o Gemini Live devolve PCM 16 bits mono a 24 kHz


def _partir(texto, lim=170):
    """Quebra frases longas (a fala do Gemini e preparada em pedacos curtos) em virgulas/espacos."""
    texto = " ".join(str(texto or "").split())
    out = []
    while len(texto) > lim:
        corte = max(texto.rfind(", ", 0, lim), texto.rfind("; ", 0, lim), texto.rfind(": ", 0, lim))
        if corte < lim // 3:
            corte = texto.rfind(" ", 0, lim)
        if corte <= 0:
            corte = lim
        out.append(texto[:corte + 1].strip())
        texto = texto[corte + 1:].strip()
    if texto:
        out.append(texto)
    return out


# --------------------------------------------------------------------------- progresso do aluno
_PROG = _DATA / "progresso.json"
_LOCK_P = threading.Lock()
_TEMAS = [("garfo", "garfos"), ("xeque", "xeques"), ("captur", "capturas"), ("ameaç", "ameaças"),
          ("desenvolv", "desenvolvimento das peças"), ("centro", "controle do centro"),
          ("seguran", "segurança do rei"), ("rei", "segurança do rei"), ("salva", "peças em perigo"),
          ("cravad", "cravadas")]


def _tema(porque):
    """Tema do que o aluno deixou passar (a ideia por tras da melhor jogada)."""
    s = str(porque or "").lower()
    for chave, nome in _TEMAS:
        if chave in s:
            return nome
    return "outros"


def _prog_novo():
    return {"sessoes": 0, "lances": 0, "erros": 0, "por_fase": {}, "temas": {}, "recentes": []}


def _prog_ler():
    try:
        d = json.loads(_PROG.read_text(encoding="utf-8"))
        base = _prog_novo()
        base.update({k: v for k, v in d.items() if k in base})
        return base
    except Exception:
        return _prog_novo()


def _prog_gravar(d):
    _DATA.mkdir(parents=True, exist_ok=True)
    tmp = _PROG.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, _PROG)


def _nova_sessao():
    with _LOCK_P:
        d = _prog_ler()
        d["sessoes"] += 1
        _prog_gravar(d)


def registrar_lance(fase, perda, tema):
    """Guarda o resultado de um lance do aluno. Devolve quantas vezes esse tema de erro ja apareceu
    (0 se o lance nao foi um erro; erro = perder mais de 60 centipeoes)."""
    with _LOCK_P:
        d = _prog_ler()
        d["lances"] += 1
        erro = perda > 60
        pf = d["por_fase"].setdefault(fase, [0, 0])
        pf[0] += 1
        pf[1] += 1 if erro else 0
        n = 0
        if erro:
            d["erros"] += 1
            t_ = tema or "outros"
            d["temas"][t_] = d["temas"].get(t_, 0) + 1
            n = d["temas"][t_]
        d["recentes"] = (list(d["recentes"]) + [1 if erro else 0])[-40:]
        _prog_gravar(d)
        return n


def _tendencia(d):
    rec = d.get("recentes") or []
    if len(rec) < 20:
        return ""
    ant, atual = rec[-20:-10], rec[-10:]
    ta, tn = sum(ant) / 10.0, sum(atual) / 10.0
    if tn + 0.15 <= ta:
        return "vem melhorando nos últimos lances"
    if tn >= ta + 0.15:
        return "tem errado mais nos últimos lances"
    return ""


def perfil_texto(d=None):
    """Resumo curto dos padroes do aluno (vazio se ainda ha poucos lances)."""
    d = d or _prog_ler()
    if d["lances"] < 8:
        return ""
    partes = []
    pior = None
    for f, (n, e) in d["por_fase"].items():
        if n >= 5 and e / float(n) >= 0.2 and (pior is None or e / float(n) > pior[1]):
            pior = (f, e / float(n))
    if pior:
        partes.append(f"erra mais no {pior[0]}, com {round(pior[1] * 100)} por cento dos lances perdendo vantagem")
    top = sorted(((n, t_) for t_, n in d["temas"].items() if n >= 3 and t_ != "outros"), reverse=True)[:2]
    if top:
        partes.append("costuma deixar passar " + " e ".join(f"{t_}, {n} vezes" for n, t_ in top))
    tend = _tendencia(d)
    if tend:
        partes.append(tend)
    return ", e ".join(partes)


def _registrar(board, sai):
    """Registra o lance avaliado do aluno; devolve fatos extras se o erro e recorrente."""
    try:
        if not sai or "perda" not in sai:
            return []
        perda = sai["perda"]
        tema = sai.get("tema") or ""
        n = registrar_lance(_fase(board), perda, tema)
        if perda > 60 and n >= 3 and tema not in ("", "outros"):
            return [f"Atenção: este é um padrão seu. O tema {tema} já passou despercebido {n} vezes nos seus treinos."]
    except Exception as exc:
        _log(f"nao consegui registrar o progresso: {type(exc).__name__}: {str(exc)[:120]}")
    return []


def _progresso_txt():
    d = _prog_ler()
    if d["lances"] == 0:
        return ("TEACHER_PROGRESS_EMPTY: ainda não há lances avaliados. Jogue algumas partidas com a aula ligada "
                "e eu passo a guardar seus erros.")
    ok = round(100.0 * (d["lances"] - d["erros"]) / d["lances"])
    linhas = [f"{d['lances']} lances avaliados em {d['sessoes']} sessões de treino, "
              f"{ok} por cento sem perder vantagem relevante."]
    fases = [f"{f}: {e} erros em {n} lances" for f, (n, e) in d["por_fase"].items()]
    if fases:
        linhas.append("Por fase, " + "; ".join(fases) + ".")
    top = sorted(((n, t_) for t_, n in d["temas"].items()), reverse=True)[:3]
    if top:
        linhas.append("Temas que mais passaram despercebidos: " + "; ".join(f"{t_}, {n} vezes" for n, t_ in top) + ".")
    perf = perfil_texto(d)
    if perf:
        linhas.append("Em resumo, o aluno " + perf + ".")
    return ("TEACHER_PROGRESS: fale como um treinador, com incentivo e sugerindo um foco de estudo para a próxima "
            "partida, usando só estes dados, sem inventar nada: " + " ".join(linhas))


# --------------------------------------------------------------------------- professor (Gemini como treinador)
_USAR_LLM = True            # False = volta a falar so as frases prontas do motor

_SISTEMA_PROFESSOR = (
    "Voce e um professor de xadrez experiente, nivel mestre, dando aula falada em portugues do Brasil "
    "a um aluno enquanto ele joga. Voce recebe FATOS calculados por um motor (melhor jogada, motivos, "
    "resposta esperada, avaliacao). Transforme-os numa explicacao natural e instrutiva, como um treinador "
    "falando: diga a ideia da jogada, o plano por tras dela e o principio estrategico envolvido "
    "(desenvolvimento, centro, estrutura de peoes, casas fracas, atividade das pecas, seguranca do rei, "
    "trocas favoraveis, finais), e o que o aluno deve observar, sempre que isso decorrer da posicao. "
    "Va alem dos fatos no PORQUE: acrescente a ideia estrategica e o plano tipicos desta posicao e desta fase "
    "do jogo, em linguagem de treinador, sem repetir os fatos palavra por palavra e sem citar lances que nao "
    "estejam nos fatos. "
    "REGRAS: use SOMENTE as jogadas, ameacas e avaliacoes que estao nos fatos; nunca invente lances, "
    "variantes nem numeros; escreva os lances exatamente como aparecem nos fatos (por extenso, como "
    "'peao, e 2 para e 4'); nao use markdown, listas, emojis, parenteses nem simbolos, porque o texto sera "
    "lido em voz alta; frases curtas e variadas, tom de professor paciente; sem cumprimentos; nao mencione "
    "'fatos' nem 'motor'. Se houver comentario sobre o lance anterior, comece por ele."
)


def _fase(b):
    """abertura / meio-jogo / final, de forma simples (material sem peoes e numero do lance)."""
    ch = _chess()
    val = {ch.KNIGHT: 3, ch.BISHOP: 3, ch.ROOK: 5, ch.QUEEN: 9}
    tot = sum(val.get(pc.piece_type, 0) for pc in b.piece_map().values())
    if tot <= 24:
        return "final"
    if b.fullmove_number <= 10 and tot >= 50:
        return "abertura"
    return "meio-jogo"


def _contexto(b, minha, prefacio, fatos, nivel, perfil=""):
    return {"fen": b.fen(), "lance": b.fullmove_number, "fase": _fase(b),
            "cor": "brancas" if minha else "pretas", "nivel": nivel,
            "pre": list(prefacio or []), "fatos": list(fatos or []), "perfil": perfil or ""}


def _limpar_texto(txt):
    txt = str(txt or "")
    txt = re.sub(r"[*#`_>\[\]{}|~]", " ", txt)
    txt = re.sub(r"\([^)]*\)", " ", txt)
    txt = " ".join(txt.split())
    return txt


def _frases_de(texto):
    partes = [x.strip() for x in re.split(r"(?<=[.!?])\s+", texto) if x.strip()]
    return partes or ([texto] if texto else [])


def _aula_llm(ctx, timeout_ms=9000):
    """Pede ao Gemini uma aula falada a partir dos fatos do motor. None se falhar (ai usa as frases prontas)."""
    from core import gemini as gem
    curto = ctx.get("nivel") == "curto"
    tam = ("No maximo 2 frases curtas (ate 45 palavras)." if curto
           else "De 4 a 7 frases curtas (ate 120 palavras).")
    prompt = (
        _SISTEMA_PROFESSOR + "\n\n"
        f"Posicao (FEN): {ctx['fen']}\n"
        f"Lance numero {ctx['lance']}, fase: {ctx['fase']}. O aluno joga de {ctx['cor']} e e a vez dele.\n"
        + ("Comentario sobre o lance anterior: " + " ".join(ctx["pre"]) + "\n" if ctx["pre"] else "")
        + ("Historico do aluno nos treinos (use no maximo UMA mencao curta e so se tiver relacao com "
           "este lance; nunca invente): " + ctx["perfil"] + "\n" if ctx.get("perfil") else "")
        + "FATOS: " + " ".join(ctx["fatos"]) + "\n\n"
        + tam + " Responda apenas com o texto da aula."
    )
    cfg = {"system_instruction": _SISTEMA_PROFESSOR, "temperature": 0.6}
    raw = gem.text(prompt, tier=gem.FAST, config=cfg, timeout_ms=timeout_ms)
    txt = _limpar_texto(raw)
    if len(txt) < 20:
        return None
    return txt[:1100].rsplit(" ", 1)[0] if len(txt) > 1100 else txt


class _Fala:
    """Fala com a voz do Gemini escolhida no Jarvis (nao a voz robotica do Windows).

    Duas threads: uma sintetiza a proxima frase enquanto a outra toca a atual. Uma aula nova
    (ou cancelar) corta o que estiver tocando. So se o Gemini falhar 3 vezes seguidas numa
    frase e que ela cai na voz do Windows, para a aula nao ficar muda."""

    def __init__(self):
        self.q: "queue.Queue" = queue.Queue()
        self.pcmq: "queue.Queue" = queue.Queue(maxsize=3)   # (gen, texto, futuro) em ordem
        self.pool = concurrent.futures.ThreadPoolExecutor(2, thread_name_prefix="chess-teacher-gen")
        self.gen = 0
        self._sapi = None
        threading.Thread(target=self._sintetizar, daemon=True, name="chess-teacher-tts").start()
        threading.Thread(target=self._tocar, daemon=True, name="chess-teacher-voz").start()

    def _gerar(self, gen, texto):
        """PCM da frase na voz escolhida no Jarvis, ou None (ate 3 tentativas)."""
        import asyncio
        try:
            from core import gemini as gem
        except Exception as exc:
            _log(f"voz do Jarvis indisponivel (core.gemini): {exc}")
            return None
        try:
            from memory.config_manager import get_voice
            voz = get_voice()
        except Exception:
            voz = "Charon"
        for _ in range(3):
            if gen != self.gen:
                return None
            try:
                pcm = asyncio.run(gem.speech_pcm(texto, voz))
            except Exception as exc:
                _log(f"sintese falhou: {type(exc).__name__}: {str(exc)[:120]}")
                pcm = None
            if pcm:
                return pcm
            time.sleep(0.4)
        if gen == self.gen:
            _log(f"Gemini nao devolveu audio; usando a voz do Windows nesta frase: {texto[:60]}")
        return None

    def _sintetizar(self):
        """Dispara a sintese das proximas frases em paralelo, mantendo a ordem."""
        while True:
            gen, texto = self.q.get()
            if gen != self.gen:
                continue
            fut = self.pool.submit(self._gerar, gen, texto)
            while gen == self.gen:
                try:
                    self.pcmq.put((gen, texto, fut), timeout=0.2)
                    break
                except queue.Full:
                    pass

    def _tocar(self):
        import numpy as np
        import sounddevice as sd
        dev = None
        try:
            from memory.config_manager import get_output_device
            dev = get_output_device() or None
        except Exception:
            pass
        while True:
            gen, texto, fut = self.pcmq.get()
            pcm = None
            while gen == self.gen:
                try:
                    pcm = fut.result(timeout=0.1)
                    break
                except concurrent.futures.TimeoutError:
                    continue
                except Exception:
                    pcm = None
                    break
            if gen != self.gen:
                continue
            if not pcm:
                self._falar_sapi(gen, texto)
                continue
            arr = np.frombuffer(pcm, dtype=np.int16)
            for tentativa in range(2):
                try:
                    sd.play(arr, _PCM_HZ, device=dev)
                    break
                except Exception as exc:
                    if dev is not None and tentativa == 0:
                        _log(f"dispositivo de saida '{dev}' falhou ({exc}); usando o padrao")
                        dev = None
                        continue
                    _log(f"reproducao falhou: {exc}")
                    break
            else:
                continue
            fim = time.time() + len(arr) / float(_PCM_HZ) + 0.4
            while time.time() < fim and gen == self.gen:
                time.sleep(0.03)
            if gen != self.gen:
                try:
                    sd.stop()
                except Exception:
                    pass
            else:
                try:
                    sd.wait()
                except Exception:
                    pass

    def _falar_sapi(self, gen, texto):
        """Ultimo recurso (voz do Windows) quando o Gemini nao responde."""
        try:
            if self._sapi is None:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
            v = self._sapi
            v.Speak(texto, 1)
            while not v.WaitUntilDone(80):
                if gen != self.gen:
                    v.Speak("", 3)
                    break
        except Exception as exc:
            _log(f"voz do Windows indisponivel: {exc}")

    def _parar_som(self):
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass

    def _enfileirar(self, g, frases):
        for f in frases:
            for parte in _partir(f):
                if g != self.gen:
                    return
                print(f"[professor] >> {parte}", flush=True)
                self.q.put((g, parte))

    def falar(self, frases):
        self.gen += 1
        g = self.gen
        self._parar_som()
        self._enfileirar(g, frases)

    def falar_aula(self, fallback, ctx):
        """Fala a aula escrita pelo Gemini (professor); se falhar, fala as frases prontas do motor.
        Roda em thread propria para nao travar a leitura do tabuleiro."""
        self.gen += 1
        g = self.gen
        self._parar_som()

        def _job():
            texto = None
            if _USAR_LLM and ctx:
                try:
                    texto = _aula_llm(ctx)
                except Exception as exc:
                    _log(f"professor-ia falhou ({type(exc).__name__}: {str(exc)[:120]}); usando frases prontas")
            if g != self.gen:
                return
            if texto:
                partes = _frases_de(texto)
                _guardar(partes)
                _log(f"aula (professor-ia): {texto}")
                self._enfileirar(g, partes)
            else:
                if _USAR_LLM and ctx:
                    _log("professor-ia sem resposta; usando frases prontas do motor")
                self._enfileirar(g, fallback)

        threading.Thread(target=_job, daemon=True, name="chess-teacher-aula").start()

    def cancelar(self):
        self.gen += 1
        self._parar_som()


_FALA = [None]


def _fala():
    if _FALA[0] is None:
        _FALA[0] = _Fala()
    return _FALA[0]


# --------------------------------------------------------------------------- tela e seta (proprias do professor)
def _ca():
    from actions import chess_assistant
    return chess_assistant


class _Desenho:
    """Desenha/apaga a seta numa thread propria: se a interface do Jarvis travar, a leitura continua."""

    def __init__(self):
        self.lock = threading.Lock()
        self.ev = threading.Event()
        self.fn = None
        self.label = ""
        self.th = None

    def pedir(self, label, fn):
        with self.lock:
            self.fn, self.label = fn, label     # so o ultimo pedido importa
            if self.th is None or not self.th.is_alive():
                self.th = threading.Thread(target=self._run, daemon=True, name="chess-teacher-seta")
                self.th.start()
        self.ev.set()

    def _run(self):
        while True:
            self.ev.wait()
            self.ev.clear()
            with self.lock:
                fn, label, self.fn = self.fn, self.label, None
            if not fn:
                continue
            t0 = time.time()
            try:
                fn()
            except Exception as exc:
                _log(f"seta ({label}) falhou: {exc}")
            dt = time.time() - t0
            if dt > 1.5:
                _log(f"interface demorou {dt:.1f}s para {label}")


_DES = _Desenho()


class _Sessao:
    def __init__(self):
        self.thread = None
        self.parar = threading.Event()
        self.erro = ""
        self.cor = ""
        self.nivel = "detalhado"
        self.resync = None
        self.seta_ate = 0.0
        self.board = None      # posicao atual da aula
        self.pre = None        # {"fen", "infos"} da ultima posicao em que era a vez do usuario
        self.ultima = []       # frases da ultima explicacao

    @property
    def ativa(self):
        return bool(self.thread and self.thread.is_alive())


_S = _Sessao()
_LOCK = threading.Lock()


def _guardar(frases):
    _S.ultima = list(frases)
    try:
        _DATA.mkdir(parents=True, exist_ok=True)
        (_DATA / "ultima_aula.txt").write_text("\n".join(frases), encoding="utf-8")
    except Exception:
        pass


def _esconder_jarvis(player):
    try:
        if player is not None and callable(getattr(player, "hide_window", None)):
            player.hide_window()
            time.sleep(0.4)
    except Exception as exc:
        _log(f"nao consegui esconder o Jarvis: {exc}")


def _limpar_seta(player):
    if time.time() < _S.seta_ate and player is not None:
        try:
            _DES.pedir("limpar", player.clear_screen_marks)
        except Exception:
            pass
    _S.seta_ate = 0.0


def _desenhar_seta(player, mon, roi, wb, sq_a, sq_b):
    if player is None or not callable(getattr(player, "show_screen_marks", None)):
        return
    try:
        from gui.screen_marks import normalize_screen_marks
        ca = _ca()
        x0, y0, w, h = roi
        cw, ch_ = w / 8.0, h / 8.0

        def centro(sq):
            r, c = ca.rc_from_sq(sq, wb)
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
        _DES.pedir("desenhar", lambda: player.show_screen_marks(payload, operation="replace"))
        _S.seta_ate = time.time() + 44
    except Exception as exc:
        _log(f"seta falhou: {exc}")


# --------------------------------------------------------------------------- aula ao vivo
def _loop(player, cfg, T, L, thr, opts, fala, motor):
    import mss
    ca = _ca()
    ch = _chess()
    tempo = opts["tempo"]
    wb = cfg["white_bottom"]
    roi = list(cfg["roi"])
    mon = cfg["monitor"]
    minha = ch.WHITE if wb else ch.BLACK
    area = {"left": roi[0], "top": roi[1], "width": roi[2], "height": roi[3]}
    pat_w = ca.symmap(ch.Board())
    pat_b = {ca.sq_from_rc(*ca.rc_from_sq(sq, False), True): sym for sq, sym in pat_w.items()}
    cores = cfg.get("cores")
    lado_ref = roi[2]
    t_reloc = [0.0]
    ult_img = [None]
    tr = ca.Tracker()
    try:
        _nova_sessao()
    except Exception:
        pass

    def relocar(sct):
        nonlocal roi, area
        if not cores:
            return False
        full = ca._grab(sct, mon)
        bb = ca._achar_tabuleiro(full, cores, lado_ref)
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

    def ensinar(prefacio=None):
        prefacio = list(prefacio or [])
        b = tr.board
        _S.board = b
        if b.is_game_over():
            _limpar_seta(player)
            fala.falar(prefacio + ["Fim de jogo."])
            return
        if b.turn != minha:
            _limpar_seta(player)
            if prefacio:
                _guardar(prefacio)
                fala.falar(prefacio)
            else:
                fala.cancelar()
            return
        if not b.is_valid():
            _log(f"posicao lida invalida ({b.status()!r}); ignorando")
            _limpar_seta(player)
            return
        try:
            infos = motor.analisar(b, tempo, 3)
        except Exception as exc:
            _log(f"motor falhou ({type(exc).__name__}: {str(exc)[:160]}); sem aula nesta jogada")
            return
        if not infos:
            return
        res = explicar(b, infos, _S.nivel)
        _S.pre = {"fen": b.fen(), "infos": infos}
        frases = prefacio + res["frases"]
        _guardar(frases)
        _log(f"aula: {res['texto']} | fen={b.fen()}")
        fala.falar_aula(frases, _contexto(b, minha == ch.WHITE, prefacio, res["frases"], _S.nivel, perfil_texto()))
        m = res["move"]
        _desenhar_seta(player, mon, roi, wb, m.from_square, m.to_square)

    def processar(pl):
        """Atualiza o Tracker; se foi UM lance, devolve a nota do seu lance ou o comentario do adversario."""
        old = tr.board.copy(stack=False)
        n0 = len(tr.board.move_stack)
        r = tr.update(pl)
        pref = []
        if r == "mov":
            fala.cancelar()
            novos = tr.board.move_stack[n0:]
            if len(novos) == 1:
                mv = novos[0]
                pc = old.piece_at(mv.from_square)
                if pc is not None and pc.color == old.turn:
                    try:
                        if old.turn == minha:
                            pre = _S.pre
                            if opts["avaliar"] and pre and pre["fen"] == old.fen():
                                sai = {}
                                pref += avaliar_lance(lambda b2: motor.nota(b2, tempo, minha), old, mv, pre["infos"], sai)
                                pref += _registrar(old, sai)
                        elif opts["comentar"]:
                            pref += comentar_lance(old, mv)
                    except Exception as exc:
                        _log(f"comentario falhou: {type(exc).__name__}: {exc}")
        return r, pref

    ultimo, estavel, feito = None, 0, False
    try:
        with mss.mss() as s:
            if cores:
                relocar(s)
            t_prev = time.time()
            while not _S.parar.is_set():
                agora = time.time()
                if agora - t_prev > 3.0:
                    _log(f"leitura ficou parada {agora - t_prev:.1f}s")
                t_prev = agora
                img = ca._grab(s, area)
                ult_img[0] = img
                raw = ca.read_position(img, T, L, thr, True)
                pl = ca._remap(raw, wb)
                if len(raw) < 8 and cores and time.time() - t_reloc[0] > 1.5:
                    t_reloc[0] = time.time()
                    if relocar(s):
                        ultimo, estavel, feito = None, 0, False
                        tr.board = None
                        continue
                if not ca._plausivel(raw):
                    if time.time() < _S.seta_ate:
                        _limpar_seta(player)       # a seta pode estar confundindo a leitura
                        _log("leitura impossivel com a seta na tela; tirando a seta e lendo de novo")
                        time.sleep(0.15)
                    else:
                        time.sleep(0.05)
                    continue
                if pl == ultimo:
                    estavel += 1
                else:
                    ultimo, estavel, feito = pl, 1, False
                    time.sleep(0.03)
                    continue
                aviso = []
                if estavel >= 2 and not feito:
                    if raw == pat_w or raw == pat_b:
                        nwb = (raw == pat_w)
                        if tr.board is None or nwb != wb or ca.symmap(tr.board) != pat_w:
                            wb = nwb
                            minha = ch.WHITE if wb else ch.BLACK
                            tr.board = None
                            _limpar_seta(player)
                            _S.cor = "brancas" if wb else "pretas"
                            _log(f"partida nova: voce esta de {_S.cor}")
                            aviso = [f"Nova partida. Você está de {_S.cor}."]
                            if not wb:
                                aviso.append("Aguardando as brancas jogarem.")
                            pl = ca._remap(raw, wb)
                            ultimo = pl
                    elif tr.board is None:
                        wb = ca._detectar_wb(raw, wb)
                        minha = ch.WHITE if wb else ch.BLACK
                        _S.cor = "brancas" if wb else "pretas"
                        _log(f"cor detectada (partida em andamento): {_S.cor} embaixo")
                        pl = ca._remap(raw, wb)
                        ultimo = pl
                if _S.resync and estavel >= 2:
                    nwb = ca._detectar_wb(raw, wb)
                    if nwb != wb:
                        wb = nwb
                        minha = ch.WHITE if wb else ch.BLACK
                        _S.cor = "brancas" if wb else "pretas"
                        pl = ca._remap(raw, wb)
                    vez = minha if _S.resync == "me" else (not minha)
                    _S.resync = None
                    _limpar_seta(player)
                    tr.init_from(pl, vez)
                    feito = True
                    _log("ressincronizacao manual")
                    ensinar()
                    continue
                if estavel >= 2 and not feito:
                    if tr.board is None:
                        vez = ch.WHITE if pl == ca.symmap(ch.Board()) else (
                            minha if opts["turno"] == "me" else (not minha))
                        tr.init_from(pl, vez)
                        feito = True
                        ensinar(aviso)
                    else:
                        r, pref = processar(pl)
                        if r == "mov":
                            feito = True
                            _log(f"lance detectado | fen={tr.board.fen()}")
                            ensinar(pref)
                        elif r == "igual":
                            feito = True
                        elif r == "desconhecido" and time.time() < _S.seta_ate:
                            _limpar_seta(player)       # a propria seta pode estar tapando pecas
                            time.sleep(0.1)
                            ultimo, estavel = None, 0
                            continue
                if estavel == 14 and not feito:        # nada bate: ressincroniza
                    if cores and relocar(s):
                        _limpar_seta(player)
                        ultimo, estavel, feito = None, 0, False
                        tr.board = None
                        continue
                    nwb = ca._detectar_wb(raw, wb)
                    if nwb != wb:
                        wb = nwb
                        minha = ch.WHITE if wb else ch.BLACK
                        _S.cor = "brancas" if wb else "pretas"
                        pl = ca._remap(raw, wb)
                    vez = ca._vez_provavel(tr.board, pl, minha)
                    _log(f"leitura nao bate com nenhum lance; ressincronizando pecas_lidas={len(pl)}")
                    tr.init_from(pl, vez)
                    feito = True
                    ensinar()
                time.sleep(0.03)
    except Exception as exc:
        _S.erro = f"{type(exc).__name__}: {exc}"
        _log(f"loop parou: {_S.erro}")
    finally:
        _limpar_seta(player)
        fala.cancelar()
        motor.fechar()


# --------------------------------------------------------------------------- acoes
def _bool(v, padrao):
    if v is None:
        return padrao
    if isinstance(v, str):
        return v.strip().lower() not in ("0", "false", "nao", "não", "no", "off", "")
    return bool(v)


def _tempo(params, padrao=0.5):
    try:
        return max(0.1, min(3.0, float(params.get("think_time") or padrao)))
    except (TypeError, ValueError):
        return padrao


def _carregar_calibracao():
    import numpy as np
    if not (_CFG.exists() and _TPL.exists()):
        return None
    cfg = json.loads(_CFG.read_text(encoding="utf-8"))
    d = np.load(_TPL)
    return cfg, d["T"], d["L"], float(d["thr"])


def _calibrar(params, player):
    """A calibracao e a mesma do assistente (so refazer ao trocar de site/tema de pecas)."""
    return _ca().chess_assistant({**params, "action": "calibrate"}, player)


def _iniciar(params, player):
    import traceback
    try:
        r = _iniciar_impl(params, player)
    except Exception:
        r = "TEACHER_START_CRASH: " + traceback.format_exc()[-700:]
    _log("iniciar -> " + r)
    return r


def _iniciar_impl(params, player):
    ca = _ca()
    with _LOCK:
        if _S.ativa:
            return "TEACHER_ALREADY_RUNNING: o professor já está dando aula."
        try:
            if ca._S.ativa:
                return ("TEACHER_BLOCKED: o assistente de xadrez está rodando. Pare-o primeiro "
                        "(chess_assistant action=stop) para os dois não desenharem setas ao mesmo tempo.")
        except Exception:
            pass
        cal = _carregar_calibracao()
        if not cal:
            return "TEACHER_NOT_CALIBRATED: calibre primeiro (action=calibrate) com a posição inicial na tela."
        cfg, T, L, thr = cal
        sf = _achar_stockfish(params.get("stockfish_path"))
        if not sf:
            return "STOCKFISH_NOT_FOUND: coloque o .exe em tools\\stockfish ou passe stockfish_path."
        try:
            motor = _Motor(sf)
        except Exception as exc:
            return f"STOCKFISH_FAILED: {type(exc).__name__}: {str(exc)[:160]}"
        opts = {
            "tempo": _tempo(params),
            "turno": "opponent" if str(params.get("turn") or "me").lower().startswith("opp") else "me",
            "avaliar": _bool(params.get("grade_my_moves"), True),
            "comentar": _bool(params.get("comment_opponent"), True),
        }
        nivel = str(params.get("level") or "").lower()
        _S.nivel = "curto" if nivel.startswith("c") else "detalhado"
        _esconder_jarvis(player)
        _S.parar.clear()
        _S.erro = ""
        _S.board = None
        _S.pre = None
        fala = _fala()
        fala.falar(["Professor de xadrez ligado. Vou explicar cada jogada."])
        _S.thread = threading.Thread(target=_loop, args=(player, cfg, T, L, thr, opts, fala, motor),
                                     daemon=True, name="chess-teacher")
        _S.thread.start()
    return ("TEACHER_STARTED: o professor está olhando a tela, vai FALAR e desenhar a explicação de cada jogada, "
            "avaliar os lances do usuário e comentar os do adversário. O HUD do Jarvis foi escondido "
            "(volta pelo ícone da bandeja). Não repita as explicações em voz alta; responda só com uma frase curta.")


def _parar(player):
    if not _S.ativa:
        return "TEACHER_NOT_RUNNING: o professor já estava parado."
    _S.parar.set()
    _S.thread.join(timeout=4)
    _fala().cancelar()
    _limpar_seta(player)
    return "TEACHER_STOPPED: aula encerrada."


def _status():
    if _S.ativa:
        return (f"TEACHER_RUNNING: você está de {_S.cor or 'cor ainda nao detectada'}; explicação "
                f"{_S.nivel}. Última aula: {' '.join(_S.ultima)[:300] or 'ainda nenhuma'}")
    base = "TEACHER_STOPPED"
    if _S.erro:
        base += f" (parou por erro: {_S.erro})"
    return base + f". Calibrado: {'sim' if (_CFG.exists() and _TPL.exists()) else 'nao'}."


def _licao(board, move_txt, tempo, sf):
    """Explica a posicao (e o lance pedido, se houver). Devolve (texto, erro)."""
    ch = _chess()
    if not board.is_valid():
        return None, "TEACHER_INVALID_POSITION: posição inválida (reis, peças ou vez impossíveis)."
    if board.is_game_over():
        return None, "TEACHER_GAME_OVER: a partida já terminou nessa posição."
    motor = _Motor(sf)
    try:
        infos = motor.analisar(board, tempo, 3)
        if not infos:
            return None, "TEACHER_NO_ANALYSIS: o motor não devolveu análise."
        frases = []
        mv = None
        if move_txt:
            mv = achar_lance(board, move_txt)
            if mv is None:
                return None, f"TEACHER_INVALID_MOVE: '{move_txt}' não é um lance legal nessa posição."
            frases.append(f"Sobre {descrever(board, mv)}:")
            frases += motivos(board, mv, True)
            frases += avaliar_lance(lambda b2: motor.nota(b2, tempo, board.turn), board, mv, infos)
        if mv is None or mv != infos[0]["move"]:
            res = explicar(board, infos, _S.nivel)
            frases += (["Para comparar:"] if mv else []) + res["frases"]
        return " ".join(frases), None
    finally:
        motor.fechar()


def _explicar_fen(params, usar_sessao=False):
    ch = _chess()
    sf = _achar_stockfish(params.get("stockfish_path"))
    if not sf:
        return "STOCKFISH_NOT_FOUND: coloque o .exe em tools\\stockfish ou passe stockfish_path."
    fen = str(params.get("fen") or "").strip()
    if fen:
        try:
            board = ch.Board(fen)
        except ValueError:
            return "TEACHER_INVALID_FEN: não entendi esse FEN."
    elif usar_sessao and _S.ativa and _S.board is not None:
        board = _S.board.copy(stack=False)
    else:
        return "TEACHER_NEEDS_POSITION: passe fen=... (ou use durante uma aula em andamento)."
    texto, erro = _licao(board, params.get("move"), _tempo(params, 0.6), sf)
    if erro:
        return erro
    _guardar([texto])
    return ("TEACHER_LESSON: explique ao usuário, em português e como um treinador experiente (a ideia, o plano e o "
            "princípio por trás da jogada), usando só os lances e avaliações que estão aqui, "
            "sem inventar nada: " + texto)


def _explicar_tela(params, player):
    import mss
    ca = _ca()
    ch = _chess()
    cal = _carregar_calibracao()
    if not cal:
        return "TEACHER_NOT_CALIBRATED: calibre primeiro (action=calibrate) com a posição inicial na tela."
    cfg, T, L, thr = cal
    sf = _achar_stockfish(params.get("stockfish_path"))
    if not sf:
        return "STOCKFISH_NOT_FOUND: coloque o .exe em tools\\stockfish ou passe stockfish_path."
    _esconder_jarvis(player)
    mon = cfg["monitor"]
    roi = list(cfg["roi"])
    with mss.mss() as s:
        if cfg.get("cores"):
            full = ca._grab(s, mon)
            bb = ca._achar_tabuleiro(full, cfg["cores"], roi[2])
            if bb:
                sx = full.shape[1] / float(mon["width"])
                sy = full.shape[0] / float(mon["height"])
                roi = [mon["left"] + int(round(bb[0] / sx)), mon["top"] + int(round(bb[1] / sy)),
                       int(round(bb[2] / sx)), int(round(bb[3] / sy))]
        img = ca._grab(s, {"left": roi[0], "top": roi[1], "width": roi[2], "height": roi[3]})
    raw = ca.read_position(img, T, L, thr, True)
    if len(raw) < 2 or not ca._plausivel(raw):
        return "TEACHER_BOARD_NOT_FOUND: não achei um tabuleiro válido na tela. Deixe-o visível e tente de novo."
    wb = ca._detectar_wb(raw, cfg["white_bottom"])
    pl = ca._remap(raw, wb)
    minha = ch.WHITE if wb else ch.BLACK
    vez = (not minha) if str(params.get("turn") or "me").lower().startswith("opp") else minha
    tr = ca.Tracker()
    tr.init_from(pl, vez)
    b = tr.board
    if not b.is_valid():
        return "TEACHER_INVALID_POSITION: a leitura da tela não formou uma posição válida; tente de novo."
    if b.is_game_over():
        return "TEACHER_GAME_OVER: a partida já terminou nessa posição."
    motor = _Motor(sf)
    try:
        infos = motor.analisar(b, _tempo(params, 0.6), 3)
    finally:
        motor.fechar()
    if not infos:
        return "TEACHER_NO_ANALYSIS: o motor não devolveu análise."
    nv = str(params.get("level") or _S.nivel).lower()
    res = explicar(b, infos, "curto" if nv.startswith("c") else "detalhado")
    _S.board = b
    _guardar(res["frases"])
    _log(f"explain: {res['texto']} | fen={b.fen()}")
    _fala().falar(res["frases"])
    m = res["move"]
    _desenhar_seta(player, mon, roi, wb, m.from_square, m.to_square)
    return ("TEACHER_EXPLAINED: o professor já FALOU e desenhou a explicação na tela. "
            "Não repita; responda só com uma frase curta.")


def chess_teacher(parameters: dict, player=None, speak=None) -> str:
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
        if action == "status":
            return _status()
        if action == "explain":
            return _explicar_tela(params, player)
        if action == "explain_fen":
            return _explicar_fen(params)
        if action == "why":
            if not params.get("move"):
                return "TEACHER_NEEDS_MOVE: diga qual lance (ex.: move=Nf3 ou move=g1f3)."
            return _explicar_fen(params, usar_sessao=True)
        if action == "repeat":
            if not _S.ultima:
                return "TEACHER_NOTHING_TO_REPEAT: ainda não houve nenhuma explicação."
            _fala().falar(_S.ultima)
            return "TEACHER_REPEATING: o professor está repetindo a última explicação. Não repita em voz alta."
        if action == "level":
            nv = str(params.get("level") or "").lower()
            if not nv:
                return f"TEACHER_LEVEL: explicação {_S.nivel}."
            _S.nivel = "curto" if nv.startswith("c") else "detalhado"
            return f"TEACHER_LEVEL_SET: explicação {_S.nivel} a partir da próxima jogada."
        if action == "progress":
            return _progresso_txt()
        if action == "resync":
            if not _S.ativa:
                return "TEACHER_NOT_RUNNING: inicie a aula primeiro (action=start)."
            _S.resync = "opponent" if str(params.get("turn") or "me").lower().startswith("opp") else "me"
            return "TEACHER_RESYNC_REQUESTED: relendo o tabuleiro agora."
        return "TEACHER_INVALID_ACTION: use start, stop, status, explain, explain_fen, why, repeat, level, progress, resync ou calibrate."
    except ImportError as exc:
        _log(f"dependencia faltando: {exc}")
        return f"TEACHER_DEPENDENCY_MISSING: {exc}. Instale: pip install python-chess opencv-python mss pywin32"
    except Exception as exc:
        _log(f"falhou: {type(exc).__name__}: {str(exc)[:200]}")
        return f"TEACHER_FAILED: {type(exc).__name__}: {str(exc)[:200]}"


TOOL = {
    "name": "chess_teacher",
    "description": (
        "PROFESSOR de xadrez (separado do assistente de xadrez). Ensina: a cada jogada FALA uma explicação "
        "detalhada do porquê de jogar naquela casa (ideia do lance, ameaças, desenvolvimento, centro, segurança do rei), "
        "o que o adversário deve responder, as alternativas, avalia o lance que o usuário jogou (excelente, imprecisão, erro) "
        "e comenta o lance do adversário, desenhando a seta no tabuleiro. "
        "Fluxo: (1) action=calibrate uma vez por site/tema (mesma calibração do assistente). (2) action=start para a aula "
        "ao vivo (NAO pergunte a cor; é detectada). (3) action=stop. Outros: action=explain (explica uma vez o que está na tela), "
        "action=explain_fen (posição por FEN, com move= opcional, sem tela), action=why (move=Nf3: por que jogar ou não esse lance "
        "na aula em andamento), action=repeat (repete a última explicação), action=level (level=curto ou detalhado), "
        "action=resync (turn=me/opponent), action=status. Depois de start/explain NAO narre: o professor já fala. "
        "Use só contra bots, treino ou estudo; contra pessoas em sites online é trapaça. "
        "action=progress (resume os erros que mais se repetem e a evolução do aluno entre partidas; o professor guarda isso sozinho a cada lance avaliado). "
        "Para apenas dizer a melhor jogada, sem ensinar, use o chess_assistant."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING",
                       "enum": ["calibrate", "start", "stop", "status", "explain", "explain_fen", "why",
                                "repeat", "level", "resync", "progress"],
                       "description": "O que fazer."},
            "level": {"type": "STRING", "enum": ["detalhado", "curto"],
                      "description": "Quanto explicar (padrão detalhado)."},
            "fen": {"type": "STRING", "description": "Posição em FEN (explain_fen, ou why fora de uma aula)."},
            "move": {"type": "STRING", "description": "Lance a explicar, em SAN (Nf3, e4, O-O) ou UCI (g1f3)."},
            "think_time": {"type": "NUMBER", "description": "Segundos de análise por jogada (0.1 a 3; padrão 0.5)."},
            "turn": {"type": "STRING", "enum": ["me", "opponent"],
                     "description": "Em start (partida em andamento), explain ou resync: de quem é a vez (padrão me)."},
            "grade_my_moves": {"type": "BOOLEAN", "description": "Avaliar os lances do usuário (padrão true)."},
            "comment_opponent": {"type": "BOOLEAN", "description": "Comentar os lances do adversário (padrão true)."},
            "bottom_color": {"type": "STRING", "enum": ["white", "black"],
                             "description": "OPCIONAL, só em calibrate; normalmente NAO informe."},
            "stockfish_path": {"type": "STRING", "description": "Caminho do stockfish.exe, se não estiver em tools\\stockfish."},
        },
        "required": ["action"],
    },
    "handler": chess_teacher,
    "tier": "extra",
    "brief": "Chess teacher: explains every move aloud and why, grades yours, comments the opponent's.",
}
