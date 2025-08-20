"""
Modern database manager with connection pooling and caching
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

import motor.motor_asyncio
from pymongo import ReturnDocument
from cachetools import TTLCache

from config.config import config


class Database:
    def __init__(self):
        self.manager = DatabaseManager(config.database.uri)

    async def connect(self):
        await self.manager.connect()

    def __getattr__(self, name):
        return getattr(self.manager, name)


class DatabaseManager:
    """
    Modern database manager with connection pooling and caching
    """

    def __init__(self, uri: str):
        self.uri = uri
        self.client: Optional[motor.motor_asyncio.AsyncIOMotorClient] = None
        self.db: Optional[motor.motor_asyncio.AsyncIOMotorDatabase] = None
        self.logger = logging.getLogger("rainbot.database")

        # Caches with TTL
        self.guild_cache = TTLCache(maxsize=1000, ttl=300)  # 5 minutes
        self.user_cache = TTLCache(maxsize=5000, ttl=600)  # 10 minutes

        # Default configurations
        self._default_logging_config = {
            "moderation": None,
            "member_join": None,
            "member_leave": None,
            "message_edit": None,
            "message_delete": None,
            "voice_activity": None,
            "server_updates": None,
        }

        self._default_automod_config = {
            "enabled": False,
            "spam_detection": False,
            "link_filtering": False,
            "word_filtering": False,
            "caps_filtering": False,
            "mention_spam": False,
            "duplicate_messages": False,
            "max_lines": 0,
            "max_words": 0,
            "max_characters": 0,
            "image_filters": [],
            "spam_threshold": 5,
            "mention_limit": 5,
            "caps_threshold": 70,
            "duplicate_threshold": 3,
            "blocked_words": [],
            "blocked_links": [],
            "whitelisted_channels": [],
            "ignored_roles": [],
        }

        self._default_punishments_config = {
            "spam": {"action": "mute", "duration": 600, "delete": True},
            "links": {"action": "warn", "duration": None, "delete": True},
            "words": {"action": "warn", "duration": None, "delete": True},
            "caps": {"action": "warn", "duration": None, "delete": False},
            "mentions": {"action": "mute", "duration": 300, "delete": True},
        }

        self.default_guild_config = {
            "guild_id": None,
            "prefix": config.bot.default_prefix,
            "timezone_offset": 0,
            "mute_role_id": None,
            "auto_role_ids": [],
            "self_role_ids": [],
            "permission_roles": {},
            "command_overrides": {},
            "log_channels": self._default_logging_config,
            "ignored_channels": {"message_delete": [], "message_edit": []},
            "automod": self._default_automod_config,
            "punishments": self._default_punishments_config,
            "moderation_logs": [],
            "warnings": [],
            "mutes": [],
            "bans": [],
            "welcome_message": {
                "enabled": False,
                "channel_id": None,
                "message": "Welcome {user} to {guild}!",
            },
            "leave_message": {
                "enabled": False,
                "channel_id": None,
                "message": "{user} has left the server.",
            },
            "giveaway_config": {
                "channel_id": None,
                "emoji": "🎉",
                "required_role": None,
            },
            "giveaways": [],
            "events_announce": {"member_join": {}, "member_remove": {}},
            "tags": {},
            "stats": {
                "commands_used": 0,
                "messages_moderated": 0,
                "members_warned": 0,
                "members_muted": 0,
                "members_banned": 0,
            },
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        self.default_user_config = {
            "user_id": None,
            "global_warnings": 0,
            "global_bans": 0,
            "reputation": 0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    async def connect(self):
        """Connect to the database"""
        try:
            self.client = motor.motor_asyncio.AsyncIOMotorClient(
                self.uri,
                serverSelectionTimeoutMS=config.database.server_selection_timeout,
                connectTimeoutMS=config.database.connection_timeout,
                maxPoolSize=config.database.max_pool_size,
                minPoolSize=config.database.min_pool_size,
            )

            # Test connection
            await self.client.admin.command("ping")

            self.db = self.client[config.database.name]
            self.logger.info("Successfully connected to database")

            # Create indexes
            await self._create_indexes()

        except Exception as e:
            self.logger.error(f"Failed to connect to database: {e}")
            raise

    async def _create_indexes(self):
        """Create database indexes for performance"""
        try:
            # Guild collection indexes - use sparse to handle existing duplicates
            try:
                await self.db.guilds.create_index("guild_id", unique=True, sparse=True)
            except Exception as e:
                if "duplicate key" in str(e).lower():
                    self.logger.warning("Duplicate guild_id found, cleaning up...")
                    # Remove duplicates keeping the most recent
                    pipeline = [
                        {
                            "$group": {
                                "_id": "$guild_id",
                                "docs": {"$push": "$$ROOT"},
                                "count": {"$sum": 1},
                            }
                        },
                        {"$match": {"count": {"$gt": 1}}},
                    ]
                    duplicates = await self.db.guilds.aggregate(pipeline).to_list(None)

                    for dup in duplicates:
                        docs = sorted(
                            dup["docs"],
                            key=lambda x: x.get(
                                "updated_at",
                                x.get("created_at", datetime.now(timezone.utc)),
                            ),
                            reverse=True,
                        )
                        # Keep the first (most recent), delete the rest
                        for doc in docs[1:]:
                            await self.db.guilds.delete_one({"_id": doc["_id"]})

                    # Try creating index again
                    await self.db.guilds.create_index(
                        "guild_id", unique=True, sparse=True
                    )
                else:
                    raise

            await self.db.guilds.create_index("updated_at")

            # User collection indexes
            await self.db.users.create_index("user_id", unique=True, sparse=True)
            await self.db.users.create_index("updated_at")

            # Moderation logs indexes
            await self.db.moderation_logs.create_index(
                [("guild_id", 1), ("timestamp", -1)]
            )
            await self.db.moderation_logs.create_index(
                [("user_id", 1), ("timestamp", -1)]
            )
            await self.db.moderation_logs.create_index(
                "case_id", unique=True, sparse=True
            )

            self.logger.info("Database indexes created successfully")

        except Exception as e:
            self.logger.error(f"Failed to create indexes: {e}")

    async def get_guild_config(self, guild_id: int) -> Dict[str, Any]:
        """Get guild configuration with caching"""
        # Check cache first
        if guild_id in self.guild_cache:
            return self.guild_cache[guild_id]

        # Get from database
        config_doc = await self.db.guilds.find_one({"guild_id": guild_id})

        if not config_doc:
            # Create default config
            config_doc = self.default_guild_config.copy()
            config_doc["guild_id"] = guild_id
            try:
                await self.db.guilds.insert_one(config_doc)
            except Exception:
                # If insert fails due to duplicate, try to get existing
                config_doc = await self.db.guilds.find_one({"guild_id": guild_id})
                if not config_doc:
                    config_doc = self.default_guild_config.copy()
                    config_doc["guild_id"] = guild_id

        # Cache and return
        self.guild_cache[guild_id] = config_doc
        return config_doc

    async def update_guild_config(
        self, guild_id: int, update: Dict[str, Any], upsert: bool = True
    ) -> Dict[str, Any]:
        """Update guild configuration"""
        # Add timestamp
        update["updated_at"] = datetime.now(timezone.utc)

        # Update in database
        result = await self.db.guilds.find_one_and_update(
            {"guild_id": guild_id},
            {"$set": update},
            upsert=upsert,
            return_document=ReturnDocument.AFTER,
        )

        # Update cache
        if result:
            self.guild_cache[guild_id] = result

        return result

    async def get_user_config(self, user_id: int) -> Dict[str, Any]:
        """Get user configuration with caching"""
        # Check cache first
        if user_id in self.user_cache:
            return self.user_cache[user_id]

        # Get from database
        config_doc = await self.db.users.find_one({"user_id": user_id})

        if not config_doc:
            # Create default config
            config_doc = self.default_user_config.copy()
            config_doc["user_id"] = user_id
            await self.db.users.insert_one(config_doc)

        # Cache and return
        self.user_cache[user_id] = config_doc
        return config_doc

    async def update_user_config(
        self, user_id: int, update: Dict[str, Any], upsert: bool = True
    ) -> Dict[str, Any]:
        """Update user configuration"""
        # Add timestamp
        update["updated_at"] = datetime.now(timezone.utc)

        # Update in database
        result = await self.db.users.find_one_and_update(
            {"user_id": user_id},
            {"$set": update},
            upsert=upsert,
            return_document=ReturnDocument.AFTER,
        )

        # Update cache
        if result:
            self.user_cache[user_id] = result

        return result

    async def add_moderation_log(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int,
        action: str,
        reason: str,
        duration: Optional[int] = None,
        case_id: Optional[str] = None,
    ) -> str:
        """Add a moderation log entry"""
        if not case_id:
            # Generate case ID
            count = await self.db.moderation_logs.count_documents(
                {"guild_id": guild_id}
            )
            case_id = f"{guild_id}-{count + 1}"

        log_entry = {
            "case_id": case_id,
            "guild_id": guild_id,
            "user_id": user_id,
            "moderator_id": moderator_id,
            "action": action,
            "reason": reason,
            "duration": duration,
            "timestamp": datetime.now(timezone.utc),
            "active": True,
        }

        await self.db.moderation_logs.insert_one(log_entry)

        # Update guild stats
        await self.update_guild_config(guild_id, {f"stats.{action}s": {"$inc": 1}})

        return case_id

    async def get_moderation_logs(
        self, guild_id: int, user_id: Optional[int] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get moderation logs"""
        query = {"guild_id": guild_id}
        if user_id:
            query["user_id"] = user_id

        cursor = self.db.moderation_logs.find(query).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_active_punishments(
        self, guild_id: int, punishment_type: str, user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get active punishments (mutes, bans, etc.)"""
        query = {
            "guild_id": guild_id,
            "action": punishment_type,
            "active": True,
            "duration": {"$ne": None},
        }

        if user_id:
            query["user_id"] = user_id

        cursor = self.db.moderation_logs.find(query)
        return await cursor.to_list(length=None)

    async def deactivate_punishment(self, case_id: str):
        """Deactivate a punishment (mark as completed)"""
        await self.db.moderation_logs.update_one(
            {"case_id": case_id},
            {"$set": {"active": False, "completed_at": datetime.now(timezone.utc)}},
        )

    async def get_guild_stats(self, guild_id: int) -> Dict[str, Any]:
        """Get comprehensive guild statistics"""
        config_doc = await self.get_guild_config(guild_id)

        # Get recent activity
        recent_logs = await self.db.moderation_logs.count_documents(
            {
                "guild_id": guild_id,
                "timestamp": {
                    "$gte": datetime.now(timezone.utc).replace(
                        hour=0, minute=0, second=0
                    )
                },
            }
        )

        return {
            "total_commands": config_doc.get("stats", {}).get("commands_used", 0),
            "total_moderation": await self.db.moderation_logs.count_documents(
                {"guild_id": guild_id}
            ),
            "recent_activity": recent_logs,
            "active_mutes": len(await self.get_active_punishments(guild_id, "mute")),
            "active_bans": len(await self.get_active_punishments(guild_id, "ban")),
            **config_doc.get("stats", {}),
        }

    async def clear_cache(
        self, guild_id: Optional[int] = None, user_id: Optional[int] = None
    ):
        """Clear cache entries"""
        if guild_id:
            self.guild_cache.pop(guild_id, None)

        if user_id:
            self.user_cache.pop(user_id, None)

        if not guild_id and not user_id:
            self.guild_cache.clear()
            self.user_cache.clear()

    async def add_warning(self, guild_id: int, user_id: int, reason: str):
        """Add a warning to a user"""
        return await self.add_moderation_log(guild_id, user_id, 0, "warn", reason)

    async def get_tags(self, guild_id: int) -> Dict[str, str]:
        """Get all tags for a guild"""
        config = await self.get_guild_config(guild_id)
        return config.get("tags", {})

    async def add_tag(self, guild_id: int, name: str, content: str, creator_id: int):
        """Add a new tag"""
        tags = await self.get_tags(guild_id)
        tags[name] = {
            "content": content,
            "creator_id": creator_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "uses": 0,
        }
        await self.update_guild_config(guild_id, {"tags": tags})

    async def update_tag(self, guild_id: int, name: str, content: str):
        """Update an existing tag"""
        tags = await self.get_tags(guild_id)
        if name in tags:
            tags[name]["content"] = content
            await self.update_guild_config(guild_id, {"tags": tags})

    async def delete_tag(self, guild_id: int, name: str):
        """Delete a tag"""
        tags = await self.get_tags(guild_id)
        if name in tags:
            del tags[name]
            await self.update_guild_config(guild_id, {"tags": tags})

    async def increment_tag_usage(self, guild_id: int, name: str):
        """Increment tag usage count"""
        tags = await self.get_tags(guild_id)
        if name in tags:
            tags[name]["uses"] = tags[name].get("uses", 0) + 1
            await self.update_guild_config(guild_id, {"tags": tags})

    async def get_tag_info(self, guild_id: int, name: str):
        """Get tag information"""
        tags = await self.get_tags(guild_id)
        return tags.get(name)

    async def get_canned_responses(self, guild_id: int) -> Dict[str, str]:
        """Get canned responses"""
        config = await self.get_guild_config(guild_id)
        return config.get("canned_responses", {})

    async def add_canned_response(self, guild_id: int, name: str, content: str):
        """Add a canned response"""
        responses = await self.get_canned_responses(guild_id)
        responses[name] = content
        await self.update_guild_config(guild_id, {"canned_responses": responses})

    async def get_reaction_roles(self, guild_id: int) -> Dict[str, int]:
        """Get reaction roles mapping"""
        config = await self.get_guild_config(guild_id)
        return config.get("reaction_roles", {})

    async def update_reaction_roles(
        self, guild_id: int, reaction_roles: Dict[str, int]
    ):
        """Update reaction roles mapping"""
        await self.update_guild_config(guild_id, {"reaction_roles": reaction_roles})

    async def create_giveaway(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        host_id: int,
        prize: str,
        winners: int,
        end_time: datetime,
    ):
        """Create a new giveaway"""
        giveaway = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
            "host_id": host_id,
            "prize": prize,
            "winners": winners,
            "end_time": end_time,
            "active": True,
            "created_at": datetime.now(timezone.utc),
        }
        await self.db.giveaways.insert_one(giveaway)

    async def get_giveaway(self, message_id: int):
        """Get a giveaway by message ID"""
        return await self.db.giveaways.find_one({"message_id": message_id})

    async def get_active_giveaways(self):
        """Get all active giveaways"""
        cursor = self.db.giveaways.find(
            {"active": True, "end_time": {"$lte": datetime.now(timezone.utc)}}
        )
        return await cursor.to_list(length=None)

    async def get_guild_giveaways(self, guild_id: int):
        """Get active giveaways for a guild"""
        cursor = self.db.giveaways.find({"guild_id": guild_id, "active": True})
        return await cursor.to_list(length=None)

    async def end_giveaway(self, message_id: int):
        """Mark a giveaway as ended"""
        await self.db.giveaways.update_one(
            {"message_id": message_id},
            {"$set": {"active": False, "ended_at": datetime.now(timezone.utc)}},
        )

    async def update_giveaway(self, message_id: int, update: Dict[str, Any]):
        """Update a giveaway"""
        await self.db.giveaways.update_one({"message_id": message_id}, {"$set": update})

    async def reset_guild_config(self, guild_id: int):
        """Reset guild configuration to defaults"""
        default_config = self.default_guild_config.copy()
        default_config["guild_id"] = guild_id
        await self.db.guilds.replace_one(
            {"guild_id": guild_id}, default_config, upsert=True
        )
        self.guild_cache.pop(guild_id, None)

    async def get_user_moderation_logs(
        self, guild_id: int, user_id: int, limit: int = 50
    ):
        """Get moderation logs for a specific user"""
        cursor = (
            self.db.moderation_logs.find({"guild_id": guild_id, "user_id": user_id})
            .sort("timestamp", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def get_guild_moderation_logs(self, guild_id: int, limit: int = 50):
        """Get recent moderation logs for a guild"""
        cursor = (
            self.db.moderation_logs.find({"guild_id": guild_id})
            .sort("timestamp", -1)
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def close(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            self.logger.info("Database connection closed")
