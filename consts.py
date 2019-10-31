import datetime
import dateparser
import json
import pytz
import asyncio
import discord
from discord.ext import commands

class Templates:
    STATIC_PARTY_SQL_TEMPLATE = {
    "name" : "TEXT",
    "description": "TEXT",
    "event_id" : "TEXT",
    "leader" : "INTEGER",
    "players" : "TEXT",
    "pending": "TEXT"
    }
    STATIC_PARTY= {
    "name" : None,
    "description": None,
    "event_id" : None,
    "leader" : None,
    "players" : '[]',
    "pending": '[]'
    }
#-------------------------------------
    PLAYER_SQL_TEMPLATE = {
    "attendence": "INTEGER",
    "attended" : "TEXT",
    "not_attended" : "TEXT",
    "static_party" : "INTEGER"
    }
    PLAYER = {
    "attendence" : 80,
    "attended" : '[]',
    "not_attended": '[]',
    "static_party" : None,
    }
#-------------------------------------
    EVENT = {
    "name" : None,
    "description" : None,
    "timestamp" : None,
    "leader": None,
    "alert": False,
    "ended": False,
    "started": False,
    "party" : None,
    "max": 6,
    "message": None,
    "attended" : '[]',
    "pending": '[]'
    }
    EVENT_SQL_TEMPLATE = {
    "name" : "TEXT",
    "description" : "TEXT",
    "timestamp" : "TEXT",
    "leader": "INTEGER",
    "alert": "BOOLEAN",
    "ended": "BOOLEAN",
    "started": "BOOLEAN",
    "party": "INTEGER",
    "max" : "INTEGER",
    "message": "INTEGER",
    "attended": "TEXT",
    "pending": "TEXT"
    }
class CustomObject:
    def __init__(self, **kwargs):
        self.flatten(**kwargs)
    def flatten(self, **kwargs):
        for a, b in kwargs.items():
            setattr(self, a, b)

class Player:
    def __init__(self, table, id, *,auto=False):
        self.table=table
        self.id = int(id)
        self.attendence = None
        self.attended = None
        self.not_attended = None
        self.static_party = None
        self._ready = None
        if auto:
            self.table.data.loop.create_task(self.initialize())
    
    async def initialize(self, *, data=None):
        if not data:
            db = await self.table.get_entry(self.id)
            if not db:
                temp = Templates.PLAYER
                temp["id"] = self.id
                await self.table.add_entry(**temp)
                db = CustomObject(**temp)
            data = db
        self.attendence = data.attendence
        self.attended = json.loads(data.attended)
        self.not_attended = json.loads(data.not_attended)
        if data.static_party:
            table = self.table.db.get_table("static_party'")
            self.static_party = StaticParty(table, data.static_party)
        self._ready = True

    def to_json(self):
        PLAYER = {
        "attendence" : self.attendence,
        "attended" : json.dumps(self.attended),
        "not_attended": json.dumps(self.not_attended),
        "static_party" : self.static_party.id if self.static_party else None
        }
    def embed(self, bot):
        embed = discord.Embed()
        embed.colour = discord.Colour.red()
        embed.title = f"Your Profile"
        embed.add_field(name="Attendence", value= str(self.attendence))
        if self.static_party:
            embed.add_field(name="Team", value = self.static_party.to_str(bot), inline=False)
        else:
            embed.add_field(name="Team", value= "None Joined", inline=False)

        at = ", ".join(self.attended)
        if len(self.attended) >10:
            at = ", ".join(self.attended[:10]) 
            at += " and {} more".format(len(self.attended)-10)
        nat = ", ".join(self.not_attended)
        if len(self.not_attended) >10:
            at = ", ".join(self.not_attended[:10]) 
            at += " and {} more".format(len(self.attended)-10)
        embed.add_field(name = "Attended Event IDs", value = at or "None Attended.", inline=False)
        embed.add_field(name = "Not Attended Event IDs", value = nat or "None Attended.", inline=False)
        return embed



class Event:
    def __init__(self, table, id, *, auto=False):
        self.table=table
        self.id = int(id)
        self.name = None
        self.description = None
        self.alert = None
        self.party = None
        self.timestamp = None
        self.attended = None
        self.message = None
        self.ended = False
        self.started = False
        self.pending = None
        self._ready = False
        self._static_party = None
        if auto:
            self.table.data.loop.create_task(self.initialize())

    def to_json(self):
        fut = {
        "name": self.name,
        "description": self.description,
        "alert": self.alert,
        "party": self._party,
        "static_party": self._static_party,
        "ended": self.ended,
        "attended": json.dumps(self.attended),
        "started": self.started,
        "pending": json.dumps(self.pending)
        }
    
    def to_str(self, bot=None,*, for_party = True, type="Party"):
        status = "Not Started Yet"
        if self.started:
            status = "Running"
        if self.ended:
            status = "Ended"
        timestamp  = self.parse_time(self.timestamp) or "None Set"
        a = f"**ID:** {self.id}\n"
        a += f"**Description:** {self.description}\n"
        a += f"**Starts At:** {timestamp}\n"
        a += f"**Event Status:** {status}\n"
        if not for_party:
            fmt = ("\n" +self.party.to_str()) if self.party else "None Linked"
            a += f"**:Linked {type}:**{fmt}"
    async def initialize(self, *, data=None):
        if not data:
            data = await self.table.get_entry(self.id)
        self.name = data.name or "None Set"
        self.description = data.description or "None Set"
        self.alert = bool(data.alert)
        self.timestamp = dateparser.parse(data.timestamp) if data.timestamp else None
        self.ended = bool(data.ended)
        self.started = bool(data.started)
        self.attended = json.loads(data.attended)
        self.message = data.message
        self.pending = json.loads(data.pending)
        if data.party:
            party_table = self.table.db.get_table("static_party")
            party = StaticParty(party_table, data.party)
            await party.initialize()
            self.party = party
            self._static_party = data.party
        self._ready = True
    def embed(self, bot):
        e = discord.Embed()
        e.colour = discord.Colour.blue()
        e.title = self.name
        e.description = self.description
        status = "Not Started Yet"
        if self.started:
            status = "Running"
        if self.ended:
            status = "Ended"
        e.add_field(name= "ID", value=self.id)
        e.add_field(name ="Status", value = status)
        e.add_field(name = "Starts At", value = self.parse_time(self.timestamp) or "None Set")
        e.add_field(name="Linked Party", value = self.party.to_str() if self.party else "None Linked", inline=False)
        return e

    def parse_time(self, timestamp):
        if not timestamp:
            return None
        now = datetime.datetime.utcnow()
        if timestamp.tzinfo:
            now = now.astimezone(pytz.utc)
        delta = timestamp - now
        if delta.total_seconds() < 0:
            return "Event Ended."
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        if days:
            fmt = '{d} days, {h} hours, {m} minutes, and {s} seconds'
        else:
            fmt = '{h} hours, {m} minutes, and {s} seconds'
        x = format(timestamp, "%d %b %Y at %H:%M UTC")
        new = f"{x} (In {fmt})"
        return new


class StaticParty:
    """Class
    Requires a CustomObject/derived CustomObject to fetch attributes from"""
    def __init__(self, table,id, auto=False):
        self._static = True
        self.table = table
        self.id= int(id)
        self.name = None
        self.event = None
        self.description = None
        self.leader = None
        self.players = []
        self.pending = []
        self._ready = False
        if auto:
            self.table.data.loop.create_task(self.initialize())
    
    def to_json(self):
        f = {
        "id" : self.id,
        "name": self.name,
        "event_id": self.event.id if self.event else None,
        "description": self.description,
        "leader": self.leader,
        "players": json.dumps(self.players),
        "pending": json.dumps(self.pending)
        }
        return f
    def embed(self, bot):
        e = discord.Embed()
        e.colour = discord.Colour.green()
        e.title = self.name
        e.description = self.description
        leader = discord.utils.get(bot.get_all_members(), id=int(self.leader))
        if not leader:
            leader = f"Not Found (ID: {self.leader})"
        members = []
        event = "None Linked"
        if self.event:
            event = self.event.to_str(bot, type="Team")

        fmt = ""
        for i in self.players:
            if int(i) == int(self.leader):
                fmt += f"-  {leader.mention}~**{leader.name}#{leader.discriminator}** ⭐\n\n"
            else:
                user = discord.utils.get(bot.get_all_members(), id=int(i))
                if user:
                    fmt += f"-  {user.mention}~**{user.name}#{user.discriminator}**\n\n"
                else:
                    fmt += f"-  Not Found **ID({i})**\n\n"

        if leader:
            leader = f"{leader.mention} {leader.name}#{leader.discriminator}"
        e.add_field(name="ID", value=str(self.id))
        e.add_field(name="Leader", value= leader)
        e.add_field(name="Players", value = fmt, inline=False)
        e.add_field(name="Linked Event", value = event, inline=False)
        return e 

    def to_str(self, bot=None):
        event = "None Linked"
        if self.event:
            event = "\n" + self.event.to_str(bot, type="Team")
        leader = discord.utils.get(bot.get_all_members(), id=int(self.leader))
        if not leader:
            leader = f"Not Found (ID: {self.leader})"
        fmt = ""
        for i in self.players:
            if int(i) == int(self.leader):
                fmt += f"-  {leader.mention}~**{leader.name}#{leader.discriminator}** ⭐\n\n"
            else:
                user = discord.utils.get(bot.get_all_members(), id=int(i))
                if user:
                    fmt += f"-  {user.mention}~**{user.name}#{user.discriminator}**\n\n"
                else:
                    fmt += f"-  Not Found **ID({i})**\n\n"
        fmt = f"ID: {self.id}\n"
        fmt += f"Name: {self.name}\n"
        fmt += f"Leader: {leader.mention}~**{leader.name}#{leader.discriminator}**\n"
        fmt += f":Description:\n{self.description}\n"
        fmt += "-------------------------------------------------\n"
        fmt += f":Players:\n{fmt}\n"
        fmt += "-------------------------------------------------\n"
        fmt += f":Event:\n{event}"
    async def initialize(self, *, data=None):
        if not data:
            data = await self.table.get_entry(self.id)
        self.name = data.name
        self.description = data.description
        self.leader = data.leader
        event = data.event_id
        if event:
            event_table = self.table.db.get_table("events")
            event_obj = Event(event_table, event)
            await event_obj.initialize()
            self.event = event_obj
        players = json.loads(data.players)
        self.players = players
        pending = json.loads(data.pending)
        self.pending = pending
        self._ready = True        



        