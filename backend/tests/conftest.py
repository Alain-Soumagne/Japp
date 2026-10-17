"""Isole les tests : le dossier de données est un répertoire temporaire, défini avant tout import de l'application."""
import os
import tempfile

os.environ["JAPP_DATA_DIR"] = tempfile.mkdtemp(prefix="japp-test-")
