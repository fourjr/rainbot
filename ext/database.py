from __future__ import annotations

import asyncio
import copy
from typing import Any, Dict, List, Union

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument
from cachetools import TTLCache

DEFAULT: Dict[str, Any] = {
    "guild_id": None,
    "logs": {
        "message_delete": None,
        "message_edit": None,
        "member_join": None,
        "member_remove": None,
        "member_ban": None,
        "member_unban": None,
        "vc_state_change": None,
        "channel_create": None,
        "channel_delete": None,
        "role_create": None,
        "role_delete": None,
    },
    "modlog": {
        "member_warn": None,
        "member_mute": None,
        "member_unmute": None,
        "member_kick": None,
        "member_ban": None,
        "member_unban": None,
        "member_mute": None,
        "member_softban": None,
        "message_purge": None,
        "channel_lockdown": None,
        "channel_slowmode": None,
    },
    "time_offset": 0,
    "detections": {
        "filters": [],
        "regex_filters": [],
        "image_filters": [],
        "block_invite": False,
        "english_only": False,
        "mention_limit": None,
        "spam_detection": None,
        "repetitive_message": None,
        "repetitive_characters": None,
        "max_lines": None,
        "max_words": None,
        "max_characters": None,
        "sexually_explicit": [],
        "caps_message_percent": None,
        "caps_message_min_words": None,
    },
    "detection_punishments": {
        "filters": {"warn": 1, "mute": None, "kick": False, "ban": False, "delete": True},
        "regex_filters": {"warn": 1, "mute": None, "kick": False, "ban": False, "delete": True},
        "image_filters": {"warn": 1, "mute": None, "kick": False, "ban": False, "delete": True},
        "block_invite": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "english_only": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
        "mention_limit": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "spam_detection": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "repetitive_message": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "repetitive_characters": {
            "warn": 0,
            "mute": None,
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "max_lines": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
        "max_words": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
        "max_characters": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
        "sexually_explicit": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "caps_message": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
    },
    "alert": {
        "kick": None,
        "ban": None,
        "softban": None,
        "mute": None,
        "unmute": None,
    },
    "giveaway": {
        "channel_id": None,
        "role_id": None,
        "emoji_id": None,
        "message_id": None,
        "ended": False,
    },
    "perm_levels": [],
    "command_levels": [],
    "warn_punishments": [],
    "notes": [],
    "warns": [],
    "mutes": [],
    "tags": [],
    "whitelisted_guilds": [],
    "reaction_roles": [],
    "selfroles": [],
    "autoroles": [],
    "ignored_channels": {
        "filters": [],
        "regex_filters": [],
        "image_filters": [],
        "block_invite": [],
        "english_only": [],
        "mention_limit": [],
        "spam_detection": [],
        "repetitive_message": [],
        "repetitive_characters": [],
        "max_lines": [],
        "max_words": [],
        "max_characters": [],
        "sexually_explicit": [],
        "caps_message": [],
        "message_delete": [],
        "message_edit": [],
        "channel_delete": [],
    },
    "events_announce": {"member_join": {}, "member_remove": {}},
    "canned_variables": {},
    "ignored_channels_in_prod": [],
    "mute_role": None,
    "ban_prune_days": 3,
    "prefix": "!!",
}

RECOMMENDED_DETECTIONS: Dict[str, Any] = {
    "detections": {
        "block_invite": True,
        "english_only": True,
        "mention_limit": 5,
        "spam_detection": 5,
        "repetitive_message": 15,
        "repetitive_characters": 8,
        "max_lines": 15,
        "max_words": 450,
        "sexually_explicit": [
            "EXPOSED_ANUS",
            "EXPOSED_BELLY",
            "EXPOSED_BUTTOCKS",
            "EXPOSED_BREAST_F",
            "EXPOSED_GENITALIA_F",
            "COVERED_GENITALIA_F",
            "EXPOSED_GENITALIA_M",
        ],
        "caps_message_percent": 0.80,
        "caps_message_min_words": 10,
    },
    "detection_punishments": {
        "filters": {"warn": 1, "mute": None, "kick": False, "ban": False, "delete": True},
        "regex_filters": {"warn": 1, "mute": None, "kick": False, "ban": False, "delete": True},
        "image_filters": {"warn": 1, "mute": None, "kick": False, "ban": False, "delete": True},
        "block_invite": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "english_only": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
        "mention_limit": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "spam_detection": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "repetitive_message": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "repetitive_characters": {
            "warn": 0,
            "mute": None,
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "max_lines": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
        "max_words": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
        "max_characters": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
        "sexually_explicit": {
            "warn": 1,
            "mute": "10 minutes",
            "kick": False,
            "ban": False,
            "delete": True,
        },
        "caps_message": {"warn": 0, "mute": None, "kick": False, "ban": False, "delete": True},
    },
}


class DBDict(dict):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._default = kwargs.pop("_default", DEFAULT)
        super().__init__(*args, **kwargs)

    def __getitem__(self, key: str) -> Any:
        try:
            item = super().__getitem__(key)
        except KeyError:
            item = self._default[key]

        if isinstance(item, dict):
            return DBDict(item, _default=tryget(self._default, key))
        elif isinstance(item, list):
            return DBList(item, _default=tryget(self._default, key))

        return item

    def __getattr__(self, name: str) -> Any:
        try:
            return super().__getattribute__(name)
        except AttributeError as e:
            try:
                return self[name]
            except KeyError:
                raise e

    def __copy__(self) -> DBDict:
        return DBDict(copy.copy(dict(self)))

    def getlist(self, key: str) -> List[Any]:
        return [self[key]]


class DBList(list):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._default = kwargs.pop("_default", DEFAULT)
        super().__init__(*args, **kwargs)

    def __getitem__(self, index: Union[int, slice]) -> Any:
        try:
            item = super().__getitem__(index)
        except KeyError:
            item = self._default[index]

        if isinstance(item, dict):
            return DBDict(item, _default=tryget(self._default, index))
        elif isinstance(item, list):
            return DBList(item, _default=tryget(self._default, index))

        return item

    def __copy__(self) -> DBList:
        return DBList(copy.copy(list(self)))

    def __iter__(self) -> Any:
        for i in super().__iter__():
            if isinstance(i, dict):
                i = DBDict(i)
            if isinstance(i, list):
                i = DBList(i)
            yield i

    def get_kv(self, key: str, value: Any) -> DBDict:
        for i in self:
            if i[key] == value:
                return i

        raise IndexError(f"Key {key} with {value} not found")


class DatabaseManager:
    def __init__(self, mongo_uri: str, *, loop: asyncio.AbstractEventLoop = None) -> None:
        self.mongo = AsyncIOMotorClient(mongo_uri)
        self.coll = self.mongo.rainbot.guilds
        self.users = self.mongo.rainbot.users
        self.guild_cache = TTLCache(maxsize=1000, ttl=300)
        self.users_data: Dict[int, DBDict] = {}

        self.loop = loop or asyncio.get_event_loop()

    def start_change_listener(self) -> None:
        """Start the change listener task"""
        pass # Disabling change listener in favor of cache

    async def get_guild_config(self, guild_id: int) -> DBDict:
        if guild_id in self.guild_cache:
            return self.guild_cache[guild_id]
        
        data = await self.coll.find_one({"guild_id": str(guild_id)})
        if not data:
            config = await self.create_new_config(guild_id)
        else:
            config = DBDict(data)

        self.guild_cache[guild_id] = config
        return config

    # Guilds
    async def update_guild_config(self, guild_id: int, update: dict, **kwargs: Any) -> DBDict:
        if guild_id in self.guild_cache:
            del self.guild_cache[guild_id] # Invalidate cache

        updated_document = await self.coll.find_one_and_update(
            {"guild_id": str(guild_id)},
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
            **kwargs,
        )
        config = DBDict(updated_document)
        self.guild_cache[guild_id] = config
        return config

    async def create_new_config(self, guild_id: int) -> DBDict:
        data = copy.copy(DEFAULT)
        data["guild_id"] = str(guild_id)
        await self.coll.insert_one(data)
        config = DBDict(data)
        self.guild_cache[guild_id] = config
        return config

    # Users
    async def get_user(self, user_id: int) -> DBDict:
        self.users_data[user_id] = await self.users.find_one({"user_id": str(user_id)})
        return self.users_data[user_id]

    async def update_user(self, user_id: int, update: dict) -> DBDict:
        self.users_data[user_id] = await self.users.find_one_and_update(
            {"user_id": str(user_id)}, update, upsert=True, return_document=ReturnDocument.AFTER
        )
        return self.users_data[user_id]


def tryget(obj: Union[dict, list], key: Any) -> Any:
    try:
        return obj[key]
    except (KeyError, IndexError):
        return None
