"""Config flow for TrueAchievements."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.components import webhook
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
    CONF_FILE_ONLY,
    CONF_GAMER_ID,
    CONF_GAMERTAG,
    CONF_GAMERTOKEN,
    CONF_GAMES_FILE,
    CONF_NOTIFY_AUTH_ERROR,
    CONF_NOTIFY_COMPLETION_LOST,
    CONF_NOTIFY_MAPPING,
    CONF_NOW_PLAYING_ENTITY,
    CONF_USER_AGENT,
    CONF_WEBHOOK_ID,
    DEFAULT_GAMES_FILE,
    DEFAULT_NOTIFY_AUTH_ERROR,
    DEFAULT_NOTIFY_COMPLETION_LOST,
    DEFAULT_NOTIFY_MAPPING,
    DOMAIN,
)

# Text fields of the options form that may be cleared by the user.
OPTIONAL_TEXT_KEYS = (
    CONF_GAMERTOKEN,
    CONF_USER_AGENT,
    CONF_EXCLUDED_APPS,
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
                title=f"TA ({user_input[CONF_GAMERTAG]})",
                data={**user_input, CONF_WEBHOOK_ID: webhook.async_generate_id()},
            )

        # Show the configuration form to the user
        return self.async_show_form(
            step_id="user",
            data_schema=probatio.Schema(
                {
                    probatio.Required(CONF_GAMERTAG): str,
                    probatio.Required(CONF_GAMER_ID): str,
                    probatio.Optional(CONF_GAMERTOKEN, default=""): str,
                    probatio.Optional(CONF_USER_AGENT, default=""): str,
                    probatio.Optional(CONF_FILE_ONLY, default=False): bool,
                    probatio.Optional(CONF_NOW_PLAYING_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            integration="xbox", domain="sensor"
                        )
                    ),
                    probatio.Optional(CONF_EXCLUDED_APPS, default=""): str,
                    probatio.Required(CONF_GAMES_FILE, default=DEFAULT_GAMES_FILE): str,
                    probatio.Optional(
                        CONF_NOTIFY_MAPPING, default=DEFAULT_NOTIFY_MAPPING
                    ): bool,
                    probatio.Optional(
                        CONF_NOTIFY_AUTH_ERROR, default=DEFAULT_NOTIFY_AUTH_ERROR
                    ): bool,
                    probatio.Optional(
                        CONF_NOTIFY_COMPLETION_LOST,
                        default=DEFAULT_NOTIFY_COMPLETION_LOST,
                    ): bool,
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
            # A cleared text field is not sent at all by the frontend. Store an
            # empty value so that it overrides the one saved in the entry data.
            for key in OPTIONAL_TEXT_KEYS:
                user_input.setdefault(key, "")
            return self.async_create_entry(title="", data=user_input)

        # Retrieve current options or fall back to initial data
        token = self.config_entry.options.get(
            CONF_GAMERTOKEN, self.config_entry.data.get(CONF_GAMERTOKEN)
        )
        user_agent = self.config_entry.options.get(
            CONF_USER_AGENT, self.config_entry.data.get(CONF_USER_AGENT, "")
        )
        file_only = self.config_entry.options.get(
            CONF_FILE_ONLY, self.config_entry.data.get(CONF_FILE_ONLY, False)
        )
        excluded = self.config_entry.options.get(
            CONF_EXCLUDED_APPS, self.config_entry.data.get(CONF_EXCLUDED_APPS, "")
        )
        current_now_playing = self.config_entry.options.get(
            CONF_NOW_PLAYING_ENTITY, self.config_entry.data.get(CONF_NOW_PLAYING_ENTITY)
        )
        notify_mapping = self.config_entry.options.get(
            CONF_NOTIFY_MAPPING,
            self.config_entry.data.get(CONF_NOTIFY_MAPPING, DEFAULT_NOTIFY_MAPPING),
        )
        notify_auth_error = self.config_entry.options.get(
            CONF_NOTIFY_AUTH_ERROR,
            self.config_entry.data.get(
                CONF_NOTIFY_AUTH_ERROR, DEFAULT_NOTIFY_AUTH_ERROR
            ),
        )
        notify_completion_lost = self.config_entry.options.get(
            CONF_NOTIFY_COMPLETION_LOST,
            self.config_entry.data.get(
                CONF_NOTIFY_COMPLETION_LOST, DEFAULT_NOTIFY_COMPLETION_LOST
            ),
        )

        # An entity selector cannot validate a default of None: only pre-fill the
        # field when an Xbox entity was actually selected.
        now_playing_key = (
            probatio.Optional(CONF_NOW_PLAYING_ENTITY, default=current_now_playing)
            if current_now_playing
            else probatio.Optional(CONF_NOW_PLAYING_ENTITY)
        )

        webhook_id = self.config_entry.data.get(CONF_WEBHOOK_ID)
        return self.async_show_form(
            step_id="init",
            description_placeholders={
                "webhook_path": webhook.async_generate_path(str(webhook_id))
                if webhook_id
                else "-"
            },
            data_schema=probatio.Schema(
                {
                    probatio.Optional(
                        CONF_GAMERTOKEN, description={"suggested_value": token}
                    ): str,
                    probatio.Optional(CONF_FILE_ONLY, default=file_only): bool,
                    probatio.Optional(
                        CONF_USER_AGENT, description={"suggested_value": user_agent}
                    ): str,
                    now_playing_key: selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            integration="xbox", domain="sensor"
                        )
                    ),
                    probatio.Optional(
                        CONF_EXCLUDED_APPS, description={"suggested_value": excluded}
                    ): str,
                    probatio.Optional(
                        CONF_NOTIFY_MAPPING, default=notify_mapping
                    ): bool,
                    probatio.Optional(
                        CONF_NOTIFY_AUTH_ERROR, default=notify_auth_error
                    ): bool,
                    probatio.Optional(
                        CONF_NOTIFY_COMPLETION_LOST, default=notify_completion_lost
                    ): bool,
                }
            ),
        )
