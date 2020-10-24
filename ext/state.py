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
        raw.cached_message = found
        if self._messages is not None and found is not None:
            self.dispatch('message_delete', found)
            self._messages.remove(found)
        else:
            self.dispatch('raw_message_delete', raw)

    def parse_message_delete_bulk(self, data):
        raw = RawBulkMessageDeleteEvent(data)
        if self._messages:
            found_messages = [message for message in self._messages if message.id in raw.message_ids]
        else:
            found_messages = []
        raw.cached_messages = found_messages
        if found_messages:
            self.dispatch('bulk_message_delete', found_messages)
            for msg in found_messages:
                self._messages.remove(msg)
        else:
            self.dispatch('raw_bulk_message_delete', raw)

    def parse_message_update(self, data):
        raw = RawMessageUpdateEvent(data)
        message = self._get_message(raw.message_id)
        if message is not None:
            older_message = copy.copy(message)
            raw.cached_message = older_message
            message._update(data)
            self.dispatch('message_edit', older_message, message)
        else:
            self.dispatch('raw_message_edit', raw)
