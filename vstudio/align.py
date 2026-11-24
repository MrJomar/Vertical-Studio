"""Alineación de subtítulos con la voz real: Whisper local oye el audio y da el tiempo de cada palabra;
esos tiempos se ponen sobre el TEXTO DEL GUION (así los subtítulos siempre dicen lo que escribiste)."""
import difflib
import re
import unicodedata

from . import audio as A

MIN_MATCH = 0.45      # fracción mínima de palabras del guion reconocidas por Whisper; si no, se usa el tiempo estimado


def _norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", t)


def _weights(toks):
    return [len(t) + 2.0 for t in toks]


def _spread(toks, t0, t1):
    """Reparte toks entre t0 y t1 proporcional a su longitud."""
    w = _weights(toks)
    tot = sum(w) or 1.0
    out, t = [], t0
    for tk, x in zip(toks, w):
        d = (t1 - t0) * x / tot
        out.append((t, t + d))
        t += d
    return out


def align_words(script_toks, asr_words, duration):
    """script_toks: palabras del guion; asr_words: [(texto, ini, fin)] de Whisper.
    Devuelve [(palabra_del_guion, ini, fin)] o None si Whisper reconoció muy poco."""
    a = [_norm(t) for t in script_toks]
    b = [_norm(w[0]) for w in asr_words]
    if not script_toks or not asr_words:
        return None
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    times = [None] * len(a)
    hits = 0
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = (asr_words[j1 + k][1], asr_words[j1 + k][2])
            hits += i2 - i1
        elif op == "replace":
            if i2 - i1 == j2 - j1:                      # palabra mal oída: se aprovecha su tiempo
                for k in range(i2 - i1):
                    times[i1 + k] = (asr_words[j1 + k][1], asr_words[j1 + k][2])
            else:
                sp = _spread(script_toks[i1:i2], asr_words[j1][1], asr_words[j2 - 1][2])
                for k, s in enumerate(sp):
                    times[i1 + k] = s
    if hits / len(a) < MIN_MATCH:
        return None
    known = [i for i, t in enumerate(times) if t]
    if not known:
        return None
    # huecos: antes de la primera, entre conocidas y después de la última
    first, last = known[0], known[-1]
    avg = max(0.18, min(0.5, (times[last][1] - times[first][0]) / max(1, last - first + 1)))
    if first > 0:
        t1 = times[first][0]
        t0 = max(0.0, t1 - avg * first)
        for k, s in enumerate(_spread(script_toks[:first], t0, t1)):
            times[k] = s
    if last < len(a) - 1:
        t0 = times[last][1]
        t1 = min(duration, t0 + avg * (len(a) - 1 - last)) if duration else t0 + avg * (len(a) - 1 - last)
        t1 = max(t1, t0 + 0.1 * (len(a) - 1 - last))
        for k, s in enumerate(_spread(script_toks[last + 1:], t0, t1)):
            times[last + 1 + k] = s
    for p, q in zip(known, known[1:]):
        if q - p > 1:
            for k, s in enumerate(_spread(script_toks[p + 1:q], times[p][1], max(times[p][1] + 0.05 * (q - p - 1), times[q][0]))):
                times[p + 1 + k] = s
    out, prev = [], 0.0
    for tk, (s, e) in zip(script_toks, times):
        s = max(s, prev)
        e = max(e, s + 0.06)
        out.append((tk, round(s, 3), round(e, 3)))
        prev = e
    return out


def asr_words_for(path, size="small", language="es"):
    segs = A.transcribe(path, size, language or None)
    return [tuple(w) for sg in segs for w in sg["words"]]


def align_audio(path, text, size="small", language="es", duration=None):
    """Palabras del guion con tiempos reales medidos en el audio. None si no se pudo (falta faster-whisper, error…)."""
    if not A.whisper_available():
        return None
    toks = re.findall(r"\S+", text or "")
    if not toks:
        return None
    try:
        asr = asr_words_for(path, size, language)
    except Exception:
        return None
    return align_words(toks, asr, duration or 0.0)
