import discord
import datetime
import pytz
import json
import asyncio

from discord.ext import commands
from data import DB
from consts import StaticParty, Event, Player, Templates


async def check_guild_permissions(ctx, perms, *, check=all):
    is_owner = await ctx.bot.is_owner(ctx.author)
    if is_owner:
        return True

    if ctx.guild is None:
        return False

    resolved = ctx.author.guild_permissions
    return check(getattr(resolved, name, None) == value for name, value in perms.items())

def is_admin():
    async def pred(ctx):
        return await check_guild_permissions(ctx, {'administrator': True})
    return commands.check(pred)

def is_mod():
    async def pred(ctx):
        return await check_guild_permissions(ctx, {'manage_guild': True})
    return commands.check(pred)

def convert_to_utc(timestamp):
    converted = timestamp.astimezone(pytz.utc)
    return converted
class Manager:
    def __init__(self, bot,auto=False):
        self.bot = bot
        self.db = DB(name="main", loop=bot.loop)
        self.loop = bot.loop
        self.players = None
        self.events = None
        self.party = None
        self.static_party = None
        if auto:
            self.loop.create_task(self.initialize())


    async def initialize(self):
        """Tables to be created:
        -players
        -party
        -static_party
        -events"""
        await self.db.initialize()
        tables = self.db.tables
        if not "players" in tables:
            t = await self.db.create_table(name="players", primary_key = {"id": "INTEGER"}, values=Templates.PLAYER_SQL_TEMPLATE)
            self.players = t
        else:
            self.players = await self.db.get_table("players")
        if not "static_party" in tables:
            t = await self.db.create_table(name="static_party", primary_key = {"id": "INTEGER"}, values=Templates.STATIC_PARTY_SQL_TEMPLATE)
            self.static_party = t
        else:
            self.static_party = await self.db.get_table("static_party")
        if not "events" in tables:
            t = await self.db.create_table(name="events", primary_key = {"id": "INTEGER"}, values=Templates.EVENT_SQL_TEMPLATE)
            self.events = t
        else:
            self.events = await self.db.get_table("events")
    async def get_party(self, id):
        data = await self.party.get_entry(int(id))
        if not data:
            return None
        obj = Party(self.party, int(id))
        await obj.initialize()
        return obj
    async def get_parties(self, ids):
        f = []
        for id in ids:
            obj = await self.get_party(int(id))
            if obj:
                f.append(obj)
        return f

    async def get_all_parties(self):
        f = []
        data = await self.party.get_all_entries()
        for i in data:
            obj = await self.get_party(i.id)
            f.append(obj)
        return f
    async def get_static_party(self, id):
        data = await self.static_party.get_entry(int(id))
        if not data:
            return None
        obj = StaticParty(self.static_party, int(id))
        await obj.initialize()
        return obj
    async def get_static_parties(self, ids):
        f = []
        for id in ids:
            obj = await self.get_static_party(int(id))
            if obj:
                f.append(obj)
        return f
    async def get_all_static_parties(self, ids):
        f = []
        data = await self.static_party.get_all_entries()
        for i in data:
            obj = await self.get_static_party(i.id)
            f.append(obj)
        return f
    async def get_player(self, id):
        obj = Player(self.players, int(id))
        await obj.initialize()
        return obj
    async def get_players(self, ids):
        f = []
        for id in ids:
            obj = await self.get_player(int(id))
            if obj:
                f.append(obj)
        return f
    async def get_event(self, id):
        data = await self.events.get_entry(int(id))
        if not data:
            return None
        obj = Event(self.events, int(id))
        await obj.initialize()
        return obj
    async def get_events(self, ids):
        f = []
        for id in ids:
            obj = await self.get_event(int(id))
            if obj:
                f.append(obj)
        return f

class Visualizer:
    def __init__(self, bot, ctx, data):
        self.bot = bot
        self.loop = self.bot.loop
        self.message = None
        self.index = 0
        self.data = data
        self.ctx = ctx
        self.details = "Showing Entry **{index}** of **{max}**"
        self.running = True
        self.reaction_emojis = [
        ("⏮", self.prev),
        ("⏹", self.stop),
        ("⏭", self.next)
        ]
        self.match = None
        print(self.data)

    async def add_reactions(self):
        emojis = ["⏮","⏹","⏭"]

        for i in emojis:
            await self.message.add_reaction(i)
    def react_check(self, payload):
        if payload.user_id != self.ctx.author.id:
            return False

        if payload.message_id != self.message.id:
            return False

        to_check = str(payload.emoji)
        for (emoji, func) in self.reaction_emojis:
            if to_check == emoji:
                self.match = func
                return True
        return False
    async def start(self):
        embed = self.get_embed()

        details = self.details.format(index = self.index+1, max = len(self.data))
        msg = await self.ctx.send(details, embed = embed)
        self.message = msg

        await self.add_reactions()

        while self.running:
            try:
                payload = await self.bot.wait_for('raw_reaction_add', check=self.react_check, timeout=120.0)
            except asyncio.TimeoutError:
                await self.stop()
                continue

            try:
                await self.message.remove_reaction(payload.emoji, discord.Object(id=payload.user_id))
            except:
                pass # can't remove it so don't bother doing so

            await self.match()


    async def next(self):
        ind = self.index + 1
        if ind == len(self.data):
            ind = 0

        self.index = ind

        embed = self.get_embed()
        details = self.details.format(index = self.index+1, max = len(self.data))
        await self.message.edit(content=details, embed = embed)

    async def prev(self):
        ind = self.index - 1
        if ind < 0:
            ind = len(self.data) - 1
        self.index = ind

        embed = self.get_embed()
        details = self.details.format(index = self.index+1, max = len(self.data))
        await self.message.edit(content=details, embed = embed)

    async def stop(self):
        self.running = False
        try:
            await self.message.clear_reactions()
        except:
            pass
        embed = discord.Embed()
        embed.colour = discord.Colour.blurple()
        embed.description = "This Message is going to auto delete in 5 seconds"
        await self.message.edit(content = "\u200b", embed = embed)
        await asyncio.sleep(5)

        await self.message.delete()

    def get_embed(self):
        obj = self.data[self.index]
        embed = obj.embed(self.bot)
        return embed




