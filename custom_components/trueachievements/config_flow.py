"""Config flow for TrueAchievements."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_EXCLUDED_APPS,
    CONF_GAMER_ID,
    CONF_GAMERTAG,
    CONF_GAMERTOKEN,
    CONF_GAMES_FILE,
    CONF_NOW_PLAYING_ENTITY,
    DEFAULT_GAMES_FILE,
    DOMAIN,
)


class TrueAchievementsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TrueAchievements."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        if user_input is not None:
            # Create the config entry with a title showing the Gamertag
            return self.async_create_entry(
                title=f"TA ({user_input[CONF_GAMERTAG]})", data=user_input
            )

        # Show the configuration form to the user
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GAMERTAG): str,
                    vol.Required(CONF_GAMER_ID): str,
                    vol.Required(CONF_GAMERTOKEN): str,
                    vol.Optional(CONF_NOW_PLAYING_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            integration="xbox", domain="sensor"
                        )
                    ),
                    vol.Optional(CONF_EXCLUDED_APPS, default=""): str,
                    vol.Required(CONF_GAMES_FILE, default=DEFAULT_GAMES_FILE): str,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> TrueAchievementsOptionsFlowHandler:
        """Get the options flow for this handler."""
        return TrueAchievementsOptionsFlowHandler()


class TrueAchievementsOptionsFlowHandler(OptionsFlow):
    """Handle TrueAchievements options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Retrieve current options or fall back to initial data
        token = self.config_entry.options.get(
            CONF_GAMERTOKEN, self.config_entry.data.get(CONF_GAMERTOKEN)
        )
        excluded = self.config_entry.options.get(
            CONF_EXCLUDED_APPS, self.config_entry.data.get(CONF_EXCLUDED_APPS, "")
        )
        current_now_playing = self.config_entry.options.get(
            CONF_NOW_PLAYING_ENTITY, self.config_entry.data.get(CONF_NOW_PLAYING_ENTITY)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_GAMERTOKEN, default=token): str,
                    vol.Optional(
                        CONF_NOW_PLAYING_ENTITY, default=current_now_playing
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            integration="xbox", domain="sensor"
                        )
                    ),
                    vol.Optional(CONF_EXCLUDED_APPS, default=excluded): str,
                }
            ),
        )
