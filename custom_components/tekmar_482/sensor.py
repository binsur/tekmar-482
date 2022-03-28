from homeassistant.components.sensor import (
    STATE_CLASS_MEASUREMENT,
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE, TEMP_CELSIUS
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.components.climate.const import (
    CURRENT_HVAC_IDLE, CURRENT_HVAC_HEAT, CURRENT_HVAC_COOL,
)

from .const import (
    DOMAIN,
    DEVICE_TYPES, DEVICE_FEATURES,
    SETBACK_STATE, SETBACK_DESCRIPTION,
    THA_NA_8, THA_NA_16, NETWORK_ERRORS, 
    THA_TYPE_THERMOSTAT, THA_TYPE_SETPOINT,
)

def regBytes(integer):
    return divmod(integer, 0x100)

def degCtoF(degC):
    """ convert Celcius to degF """
    return ((degC * 9/5) + 32)

def degEtoC(degE):
    """ convert degE to degC """
    #degE = 2*(degC)
    return (degE / 2)

def degHtoF(degH):
    """ convert degH to degF """
    #degH = 10*(degF) + 850
    return ((degH - 850) / 10)

def degFtoC(degF):
    """ convert degF to degC """
    #degC = (degF - 32) / 1.8
    return ((degF - 32) / 1.8)
    
def degHtoC(degH):
    return degFtoC(degHtoF(degH))

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:

    hub = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []

    for gateway in hub.tha_gateway:
        entities.append(OutdoorTemprature(gateway, config_entry))
        entities.append(NetworkError(gateway, config_entry))
        entities.append(LastPing(gateway, config_entry))

    for device in hub.tha_devices:
        
        if DEVICE_TYPES[device.tha_device['type']] == THA_TYPE_THERMOSTAT:
            entities.append(CurrentTemperature(device, config_entry))
            entities.append(SetbackState(device, config_entry))
        
            if (
                DEVICE_FEATURES[device.tha_device['type']]['humid'] and
                hub.tha_pr_ver in [2,3]
            ):
                entities.append(RelativeHumidity(device, config_entry))
            
            if (
                device.tha_device['attributes'].Slab_Setpoint and
                hub.tha_pr_ver in [3]
            ):
                entities.append(CurrentFloorTemperature(device, config_entry))
                
        if DEVICE_TYPES[device.tha_device['type']] == THA_TYPE_SETPOINT:
            entities.append(CurrentTemperature(device, config_entry))
            #entities.append(CurrentFloorTemperature(device, config_entry))
            entities.append(SetbackState(device, config_entry))
            entities.append(SetpointTarget(device, config_entry))
            entities.append(SetpointDemand(device, config_entry))


    if entities:
        async_add_entities(entities)


class ThaSensorBase(SensorEntity):

    should_poll = False

    def __init__(self, tekmar_tha, config_entry):
        """Initialize the sensor."""
        self._tekmar_tha = tekmar_tha
        self._config_entry = config_entry

    # To link this entity to the cover device, this property must return an
    # identifiers value matching that used in the cover, but no other information such
    # as name. If name is returned, this entity will then also become a device in the
    # HA UI.
    @property
    def device_info(self):
        """Return information to link this entity with the correct device."""
        return self._tekmar_tha.device_info

    # This property is important to let HA know if this entity is online or not.
    # If an entity is offline (return False), the UI will refelect this.
    @property
    def available(self) -> bool:
        return self._tekmar_tha.online and self._tekmar_tha.hub.online

    @property
    def config_entry_id(self):
        return self._config_entry.entry_id

    @property
    def config_entry_name(self):
        return self._config_entry.data['name']

    async def async_added_to_hass(self):
        """Run when this Entity has been added to HA."""
        # Sensors should also register callbacks to HA when their state changes
        self._tekmar_tha.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self):
        """Entity being removed from hass."""
        # The opposite of async_added_to_hass. Remove any registered call backs here.
        self._tekmar_tha.remove_callback(self.async_write_ha_state)

class OutdoorTemprature(ThaSensorBase):
    """Representation of a Sensor."""
    device_class = SensorDeviceClass.TEMPERATURE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, tekmar_tha, config_entry):
        """Initialize the sensor."""
        super().__init__(tekmar_tha, config_entry)

        self._attr_unique_id = f"{self.config_entry_id}-outdoor-temperature"
        self._attr_name = f"{self.config_entry_name.capitalize()} Outdoor Temperature"

    @property
    def available(self) -> bool:
        if self._tekmar_tha.outdoor_temprature == THA_NA_16:
            return False
        else:
            return True

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if (
            self._tekmar_tha.outdoor_temprature == THA_NA_16 or
            self._tekmar_tha.outdoor_temprature == None
        ):
            return None

        else:
            try:
                temp = degHtoC(self._tekmar_tha.outdoor_temprature) # degH need degC
                return round(temp, 1)

            except TypeError:
                return None

class LastPing(ThaSensorBase):
    """Representation of a Sensor."""
    entity_category = EntityCategory.DIAGNOSTIC
    device_class = SensorDeviceClass.TIMESTAMP
    icon = 'mdi:heart-pulse'

    def __init__(self, tekmar_tha, config_entry):
        """Initialize the sensor."""
        super().__init__(tekmar_tha, config_entry)

        self._attr_unique_id = f"{self.config_entry_id}-last-ping"
        self._attr_name = f"{self.config_entry_name.capitalize()} Last Ping"

    @property
    def available(self) -> bool:
        if self._tekmar_tha.last_ping == None:
            return False
        else:
            return True

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self._tekmar_tha.last_ping == None:
            return None
        else:
            return self._tekmar_tha.last_ping

class NetworkError(ThaSensorBase):
    entity_category = EntityCategory.DIAGNOSTIC
    icon = 'mdi:alert-outline'

    def __init__(self, tekmar_tha, config_entry):
        super().__init__(tekmar_tha, config_entry)

        self._attr_unique_id = f"{self.config_entry_id}-network-error"
        self._attr_name = f"{self.config_entry_name.capitalize()} Network Error"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return hex(self._tekmar_tha.network_error)

    @property
    def extra_state_attributes(self):
        err_high, err_low = regBytes(self._tekmar_tha.network_error)
        try:
            if err_low != 0x00:
                if err_low in [0x80, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x8B, 0x8C, 0x8D, 0x8E, 0x8F, 0x90, 0x91, 0x92, 0x93, 0x94]:
                    if err_high & 0x20 != 0:
                        sen_err = "open"
                    else:
                        sen_err = "short"
                    
                    if err_low in [0x90, 0x92, 0x93, 0x94]:
                        ag_id = err_high & 0x0F
                        return {"description": f"{NETWORK_ERRORS[err_low]} {sen_err} {ag_id}"}
                    else:
                        return {"description": f"{NETWORK_ERRORS[err_low]} {sen_err}"}
                
                elif err_low in [0x04]:
                    device_id = err_high & 0x1F
                    return {"description": f"{NETWORK_ERRORS[err_low]}: device {device_id}"}
                
                else:
                    return {"description": f"{NETWORK_ERRORS[err_low]}"}
            
            else:
                return {"description": f"{NETWORK_ERRORS[err_low]}"}
        
        except KeyError:
            return {"description": "Unknown Error"}

class CurrentTemperature(ThaSensorBase):
    """Representation of a Sensor."""
    device_class = SensorDeviceClass.TEMPERATURE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, tekmar_tha, config_entry):
        """Initialize the sensor."""
        super().__init__(tekmar_tha, config_entry)
        
        self._attr_unique_id = f"{self.config_entry_id}-{self._tekmar_tha.model}-{self._tekmar_tha.device_id}-current-temperature"
        self._attr_name = f"{self._tekmar_tha.tha_full_device_name} Current Temperature"

    @property
    def available(self) -> bool:
        if self._tekmar_tha.current_temperature == THA_NA_16:
            return False
        elif self._tekmar_tha.current_temperature == 0x00:
            return False
        else:
            return True

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if (
            self._tekmar_tha.current_temperature == THA_NA_16 or
            self._tekmar_tha.current_temperature == None
        ):
            return None

        else:
            try:
                temp = degHtoC(self._tekmar_tha.current_temperature)
                return round(temp, 1)

            except TypeError:
                return None

class CurrentFloorTemperature(ThaSensorBase):
    """Representation of a Sensor."""
    device_class = SensorDeviceClass.TEMPERATURE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, tekmar_tha, config_entry):
        """Initialize the sensor."""
        super().__init__(tekmar_tha, config_entry)
        
        self._attr_unique_id = f"{self.config_entry_id}-{self._tekmar_tha.model}-{self._tekmar_tha.device_id}-current-floor-temperature"
        self._attr_name = f"{self._tekmar_tha.tha_full_device_name} Current Floor Temperature"

    @property
    def available(self) -> bool:
        if (
            self._tekmar_tha.current_floor_temperature == THA_NA_16 or
            self._tekmar_tha.current_floor_temperature == 0x00
        ):
            return False
        else:
            return True

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if (
            self._tekmar_tha.current_floor_temperature == THA_NA_16 or
            self._tekmar_tha.current_floor_temperature == None
        ):
            return None

        else:
            try:
                temp = degHtoC(self._tekmar_tha.current_floor_temperature)
                return round(temp, 1)

            except TypeError:
                return None

class RelativeHumidity(ThaSensorBase):
    """Representation of a Sensor."""
    device_class = SensorDeviceClass.HUMIDITY
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = PERCENTAGE

    def __init__(self, tekmar_tha, config_entry):
        """Initialize the sensor."""
        super().__init__(tekmar_tha, config_entry)
        
        self._attr_unique_id = f"{self.config_entry_id}-{self._tekmar_tha.model}-{self._tekmar_tha.device_id}-relative-humidity"
        self._attr_name = f"{self._tekmar_tha.tha_full_device_name} Relative Humidity"

    @property
    def available(self) -> bool:
        if self._tekmar_tha.relative_humidity == THA_NA_8:
            return False
        else:
            return True

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if (
            self._tekmar_tha.relative_humidity == THA_NA_8 or
            self._tekmar_tha.relative_humidity == None
        ):
            return None

        else:
            return self._tekmar_tha.relative_humidity

class SetbackState(ThaSensorBase):
    """Representation of a Sensor."""
    icon = 'mdi:format-list-bulleted'

    def __init__(self, tekmar_tha, config_entry):
        """Initialize the sensor."""
        super().__init__(tekmar_tha, config_entry)
        
        self._attr_unique_id = f"{self.config_entry_id}-{self._tekmar_tha.model}-{self._tekmar_tha.device_id}-setback-state"
        self._attr_name = f"{self._tekmar_tha.tha_full_device_name} Setback State"

    @property
    def available(self) -> bool:
        if (
            self._tekmar_tha.setback_state == THA_NA_8 or
            self._tekmar_tha.setback_enable == 0x00
        ):
            return False

        else:
            return True

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self._tekmar_tha.setback_state == THA_NA_8:
            return None
            
        try:
            return SETBACK_STATE[self._tekmar_tha.setback_state]
        except KeyError:
            return None

    @property
    def extra_state_attributes(self):
        try:
            return {"description": SETBACK_DESCRIPTION[self._tekmar_tha.setback_state]}
        except KeyError:
            return None
            
class SetpointTarget(ThaSensorBase):
    """Representation of a Sensor."""
    device_class = SensorDeviceClass.TEMPERATURE
    state_class = STATE_CLASS_MEASUREMENT
    native_unit_of_measurement = TEMP_CELSIUS

    def __init__(self, tekmar_tha, config_entry):
        """Initialize the sensor."""
        super().__init__(tekmar_tha, config_entry)
        
        self._attr_unique_id = f"{self.config_entry_id}-{self._tekmar_tha.model}-{self._tekmar_tha.device_id}-setpoint-target"
        self._attr_name = f"{self._tekmar_tha.tha_full_device_name} Setpoint Target"

    @property
    def available(self) -> bool:
        if (
            self._tekmar_tha.setpoint_target == THA_NA_16 or
            self._tekmar_tha.setpoint_target == 0x00
        ):
            return False
        else:
            return True

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if (
            self._tekmar_tha.setpoint_target == THA_NA_16 or
            self._tekmar_tha.setpoint_target == None or
            self._tekmar_tha.setpoint_target == 0x00
        ):
            return None

        else:
            try:
                temp = degHtoC(self._tekmar_tha.setpoint_target)
                return round(temp, 1)

            except TypeError:
                return None

class SetpointDemand(ThaSensorBase):

    """Representation of a Sensor."""
    icon = 'mdi:format-list-bulleted'

    def __init__(self, tekmar_tha, config_entry):
        """Initialize the sensor."""
        super().__init__(tekmar_tha, config_entry)
        
        self._attr_unique_id = f"{self.config_entry_id}-{self._tekmar_tha.model}-{self._tekmar_tha.device_id}-active-demand"
        self._attr_name = f"{self._tekmar_tha.tha_full_device_name} Active Demand"

    @property
    def available(self) -> bool:
        if self._tekmar_tha.active_demand == THA_NA_8:
            return False
        else:
            return True

    @property
    def native_value(self):
        if self._tekmar_tha.active_demand == 0x00:
            return CURRENT_HVAC_IDLE
            
        elif self._tekmar_tha.active_demand == 0x01:
            return CURRENT_HVAC_HEAT
        
        elif self._tekmar_tha.active_demand == 0x03:
            return CURRENT_HVAC_COOL
            
        else:
            return None

    #@property
    #def extra_state_attributes(self):
        #try:
        #    return {"description": SETBACK_DESCRIPTION[self._tekmar_tha.setback_state]}
        #except KeyError:
        #    return None
