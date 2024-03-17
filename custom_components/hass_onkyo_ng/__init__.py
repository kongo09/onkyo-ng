"""The Onkyo AV receiver component."""
from __future__ import annotations
from datetime import timedelta

from .const import *

from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_HOST, CONF_SCAN_INTERVAL
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
    UpdateFailed,
)

from .onkyo import OnkyoReceiver

import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Setup an Onkyo AV receiver from a config entry."""

    # get the host address
    host = entry.data[CONF_HOST]

    # get the receiver
    update_interval = entry.data[CONF_SCAN_INTERVAL]

    try:
        # TODO: Where is this removed when the entry is unloaded...
        onkyo_receiver = OnkyoReceiver(
            host=host,
            hass=hass,
            max_volume=ONKYO_SUPPORTED_MAX_VOLUME,
            receiver_max_volume=ONKYO_DEFAULT_RECEIVER_MAX_VOLUME,
        )
        await onkyo_receiver.load_data()

        retries = 3
        receiver_info = None
        while receiver_info is None and retries > 0:
            retries -= 1
            try:
                receiver_info = onkyo_receiver.receiver_info
            except Exception as error:
                _LOGGER.error("Error getting receiver information", error)
                raise error

        _LOGGER.info(receiver_info)
        name = receiver_info.model
        serial = receiver_info.serial
        productid = receiver_info.productid
        macaddress = receiver_info.macaddress
        _LOGGER.debug("Found %s (Serial: %s) (Product ID: %s) (Mac Address: %s)", name, serial, productid, macaddress)
    except (ConnectionError) as error:
        _LOGGER.error("Cannot load data with error: %s", error)
        return False

    # setup a coordinator
    coordinator = OnkyoDataUpdateCoordinator(
        hass, onkyo_receiver, timedelta(seconds=update_interval)
    )

    # refresh coordinator for the first time to load initial data
    await coordinator.async_config_entry_first_refresh()

    # store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # setup sensors
    for p in PLATFORMS:
        hass.async_create_task(hass.config_entries.async_forward_entry_setup(entry, p))
    # hass.config_entries.async_setup_platforms(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""

    for p in PLATFORMS:
        await hass.config_entries.async_forward_entry_unload(entry, p)

    hass.data[DOMAIN].pop(entry.entry_id)

    return True


class OnkyoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Onkyo data from the receiver."""

    def __init__(
        self,
        hass: HomeAssistant,
        onkyo_receiver: OnkyoReceiver,
        update_interval: timedelta,
    ) -> None:
        """Initialize."""
        self._onkyo_receiver = onkyo_receiver
        self._onkyo_receiver.register_listener(self.receive_data)
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)
        self._onkyo_receiver.update()

    def receive_data(self, data):
        _LOGGER.debug(f"Data: {data}")
        self.async_set_updated_data(data)

    async def _async_update_data(self) -> dict:
        """Update data via library."""
        data = {}
        try:
            # Ask the library to reload fresh data
            self._onkyo_receiver.update()
            return self._onkyo_receiver.data
        except (ConnectionError) as error:
            raise UpdateFailed(error) from error


class OnkyoReceiverEntity(CoordinatorEntity):
    """Class to set basics for a receiver entity."""

    def __init__(self, coordinator: OnkyoDataUpdateCoordinator) -> None:
        super().__init__(coordinator, )
        self._model_name = coordinator.data[ATTR_NAME]
        self._name = coordinator.data[ATTR_NAME]
        self._identifier = coordinator.data[ATTR_IDENTIFIER]
        self._serial_number = f"{self._model_name}_{self._identifier}"
        self._available = True

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._serial_number)},
            "name": self._name,
            "model": self._model_name,
            "manufacturer": "Onkyo",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available
