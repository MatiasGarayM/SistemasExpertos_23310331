# para correr ingrese lo siguiente en terminal:
#   py -3.12 -m streamlit run arbolsemántico.py

import re
import unicodedata

import streamlit as st

# ------------------REPRESENTACIÓN DE FÓRMULAS-------------------------------
# Las fórmulas son tuplas inmutables:
#   ('atom', 'p')           átomo
#   ('not', f)              ¬f
#   ('and', a, b)           a ∧ b
#   ('or', a, b)            a ∨ b
#   ('imp', a, b)           a → b
#   ('iff', a, b)           a ↔ b

SIMBOLOS = {'and': '∧', 'or': '∨', 'imp': '→', 'iff': '↔'}


def formatear(f, raiz=True):
    """Convierte una fórmula a texto con la jerarquía de paréntesis correcta."""
    tipo = f[0]
    if tipo == 'atom':
        return f[1]
    if tipo == 'not':
        return '¬' + formatear(f[1], False)
    texto = f"{formatear(f[1], False)} {SIMBOLOS[tipo]} {formatear(f[2], False)}"
    return texto if raiz else f"({texto})"


def es_literal(f):
    """Un literal es un átomo o la negación de un átomo."""
    return f[0] == 'atom' or (f[0] == 'not' and f[1][0] == 'atom')


def complemento(f):
    """Devuelve el literal complementario (p <-> ¬p)."""
    return f[1] if f[0] == 'not' else ('not', f)


# -------------PARSER DE LENGUAJE NATURAL (ESPAÑOL) -> WFF---------------------------------------
def sin_acentos(texto):
    """Elimina tildes para comparar palabras clave y claves de átomos."""
    nfd = unicodedata.normalize('NFD', texto)
    return ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')


class Traductor:
    """
    Traduce frases en español a fórmulas.
    Precedencia (de menor a mayor ligadura):
        si y solo si  <  si...entonces  <  o  <  y  <  no
    """
    LETRAS = list("pqrstuvwxyzabcdefghijklmno")

    def __init__(self):
        self.clave_a_letra = {}   # clave normalizada -> letra
        self.letra_a_texto = {}   # letra -> significado en español (orden de aparición)

    # --- tokenización -------------------------------------------------------
    @staticmethod
    def tokenizar(texto):
        """Devuelve lista de pares (palabra_original, palabra_normalizada)."""
        texto = texto.strip().lower()
        palabras = re.findall(r"\w+|,", texto)
        return [(w, sin_acentos(w)) for w in palabras]

    @staticmethod
    def _recortar(toks):
        """Quita comas sobrantes al inicio y al final."""
        while toks and toks[0][1] == ',':
            toks = toks[1:]
        while toks and toks[-1][1] == ',':
            toks = toks[:-1]
        return toks

    @staticmethod
    def _buscar(norms, secuencia, desde=0):
        """Busca una secuencia de palabras; devuelve el índice o None."""
        n = len(secuencia)
        for i in range(desde, len(norms) - n + 1):
            if norms[i:i + n] == secuencia:
                return i
        return None

    @staticmethod
    def _dividir(toks, palabra):
        """Divide la lista de tokens por una palabra conectiva (sin partes vacías)."""
        partes, actual = [], []
        for t in toks:
            if t[1] == palabra:
                partes.append(actual)
                actual = []
            else:
                actual.append(t)
        partes.append(actual)
        return partes

    # --- átomos ----------------------------------------
    def _atomo(self, toks):
        """Registra (o recupera) el átomo asociado a una frase simple."""
        clave = ' '.join(n for _, n in toks)
        if clave not in self.clave_a_letra:
            idx = len(self.clave_a_letra)
            letra = self.LETRAS[idx] if idx < len(self.LETRAS) else f"p{idx}"
            self.clave_a_letra[clave] = letra
            self.letra_a_texto[letra] = ' '.join(w for w, _ in toks)
        return ('atom', self.clave_a_letra[clave])

    # --- parser recursivo ---------------------
    def _parse(self, toks):
        toks = self._recortar(toks)
        if not toks:
            raise ValueError("Frase vacía o mal formada.")
        norms = [n for _, n in toks]

        # 1) "A si y solo si B"  ->  A ↔ B
        i = self._buscar(norms, ["si", "y", "solo", "si"], 1)
        if i is not None:
            return ('iff', self._parse(toks[:i]), self._parse(toks[i + 4:]))

        # 2) "Si A (,) entonces B"  ->  A → B
        if norms[0] == "si":
            if "entonces" in norms:
                j = norms.index("entonces")
            elif "," in norms:
                j = norms.index(",")
            else:
                raise ValueError("Condicional sin 'entonces': " + ' '.join(w for w, _ in toks))
            return ('imp', self._parse(toks[1:j]), self._parse(toks[j + 1:]))

        # 3) "A solo si B" -> A → B ;  "B si A" -> A → B
        i = self._buscar(norms, ["solo", "si"], 1)
        if i is not None:
            return ('imp', self._parse(toks[:i]), self._parse(toks[i + 2:]))
        if "si" in norms[1:]:
            i = norms.index("si", 1)
            return ('imp', self._parse(toks[i + 1:]), self._parse(toks[:i]))

        # Las comas restantes ya no son estructurales
        toks = [t for t in toks if t[1] != ',']
        norms = [n for _, n in toks]

        # 4) Disyunción "o"
        partes = [p for p in self._dividir(toks, "o") if p]
        if len(partes) > 1:
            f = self._parse(partes[0])
            for p in partes[1:]:
                f = ('or', f, self._parse(p))
            return f

        # 5) Conjunción "y"
        partes = [p for p in self._dividir(toks, "y") if p]
        if len(partes) > 1:
            f = self._parse(partes[0])
            for p in partes[1:]:
                f = ('and', f, self._parse(p))
            return f

        # 6) Negación "no ..." / "no es cierto que ..."
        if norms[0] == "no":
            resto = toks[4:] if norms[1:4] == ["es", "cierto", "que"] else toks[1:]
            return ('not', self._parse(resto))

        # 7) Átomo
        return self._atomo(toks)

    def traducir(self, texto):
        """Punto de entrada: texto en español -> fórmula."""
        return self._parse(self.tokenizar(texto))


# ------------TABLEROS SEMÁNTICOS-----------------------------------------
def clasificar(f):
    """
    Devuelve (tipo, componentes) para una fórmula no literal.
      alfa -> lista de fórmulas que se agregan a la MISMA rama.
      beta -> lista de listas; cada una forma una rama NUEVA.
    """
    neg = lambda x: ('not', x)
    t = f[0]
    if t == 'and':
        return 'alfa', [f[1], f[2]]
    if t == 'or':
        return 'beta', [[f[1]], [f[2]]]
    if t == 'imp':
        return 'beta', [[neg(f[1])], [f[2]]]
    if t == 'iff':
        return 'beta', [[f[1], f[2]], [neg(f[1]), neg(f[2])]]
    # t == 'not'
    g = f[1]
    if g[0] == 'not':
        return 'alfa', [g[1]]                                   # ¬¬a
    if g[0] == 'or':
        return 'alfa', [neg(g[1]), neg(g[2])]                   # ¬(a ∨ b)
    if g[0] == 'imp':
        return 'alfa', [g[1], neg(g[2])]                        # ¬(a → b)
    if g[0] == 'and':
        return 'beta', [[neg(g[1])], [neg(g[2])]]               # ¬(a ∧ b)
    if g[0] == 'iff':
        return 'beta', [[g[1], neg(g[2])], [neg(g[1]), g[2]]]   # ¬(a ↔ b)
    raise ValueError("Fórmula no reconocida")


class Nodo:
    """Nodo (segmento lineal) del tablero."""
    def __init__(self, lineas):
        self.lineas = list(lineas)   # texto a mostrar
        self.hijos = []
        self.cerrada = False
        self.razon = ""
        self.abierta = False
        self.modelo = {}
        self.literales = set()


def seleccionar(pendientes):
    """Prioridad: literales, luego reglas alfa, luego reglas beta."""
    for i, f in enumerate(pendientes):
        if es_literal(f):
            return i
    for i, f in enumerate(pendientes):
        if clasificar(f)[0] == 'alfa':
            return i
    return 0


def expandir(nodo, pendientes, literales):
    """Expande recursivamente la rama representada por 'nodo'."""
    pendientes = list(pendientes)
    while True:
        if not pendientes:                       # solo quedan literales
            nodo.abierta = True
            nodo.literales = set(literales)
            return
        f = pendientes.pop(seleccionar(pendientes))

        if es_literal(f):
            comp = complemento(f)
            if comp in literales:                # contradicción explícita
                nodo.cerrada = True
                nodo.razon = f"{formatear(f)} y {formatear(comp)}"
                return
            literales.add(f)
            continue

        tipo, comps = clasificar(f)
        if tipo == 'alfa':
            nodo.lineas.append(f"α  {formatear(f)}  ⇒  " + ", ".join(formatear(c) for c in comps))
            pendientes = comps + pendientes
        else:
            nodo.lineas.append(f"β  {formatear(f)}  ⇒  bifurcación")
            for rama in comps:
                hijo = Nodo([", ".join(formatear(c) for c in rama)])
                nodo.hijos.append(hijo)
                expandir(hijo, rama + pendientes, set(literales))
            return


def hojas(nodo):
    """Recorre el árbol y devuelve las hojas en orden (izquierda a derecha)."""
    if not nodo.hijos:
        return [nodo]
    res = []
    for h in nodo.hijos:
        res.extend(hojas(h))
    return res


def modelo_de(nodo, letras):
    """Obtiene la asignación de verdad de una rama abierta."""
    asign = {}
    for l in letras:
        if ('atom', l) in nodo.literales:
            asign[l] = 'V'
        elif ('not', ('atom', l)) in nodo.literales:
            asign[l] = 'F'
        else:
            asign[l] = 'V ó F (indiferente)'
    return asign


# ------------------------ VISUALIZACIÓN -------------------------------------
def estado_hoja(nodo, letras):
    if nodo.cerrada:
        return f"[✕] CERRADA  (contradicción: {nodo.razon})"
    m = modelo_de(nodo, letras)
    return "[○] ABIERTA  →  " + ", ".join(f"{k} = {v}" for k, v in m.items())


def dibujar_ascii(nodo, cabeza, cuerpo, letras, salida):
    """Genera el árbol en texto con conectores ├── y └── (acumula en 'salida')."""
    for i, linea in enumerate(nodo.lineas):
        salida.append((cabeza if i == 0 else cuerpo) + linea)
    if not nodo.hijos:
        salida.append(cuerpo + estado_hoja(nodo, letras))
        return
    salida.append(cuerpo + "│")
    for j, h in enumerate(nodo.hijos):
        ultimo = (j == len(nodo.hijos) - 1)
        dibujar_ascii(h,
                      cuerpo + ("└── " if ultimo else "├── "),
                      cuerpo + ("    " if ultimo else "│   "),
                      letras, salida)
        if not ultimo:
            salida.append(cuerpo + "│")


def _esc(txt):
    return txt.replace("\\", "\\\\").replace('"', '\\"')


def a_dot(raiz, letras):
    """Convierte el tablero en un grafo Graphviz (DOT) para st.graphviz_chart."""
    out = [
        "digraph Tablero {",
        "  rankdir=TB;",
        '  graph [nodesep=0.4, ranksep=0.5];',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", '
        'fontsize=11, fillcolor="#F4F6F8", color="#8A94A6"];',
        '  edge [color="#8A94A6"];',
    ]
    contador = [0]

    def visitar(nodo):
        nid = f"n{contador[0]}"
        contador[0] += 1
        etiqueta = list(nodo.lineas)
        color = None
        if not nodo.hijos:
            if nodo.cerrada:
                etiqueta.append("✕ CERRADA")
                etiqueta.append(f"({nodo.razon})")
                color = "#F8D7DA"
            else:
                m = modelo_de(nodo, letras)
                etiqueta.append("○ ABIERTA")
                etiqueta.append(", ".join(f"{k}={v}" for k, v in m.items()))
                color = "#D4EDDA"
        texto_etq = "\\n".join(_esc(l) for l in etiqueta)
        attrs = f'label="{texto_etq}"'
        if color:
            attrs += f', fillcolor="{color}"'
        out.append(f"  {nid} [{attrs}];")
        for h in nodo.hijos:
            hid = visitar(h)
            out.append(f"  {nid} -> {hid};")
        return nid

    visitar(raiz)
    out.append("}")
    return "\n".join(out)


# ---------------------PROCESO COMPLETO----------------------------
def parsear_entrada(texto):
    """Cada línea: 'ETIQUETA: frase' o solo 'frase' (se etiqueta automáticamente)."""
    kb = []
    for n, linea in enumerate((l for l in texto.splitlines() if l.strip()), 1):
        m = re.match(r"^\s*([A-Za-z]\w{0,3})\s*:\s*(.+)$", linea)
        if m:
            kb.append((m.group(1), m.group(2).strip()))
        else:
            kb.append((f"F{n}", linea.strip()))
    return kb


def analizar(kb):
    """Traduce, construye el tablero y devuelve todos los resultados."""
    tr = Traductor()
    formulas = [(etq, texto, tr.traducir(texto)) for etq, texto in kb]
    letras = list(tr.letra_a_texto.keys())

    raiz = Nodo(["Supuesto: todas las fórmulas de la KB son Verdaderas"] +
                [f"   {etq}: {formatear(f)}" for etq, _, f in formulas])
    expandir(raiz, [f for _, _, f in formulas], set())

    ramas = hojas(raiz)
    return {
        "tr": tr, "formulas": formulas, "letras": letras, "raiz": raiz,
        "ramas": ramas,
        "abiertas": [r for r in ramas if r.abierta],
        "cerradas": [r for r in ramas if r.cerrada],
    }


# ------------------------------ INTERFAZ STREAMLIT ---------------------------
EJEMPLOS = {
    "Día / trabajo (consistente)": (
        "R1: Si es de día, entonces voy a trabajar\n"
        "R2: Si llueve, entonces no voy a trabajar\n"
        "H1: Es de día"
    ),
    "Inconsistente": (
        "R1: Si es de día, entonces voy a trabajar\n"
        "R2: Si llueve, entonces no voy a trabajar\n"
        "H1: Es de día\n"
        "H2: Llueve"
    ),
    "Disyunción": (
        "R1: Llueve o hace frío\n"
        "R2: Si llueve, entonces me quedo en casa\n"
        "H1: No me quedo en casa"
    ),
    "Bicondicional": (
        "R1: Apruebo si y solo si estudio\n"
        "H1: No estudio\n"
        "H2: Apruebo"
    ),
}


def main():
    st.set_page_config(page_title="Tableros semánticos", page_icon="🌳", layout="wide")
    st.title(" Analizador proposicional y tableros semánticos")
    st.caption("Escribe una base de conocimiento en español (una frase por línea) "
               "y obtén su traducción a lógica proposicional, el tablero y los modelos.")

    # --- barra lateral: entrada ---
    with st.sidebar:
        st.header("Base de conocimiento")
        ejemplo = st.selectbox("Cargar ejemplo", list(EJEMPLOS.keys()))
        if st.session_state.get("_ejemplo") != ejemplo:
            st.session_state["_ejemplo"] = ejemplo
            st.session_state["kb_texto"] = EJEMPLOS[ejemplo]
        texto = st.text_area("Frases (formato opcional  ETIQUETA: frase)",
                             key="kb_texto", height=260)
        st.markdown(
            "**Conectores reconocidos:** `si … entonces`, `y`, `o`, `no`, "
            "`no es cierto que`, `si y solo si`, `solo si`."
        )
        ejecutar = st.button("Analizar", type="primary", use_container_width=True)

    if not ejecutar and "resultado" not in st.session_state:
        st.info("Elige un ejemplo o escribe tus frases y pulsa **Analizar**.")
        return

    if ejecutar:
        kb = parsear_entrada(texto)
        if not kb:
            st.warning("Escribe al menos una frase.")
            return
        try:
            st.session_state["resultado"] = (kb, analizar(kb))
        except ValueError as e:
            st.session_state.pop("resultado", None)
            st.error(f"No se pudo traducir la base de conocimiento: {e}")
            return

    kb, r = st.session_state["resultado"]
    tr, formulas, letras = r["tr"], r["formulas"], r["letras"]

    # --- 1 y 2: átomos y fórmulas ---
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1) Tabla de equivalencias")
        st.dataframe(
            [{"Átomo": l, "Significado": t} for l, t in tr.letra_a_texto.items()],
            hide_index=True, use_container_width=True)
    with col2:
        st.subheader("2) Fórmulas")
        st.dataframe(
            [{"Etiqueta": e, "Fórmula": formatear(f), "Frase original": t}
             for e, t, f in formulas],
            hide_index=True, use_container_width=True)

    # --- 3: tablero ---
    st.subheader("3) Tablero semántico")
    st.caption("α = regla sin bifurcación · β = regla con bifurcación · "
               "rojo = rama cerrada ✕ · verde = rama abierta ○")
    st.graphviz_chart(a_dot(r["raiz"], letras), use_container_width=True)

    with st.expander("Ver versión en texto (ASCII)"):
        salida = []
        dibujar_ascii(r["raiz"], "", "", letras, salida)
        st.code("\n".join(salida), language=None)

    # --- 4: resultados ---
    st.subheader("4) Resultados")
    c1, c2, c3 = st.columns(3)
    c1.metric("Ramas totales", len(r["ramas"]))
    c2.metric("Cerradas ✕", len(r["cerradas"]))
    c3.metric("Abiertas ○", len(r["abiertas"]))

    if not r["abiertas"]:
        st.error("Todas las ramas se cierran: la base de conocimiento es "
                 "**INCONSISTENTE / INSATISFACIBLE**.")
    else:
        st.success("La base de conocimiento es **CONSISTENTE / SATISFACIBLE**.")
        st.markdown("**Asignaciones que satisfacen la KB:**")
        filas = []
        for k, rama in enumerate(r["abiertas"], 1):
            m = modelo_de(rama, letras)
            fila = {"Modelo": k}
            fila.update(m)
            filas.append(fila)
        st.dataframe(filas, hide_index=True, use_container_width=True)

        for k, rama in enumerate(r["abiertas"], 1):
            m = modelo_de(rama, letras)
            sig = "; ".join(
                f"«{tr.letra_a_texto[a]}» es "
                f"{'verdadero' if v == 'V' else 'falso' if v == 'F' else 'indiferente'}"
                for a, v in m.items())
            st.write(f"**Modelo {k}:** {sig}")


main()