import asyncio
import json
from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx
import websockets
from pydantic import ValidationError

from app.core.config import settings
from app.modules.home_assistant.schemas.home_assistant import (
    HomeAssistantConfigSchema,
    HomeAssistantHistoryStateSchema,
    HomeAssistantStateSchema,
)


class HomeAssistantConfigInvalidError(RuntimeError):
    pass


class HomeAssistantService:
    def __init__(self) -> None:
        self.base_url = settings.ha_url.rstrip("/")
        self.token = settings.ha_token
        self.timeout = 10.0

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    async def check_connection(self) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/",
                headers=self._get_headers(),
            )

            response.raise_for_status()

            return response.json()

    async def get_states(self) -> list[HomeAssistantStateSchema]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/states",
                headers=self._get_headers(),
            )

            response.raise_for_status()

            states = response.json()

        return [
            HomeAssistantStateSchema.model_validate(state)
            for state in states
        ]

    async def get_registries(self) -> dict[str, list[dict[str, Any]]]:
        """Read HA registries through its authenticated local WebSocket API."""
        websocket_url = (
            self.base_url.replace("https://", "wss://", 1)
            .replace("http://", "ws://", 1)
            + "/api/websocket"
        )
        commands = {
            "areas": "config/area_registry/list",
            "devices": "config/device_registry/list",
            "entities": "config/entity_registry/list",
        }
        async with asyncio.timeout(self.timeout):
            async with websockets.connect(websocket_url) as websocket:
                hello = json.loads(await websocket.recv())
                if hello.get("type") != "auth_required":
                    raise RuntimeError("Unexpected Home Assistant WebSocket handshake.")
                await websocket.send(
                    json.dumps({"type": "auth", "access_token": self.token})
                )
                authenticated = json.loads(await websocket.recv())
                if authenticated.get("type") != "auth_ok":
                    raise RuntimeError("Home Assistant WebSocket authentication failed.")

                result: dict[str, list[dict[str, Any]]] = {}
                for request_id, (key, command) in enumerate(commands.items(), start=1):
                    await websocket.send(
                        json.dumps({"id": request_id, "type": command})
                    )
                    message = json.loads(await websocket.recv())
                    if (
                        message.get("id") != request_id
                        or message.get("type") != "result"
                        or message.get("success") is not True
                    ):
                        raise RuntimeError(f"Home Assistant {key} registry request failed.")
                    payload = message.get("result", [])
                    result[key] = payload if isinstance(payload, list) else []
                return result

    async def get_config(self) -> HomeAssistantConfigSchema:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/config",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            config = response.json()

        try:
            return HomeAssistantConfigSchema.model_validate(config)
        except ValidationError as exc:
            raise HomeAssistantConfigInvalidError(
                "Home Assistant config has no valid latitude, longitude, or time_zone."
            ) from exc

    async def get_state(
        self,
        entity_id: str,
    ) -> HomeAssistantStateSchema:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/states/{entity_id}",
                headers=self._get_headers(),
            )

            response.raise_for_status()

            state = response.json()

        return HomeAssistantStateSchema.model_validate(state)

    async def get_history(
        self,
        entity_id: str,
        start_time: datetime,
        end_time: datetime,
        minimal_response: bool = True,
        no_attributes: bool = True,
    ) -> list[HomeAssistantHistoryStateSchema]:
        if start_time.tzinfo is None or start_time.utcoffset() is None:
            raise ValueError("start_time must be timezone-aware.")
        if end_time.tzinfo is None or end_time.utcoffset() is None:
            raise ValueError("end_time must be timezone-aware.")
        if end_time <= start_time:
            raise ValueError("end_time must be after start_time.")

        start_timestamp = quote(start_time.isoformat(), safe="")
        params = {
            "filter_entity_id": entity_id,
            "end_time": end_time.isoformat(),
            "minimal_response": str(minimal_response).lower(),
            "no_attributes": str(no_attributes).lower(),
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}/api/history/period/{start_timestamp}",
                headers=self._get_headers(),
                params=params,
            )
            response.raise_for_status()
            history_groups = response.json()

        if not isinstance(history_groups, list) or not history_groups:
            return []
        history = history_groups[0]
        if not isinstance(history, list):
            return []
        return [
            HomeAssistantHistoryStateSchema.model_validate(item)
            for item in history
        ]

    async def call_service(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
        *,
        entity_id: str | None = None,
        target: dict[str, Any] | None = None,
    ) -> Any:
        payload: dict[str, Any] = dict(service_data or {})

        if entity_id is not None:
            payload.setdefault("entity_id", entity_id)

        if target is not None:
            payload["target"] = target

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/services/{domain}/{service}",
                headers=self._get_headers(),
                json=payload,
            )

            response.raise_for_status()

            return response.json()


home_assistant_service = HomeAssistantService()
