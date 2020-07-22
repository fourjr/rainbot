import copy

from pymongo import ReturnDocument


DEFAULT = {
    'guild_id': None,
    'logs': {
        'message_delete': None,
        'message_edit': None,
        'member_join': None,
        'member_remove': None,
        'member_ban': None,
        'member_unban': None,
        'vc_state_change': None,
        'channel_create': None,
        'channel_delete': None,
        'role_create': None,
        'role_delete': None
    },
    'modlog': {
        'member_warn': None,
        'member_mute': None,
        'member_unmute': None,
        'member_kick': None,
        'member_ban': None,
        'member_unban': None,
        'member_mute': None,
        'member_softban': None,
        'message_purge': None,
        'channel_lockdown': None,
        'channel_slowmode': None
    },
    'time_offset': 0,
    'detections': {
        'filters': [],
        'block_invite': False,
        'mention_limit': None,
        'spam_detection': None,
        'repetitive_message': None
    },
    'giveaway': {
        'channel_id': None,
        'role_id': None,
        'emoji_id': None
    },
    'perm_levels': {},
    'command_levels': {},
    'warn_punishments': {},
    'notes': [],
    'warns': [],
    'mutes': [],
    'whitelisted_guilds': [],
    'mute_role': None,
    'prefix': '!!'
}


class DatabaseManager:
    def __init__(self, bot, mongo):
        self.bot = bot
        self.db = mongo.rainbot.guilds
        self.guilds_data = {}

    async def get_guild_config(self, guild_id):
        if guild_id not in self.guilds_data:
            data = await self.db.find_one({'guild_id': str(guild_id)})
            if not data:
                data = await self.create_new_config(guild_id)
            self.guilds_data[guild_id] = DBDict(data)

        return self.guilds_data[guild_id]

    async def update_guild_config(self, guild_id, update):
        self.guilds_data[guild_id] = DBDict(await self.db.find_one_and_update({'guild_id': str(guild_id)}, update, upsert=True, return_document=ReturnDocument.AFTER))

        return self.guilds_data[guild_id]

    async def create_new_config(self, guild_id):
        data = copy.copy(DEFAULT)
        data['guild_id'] = str(guild_id)
        self.guilds_data[guild_id] = DBDict(data)

        await self.bot.mongo.rainbot.guilds.insert_one(data)

        return self.guilds_data[guild_id]


class DBDict(dict):
    def __getitem__(self, key):
        try:
            item = super().__getitem__(key)
        except KeyError:
            item = DEFAULT[key]

        if isinstance(item, dict):
            return DBDict(item)
        elif isinstance(item, list):
            return DBList(item)

        return item

    def __getattr__(self, name):
        try:
            return super().__getattribute__(name)
        except AttributeError as e:
            try:
                return self[name]
            except KeyError:
                raise e


class DBList(list):
    def __getitem__(self, key):
        try:
            item = super().__getitem__(key)
        except KeyError:
            item = DEFAULT[key]

        if isinstance(item, dict):
            return DBDict(item)
        elif isinstance(item, list):
            return DBList(item)

        return item
