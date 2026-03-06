"""
Sistema de modo offline para ESCritORIA.
Permite guardar borradores localmente cuando no hay conexión,
detectar el estado de la red y sincronizar cambios pendientes.
"""
import json
import os
import time
import threading
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, Qt, QThread
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
    QMessageBox, QGroupBox
)

from config.settings import CONFIG_DIR


OFFLINE_DIR = CONFIG_DIR / "offline_drafts"
OFFLINE_INDEX_FILE = OFFLINE_DIR / "index.json"


def ensure_offline_dir():
    """Crea el directorio de borradores offline si no existe."""
    OFFLINE_DIR.mkdir(parents=True, exist_ok=True)


class OfflineManager(QObject):
    """
    Gestor de modo offline.
    Detecta automáticamente el estado de la red y permite
    guardar/recuperar borradores locales.
    """

    # Señales
    connection_changed = pyqtSignal(bool)  # True = online, False = offline
    draft_saved = pyqtSignal(str)  # ID del borrador guardado
    draft_synced = pyqtSignal(str)  # ID del borrador sincronizado
    sync_error = pyqtSignal(str, str)  # ID, mensaje de error

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_online = True
        self._api_client = None
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._check_connection)
        self._check_interval = 30000  # 30 segundos
        self._drafts_index = {}
        self._load_index()

    @property
    def is_online(self):
        return self._is_online

    @property
    def pending_count(self):
        """Número de borradores pendientes de sincronización."""
        return len(self._drafts_index)

    def set_api_client(self, client):
        """Establece el cliente de API para verificar la conexión."""
        self._api_client = client
        if client:
            self._check_connection()
            self._check_timer.start(self._check_interval)
        else:
            self._check_timer.stop()
            self._is_online = False
            self.connection_changed.emit(False)

    def start_monitoring(self):
        """Inicia el monitoreo de conexión."""
        if self._api_client:
            self._check_timer.start(self._check_interval)

    def stop_monitoring(self):
        """Detiene el monitoreo de conexión."""
        self._check_timer.stop()

    def _check_connection(self):
        """Verifica la conexión al servidor WordPress."""
        if not self._api_client:
            if self._is_online:
                self._is_online = False
                self.connection_changed.emit(False)
            return

        try:
            import requests
            response = self._api_client.session.get(
                f"{self._api_client.site_url}/wp-json",
                timeout=5
            )
            was_offline = not self._is_online
            self._is_online = response.status_code == 200

            if was_offline and self._is_online:
                self.connection_changed.emit(True)
            elif not self._is_online and not was_offline:
                self.connection_changed.emit(False)
        except Exception:
            if self._is_online:
                self._is_online = False
                self.connection_changed.emit(False)

    def _load_index(self):
        """Carga el índice de borradores offline."""
        ensure_offline_dir()
        if OFFLINE_INDEX_FILE.exists():
            try:
                with open(OFFLINE_INDEX_FILE, "r", encoding="utf-8") as f:
                    self._drafts_index = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._drafts_index = {}
        else:
            self._drafts_index = {}

    def _save_index(self):
        """Guarda el índice de borradores offline."""
        ensure_offline_dir()
        with open(OFFLINE_INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(self._drafts_index, f, indent=2, ensure_ascii=False)

    def save_draft(self, content_type, data, post_id=None):
        """
        Guarda un borrador localmente.

        Args:
            content_type: 'post' o 'page'
            data: dict con los datos del contenido
            post_id: ID del post/página si es una edición (None para nuevo)

        Returns:
            str: ID del borrador local
        """
        ensure_offline_dir()

        # Generar ID único para el borrador
        draft_id = f"{content_type}_{post_id or 'new'}_{int(time.time())}"

        # Guardar el archivo del borrador
        draft_file = OFFLINE_DIR / f"{draft_id}.json"
        draft_data = {
            "id": draft_id,
            "type": content_type,
            "post_id": post_id,
            "data": data,
            "created_at": datetime.now().isoformat(),
            "synced": False,
        }

        with open(draft_file, "w", encoding="utf-8") as f:
            json.dump(draft_data, f, indent=2, ensure_ascii=False)

        # Actualizar índice
        self._drafts_index[draft_id] = {
            "type": content_type,
            "post_id": post_id,
            "title": data.get("title", "Sin título"),
            "created_at": draft_data["created_at"],
            "synced": False,
        }
        self._save_index()

        self.draft_saved.emit(draft_id)
        return draft_id

    def get_draft(self, draft_id):
        """Obtiene un borrador por su ID."""
        draft_file = OFFLINE_DIR / f"{draft_id}.json"
        if draft_file.exists():
            with open(draft_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def get_all_drafts(self):
        """Obtiene todos los borradores pendientes."""
        self._load_index()
        drafts = []
        for draft_id, info in self._drafts_index.items():
            if not info.get("synced", False):
                draft_data = self.get_draft(draft_id)
                if draft_data:
                    drafts.append(draft_data)
        return drafts

    def delete_draft(self, draft_id):
        """Elimina un borrador local."""
        draft_file = OFFLINE_DIR / f"{draft_id}.json"
        if draft_file.exists():
            draft_file.unlink()
        self._drafts_index.pop(draft_id, None)
        self._save_index()

    def sync_draft(self, draft_id, posts_api=None, pages_api=None):
        """
        Sincroniza un borrador con el servidor.

        Args:
            draft_id: ID del borrador local
            posts_api: instancia de PostsAPI
            pages_api: instancia de PagesAPI

        Returns:
            bool: True si se sincronizó correctamente
        """
        if not self._is_online:
            self.sync_error.emit(draft_id, "Sin conexión al servidor")
            return False

        draft = self.get_draft(draft_id)
        if not draft:
            self.sync_error.emit(draft_id, "Borrador no encontrado")
            return False

        try:
            content_type = draft["type"]
            data = draft["data"]
            post_id = draft.get("post_id")

            api = posts_api if content_type == "post" else pages_api
            if not api:
                self.sync_error.emit(draft_id, f"No hay API disponible para {content_type}")
                return False

            if post_id:
                api.update(post_id, **data)
            else:
                api.create(**data)

            # Marcar como sincronizado
            self._drafts_index[draft_id]["synced"] = True
            self._save_index()

            # Eliminar archivo
            self.delete_draft(draft_id)
            self.draft_synced.emit(draft_id)
            return True

        except Exception as e:
            self.sync_error.emit(draft_id, str(e))
            return False

    def sync_all(self, posts_api=None, pages_api=None):
        """
        Sincroniza todos los borradores pendientes.

        Returns:
            tuple: (exitosos, errores)
        """
        drafts = self.get_all_drafts()
        success = 0
        errors = 0

        for draft in drafts:
            if self.sync_draft(draft["id"], posts_api, pages_api):
                success += 1
            else:
                errors += 1

        return success, errors

    def clear_all(self):
        """Elimina todos los borradores offline."""
        ensure_offline_dir()
        for f in OFFLINE_DIR.glob("*.json"):
            f.unlink()
        self._drafts_index = {}
        self._save_index()


class SyncThread(QThread):
    """Hilo para sincronizar borradores sin bloquear la UI."""
    finished = pyqtSignal(int, int)  # exitosos, errores
    error = pyqtSignal(str)

    def __init__(self, offline_manager, posts_api=None, pages_api=None):
        super().__init__()
        self.offline_manager = offline_manager
        self.posts_api = posts_api
        self.pages_api = pages_api

    def run(self):
        try:
            success, errors = self.offline_manager.sync_all(
                self.posts_api, self.pages_api
            )
            self.finished.emit(success, errors)
        except Exception as e:
            self.error.emit(str(e))


class OfflineStatusWidget(QWidget):
    """
    Widget de estado de conexión que se muestra en la barra superior.
    Indica si la app está online/offline y muestra borradores pendientes.
    """

    sync_requested = pyqtSignal()

    def __init__(self, offline_manager, parent=None):
        super().__init__(parent)
        self.offline_manager = offline_manager
        self._setup_ui()

        # Conectar señales
        self.offline_manager.connection_changed.connect(self._on_connection_changed)
        self.offline_manager.draft_saved.connect(self._update_pending)
        self.offline_manager.draft_synced.connect(self._update_pending)

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        # Indicador de estado
        self.lbl_status = QLabel("🟢 Online")
        self.lbl_status.setStyleSheet(
            "QLabel { color: #27ae60; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none; padding: 2px 6px; }"
        )
        layout.addWidget(self.lbl_status)

        # Borradores pendientes
        self.lbl_pending = QLabel("")
        self.lbl_pending.setStyleSheet(
            "QLabel { color: #f39c12; font-size: 11px; "
            "background: transparent; border: none; padding: 2px 4px; }"
        )
        self.lbl_pending.setVisible(False)
        layout.addWidget(self.lbl_pending)

        # Botón sincronizar
        self.btn_sync = QPushButton("⟳ Sincronizar")
        self.btn_sync.setFixedHeight(22)
        self.btn_sync.setStyleSheet("""
            QPushButton {
                background-color: #0073aa;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #005f8f;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #999;
            }
        """)
        self.btn_sync.setVisible(False)
        self.btn_sync.clicked.connect(self._on_sync_clicked)
        layout.addWidget(self.btn_sync)

    def _on_sync_clicked(self) -> None:
        """Emite la señal de sincronización solicitada."""
        self.sync_requested.emit()  # type: ignore[attr-defined]

    def _on_connection_changed(self, is_online):
        """Actualiza el indicador cuando cambia el estado de conexión."""
        if is_online:
            self.lbl_status.setText("🟢 Online")
            self.lbl_status.setStyleSheet(
                "QLabel { color: #27ae60; font-size: 11px; font-weight: bold; "
                "background: transparent; border: none; padding: 2px 6px; }"
            )
            # Si hay borradores pendientes, mostrar botón de sincronización
            if self.offline_manager.pending_count > 0:
                self.btn_sync.setVisible(True)
        else:
            self.lbl_status.setText("🔴 Offline")
            self.lbl_status.setStyleSheet(
                "QLabel { color: #e74c3c; font-size: 11px; font-weight: bold; "
                "background: transparent; border: none; padding: 2px 6px; }"
            )
            self.btn_sync.setVisible(False)

        self._update_pending()

    def _update_pending(self, _draft_id=None):
        """Actualiza el contador de borradores pendientes."""
        count = self.offline_manager.pending_count
        if count > 0:
            self.lbl_pending.setText(f"📋 {count} pendiente{'s' if count > 1 else ''}")
            self.lbl_pending.setVisible(True)
            if self.offline_manager.is_online:
                self.btn_sync.setVisible(True)
        else:
            self.lbl_pending.setVisible(False)
            self.btn_sync.setVisible(False)

    def refresh(self):
        """Refresca el estado visual."""
        self._on_connection_changed(self.offline_manager.is_online)


class OfflineDraftsDialog(QDialog):
    """Diálogo para ver y gestionar borradores offline."""

    def __init__(self, offline_manager, parent=None):
        super().__init__(parent)
        self.offline_manager = offline_manager
        self.setWindowTitle("Borradores Offline")
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._load_drafts()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info
        info = QLabel(
            "Borradores guardados localmente mientras estabas sin conexión.\n"
            "Cuando la conexión se restablezca, puedes sincronizarlos con el servidor."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #a7aaad; padding: 5px;")
        layout.addWidget(info)

        # Lista de borradores
        self.draft_list = QListWidget()
        self.draft_list.setAlternatingRowColors(True)
        layout.addWidget(self.draft_list)

        # Botones
        btn_layout = QHBoxLayout()

        self.btn_sync_all = QPushButton("⟳ Sincronizar Todos")
        self.btn_sync_all.setObjectName("btnSuccess")
        self.btn_sync_all.clicked.connect(self._sync_all)
        btn_layout.addWidget(self.btn_sync_all)

        self.btn_delete_selected = QPushButton("Eliminar Seleccionado")
        self.btn_delete_selected.setObjectName("btnDanger")
        self.btn_delete_selected.clicked.connect(self._delete_selected)
        btn_layout.addWidget(self.btn_delete_selected)

        self.btn_clear_all = QPushButton("Limpiar Todo")
        self.btn_clear_all.clicked.connect(self._clear_all)
        btn_layout.addWidget(self.btn_clear_all)

        btn_layout.addStretch()

        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.close)  # type: ignore[arg-type]
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

        # Estado
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #72aee6; padding: 3px;")
        layout.addWidget(self.lbl_status)

    def _load_drafts(self):
        """Carga la lista de borradores."""
        self.draft_list.clear()
        drafts = self.offline_manager.get_all_drafts()

        if not drafts:
            item = QListWidgetItem("No hay borradores offline pendientes.")
            item.setFlags(Qt.ItemFlag(item.flags() & ~Qt.ItemFlag.ItemIsSelectable))
            self.draft_list.addItem(item)
            self.btn_sync_all.setEnabled(False)
            self.btn_delete_selected.setEnabled(False)
            self.btn_clear_all.setEnabled(False)
            return

        for draft in drafts:
            title = draft.get("data", {}).get("title", "Sin título")
            dtype = "Entrada" if draft["type"] == "post" else "Página"
            action = "Editar" if draft.get("post_id") else "Crear"
            created = draft.get("created_at", "")[:19].replace("T", " ")

            text = f"[{dtype}] {action}: {title}  —  {created}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, draft["id"])
            self.draft_list.addItem(item)

        self.lbl_status.setText(f"{len(drafts)} borrador(es) pendiente(s)")

    def _sync_all(self):
        """Sincroniza todos los borradores."""
        if not self.offline_manager.is_online:
            QMessageBox.warning(
                self, "Sin Conexión",
                "No se puede sincronizar sin conexión al servidor."
            )
            return

        self.lbl_status.setText("Sincronizando...")
        # La sincronización se maneja desde main_window
        self.accept()

    def _delete_selected(self):
        """Elimina el borrador seleccionado."""
        item = self.draft_list.currentItem()
        if not item:
            return
        draft_id = item.data(Qt.ItemDataRole.UserRole)
        if not draft_id:
            return

        reply = QMessageBox.question(
            self, "Confirmar",
            "¿Eliminar este borrador offline?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.offline_manager.delete_draft(draft_id)
            self._load_drafts()

    def _clear_all(self):
        """Elimina todos los borradores."""
        reply = QMessageBox.question(
            self, "Confirmar",
            "¿Eliminar TODOS los borradores offline?\n"
            "Esta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.offline_manager.clear_all()
            self._load_drafts()
