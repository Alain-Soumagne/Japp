import time

from app import jobs
from app.config import JOBS_DIR


def test_sauvegarde_d_une_tache_supprimee_ne_plante_pas():
    jid = "gone" + str(int(time.time() * 1000))[-6:]
    job = {"id": jid, "name": "x", "status": "running"}
    assert not (JOBS_DIR / jid).exists()
    jobs._save(job)                      # ne lève pas FileNotFoundError
    jobs._set(job, status="error")       # idem
    assert not (JOBS_DIR / jid).exists()
