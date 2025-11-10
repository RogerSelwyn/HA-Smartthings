"""Support for media players through the SmartThings cloud API."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util
from pysmartthings import (
    Attribute,
    Capability,
    Category,
    Command,
    DeviceEvent,
    SmartThings,
)

from . import FullDevice, SmartThingsConfigEntry
from .const import MAIN
from .entity import SmartThingsEntity


class SourceType(StrEnum):
    """ "Source type."""

    EXTERNAL = "external"
    APP = "app"
    TV = "tv"
    NONE = "none"


STD_APP_LIST = {
    "org.tizen.browser": "Tizen Browser",
    "org.tizen.netflix-app": "Netflix",
    "9Ur5IzDKqV.TizenYouTube": "YouTube",
    "MCmYXNxgcu.DisneyPlus": "Disney+",
    "4ovn894vo9.Facebook": "Facebook",
    "yu1NM3vHsU.DAZN": "DAZN",
    "rJeHak5zRg.Spotify": "Spotify",
    "kIciSQlYEM.plex": "Plex",
    "org.tizen.primevideo": "Prime",
    "DqEoaplKlw.bbchybrid": "BBC iPlayer",
    "OEvCiupaFR.ITVHub": "ITV Hub",
    "com.samsung.tv.ariavideo": "Apple TV",
    "vbUQClczfR.Wuakitv": "Rakuten TV",
    "pIaMf8YZyZ.whiteLabelTal": "Discovery+",
    "AQKO41xyKP.AmazonAlexa": "Alexa",
    "OCaxbgg9v6.chfourctv": "All 4",
    "EkzyZtmneG.My5": "My5",
    "com.samsung.tv.samsunghealth": "Samsung Health",
    "com.samsung.tv.iotdashboard": "SmartThings",
    "GR7TWEBh5d.BBCSounds": "BBC Sounds",
    "org.tizen.apple.applemusic": "Apple Music",
    "1Qb6IoAcGC.NowTV": "NOW",
    "com.samsung.tv.gallery": "Gallery",
    "X1pKpFCiUu.PlutoTV": "Pluto TV",
    "yL49PNFmjW.PromotionApp": "Samsung Promotion",
    "EJZZ9Mr6D2.emanual": "eManual",
    "gz3DMB1OMy.DCHTVlive": "Digital Concert Hall",
    "AkhP5nCr24.GoogleAssistant": "Explore Google Assistant",
    "VQr0RGkyS9.UKTVPlay": "UKTV Play",
    "FHl9B04ug2.ITV": "BritBox",
    "9FhM0cODbY.TikTokTV": "TikTok",
    "com.samsung.tv.csfs": "Smart TV",
    "com.samsung.tv.searchall": "Smart TV Search",
    "org.tizen.epg": "Tizen EPG",
}

MEDIA_PLAYER_CAPABILITIES = (
    Capability.AUDIO_MUTE,
    Capability.AUDIO_VOLUME,
)

CONTROLLABLE_SOURCES = ["bluetooth", "wifi"]

DEVICE_CLASS_MAP: dict[Category | str, MediaPlayerDeviceClass] = {
    Category.NETWORK_AUDIO: MediaPlayerDeviceClass.SPEAKER,
    Category.SPEAKER: MediaPlayerDeviceClass.SPEAKER,
    Category.TELEVISION: MediaPlayerDeviceClass.TV,
    Category.RECEIVER: MediaPlayerDeviceClass.RECEIVER,
}

VALUE_TO_STATE = {
    "buffering": MediaPlayerState.BUFFERING,
    "paused": MediaPlayerState.PAUSED,
    "playing": MediaPlayerState.PLAYING,
    "stopped": MediaPlayerState.IDLE,
    "fast forwarding": MediaPlayerState.BUFFERING,
    "rewinding": MediaPlayerState.BUFFERING,
}

REPEAT_MODE_TO_HA = {
    "all": RepeatMode.ALL,
    "one": RepeatMode.ONE,
    "off": RepeatMode.OFF,
}

HA_REPEAT_MODE_TO_SMARTTHINGS = {v: k for k, v in REPEAT_MODE_TO_HA.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartThingsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add media players for a config entry."""
    entry_data = entry.runtime_data

    async_add_entities(
        SmartThingsMediaPlayer(entry_data.client, device)
        for device in entry_data.devices.values()
        if all(
            capability in device.status[MAIN]
            for capability in MEDIA_PLAYER_CAPABILITIES
        )
    )


class SmartThingsMediaPlayer(SmartThingsEntity, MediaPlayerEntity):
    """Define a SmartThings media player."""

    _attr_name = None

    def __init__(self, client: SmartThings, device: FullDevice) -> None:
        """Initialize the media_player class."""
        super().__init__(
            client,
            device,
            {
                Capability.AUDIO_MUTE,
                Capability.AUDIO_TRACK_DATA,
                Capability.AUDIO_VOLUME,
                Capability.MEDIA_INPUT_SOURCE,
                Capability.MEDIA_PLAYBACK,
                Capability.MEDIA_PLAYBACK_REPEAT,
                Capability.MEDIA_PLAYBACK_SHUFFLE,
                Capability.SAMSUNG_VD_AUDIO_INPUT_SOURCE,
                Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE,
                Capability.SWITCH,
                Capability.TV_CHANNEL,
            },
        )
        self._attr_supported_features = self._determine_features()
        self._attr_device_class = DEVICE_CLASS_MAP.get(
            device.device.components[MAIN].user_category
            or device.device.components[MAIN].manufacturer_category,
        )
        self._media_content_type = None
        self._samsung_source_type = self._source_type_initial()

    def _determine_features(self) -> MediaPlayerEntityFeature:
        flags = (
            MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.VOLUME_STEP
            | MediaPlayerEntityFeature.VOLUME_MUTE
        )
        if self.supports_capability(Capability.MEDIA_PLAYBACK):
            playback_commands = self.get_attribute_value(
                Capability.MEDIA_PLAYBACK, Attribute.SUPPORTED_PLAYBACK_COMMANDS
            )
            if "play" in playback_commands:
                flags |= MediaPlayerEntityFeature.PLAY
            if "pause" in playback_commands:
                flags |= MediaPlayerEntityFeature.PAUSE
            if "stop" in playback_commands:
                flags |= MediaPlayerEntityFeature.STOP
            if "rewind" in playback_commands:
                flags |= MediaPlayerEntityFeature.PREVIOUS_TRACK
            if "fastForward" in playback_commands:
                flags |= MediaPlayerEntityFeature.NEXT_TRACK
        if self.supports_capability(Capability.SWITCH):
            flags |= (
                MediaPlayerEntityFeature.TURN_ON | MediaPlayerEntityFeature.TURN_OFF
            )
        if self.supports_capability(Capability.MEDIA_INPUT_SOURCE):
            flags |= MediaPlayerEntityFeature.SELECT_SOURCE
        if self.supports_capability(Capability.MEDIA_PLAYBACK_SHUFFLE):
            flags |= MediaPlayerEntityFeature.SHUFFLE_SET
        if self.supports_capability(Capability.MEDIA_PLAYBACK_REPEAT):
            flags |= MediaPlayerEntityFeature.REPEAT_SET
        return flags

    def _update_handler(self, event: DeviceEvent) -> None:
        self._internal_state[event.capability][event.attribute].value = event.value
        self._internal_state[event.capability][event.attribute].data = event.data
        self._internal_state[event.capability][
            event.attribute
        ].timestamp = dt_util.now()
        self._samsung_source_type = self._source_type_update(event)
        self._handle_update()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the media player off."""
        await self.execute_device_command(
            Capability.SWITCH,
            Command.OFF,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the media player on."""
        await self.execute_device_command(
            Capability.SWITCH,
            Command.ON,
        )

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute volume."""
        await self.execute_device_command(
            Capability.AUDIO_MUTE,
            Command.SET_MUTE,
            argument="muted" if mute else "unmuted",
        )

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level."""
        await self.execute_device_command(
            Capability.AUDIO_VOLUME,
            Command.SET_VOLUME,
            argument=int(volume * 100),
        )

    async def async_volume_up(self) -> None:
        """Increase volume."""
        await self.execute_device_command(
            Capability.AUDIO_VOLUME,
            Command.VOLUME_UP,
        )

    async def async_volume_down(self) -> None:
        """Decrease volume."""
        await self.execute_device_command(
            Capability.AUDIO_VOLUME,
            Command.VOLUME_DOWN,
        )

    async def async_media_play(self) -> None:
        """Play media."""
        await self.execute_device_command(
            Capability.MEDIA_PLAYBACK,
            Command.PLAY,
        )

    async def async_media_pause(self) -> None:
        """Pause media."""
        await self.execute_device_command(
            Capability.MEDIA_PLAYBACK,
            Command.PAUSE,
        )

    async def async_media_stop(self) -> None:
        """Stop media."""
        await self.execute_device_command(
            Capability.MEDIA_PLAYBACK,
            Command.STOP,
        )

    async def async_media_previous_track(self) -> None:
        """Previous track."""
        await self.execute_device_command(
            Capability.MEDIA_PLAYBACK,
            Command.REWIND,
        )

    async def async_media_next_track(self) -> None:
        """Next track."""
        await self.execute_device_command(
            Capability.MEDIA_PLAYBACK,
            Command.FAST_FORWARD,
        )

    async def async_select_source(self, source: str) -> None:
        """Select source."""

        if self.supports_capability(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE):
            sources = self.get_attribute_value(
                Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE,
                Attribute.SUPPORTED_INPUT_SOURCES_MAP,
            )
            for item in sources:
                if item["name"] == source:
                    source = item["id"]

        if source == "dtv":
            source = "digitalTv"

        await self.execute_device_command(
            Capability.MEDIA_INPUT_SOURCE,
            Command.SET_INPUT_SOURCE,
            argument=source,
        )

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Set shuffle mode."""
        await self.execute_device_command(
            Capability.MEDIA_PLAYBACK_SHUFFLE,
            Command.SET_PLAYBACK_SHUFFLE,
            argument="enabled" if shuffle else "disabled",
        )

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set repeat mode."""
        await self.execute_device_command(
            Capability.MEDIA_PLAYBACK_REPEAT,
            Command.SET_PLAYBACK_REPEAT_MODE,
            argument=HA_REPEAT_MODE_TO_SMARTTHINGS[repeat],
        )

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        if (
            not self.supports_capability(Capability.AUDIO_TRACK_DATA)
            or (
                track_data := self.get_attribute_value(
                    Capability.AUDIO_TRACK_DATA, Attribute.AUDIO_TRACK_DATA
                )
            )
            is None
        ):
            return None
        return track_data.get("title", None)

    @property
    def media_channel(self) -> str | None:
        """Channel of current playing media."""
        if self._samsung_source_type in [SourceType.APP, SourceType.TV]:
            channel_name = self.get_attribute_value(
                Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME
            )
            return STD_APP_LIST.get(channel_name, channel_name)

        return None

    @property
    def app_id(self) -> str | None:
        """app id of current playing media."""
        # print(
        #     f"app_id - is_app:{self._samsung_source_type} - Channel Name:{self.get_attribute_value(Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME)} - {self.get_attribute_timestamp(Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME)}"
        # )
        if self._samsung_source_type == SourceType.APP:
            return self.get_attribute_value(
                Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME
            )

        return None

    @property
    def app_name(self) -> str | None:
        """app name of current playing media."""
        if self._samsung_source_type == SourceType.APP:
            channel_name = self.get_attribute_value(
                Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME
            )
            return STD_APP_LIST.get(channel_name, channel_name)

        return None

    @property
    def media_content_type(self) -> str | None:
        """app id of current playing media."""
        # print(f"media_content_type - is_app:{self._samsung_source_type}")
        if self.supports_capability(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE):
            return self._media_content_type

        return None

    @property
    def media_artist(self) -> str | None:
        """Artist of current playing media."""
        if (
            not self.supports_capability(Capability.AUDIO_TRACK_DATA)
            or (
                track_data := self.get_attribute_value(
                    Capability.AUDIO_TRACK_DATA, Attribute.AUDIO_TRACK_DATA
                )
            )
            is None
        ):
            return None
        return track_data.get("artist")

    @property
    def state(self) -> MediaPlayerState | None:
        """State of the media player."""
        if self.supports_capability(Capability.SWITCH):
            if not self.supports_capability(Capability.MEDIA_PLAYBACK):
                if (
                    self.get_attribute_value(Capability.SWITCH, Attribute.SWITCH)
                    == "on"
                ):
                    return MediaPlayerState.ON
                return MediaPlayerState.OFF
            if self.get_attribute_value(Capability.SWITCH, Attribute.SWITCH) == "on":
                if (
                    self.source is not None
                    and self.source in CONTROLLABLE_SOURCES
                    and self.get_attribute_value(
                        Capability.MEDIA_PLAYBACK, Attribute.PLAYBACK_STATUS
                    )
                    in VALUE_TO_STATE
                ):
                    return VALUE_TO_STATE[
                        self.get_attribute_value(
                            Capability.MEDIA_PLAYBACK, Attribute.PLAYBACK_STATUS
                        )
                    ]
                return MediaPlayerState.ON
            return MediaPlayerState.OFF
        return VALUE_TO_STATE[
            self.get_attribute_value(
                Capability.MEDIA_PLAYBACK, Attribute.PLAYBACK_STATUS
            )
        ]

    @property
    def is_volume_muted(self) -> bool:
        """Returns if the volume is muted."""
        return (
            self.get_attribute_value(Capability.AUDIO_MUTE, Attribute.MUTE) == "muted"
        )

    @property
    def volume_level(self) -> float:
        """Volume level."""
        return self.get_attribute_value(Capability.AUDIO_VOLUME, Attribute.VOLUME) / 100

    @property
    def source(self) -> str | None:
        """Input source."""
        if self.supports_capability(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE):
            source = self.get_attribute_value(
                Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE
            )

            sources = self.get_attribute_value(
                Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE,
                Attribute.SUPPORTED_INPUT_SOURCES_MAP,
            )
            for item in sources:
                if item["id"] == source:
                    return item["name"]
            return source

        if self.supports_capability(Capability.MEDIA_INPUT_SOURCE):
            return self.get_attribute_value(
                Capability.MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE
            )
        if self.supports_capability(Capability.SAMSUNG_VD_AUDIO_INPUT_SOURCE):
            return self.get_attribute_value(
                Capability.SAMSUNG_VD_AUDIO_INPUT_SOURCE, Attribute.INPUT_SOURCE
            )
        return None

    @property
    def source_list(self) -> list[str] | None:
        """List of input sources."""
        if self.supports_capability(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE):
            sources = self.get_attribute_value(
                Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE,
                Attribute.SUPPORTED_INPUT_SOURCES_MAP,
            )
            return [item["name"] for item in sources]

        if self.supports_capability(Capability.MEDIA_INPUT_SOURCE):
            return self.get_attribute_value(
                Capability.MEDIA_INPUT_SOURCE, Attribute.SUPPORTED_INPUT_SOURCES
            )
        if self.supports_capability(Capability.SAMSUNG_VD_AUDIO_INPUT_SOURCE):
            return self.get_attribute_value(
                Capability.SAMSUNG_VD_AUDIO_INPUT_SOURCE,
                Attribute.SUPPORTED_INPUT_SOURCES,
            )
        return None

    @property
    def shuffle(self) -> bool | None:
        """Returns if shuffle mode is set."""
        if self.supports_capability(Capability.MEDIA_PLAYBACK_SHUFFLE):
            return (
                self.get_attribute_value(
                    Capability.MEDIA_PLAYBACK_SHUFFLE, Attribute.PLAYBACK_SHUFFLE
                )
                == "enabled"
            )
        return None

    @property
    def repeat(self) -> RepeatMode | None:
        """Returns if repeat mode is set."""
        if self.supports_capability(Capability.MEDIA_PLAYBACK_REPEAT):
            return REPEAT_MODE_TO_HA[
                self.get_attribute_value(
                    Capability.MEDIA_PLAYBACK_REPEAT, Attribute.PLAYBACK_REPEAT_MODE
                )
            ]
        return None

    def _source_type_initial(self):
        # print(
        #     f"Switch:{self.get_attribute_value(Capability.SWITCH, Attribute.SWITCH)} - {self.get_attribute_timestamp(Capability.SWITCH, Attribute.SWITCH)}"
        # )
        # print(
        #     f"Samsung Source:{self.get_attribute_value(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE)} - {self.get_attribute_timestamp(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE)}"
        # )
        # print(
        #     f"Channel Name:{self.get_attribute_value(Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME)} - {self.get_attribute_timestamp(Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME)}"
        # )
        # print(
        #     f"Channel:{self.get_attribute_value(Capability.TV_CHANNEL, Attribute.TV_CHANNEL)} - {self.get_attribute_timestamp(Capability.TV_CHANNEL, Attribute.TV_CHANNEL)}"
        # )

        if not self.supports_capability(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE):
            return SourceType.NONE

        if (
            self.get_attribute_value(
                Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE
            )
            and self.get_attribute_timestamp(
                Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME
            )
            < self.get_attribute_timestamp(
                Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE
            )
            != "dtv"
        ):
            # print("Ext")
            self._media_content_type = None
            return SourceType.EXTERNAL

        if (
            self.get_attribute_value(Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME)
            != ""
            and self.get_attribute_value(Capability.TV_CHANNEL, Attribute.TV_CHANNEL)
            == ""
        ):
            # print("App")
            self._media_content_type = MediaType.APP
            return SourceType.APP
        # print("TV")
        self._media_content_type = MediaType.TVSHOW
        return SourceType.TV

    def _source_type_update(self, event: DeviceEvent):
        # print(f"---> {event.attribute} - {event.value}")
        # print(
        #     f"Switch:{self.get_attribute_value(Capability.SWITCH, Attribute.SWITCH)} - {self.get_attribute_timestamp(Capability.SWITCH, Attribute.SWITCH)}"
        # )
        # print(
        #     f"Samsung Source:{self.get_attribute_value(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE)} - {self.get_attribute_timestamp(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE)}"
        # )
        # print(
        #     f"Channel Name:{self.get_attribute_value(Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME)} - {self.get_attribute_timestamp(Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME)}"
        # )
        # print(
        #     f"Channel:{self.get_attribute_value(Capability.TV_CHANNEL, Attribute.TV_CHANNEL)} - {self.get_attribute_timestamp(Capability.TV_CHANNEL, Attribute.TV_CHANNEL)}"
        # )

        if not self.supports_capability(Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE):
            return SourceType.NONE

        if (
            event.attribute == Attribute.INPUT_SOURCE
            and self.get_attribute_value(
                Capability.SAMSUNG_VD_MEDIA_INPUT_SOURCE, Attribute.INPUT_SOURCE
            )
            != "dtv"
        ):
            # print("Ext")
            self._media_content_type = None
            return SourceType.EXTERNAL

        if event.attribute == Attribute.TV_CHANNEL and self.get_attribute_value(
            Capability.TV_CHANNEL, Attribute.TV_CHANNEL
        ):
            # print("TV")
            self._media_content_type = MediaType.TVSHOW
            return SourceType.TV

        if event.attribute == Attribute.TV_CHANNEL_NAME:
            channel_name = self.get_attribute_value(
                Capability.TV_CHANNEL, Attribute.TV_CHANNEL_NAME
            )
            if " " in channel_name or "." not in channel_name:
                # print("TV")
                self._media_content_type = MediaType.TVSHOW
                return SourceType.TV
            # print("App")
            self._media_content_type = MediaType.APP
            return SourceType.APP

        return self._samsung_source_type
        # print("TV")
        # self._media_content_type = MediaType.TVSHOW
        # return SourceType.TV

    def get_attribute_timestamp(
        self, capability: Capability, attribute: Attribute
    ) -> Any:
        """Get the value of a device attribute."""
        return self._internal_state[capability][attribute].timestamp
