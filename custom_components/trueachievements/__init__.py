"""The TrueAchievements integration."""

from __future__ import annotations

import logging
from http import HTTPStatus

from aiohttp import web
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_WEBHOOK_ID, DOMAIN, MAX_UPLOAD_BYTES, STARTUP_MESSAGE
from .coordinator import TrueAchievementsCoordinator

PLATFORMS: list[str] = ["binary_sensor", "button", "sensor"]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up TrueAchievements from a config entry."""
    _LOGGER.info(STARTUP_MESSAGE)
    session = async_get_clientsession(hass)

    coordinator = TrueAchievementsCoordinator(hass, entry, session)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Webhook used by an external tool (the PC script) to send the CSV export.
    if CONF_WEBHOOK_ID not in entry.data:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_WEBHOOK_ID: webhook.async_generate_id()}
        )
    webhook_id = str(entry.data[CONF_WEBHOOK_ID])

    async def _handle_upload(
        _hass: HomeAssistant, _webhook_id: str, request: web.Request
    ) -> web.Response:
        if (request.content_length or 0) > MAX_UPLOAD_BYTES:
            return web.Response(status=HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        content = await request.read()
        if len(content) > MAX_UPLOAD_BYTES or not await coordinator.async_receive_csv(
            content
        ):
            return web.Response(status=HTTPStatus.BAD_REQUEST)
        return web.Response(text="OK")

    webhook.async_register(
        hass,
        DOMAIN,
        f"TrueAchievements {coordinator.gamer_tag}",
        webhook_id,
        _handle_upload,
        allowed_methods=["POST", "PUT"],
        local_only=True,
    )
    entry.async_on_unload(lambda: webhook.async_unregister(hass, webhook_id))
    _LOGGER.info("CSV upload address registered (shown in the integration options)")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update and reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
