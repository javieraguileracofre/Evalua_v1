# Launcher local (Windows)

Esta carpeta permite usar **EvaluaERP como una aplicación de escritorio**: un icono, doble clic, se abre el navegador. No hace falta PowerShell ni CMD en el día a día.

El servidor se inicia con `python main.py` (FastAPI + Uvicorn). El host y el puerto salen de `.env` (`UVICORN_HOST`, `UVICORN_PORT`). En este proyecto el puerto local suele ser **8001**, no 8000.

Si `.env` no define puerto, el valor por defecto es **8000**.

---

## 1. Crear el icono del escritorio (una sola vez)

No se necesitan permisos de administrador.

**Opción más simple:** en el Explorador de archivos abra la carpeta `launcher` y haga doble clic en:

`create_desktop_shortcut.cmd`

**Opción equivalente en una terminal** (desde la carpeta del proyecto):

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File ".\launcher\create_desktop_shortcut.ps1"
```

Eso crea en el escritorio:

- **Iniciar Aplicación** — arranca EvaluaERP y abre el navegador
- **Detener Aplicación** — cierra el servidor local

Icono personalizado (opcional): copie un archivo `.ico` a `launcher\app.ico` y vuelva a ejecutar el creador de accesos. O indíquelo a mano:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File ".\launcher\create_desktop_shortcut.ps1" -IconPath "C:\ruta\mi-icono.ico"
```

---

## 2. Cómo iniciar la app

Doble clic en **Iniciar Aplicación** del escritorio.

Debería ocurrir esto:

1. Se inicia el entorno virtual (`env`, o `.venv` / `venv` si existieran).
2. Si faltan dependencias, se instalan desde `requirements.txt` (solo cuando hace falta).
3. Si el puerto ya está ocupado por esta misma app, no se lanza una segunda instancia: solo se abre el navegador.
4. Se abre `http://127.0.0.1:<puerto>` (el puerto de `.env`).

No debería quedar una ventana negra de PowerShell. Los mensajes de error salen en un recuadro de Windows.

---

## 3. Cómo detenerla

Doble clic en **Detener Aplicación** del escritorio.

También puede ejecutar:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File ".\launcher\stop_app.ps1"
```

Solo se detiene el proceso de esta aplicación en el puerto configurado. No se mata cualquier programa ajeno que coincida con el puerto: en ese caso se avisa y no se toca.

---

## 4. Cómo cambiar el puerto

Edite el archivo `.env` en la raíz del proyecto:

```env
UVICORN_HOST=0.0.0.0
UVICORN_PORT=8001
```

- `127.0.0.1` — solo este PC
- `0.0.0.0` — también otros dispositivos en la misma Wi‑Fi (el navegador local sigue abriéndose en `http://127.0.0.1:<puerto>`)

Guarde el archivo, **detenga** la app si estaba corriendo e **iníciela** de nuevo. El launcher lee el puerto en cada arranque.

---

## 5. Inicio automático con Windows (opcional)

**No está activo por defecto.**

Para que EvaluaERP arranque al iniciar sesión (este usuario, sin admin):

Doble clic en `launcher\create_startup_shortcut.cmd`

O:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File ".\launcher\create_startup_shortcut.ps1"
```

Para quitarlo:

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File ".\launcher\create_startup_shortcut.ps1" -Remove
```

o `create_startup_shortcut.cmd -Remove`.

Eso solo crea o borra un acceso en la carpeta de inicio del usuario (`shell:startup`). No instala servicios de Windows.

---

## 6. Si Windows bloquea los scripts de PowerShell

El acceso directo **no** depende de la política de ejecución de PowerShell: `run_hidden.vbs` llama a PowerShell con `-ExecutionPolicy Bypass` solo para estos scripts.

Si al crear el icono Windows muestra *“no se puede cargar porque la ejecución de scripts está deshabilitada”*, use siempre el `.cmd` (ya incluye Bypass) o el comando de la sección 1.

Si SmartScreen pregunta *“Windows protegió su PC”*:

1. Clic en **Más información**
2. Clic en **Ejecutar de todas formas**

Es normal la primera vez con un `.cmd` / `.vbs` local.

---

## 7. Dónde están los logs

Carpeta `logs\` (se crea sola, no se versiona):

| Archivo | Contenido |
|---|---|
| `launcher-YYYYMMDD.log` | Arranque, parada, errores del launcher |
| `uvicorn.log` | Salida estándar del servidor |
| `uvicorn.err.log` | Errores del servidor |
| `app.pid` | PID del proceso actual (interno) |

---

## 8. Requisitos y diseño

- Windows 10/11, **sin administrador**.
- Python 3 ya instalado (si existe `env\Scripts\python.exe`, se usa ese y no hace falta el Python del sistema).
- Dependencias: `requirements.txt` + `pip` del entorno virtual.
- Comando real de arranque: `python -u main.py` en la raíz del proyecto, igual que `lanzar_localhost.cmd`. Así se respetan `UVICORN_HOST`, `UVICORN_PORT` y el resto de `.env` sin duplicar flags de Uvicorn.
- Se eligió un acceso `.lnk` → `wscript.exe` → `run_hidden.vbs` → PowerShell oculto porque es lo más simple en Windows para un usuario no técnico: no crea un servicio, no pide admin y no deja consola abierta.

`lanzar_localhost.cmd` de la raíz se deja como estaba por si alguien prefiere ver la consola.
