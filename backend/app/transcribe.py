"""Transcription locale (faster-whisper, GPU) avec progression et exports .txt/.srt/.md."""
import glob
import gc
import os
import site
import subprocess
from pathlib import Path
from collections.abc import Callable

from .config import WHISPER_MODEL


def _register_cuda_dlls() -> None:
    """Windows : les DLL cublas/cudnn installées via pip doivent être dans le PATH."""
    for sp in site.getsitepackages():
        for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]


def ts(t: float, sep: str = ",") -> str:
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02}:{int(m):02}:{int(s):02}{sep}{int((s % 1) * 1000):03}"


def decode_audio(path: str, sr: int = 16000):
    """Décode n'importe quel audio/vidéo en float32 mono 16 kHz.
    PyAV embarque ses propres bibliothèques FFmpeg : aucun ffmpeg à installer. Secours : ffmpeg du PATH."""
    import numpy as np
    try:
        import av
        chunks = []
        with av.open(path) as container:
            if not container.streams.audio:
                raise ValueError("Aucune piste audio dans ce fichier.")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=sr)
            for frame in container.decode(container.streams.audio[0]):
                for out in resampler.resample(frame):
                    chunks.append(out.to_ndarray().reshape(-1))
            for out in resampler.resample(None):
                chunks.append(out.to_ndarray().reshape(-1))
        if not chunks:
            raise ValueError("Audio vide.")
        return np.concatenate(chunks).astype(np.float32) / 32768.0
    except ValueError:
        raise
    except Exception:  # noqa: BLE001 - PyAV indisponible/incompatible -> ffmpeg en ligne de commande
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"],
                             capture_output=True, check=True, creationflags=flags).stdout
        return np.frombuffer(raw, dtype=np.float32)


def transcribe(src: str, out_base: Path, lang: str | None = None, prompt: str | None = None,
               on_progress: Callable[[float, str], None] | None = None) -> dict:
    """Retourne {language, duration, segments:[{start,end,text}]} et écrit .txt/.srt/.md."""
    _register_cuda_dlls()
    from faster_whisper import WhisperModel

    if on_progress:
        on_progress(0.0, "Chargement du modèle de transcription…")
    model = WhisperModel(WHISPER_MODEL, device="cuda", compute_type="float16")
    try:
        if on_progress:
            on_progress(0.0, "Décodage de l'audio…")
        audio = decode_audio(src)
        segs, info = model.transcribe(
            audio, language=None if lang in (None, "", "auto") else lang, vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500), condition_on_previous_text=False,
            initial_prompt=prompt or None, beam_size=5)
        rows = []
        for s in segs:
            rows.append({"start": s.start, "end": s.end, "text": s.text.strip()})
            if on_progress and info.duration:
                on_progress(min(s.end / info.duration, 1.0), "Transcription…")
    finally:
        del model
        gc.collect()  # libère la VRAM avant le LLM

    write_outputs(rows, out_base)
    return {"language": info.language, "duration": info.duration, "segments": rows}


def write_outputs(rows: list[dict], out_base: Path) -> None:
    out_base.with_suffix(".txt").write_text("\n".join(r["text"] for r in rows), encoding="utf-8")
    out_base.with_suffix(".srt").write_text(
        "\n".join(f"{i}\n{ts(r['start'])} --> {ts(r['end'])}\n{r['text']}\n" for i, r in enumerate(rows, 1)),
        encoding="utf-8")
    out_base.with_suffix(".md").write_text(
        "\n".join(f"**[{ts(r['start'], '.')[:8]}]** {r['text']}\n" for r in rows), encoding="utf-8")
