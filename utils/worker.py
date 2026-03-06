"""
Worker thread genérico para ejecutar operaciones de red
fuera del hilo principal de Qt, evitando bloqueos de la UI.

Uso:
    worker = WorkerThread(lambda: api.list(per_page=20))
    worker.finished.connect(self._on_data_loaded)
    worker.error.connect(self._on_error)
    worker.start()
"""
from PyQt5.QtCore import QThread, pyqtSignal


class WorkerThread(QThread):
    """Ejecuta una función callable en un hilo separado."""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
