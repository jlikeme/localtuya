"""Test for localtuya."""

from . import *
import copy
from custom_components.localtuya.climate import (
    ClimateEntityFeature,
    FAN_SPEEDS_DEFAULT,
    LocalTuyaClimate,
    HVACAction,
    HVACMode,
    DOMAIN as PLATFORM_DOMAIN,
    flow_schema,
)

FAN_SPEED_LIST = ["auto", "low", "middle", "high"]
FAN_SPEED_DICT = {"1": "Silent", "2": "Low", "3": "Middle", "4": "High"}
ENTITY_CONFIG = {
    "friendly_name": "Terrace Floor",
    "entity_category": "None",
    "target_temperature_dp": "16",
    "current_temperature_dp": "24",
    "temperature_step": "1",
    "min_temperature": 7.0,
    "max_temperature": 35.0,
    "precision": "1",
    "target_precision": "1",
    "hvac_mode_dp": "2",
    "hvac_mode_set": {
        "auto": "program",
        "heat": "manual",
        "cool": "COLD",
    },
    "hvac_action_dp": "100",
    "hvac_action_set": {
        "heating": True,
        "idle": False,
    },
    "preset_dp": "5",
    "preset_set": {"holiday": "Holiday Friendly Name"},
    "fan_speed_dp": "6",
    "fan_speed_list": ",".join(FAN_SPEED_LIST),
    "swing_mode_dp": "11",
    "swing_modes": {
        "both": "up-and-down",
        "up": "up-only",
        "down": "down-only",
    },
    "swing_horizontal_dp": "12",
    "swing_horizontal_modes": {
        "both": "left-and-right",
        "left": "left-only",
        "right": "right-only",
    },
    "temperature_unit": "fahrenheit/celsius",
    "id": "1",
    "eco_dp": "101",
    "eco_value": "eco_on",
    "platform": "climate",
    "icon": "",
    "heuristic_action": False,
}
CONFIG = {
    DEVICE_NAME: {
        **DEVICE_CONFIG,
        "entities": [
            ENTITY_CONFIG,
            {**ENTITY_CONFIG, "id": "2", "fan_speed_list": FAN_SPEED_DICT},
        ],
    }
}

DPS_STATUS = {
    "1": True,
    "2": "COLD",
    "5": "holiday",
    "6": "middle",
    "11": "both",
    "12": "right",
    "16": 68,  # F
    "24": 24,  # c
    "100": False,
    "101": "ECO_NOT",
}


async def test_climate():
    device = await init(CONFIG, PLATFORM_DOMAIN, LocalTuyaClimate)
    entities: list[LocalTuyaClimate] = get_entites(device)

    assert len(entities) > 0
    entity_1, entity_2, *_ = entities
    assert type(entity_1) is LocalTuyaClimate

    assert entity_1._is_on == None

    status = {**DPS_STATUS, **{"1": False}}
    device.status_updated(status)
    assert type(entity_1._state_on) is bool

    assert entity_1._is_on == False
    assert entity_1.hvac_action == HVACAction.OFF
    assert entity_1.hvac_mode == HVACMode.OFF

    device.status_updated(DPS_STATUS)
    assert entity_1._is_on == True
    assert entity_1.hvac_action == HVACAction.IDLE
    assert entity_1.hvac_mode == HVACMode.COOL
    assert entity_1.fan_modes == FAN_SPEED_LIST
    assert entity_2.fan_modes == list(FAN_SPEED_DICT.values())
    assert entity_1.preset_mode == "Holiday Friendly Name"
    assert entity_1.current_temperature == 24
    assert entity_1.target_temperature == 20  # f to c
    assert entity_1.fan_mode == "middle"

    # Eco Preset
    device.status_updated({**DPS_STATUS, **{"101": "eco_on"}})
    assert entity_1.preset_mode == "eco"

    # heuristic_action
    entity_1._hvac_action_dp = None
    status = {**DPS_STATUS, **{"2": "manual", "24": 18.9}}
    device.status_updated(status)
    assert entity_1.hvac_action == HVACAction.HEATING
    status = {**DPS_STATUS, **{"2": "manual", "24": 21.1}}
    device.status_updated(status)
    assert entity_1.hvac_action == HVACAction.IDLE

    # String DP ID
    status = {**DPS_STATUS, **{"1": "OFF"}}
    device.status_updated(status)
    assert not entity_1._is_on
    assert type(entity_1._state_on) is str

    # Integer DP ID
    status = {**DPS_STATUS, **{"1": 1}}
    device.status_updated(status)
    assert entity_1._is_on
    assert type(entity_1._state_on) is int

    # Swing modes
    assert entity_1.swing_mode == "up-and-down"
    assert entity_1.swing_horizontal_mode == "right-only"
    device.status_updated({**DPS_STATUS, **{"11": "up", "12": "both"}})
    assert entity_1.swing_mode == "up-only"
    assert entity_1.swing_horizontal_mode == "left-and-right"


@pytest.mark.parametrize(
    ("fan_config", "expected_modes", "device_value", "fan_mode"),
    [
        (
            {"fan_speed_list": "auto, low, middle, high"},
            FAN_SPEED_LIST,
            "middle",
            "middle",
        ),
        (
            {"fan_speed_list": FAN_SPEED_DICT},
            list(FAN_SPEED_DICT.values()),
            "3",
            "Middle",
        ),
        (
            {"fan_speed_set": {"Auto": "auto", "Medium": "middle"}},
            ["auto", "medium"],
            "middle",
            "medium",
        ),
        (
            {"fan_speed_list": FAN_SPEED_DICT, "fan_speed_set": {"Medium": "middle"}},
            ["medium"],
            "middle",
            "medium",
        ),
        (
            {"fan_speed_list": FAN_SPEED_DICT, "fan_speed_set": {}},
            list(FAN_SPEED_DICT.values()),
            "3",
            "Middle",
        ),
        ({"fan_speed_list": {0: "Auto", 1: "Low"}}, ["Auto", "Low"], 0, "Auto"),
        ({"fan_speed_set": {"Auto": 0, "Low": 1}}, ["auto", "low"], 0, "auto"),
    ],
)
async def test_fan_speed_mapping(fan_config, expected_modes, device_value, fan_mode):
    """Both mapping directions and legacy lists round-trip through the device DP."""
    entity_config = copy.deepcopy(ENTITY_CONFIG)
    entity_config.pop("fan_speed_list")
    entity_config.update(fan_config)
    original_config = copy.deepcopy(entity_config)
    device = Mock(set_dp=AsyncMock())
    climate = LocalTuyaClimate(
        device, {**DEVICE_CONFIG, "entities": [entity_config]}, "1"
    )

    assert climate.fan_modes == expected_modes
    assert climate.supported_features & ClimateEntityFeature.FAN_MODE
    assert climate.fan_mode is None
    assert entity_config == original_config

    climate._status = {**DPS_STATUS, "6": device_value}
    climate.status_updated()
    assert climate.fan_mode == fan_mode
    await climate.async_set_fan_mode(fan_mode)
    device.set_dp.assert_awaited_once_with(device_value, "6")

    # Changing speed while off must still turn the device on first.
    climate._status["1"] = False
    climate.status_updated()
    device.set_dp.reset_mock()
    await climate.async_set_fan_mode(fan_mode)
    assert [call.args for call in device.set_dp.await_args_list] == [
        (True, "1"),
        (device_value, "6"),
    ]

    # Unknown or unavailable values must not retain the previous fan mode.
    climate._status["6"] = "unknown"
    climate.status_updated()
    assert climate.fan_mode is None
    climate._status.pop("6")
    climate.status_updated()
    assert climate.fan_mode is None


@pytest.mark.parametrize(
    "fan_config",
    [
        {},
        {"fan_speed_list": ""},
        {"fan_speed_list": {}, "fan_speed_set": {}},
        {"fan_speed_list": FAN_SPEED_DICT, "fan_speed_dp": None},
    ],
)
def test_fan_mode_requires_dp_and_speeds(fan_config):
    """A fan DP and a nonempty mapping are both required for fan control."""
    entity_config = copy.deepcopy(ENTITY_CONFIG)
    entity_config.pop("fan_speed_list")
    entity_config.update(fan_config)
    climate = LocalTuyaClimate(
        Mock(), {**DEVICE_CONFIG, "entities": [entity_config]}, "1"
    )
    assert not climate.supported_features & ClimateEntityFeature.FAN_MODE


def test_fan_schema_defaults():
    """The legacy mapping must not override the upstream mapping by default."""
    schema = {field.schema: field for field in flow_schema([])}
    assert schema["fan_speed_list"].default() == FAN_SPEEDS_DEFAULT
    assert schema["fan_speed_set"].default() == {}
