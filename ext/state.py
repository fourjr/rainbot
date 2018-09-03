import copy

import discord
from discord.state import ConnectionState
from discord.raw_models import RawMessageUpdateEvent, RawBulkMessageDeleteEvent, RawMessageDeleteEvent


class RawBulkMessageIndividualDeleteEvent(RawBulkMessageDeleteEvent):
    """Represents the event payload for a :func:`on_raw_bulk_message_individual_delete` event.
    Attributes
    -----------
    message_ids: Set[:class:`int`]
        A :class:`set` of the message IDs that were deleted.
    channel_id: :class:`int`
        The channel ID where the message got deleted.
    guild_id: Optional[:class:`int`]
        The guild ID where the message got deleted, if applicable.
    """

    __slots__ = ('message_id', 'channel_id', 'guild_id')

    def __init__(self, data, message_id):
        self.message_id = message_id
        self.channel_id = int(data['channel_id'])

        try:
            self.guild_id = int(data['guild_id'])
        except KeyError:
            self.guild_id = None


class ConnState(ConnectionState):
    """Overwrites the default Connection State so raw events will not get called
    if message exists in cache
    """

    def parse_message_delete(self, data):
        raw = RawMessageDeleteEvent(data)
        found = self._get_message(raw.message_id)
        if found is not None:
            self.dispatch('message_delete', found)
            self._messages.remove(found)
        else:
            self.dispatch('raw_message_delete', raw)

    def parse_message_delete_bulk(self, data):
        raw = RawBulkMessageDeleteEvent(data)
        self.dispatch('raw_bulk_message_delete', raw)

        to_be_deleted = [message for message in self._messages if message.id in raw.message_ids]
        to_be_deleted_ids = [i.id for i in to_be_deleted]
        raw_deleted = [i for i in raw.message_ids if i not in to_be_deleted_ids]
        for msg in to_be_deleted:
            self.dispatch('message_delete', msg)
            self._messages.remove(msg)
        for msg in raw_deleted:
            dispatch_data = RawBulkMessageIndividualDeleteEvent(data, msg)
            self.dispatch('raw_message_individual_delete', dispatch_data)

    def parse_message_update(self, data):
        raw = RawMessageUpdateEvent(data)
        message = self._get_message(raw.message_id)
        if message is not None:
            older_message = copy.copy(message)
            if 'call' in data:
                # call state message edit
                message._handle_call(data['call'])
            elif 'content' not in data:
                # embed only edit
                message.embeds = [discord.Embed.from_data(d) for d in data['embeds']]
            else:
                message._update(channel=message.channel, data=data)

            self.dispatch('message_edit', older_message, message)
        else:
            self.dispatch('raw_message_edit', raw)
