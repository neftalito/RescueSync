"""Distribuye notificaciones confirmadas a conexiones WebSocket locales."""

from __future__ import annotations

import asyncio
from collections import defaultdict

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.schemas.notificacion import EventoNotificacion, NotificacionResponse
from app.services.notificaciones import listar_por_clave


class GestorTiempoReal:
    """Mantiene conexiones autenticadas y programa envíos desde rutas sync."""

    def __init__(self) -> None:
        self._conexiones: dict[int, set[WebSocket]] = defaultdict(set)
        self._auditores: set[int] = set()
        self._candado = asyncio.Lock()
        self._bucle: asyncio.AbstractEventLoop | None = None

    def iniciar(self) -> None:
        """Vincula el gestor con el bucle de vida de FastAPI."""

        self._bucle = asyncio.get_running_loop()

    async def detener(self) -> None:
        """Cierra conexiones abiertas durante el apagado de la API."""

        async with self._candado:
            conexiones = [
                websocket
                for conexiones_usuario in self._conexiones.values()
                for websocket in conexiones_usuario
            ]
            self._conexiones.clear()
            self._auditores.clear()
        for websocket in conexiones:
            try:
                await websocket.close(code=1001)
            except (RuntimeError, OSError, WebSocketDisconnect):
                pass
        self._bucle = None

    async def conectar(
        self, usuario_id: int, websocket: WebSocket, *, auditor: bool = False
    ) -> None:
        """Acepta y registra un socket ya autenticado."""

        await websocket.accept()
        async with self._candado:
            self._conexiones[usuario_id].add(websocket)
            if auditor:
                self._auditores.add(usuario_id)

    async def desconectar(self, usuario_id: int, websocket: WebSocket) -> None:
        """Retira una conexión sin afectar otras pestañas del usuario."""

        async with self._candado:
            conexiones = self._conexiones.get(usuario_id)
            if conexiones is None:
                return
            conexiones.discard(websocket)
            if not conexiones:
                self._conexiones.pop(usuario_id, None)
                self._auditores.discard(usuario_id)

    def programar_metricas(self) -> None:
        """Invalida el panel de los auditores sin enviar datos ni llenar su buzón."""
        if self._bucle is not None and not self._bucle.is_closed():
            self._bucle.call_soon_threadsafe(
                lambda: asyncio.create_task(self._emitir_metricas())
            )

    async def _emitir_metricas(self) -> None:
        async with self._candado:
            conexiones = [
                (usuario_id, websocket)
                for usuario_id in self._auditores
                for websocket in self._conexiones.get(usuario_id, ())
            ]
        for usuario_id, websocket in conexiones:
            try:
                await websocket.send_json({"evento": "metricas.actualizadas"})
            except (RuntimeError, OSError, WebSocketDisconnect):
                await self.desconectar(usuario_id, websocket)

    def programar(self, notificaciones: list[NotificacionResponse]) -> None:
        """Agenda envíos seguros desde el threadpool de rutas sincrónicas."""

        bucle = self._bucle
        if bucle is None or bucle.is_closed() or not notificaciones:
            return
        bucle.call_soon_threadsafe(
            lambda: asyncio.create_task(self._emitir(notificaciones))
        )

    async def _emitir(self, notificaciones: list[NotificacionResponse]) -> None:
        for notificacion in notificaciones:
            async with self._candado:
                conexiones = tuple(self._conexiones.get(notificacion.usuario_id, ()))
            mensaje = EventoNotificacion(notificacion=notificacion).model_dump(
                mode="json"
            )
            fallidas: list[WebSocket] = []
            for websocket in conexiones:
                try:
                    await websocket.send_json(mensaje)
                except (RuntimeError, OSError, WebSocketDisconnect):
                    fallidas.append(websocket)
            for websocket in fallidas:
                await self.desconectar(notificacion.usuario_id, websocket)


def programar_evento_confirmado(
    gestor: GestorTiempoReal,
    session: Session,
    clave_evento: str,
) -> None:
    """Carga un evento ya confirmado y agenda su entrega a cada destinatario."""

    gestor.programar_metricas()
    gestor.programar(
        [
            NotificacionResponse.model_validate(notificacion)
            for notificacion in listar_por_clave(session, clave_evento)
        ]
    )
