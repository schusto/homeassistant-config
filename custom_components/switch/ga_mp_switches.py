"""
Automatic Media Player switches for Google Assistant by Erik Schumann (@schusto)

"""

import logging

import voluptuous as vol

import homeassistant.helpers.config_validation as cv

from homeassistant.components.switch import DOMAIN, SwitchDevice
from homeassistant.const import (
    CONF_NAME, CONF_PLATFORM, CONF_MEDIA_PLAYER, CONF_MODE)
from homeassistant.helpers.event import (
    track_time_change, async_track_state_change)

from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)

CONF_PREFIX = 'prefix'
DEPENDENCIES = ['media_player']


PLATFORM_SCHEMA = vol.Schema({
    vol.Required(CONF_PLATFORM): 'mp_for_ga',
    vol.Required(CONF_MEDIA_PLAYER): cv.entity_ids,
    vol.Optional(CONF_NAME, default="mp_for_ga"): cv.string,
    vol.Optional(CONF_PREFIX): cv.string
})


def set_lights_xy(hass, lights, x_val, y_val, brightness, transition, lastcolor):
    """Set color of array of lights."""
    for light in lights:
        if is_on(hass, light):
            states = hass.states.get(light)
            if (lastcolor == 0) or (states.attributes.get('xy_color') == lastcolor):
                turn_on(hass, light,
                        xy_color=[x_val, y_val],
                        brightness=brightness,
                        transition=transition)
    return [x_val, y_val]

# pylint: disable=unused-argument
def setup_platform(hass, config, add_devices, discovery_info=None):
    """Set up the MP_for_GA switches."""
    name = config.get(CONF_NAME)
    mps = config.get(CONF_MEDIA_PLAYER)
    prefix = config.get(CONF_PREFIX)

    for mp in mps:
        mp_switch[mp] = MpSwitch(name, hass, mp, prefix)

		
		
    add_devices([flux])

    def update(call=None):
        """Update lights."""
        flux.flux_update()

    service_name = slugify("{} {}".format(name, 'update'))
    hass.services.register(DOMAIN, service_name, update)

    def force_update(call=None):
        """Update lights."""
        flux.flux_force_update(call)

    service_name = slugify("{} {}".format(name, 'force_update'))
    hass.services.register(DOMAIN, service_name, force_update)


class MpSwitch(SwitchDevice):
    """Representation of a Flux switch."""

    def __init__(self, name, hass, mp, prefix):
        """Initialize the Flux switch."""
        self._name = name
        self.hass = hass
        self._mp = mp
        self._prefix = prefix
        self.state
        self.play
        self.stop
        self.previous
        self.next
        self.shuffle
    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    @property
    def is_on(self):
        """Return true if switch is on."""
        return self.unsub_tracker is not None

    def turn_on(self):
        """Turn on flux."""

        # Make initial update
        self.flux_force_update()

        if self.is_on:
            return

        self.unsub_tracker = track_time_change(
            self.hass, self.flux_update, second=[0, self._interval])
        if self._init_on_turn_on:
            self.unsub_turn_on_trigger = async_track_state_change(self.hass, 
                self._lights, self.flux_force_update_cb, 'off', 'on')
        else:
            self.unsub_turn_on_trigger = None

        self.schedule_update_ha_state()

    def turn_off(self, **kwargs):
        """Turn off flux."""
        if self.unsub_tracker is not None:
            self.unsub_tracker()
            self.unsub_tracker = None
        if self.unsub_turn_on_trigger is not None:
            self.unsub_turn_on_trigger()
            self.unsub_turn_on_trigger = None

        self.schedule_update_ha_state()


    def flux_force_update(self, call=None, entity=None):
        """Forced update of given or all the lights using flux."""
        now = dt_now()

        if call is None:
            if entity is None:
                entity_id = self._lights
            else:
                entity_id = entity
        else:
            entity_id = call.data.get("entity_id", self._lights)

        _LOGGER.info("Flux forced update for %s",
            entity_id)


        sunset = get_astral_event_date(self.hass, 'sunset', now.date())
        start_time = self.find_start_time(now)
        stop_time = now.replace(
            hour=self._stop_time.hour, minute=self._stop_time.minute,
            second=0)

        if stop_time <= start_time:
            # stop_time does not happen in the same day as start_time
            if start_time < now:
                # stop time is tomorrow
                stop_time += datetime.timedelta(days=1)
        elif now < start_time:
            # stop_time was yesterday since the new start_time is not reached
            stop_time -= datetime.timedelta(days=1)

        if start_time < now < sunset:
            # Daytime
            time_state = 'day'
            temp_range = abs(self._start_colortemp - self._sunset_colortemp)
            day_length = int(sunset.timestamp() - start_time.timestamp())
            seconds_from_start = int(now.timestamp() - start_time.timestamp())
            percentage_complete = seconds_from_start / day_length
            temp_offset = temp_range * percentage_complete
            if self._start_colortemp > self._sunset_colortemp:
                temp = self._start_colortemp - temp_offset
            else:
                temp = self._start_colortemp + temp_offset
        else:
            # Nightime
            time_state = 'night'

            if now < stop_time:
                if stop_time < start_time and stop_time.day == sunset.day:
                    # we need to use yesterday's sunset time
                    sunset_time = sunset - datetime.timedelta(days=1)
                else:
                    sunset_time = sunset

                # pylint: disable=no-member
                night_length = int(stop_time.timestamp() -
                                   sunset_time.timestamp())
                seconds_from_sunset = int(now.timestamp() -
                                          sunset_time.timestamp())
                percentage_complete = seconds_from_sunset / night_length
            else:
                percentage_complete = 1

            temp_range = abs(self._sunset_colortemp - self._stop_colortemp)
            temp_offset = temp_range * percentage_complete
            if self._sunset_colortemp > self._stop_colortemp:
                temp = self._sunset_colortemp - temp_offset
            else:
                temp = self._sunset_colortemp + temp_offset
        rgb = color_temperature_to_rgb(temp)
        x_val, y_val, b_val = color_RGB_to_xy(*rgb)
        brightness = self._brightness if self._brightness else b_val
        
        if self._mode == MODE_XY:
            _LOGGER.debug("Trying to force update of %s to XY %s, %s", entity_id, x_val, y_val)
            force_light_xy(self.hass, entity_id, x_val,
                          y_val, brightness)
            new_color_xy = set_lights_xy(self.hass, self._lights, x_val,
                              y_val, brightness, self._transition, self._last_colortemp)
            _LOGGER.info("Lights updated to x:%s y:%s brightness:%s, %s%% "
                         "of %s cycle complete at %s", x_val, y_val,
                         brightness, round(
                             percentage_complete * 100), time_state, now)
            self._last_colortemp = new_color_xy
        elif self._mode == MODE_RGB:
            force_light_rgb(self.hass, entity_id, rgb)
            new_color_rgb = set_lights_rgb(self.hass, self._lights, rgb, self._transition, self._last_colortemp)
            _LOGGER.info("Lights updated to rgb:%s, %s%% "
                         "of %s cycle complete at %s", rgb,
                         round(percentage_complete * 100), time_state, now)
            self._last_colortemp = new_color_rgb
        else:
            # Convert to mired and clamp to allowed values
            mired = color_temperature_kelvin_to_mired(temp)
            _LOGGER.debug("Trying to force update of %s to mired %s", entity_id, mired)
            force_light_temp(self.hass, entity_id, mired, brightness)
            new_colortemp = set_lights_temp(self.hass, self._lights, mired, brightness,
                            self._transition, self._last_colortemp)
            _LOGGER.info("Lights updated from %s to mired:%s brightness:%s, %s%% "
                         "of %s cycle complete at %s", self._last_colortemp, mired, brightness,
                         round(percentage_complete * 100), time_state, now)
            self._last_colortemp = new_colortemp

    def flux_update(self, now=None):
        """Update all the lights using flux."""
        if now is None:
            now = dt_now()

        sunset = get_astral_event_date(self.hass, 'sunset', now.date())
        start_time = self.find_start_time(now)
        stop_time = now.replace(
            hour=self._stop_time.hour, minute=self._stop_time.minute,
            second=0)

        if stop_time <= start_time:
            # stop_time does not happen in the same day as start_time
            if start_time < now:
                # stop time is tomorrow
                stop_time += datetime.timedelta(days=1)
        elif now < start_time:
            # stop_time was yesterday since the new start_time is not reached
            stop_time -= datetime.timedelta(days=1)

        if start_time < now < sunset:
            # Daytime
            time_state = 'day'
            temp_range = abs(self._start_colortemp - self._sunset_colortemp)
            day_length = int(sunset.timestamp() - start_time.timestamp())
            seconds_from_start = int(now.timestamp() - start_time.timestamp())
            percentage_complete = seconds_from_start / day_length
            temp_offset = temp_range * percentage_complete
            if self._start_colortemp > self._sunset_colortemp:
                temp = self._start_colortemp - temp_offset
            else:
                temp = self._start_colortemp + temp_offset
        else:
            # Nightime
            time_state = 'night'

            if now < stop_time:
                if stop_time < start_time and stop_time.day == sunset.day:
                    # we need to use yesterday's sunset time
                    sunset_time = sunset - datetime.timedelta(days=1)
                else:
                    sunset_time = sunset

                # pylint: disable=no-member
                night_length = int(stop_time.timestamp() -
                                   sunset_time.timestamp())
                seconds_from_sunset = int(now.timestamp() -
                                          sunset_time.timestamp())
                percentage_complete = seconds_from_sunset / night_length
            else:
                percentage_complete = 1

            temp_range = abs(self._sunset_colortemp - self._stop_colortemp)
            temp_offset = temp_range * percentage_complete
            if self._sunset_colortemp > self._stop_colortemp:
                temp = self._sunset_colortemp - temp_offset
            else:
                temp = self._sunset_colortemp + temp_offset
        rgb = color_temperature_to_rgb(temp)
        x_val, y_val, b_val = color_RGB_to_xy(*rgb)
        brightness = self._brightness if self._brightness else b_val
        if self._disable_brightness_adjust:
            brightness = None
        if self._mode == MODE_XY:
            new_color_xy = set_lights_xy(self.hass, self._lights, x_val,
                          y_val, brightness, self._transition, self._last_colortemp)
            _LOGGER.info("Lights updated to x:%s y:%s brightness:%s, %s%% "
                         "of %s cycle complete at %s", x_val, y_val,
                         brightness, round(
                             percentage_complete * 100), time_state, now)
            self._last_colortemp = new_color_xy
        elif self._mode == MODE_RGB:
            new_color_rgb = set_lights_rgb(self.hass, self._lights, rgb, self._transition, self._last_colortemp)
            _LOGGER.info("Lights updated to rgb:%s, %s%% "
                         "of %s cycle complete at %s", rgb,
                         round(percentage_complete * 100), time_state, now)
            self._last_colortemp = new_color_xy
        else:
            # Convert to mired and clamp to allowed values
            mired = color_temperature_kelvin_to_mired(temp)
            new_colortemp = set_lights_temp(self.hass, self._lights, mired, brightness,
                            self._transition, self._last_colortemp)
            _LOGGER.info("Lights updated from %s to mired:%s brightness:%s, %s%% "
                         "of %s cycle complete at %s", self._last_colortemp, mired, brightness,
                         round(percentage_complete * 100), time_state, now)
            self._last_colortemp = new_colortemp

    def find_start_time(self, now):
        """Return sunrise or start_time if given."""
        if self._start_time:
            sunrise = now.replace(
                hour=self._start_time.hour, minute=self._start_time.minute,
                second=0)
        else:
            sunrise = get_astral_event_date(self.hass, 'sunrise', now.date())
        return sunrise


    def flux_force_update_cb(self, entity, old_state, new_state):
        _LOGGER.info("Flux Callback for %s triggered for entity %s",
            self, entity)
        call = None
        self.flux_force_update(call, entity)
