"""Small, strict SMILES reader and deterministic 2D molecule layout.

This is deliberately not a chemistry engine: it parses common structural SMILES
(connectivity, bond order, branches and ring closures), rejects unsupported
stereochemistry/isotopes, and lays out a graph for a labelled teaching card.
"""
from __future__ import annotations

import math
import re

MAX_ATOMS = 80
MAX_BONDS = 160
_ELEMENTS = {
    "H","B","C","N","O","F","P","S","Cl","Br","I","Si","Na","K","Ca",
    "Mg","Fe","Cu","Zn","Ag","Au","Pt","Al","Se","As","Li",
}
_AROMATIC = {"b","c","n","o","p","s"}
_BOND = {"-":1.0,"=":2.0,"#":3.0,":":1.5}


def parse_smiles(smiles: str) -> tuple[list[dict], list[dict]]:
    text = str(smiles or "").strip()
    if not text:
        raise ValueError("SMILES vazio.")
    atoms: list[dict] = []
    bonds: list[dict] = []
    branch_stack: list[int] = []
    rings: dict[str, tuple[int,float|None]] = {}
    previous: int | None = None
    pending: float | None = None
    i = 0

    def fail(message):
        raise ValueError(f"SMILES inválido na posição {i+1}: {message}")

    def add_atom(symbol: str, aromatic=False, charge=0):
        nonlocal previous, pending
        if len(atoms) >= MAX_ATOMS:
            fail(f"mais de {MAX_ATOMS} átomos.")
        if previous is not None:
            order = pending
            if order is None:
                order = 1.5 if aromatic and atoms[previous]["aromatic"] else 1.0
            bonds.append({"a":previous,"b":len(atoms),"order":order})
        atoms.append({"element":symbol,"aromatic":bool(aromatic),"charge":int(charge)})
        previous=len(atoms)-1
        pending=None

    while i < len(text):
        ch=text[i]
        if ch.isspace():
            i+=1
            continue
        if ch=="(":
            if previous is None: fail("ramificação sem átomo anterior.")
            branch_stack.append(previous); i+=1; continue
        if ch==")":
            if not branch_stack: fail("')' sem '(' correspondente.")
            previous=branch_stack.pop(); i+=1; continue
        if ch in _BOND:
            if previous is None or pending is not None: fail("ligação fora de posição.")
            pending=_BOND[ch]; i+=1; continue
        if ch.isdigit() or ch=="%":
            if previous is None: fail("anel sem átomo anterior.")
            if ch=="%":
                if i+2>=len(text) or not text[i+1:i+3].isdigit():
                    fail("fecho de anel '%' exige dois algarismos.")
                token=text[i+1:i+3]; i+=3
            else:
                token=ch; i+=1
            if token in rings:
                other, other_order=rings.pop(token)
                if other==previous: fail("anel fecha sobre o mesmo átomo.")
                order=pending if pending is not None else other_order
                if order is None:
                    order=1.5 if atoms[other]["aromatic"] and atoms[previous]["aromatic"] else 1.0
                bonds.append({"a":other,"b":previous,"order":order})
                pending=None
            else:
                rings[token]=(previous,pending); pending=None
            continue
        if ch=="[":
            end=text.find("]",i+1)
            if end<0: fail("'[' sem ']' correspondente.")
            token=text[i+1:end]
            match=re.fullmatch(r"([A-Z][a-z]?|[bcnops])(?:H\d*)?([+-]\d*|[+-])?",token)
            if not match: fail(f"átomo entre colchetes não suportado: [{token}].")
            raw=match.group(1); aromatic=raw in _AROMATIC
            element=raw.capitalize() if aromatic else raw
            if element not in _ELEMENTS: fail(f"elemento não suportado: {element}.")
            charge_txt=match.group(2) or ""
            charge=(1 if charge_txt.startswith("+") else -1 if charge_txt.startswith("-") else 0)
            digits=re.search(r"\d+",charge_txt)
            if digits: charge*=int(digits.group())
            add_atom(element,aromatic,charge)
            i=end+1; continue
        if ch.isupper():
            token=ch
            if i+1<len(text) and text[i+1].islower():
                candidate=ch+text[i+1]
                if candidate in _ELEMENTS: token=candidate
            if token not in _ELEMENTS: fail(f"elemento não suportado: {token}.")
            add_atom(token,False,0)
            i+=len(token); continue
        if ch in _AROMATIC:
            add_atom(ch.upper(),True,0)
            i+=1; continue
        fail(f"caractere não suportado: {ch!r}.")

    if branch_stack: fail("ramificação '(' não foi fechada.")
    if rings: fail("número de anel sem par: "+", ".join(sorted(rings)))
    if pending is not None: fail("ligação sem átomo no final.")
    if not atoms: fail("nenhum átomo encontrado.")
    if len(bonds)>MAX_BONDS: raise ValueError(f"mais de {MAX_BONDS} ligações.")
    return atoms,bonds


def layout_molecule(atoms: list[dict], bonds: list[dict]) -> list[dict]:
    """Return bounded normalised x/y coordinates using a deterministic force layout."""
    n=len(atoms)
    if n==0: return []
    if n==1: return [{"element":atoms[0]["element"],"charge":atoms[0].get("charge",0),"x":50.0,"y":50.0}]
    # Stable initial circle, then a small force-directed relaxation.
    positions=[
        [math.cos(math.tau*i/n)*40.0,math.sin(math.tau*i/n)*40.0]
        for i in range(n)
    ]
    edges=[(int(b["a"]),int(b["b"]),float(b.get("order",1))) for b in bonds]
    if any(a<0 or b<0 or a>=n or b>=n or a==b for a,b,_ in edges):
        raise ValueError("ligação aponta para um átomo inválido.")
    velocities=[[0.0,0.0] for _ in range(n)]
    desired=48.0
    for step in range(180):
        forces=[[0.0,0.0] for _ in range(n)]
        # Repulsion prevents labels/nodes from collapsing on top of each other.
        for i in range(n):
            for j in range(i+1,n):
                dx=positions[i][0]-positions[j][0]
                dy=positions[i][1]-positions[j][1]
                d2=max(16.0,dx*dx+dy*dy)
                f=1200.0/d2
                inv=1.0/math.sqrt(d2)
                fx=dx*inv*f; fy=dy*inv*f
                forces[i][0]+=fx; forces[i][1]+=fy
                forces[j][0]-=fx; forces[j][1]-=fy
        for a,b,order in edges:
            dx=positions[b][0]-positions[a][0]
            dy=positions[b][1]-positions[a][1]
            dist=max(0.01,math.hypot(dx,dy))
            f=(dist-desired)*0.028
            fx=dx/dist*f; fy=dy/dist*f
            forces[a][0]+=fx; forces[a][1]+=fy
            forces[b][0]-=fx; forces[b][1]-=fy
        damping=0.82
        for i in range(n):
            velocities[i][0]=(velocities[i][0]+forces[i][0])*damping
            velocities[i][1]=(velocities[i][1]+forces[i][1])*damping
            positions[i][0]+=max(-8,min(8,velocities[i][0]))
            positions[i][1]+=max(-8,min(8,velocities[i][1]))
    xs=[p[0] for p in positions]; ys=[p[1] for p in positions]
    minx,maxx=min(xs),max(xs); miny,maxy=min(ys),max(ys)
    sx=max(1.0,maxx-minx); sy=max(1.0,maxy-miny)
    scale=min(82.0/sx,68.0/sy)
    coords=[]
    for atom,(x,y) in zip(atoms,positions):
        coords.append({
            "element":str(atom["element"])[:2],
            "charge":int(atom.get("charge",0)),
            "x":50.0+(x-(minx+maxx)/2)*scale,
            "y":50.0+(y-(miny+maxy)/2)*scale,
        })
    return coords
