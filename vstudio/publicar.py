"""Publicación en redes vía Buffer (video alojado en Cloudinary).

- Las claves NUNCA se guardan en archivos del proyecto ni en la configuración: viven en el almacén de credenciales
  del sistema (keyring). Si ya las guardaste con DiffStudio, se reutilizan sin pedirlas otra vez.
- Nada se envía sin una confirmación explícita (preparar → confirmar) y se registra cada envío para no duplicarlo.
- Solo TikTok está verificado (es el flujo que ya funciona en DiffStudio); otros canales se listan pero no se envían.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets as _secrets
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .core import CACHE_DIR

OWN_SERVICE = "Vertical Studio"
SERVICES = (OWN_SERVICE, "DiffStudio - API Keys")          # primero la propia; luego la de DiffStudio
ENV_FALLBACK = {"buffer_token": "BUFFER_API_KEY", "cloudinary_secret": "CLOUDINARY_API_SECRET"}
CONFIG_FILE = CACHE_DIR / "publicar.json"
BUFFER_ENDPOINT = "https://api.buffer.com"
SUPPORTED = {"tiktok"}


class PublishError(Exception):
    pass


class Rejected(PublishError):
    """Buffer rechazó explícitamente: se puede corregir y reintentar."""


class Ambiguous(PublishError):
    """No se sabe si Buffer llegó a crear la publicación: NO reintentar sin revisar el panel de Buffer."""


# ----------------------------------------------------------------------------- claves y preferencias
def _keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except ImportError as exc:
        raise PublishError("Falta el componente «keyring». Ejecuta instalar.bat para activarlo.") from exc


def get_secret(name: str) -> str:
    if name not in ENV_FALLBACK:
        raise PublishError("Credencial desconocida.")
    try:
        kr = _keyring()
        for svc in SERVICES:
            try:
                v = kr.get_password(svc, "publicacion:" + name)
            except Exception:
                v = None
            if v and v.strip():
                return v.strip()
    except PublishError:
        pass
    return os.environ.get(ENV_FALLBACK[name], "").strip()


def save_secret(name: str, value: str) -> None:
    if name not in ENV_FALLBACK or len(value.strip()) < 12:
        raise PublishError("La clave parece incompleta.")
    try:
        _keyring().set_password(OWN_SERVICE, "publicacion:" + name, value.strip())
    except PublishError:
        raise
    except Exception as exc:
        raise PublishError("No se pudo guardar la clave en el almacén seguro de Windows.") from exc


def _diffstudio_prefs() -> dict:
    base = Path(os.environ.get("APPDATA") or Path.home() / ".config")
    try:
        d = json.loads((base / "DiffStudio" / "preferencias.json").read_text("utf-8"))
        return {"cloud_name": str(d.get("cloudinary_cloud_name", "")), "api_key": str(d.get("cloudinary_api_key", "")),
                "channel_id": str(d.get("buffer_tiktok_channel", ""))} if isinstance(d, dict) else {}
    except Exception:
        return {}


def get_prefs() -> dict:
    """Datos no secretos: los propios y, si faltan, los que ya configuraste en DiffStudio."""
    try:
        own = json.loads(CONFIG_FILE.read_text("utf-8"))
    except Exception:
        own = {}
    base = _diffstudio_prefs()
    return {k: (str(own.get(k) or base.get(k) or "")).strip() for k in ("cloud_name", "api_key", "channel_id", "channel_name")}


def save_prefs(values: dict) -> None:
    cur = get_prefs()
    for k in ("cloud_name", "api_key", "channel_id", "channel_name"):
        if k in values and values[k] is not None:
            cur[k] = str(values[k]).strip()
    if cur["cloud_name"] and not re.fullmatch(r"[A-Za-z0-9_-]+", cur["cloud_name"]):
        raise PublishError("Cloudinary: el nombre de nube solo puede llevar letras, números, - y _.")
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cur, ensure_ascii=False, indent=1), "utf-8")


def status() -> dict:
    """Estado de la configuración sin revelar ninguna clave."""
    p = get_prefs()
    try:
        _keyring()
        kr_ok = True
    except PublishError:
        kr_ok = False
    tok, sec = (get_secret("buffer_token"), get_secret("cloudinary_secret")) if kr_ok else ("", "")
    k = p["api_key"]
    return {"keyring": kr_ok, "buffer": bool(tok), "cloudinary_secret": bool(sec), "cloud_name": p["cloud_name"],
            "api_key": ("•••" + k[-4:]) if len(k) >= 6 else ("•••" if k else ""), "channel_id": p["channel_id"],
            "channel_name": p["channel_name"],
            "listo": bool(tok and sec and p["cloud_name"] and k and p["channel_id"])}


# ----------------------------------------------------------------------------- Buffer
def _graphql(token: str, query: str, variables: dict | None = None, endpoint: str = BUFFER_ENDPOINT) -> dict:
    if len(token.strip()) < 12:
        raise PublishError("Configura primero la clave personal de Buffer.")
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(endpoint, data=payload, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + token.strip(),
                                          "User-Agent": "VerticalStudio/2.19"})
    modifying = query.lstrip().startswith("mutation")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            if modifying:
                raise Ambiguous("Buffer falló al responder. Confirma en su panel si creó la publicación antes de reintentar.") from exc
            raise PublishError("Buffer no respondió; inténtalo más tarde.") from exc
        raise Rejected(f"Buffer respondió HTTP {exc.code}. Revisa la clave y sus permisos.") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        if modifying:
            raise Ambiguous("No se pudo confirmar la respuesta de Buffer. Verifica su panel antes de reintentar.") from exc
        raise PublishError("No se pudo consultar Buffer. Comprueba la conexión.") from exc
    if not isinstance(data, dict):
        raise Ambiguous("Buffer devolvió una respuesta inesperada. Revisa su panel.")
    if data.get("errors"):
        msgs = [str(e.get("message", "Error")) for e in data["errors"] if isinstance(e, dict)]
        raise Rejected(("Buffer: " + "; ".join(msgs)).replace(token, "[CLAVE OCULTA]")[:350])
    return data.get("data") or {}


def list_channels(token: str, endpoint: str = BUFFER_ENDPOINT) -> list[dict]:
    orgs = _graphql(token, "query { account { organizations { id name } } }", endpoint=endpoint)
    out = []
    for org in (orgs.get("account") or {}).get("organizations") or []:
        res = _graphql(token, "query { channels(input: { organizationId: " + json.dumps(org["id"]) +
                       " }) { id name displayName service } }", endpoint=endpoint)
        for c in res.get("channels") or []:
            svc = str(c.get("service", "")).lower()
            out.append({"id": str(c["id"]), "nombre": str(c.get("displayName") or c.get("name") or c["id"]),
                        "servicio": svc, "soportado": svc in SUPPORTED})
    return out


def create_post(token: str, channel_id: str, media_url: str, text: str, scheduled_utc: datetime | None,
                endpoint: str = BUFFER_ENDPOINT) -> dict:
    if not re.match(r"^https://[^\s]+\.(?:mp4|mov)(?:\?[^\s]*)?$", media_url, re.I):
        raise PublishError("El video necesita una URL HTTPS directa, pública y estable.")
    if not text.strip():
        raise PublishError("Escribe una descripción antes de publicar.")
    if scheduled_utc is not None:
        if scheduled_utc.tzinfo is None:
            raise PublishError("La fecha programada debe incluir zona horaria.")
        if scheduled_utc.astimezone(timezone.utc) <= datetime.now(timezone.utc) + timedelta(minutes=2):
            raise PublishError("Programa la publicación al menos 2 minutos en el futuro.")
    inp = {"text": text.strip(), "channelId": channel_id.strip(), "schedulingType": "automatic",
           "mode": "customScheduled" if scheduled_utc else "shareNow",
           "assets": [{"video": {"url": media_url, "metadata": {"thumbnailOffset": 1500}}}]}
    if scheduled_utc:
        inp["dueAt"] = scheduled_utc.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    data = _graphql(token, """mutation($input: CreatePostInput!) {
      createPost(input:$input) {
        ... on PostActionSuccess { post { id dueAt status } }
        ... on MutationError { message }
      }
    }""", {"input": inp}, endpoint=endpoint)
    res = data.get("createPost") or {}
    if res.get("message"):
        raise Rejected("Buffer: " + str(res["message"])[:350])
    post = res.get("post") or {}
    if not post.get("id"):
        raise Ambiguous("Buffer no confirmó un ID de publicación. Revisa su panel antes de reintentar.")
    return post


# ----------------------------------------------------------------------------- Cloudinary (sin SDK, por fragmentos)
def _sign(params: dict, secret: str) -> str:
    base = "&".join(f"{k}={params[k]}" for k in sorted(params)) + secret
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _multipart(fields: dict, filename: str, blob: bytes) -> tuple[bytes, str]:
    b = "----vs" + _secrets.token_hex(12)
    parts = []
    for k, v in fields.items():
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                 f'Content-Type: application/octet-stream\r\n\r\n'.encode() + blob + b"\r\n")
    parts.append(f"--{b}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={b}"


def host_video(video: str | Path, cloud: str, key: str, secret: str, public_id: str, progress=lambda m: None,
               base: str = "https://api.cloudinary.com", chunk: int = 6_000_000) -> str:
    video = Path(video)
    if not video.is_file() or video.stat().st_size <= 0 or video.suffix.lower() != ".mp4":
        raise PublishError("No se encontró el MP4 final para subirlo.")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", cloud):
        raise PublishError("Cloudinary: nombre de nube no válido.")
    if not key.strip() or len(secret.strip()) < 12:
        raise PublishError("Cloudinary: configura API Key y API Secret.")
    size = video.stat().st_size
    uid = _secrets.token_hex(8)
    url = f"{base}/v1_1/{cloud}/video/upload"
    progress(f"Subiendo el video a Cloudinary ({size / 1024**2:.1f} MB)…")
    last = {}
    try:
        with open(video, "rb") as f:
            pos = 0
            while pos < size:
                blob = f.read(chunk)
                end = pos + len(blob) - 1
                params = {"overwrite": "true", "public_id": public_id, "timestamp": int(time.time()), "unique_filename": "false"}
                fields = {**params, "api_key": key.strip(), "signature": _sign(params, secret.strip())}
                body, ctype = _multipart(fields, video.name, blob)
                req = urllib.request.Request(url, data=body, method="POST", headers={
                    "Content-Type": ctype, "X-Unique-Upload-Id": uid, "Content-Range": f"bytes {pos}-{end}/{size}"})
                with urllib.request.urlopen(req, timeout=180) as r:
                    last = json.loads(r.read().decode("utf-8"))
                pos = end + 1
                progress(f"Cloudinary: {min(100, int(pos * 100 / size))} %")
    except Exception as exc:                                   # nunca mostrar la excepción: puede traer URLs firmadas
        raise PublishError("No se pudo subir el video a Cloudinary. Revisa conexión, cuota y claves.") from exc
    out = str(last.get("secure_url", "")) if isinstance(last, dict) else ""
    if not out.startswith(f"https://res.cloudinary.com/{cloud}/video/upload/"):
        raise PublishError("Cloudinary no devolvió una URL pública directa para el video.")
    return out


# ----------------------------------------------------------------------------- confirmación y envío
_PENDING: dict[str, dict] = {}
BLOCKED = {"enviando", "enviado", "programado", "incierto"}


def file_digest(path: str | Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()[:20]


def prepare(item: dict, channel_id: str, channel_name: str, service: str, text: str, scheduled_iso: str | None) -> dict:
    """Valida todo y devuelve el resumen que el usuario debe confirmar. No envía nada."""
    st = status()
    if not (st["buffer"] and st["cloudinary_secret"] and st["cloud_name"] and st["api_key"]):
        raise PublishError("Faltan claves de Buffer o Cloudinary. Configúralas en «Publicación».")
    if service.lower() not in SUPPORTED:
        raise PublishError("Por ahora solo se puede publicar en TikTok (es el único flujo ya verificado).")
    video = item.get("video", "")
    if item.get("estado") != "listo" or not video or not os.path.isfile(video):
        raise PublishError("Primero renderiza el video: no hay un MP4 final válido.")
    if not text.strip():
        raise PublishError("Escribe la descripción de la publicación.")
    digest = file_digest(video)
    prev = item.get("pub") or {}
    if prev.get("digest") == digest and prev.get("estado") in BLOCKED:
        raise PublishError(f"Este video ya está «{prev.get('estado')}»"
                           + (" y su estado es incierto: revisa el panel de Buffer antes de reintentar." if prev.get("estado") == "incierto" else "."))
    due = None
    if scheduled_iso:
        try:
            due = datetime.fromisoformat(scheduled_iso.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PublishError("Fecha de programación no válida.") from exc
        if due.tzinfo is None:
            raise PublishError("La fecha de programación debe incluir zona horaria.")
        if due.astimezone(timezone.utc) <= datetime.now(timezone.utc) + timedelta(minutes=2):
            raise PublishError("Programa al menos 2 minutos en el futuro.")
    token = uuid.uuid4().hex
    for k in [k for k, v in _PENDING.items() if v["exp"] < time.time()]:
        _PENDING.pop(k, None)
    _PENDING[token] = {"exp": time.time() + 600, "item_id": item["id"], "video": video, "digest": digest,
                       "channel_id": channel_id, "channel_name": channel_name, "text": text.strip(), "due": due,
                       "titulo": item["titulo"]}
    return {"confirm": token, "resumen": {"titulo": item["titulo"], "canal": channel_name or channel_id, "servicio": service,
                                           "texto": text.strip(), "programado": due.astimezone().strftime("%d/%m/%Y %H:%M") if due else "",
                                           "mb": round(os.path.getsize(video) / 1024**2, 1)}}


def take_confirmed(token: str) -> dict:
    d = _PENDING.pop(token, None)
    if not d or d["exp"] < time.time():
        raise PublishError("La confirmación expiró. Vuelve a revisar y confirmar.")
    return d


def execute(d: dict, save, progress=lambda m: None, cloud_base: str = "https://api.cloudinary.com", buffer_endpoint: str = BUFFER_ENDPOINT) -> dict:
    """Sube el MP4 y crea la publicación. `save(**campos)` registra cada fase para evitar duplicados."""
    p = get_prefs()
    token, secret = get_secret("buffer_token"), get_secret("cloudinary_secret")
    base = {"digest": d["digest"], "canal_id": d["channel_id"], "canal": d["channel_name"], "texto": d["text"],
            "programado": d["due"].isoformat() if d["due"] else ""}
    phase = "subiendo"
    try:
        save(pub={**base, "estado": "subiendo", "ts": time.time()})
        url = host_video(d["video"], p["cloud_name"], p["api_key"], secret, "verticalstudio/" + d["digest"], progress, cloud_base)
        phase = "enviando"
        save(pub={**base, "estado": "enviando", "media_url": url, "ts": time.time()})
        progress("Enviando la publicación a Buffer…")
        post = create_post(token, d["channel_id"], url, d["text"], d["due"], endpoint=buffer_endpoint)
        estado = "programado" if d["due"] else "enviado"
        save(pub={**base, "estado": estado, "media_url": url, "buffer_id": str(post["id"]), "ts": time.time(),
                  "detalle": "Buffer aceptó la solicitud; comprueba la publicación en la red."})
        return {"estado": estado, "buffer_id": str(post["id"])}
    except Exception as exc:
        if isinstance(exc, Rejected):
            estado = "error"
        elif isinstance(exc, Ambiguous) or phase == "enviando":
            estado = "incierto"
        else:
            estado = "error"
        try:
            save(pub={**base, "estado": estado, "ts": time.time(), "detalle": str(exc)[:350]})
        except Exception:
            pass
        raise
