import discord
import asyncio
import datetime
import dateparser
import json
import configparser
import traceback
from utils import Manager, Visualizer, is_admin,check_guild_permissions, convert_to_utc
from consts import StaticParty, Event, Player,Templates
from discord.ext import commands


config = configparser.ConfigParser()
config.read(['default.ini', 'config.ini'])

BOT_PREFIX = config["Discord"]["Prefix"]
BOT_TOKEN = config["Discord"]["Token"]
CHANNEL = int(config["Discord"]["AnnouncementChannel"])
bot = commands.Bot(command_prefix= BOT_PREFIX)

manager = Manager(bot)

CACHE = None

bot.remove_command("help")
bot.load_extension("misc")

def update_cache(data):
    global CACHE
    CACHE = data
@bot.event
async def on_ready():
    print("Bot Online.")
    global CACHE
    if not CACHE:
        channel = discord.utils.get(bot.get_all_channels(), id=CHANNEL)
        if not channel:
            return
        logs = await channel.history(limit=None).flatten()
        CACHE = logs

@bot.event
async def on_raw_reaction_add(payload):

    channel = discord.utils.get(bot.get_all_channels(), id = CHANNEL)
    if not channel:
        return
    message_id = payload.message_id
    user_id = payload.user_id
    channel_id = payload.user_id
    if channel.id != payload.channel_id:
        return
    if str(payload.emoji) != "✅":
        return
    events = await manager.events.get_entries("started='False' AND ended='False'")

    found = None
    for event in events:
        if not event.message:
            continue
        if event.message == message_id:
            found = event
            break

    if not found:
        return
    added = False
    member = discord.utils.get(bot.get_all_members(), id=user_id)
    fmt = None
    if user_id in found.pending:
        fmt = "You have already been added to the Attending List."
        added = True

    if not added:
        found.pending.append(user_id)
        data = json.dumps(found.pending)

        await found.table.update(found.id, pending = data)

    check = discord.utils.get(CACHE, id=message_id)
    c_pass = False
    if check:
        try:
            await check.remove_reaction(payload.emoji, discord.Object(id=payload.user_id))
        except:
            pass
        c_pass=True 
    if member:
        fmt = "You have been added to the Attending List for Event {found.id}. Please click on =event attend once the event starts in order to let me know you are attending the event."
        await member.send(fmt)
    if c_pass:
        return
    logs = await channel.history(limit = None).flatten()
    update_cache(logs)
    check = discord.utils.get(cache, id=message_id)
    if check:
        try:
            await check.remove_reaction(payload.emoji, discord.Object(id=payload.user_id))
        except:
            pass

async def event_announcer():
    await manager.initialize()
    await bot.wait_until_ready()

    while not bot.is_closed():
        channel = discord.utils.get(bot.get_all_channels(), id = CHANNEL)

        events = await manager.events.get_entries("ended = 'False' AND alert = 'False'")
        checklist2 = await manager.events.get_entries("started='False' AND alert='True'")
        try:
            await monitor_alert(events, channel)
            await monitor_start(checklist2, channel)
        except Exception as e:
            traceback.print_exc()
        await asyncio.sleep(1)

async def monitor_alert(events, channel):
    for i in events:
        event = Event(manager.events,int(i.id))
        await event.initialize()
        wait_list = event.attended
        now = datetime.datetime.utcnow()
        diff = event.timestamp - now
        seconds = diff.total_seconds()
        check = seconds <= 900 and (not event.alert) and bool(event.party)
        if not check:
            continue
        content = f"Event: {event.id} Linked to {name} {event.party.id} is going to start in 15 minutes!"
        name = "Team" if event.party._static else "Party"
        for member in wait_list:
            user = discord.utils.get(bot.get_all_members(), id=int(member))
            if user:
                try:
                    await user.send(content, embed = event.embed(bot))
                except:
                    pass
        try:
            if channel:
                await channel.send(f"@here, {content}", embed = event.embed(bot))
        except:
            pass

        await event.table.update_entry(event.id, alert=True)

async def monitor_start(events, channel):
    for i in events:
        event = Event(manager.events,int(i.id))
        await event.initialize()
        wait_list = event.attended
        now = datetime.datetime.utcnow()
        diff = event.timestamp - now
        seconds = diff.total_seconds()
        check = seconds <= 0 and (not event.started) and bool(event.party)
        if not check:
            continue
        content = f"Event: {event.id} Linked to {name} {event.party.id} has Started!"
        name = "Team" if event.party._static else "Party"
        for member in wait_list:
            user = discord.utils.get(bot.get_all_members(), id=int(member))
            if user:
                try:
                    await user.send(content, embed = event.embed(bot))
                except:
                    pass
        try:
            if channel:
                await channel.send(f"@here, {content}", embed = event.embed(bot))
        except:
            pass

        await event.table.update_entry(event.id, started=True)

@bot.command(name="profile")
async def prof(ctx, user:discord.Member=None):
    """Views Your Profile, Mentioning another user views their profile"""
    if not user:
        user = ctx.author

    obj = await manager.get_player(user.id)

    embed = obj.embed(bot)

    await ctx.send(embed = embed)

@is_admin()
@bot.command(name="editattendence")
async def edit_attendence(ctx, player_id:int, value:int):
    """Edits the Attendence of a player
    Usage:
    !editattendence 12345678932 40"""
    if value<0:
        value=0
    if value>100:
        value =100

    obj = await manager.get_player(int(player_id))

    await obj.table.update_entry(obj.id, attendence = value)

    await ctx.send(f"Set Player(ID {player_id})'s Attendence to {value}")
@bot.group(name="event")
async def ev(ctx):
    """Event Related Commands. Do !help event to know more."""
    if not ctx.invoked_subcommand:
        return await ctx.send(f"Please mention what you would like to do. for more info do {ctx.prefix}event")


@is_admin()
@ev.command(name="viewlist")
async def _view_ev_list(ctx, event_id):
    event = await manager.get_event(event_id)
    if not event:
        return await ctx.send(f"Event (ID: {event_id}) Not Found.")

    pending = []
    for i in event.pending:
        user = discord.utils.get(bot.get_all_members(), id=int(i))
        if user:
            pending.append(f"{user.mention} ~{user.name}#{user.discriminator}")
        else:
            pending.append(f"Not Found(ID : {i})")
    attending = []
    for i in event.attended:
        user = discord.utils.get(bot.get_all_members(), id=int(i))
        if user:
            attending.append(f"{user.name}#{user.discriminator}")
        else:
            attending.append(f"Not Found(ID : {i})")
    e = discord.Embed()
    e.colour = discord.Colour.blue()
    e.title = "Event Statistics"
    e.description = f"Pending: {len(event.pending)}\nAttended: {len(event.attended)}"
    e.add_field(name="Pending", value = ", ".join(pending) or "No Users.", inline=False)
    e.add_field(name="Attended", value= ", ".join(attending) or "No Users.", inline=False)
    await ctx.send(embed= e)

@ev.command(name="view")
async def _view_ev(ctx, *ids):
    """View Events
    Options:
    passing IDs will show those events. Example 1 2 3
    passing 'all' will show all events which have not started yet
    """
    if not ids:
        return await ctx.send("Please give some ids to view those events")
    if len(ids) == 1 and ids[0] != "all":
        event = await manager.get_event(ids[0])
        return await ctx.send(embed = event.embed(bot))
    if ids[0] == "all":
        events = await manager.events.get_entries("started = 'False'")
        fmt = []
        for i in events:
            foo = Event(manager.events, i.id)
            await foo.initialize()
            fmt.append(foo)
        events = fmt
    else:
        events = await manager.get_events(ids)
    reactor = Visualizer(bot, ctx, events)
    await reactor.start()

@is_admin()
@ev.command(name="announce")
async def _ev_announce(ctx, event_id : int, *, description:str=None):
    event = await manager.get_event(event_id)
    if not event:
        return await ctx.send(f"Event (ID: {event_id}) Not Found.")

    if event.message:
        await ctx.send("Event has an assigned message, Changing.....")

    fmt = "@here, A New Event is Starting. React with the ✅ Emoji to Attend."
    if description:
        fmt = f"@here, {description}"

    channel = discord.utils.get(bot.get_all_channels(), id=CHANNEL)
    if not channel:
        return await ctx.send("No Channel has been set up!")

    message = await channel.send(fmt, embed = event.embed(bot))
    await message.add_reaction("✅")
    await event.table.update_entry(event.id, message= message.id)

    await ctx.send("Added an Announcer.")

@is_admin()
@ev.command(name = "create")
async def _create_ev(ctx, id, *, timestamp = None):
    """Create an Event"""
    check = await manager.get_event(int(id))
    if check:
        return await ctx.send(f"An Event exists with the ID: {id}. Please choose another ID")
    table = manager.events
    fut = Templates.EVENT
    fut["id"] = int(id)
    fut["leader"] = ctx.author.id
    if timestamp:
        value = dateparser.parse(timestamp)
        if not value:
            return await ctx.send("Timestamp Not Recognized")
        fut["timestamp"] = timestamp.isoformat()
    await table.add_entry(**fut)

    obj = Event(manager.events, id)
    await obj.initialize()
    await ctx.send(f"An Event has been created with ID {id}", embed = obj.embed(bot))
@is_admin()
@ev.command(name="checkid")
async def _ev_check(ctx, id):
    check = await manager.get_event(int(id))
    if not check:
        return await ctx.send(f"ID : {id} is available to create an Event!")
    await ctx.send(f"ID {id} has been taken!")
@is_admin()
@ev.command(name="edit")
async def _edit_ev(ctx,event_id, name, *, value):
    """Edit an Event.
    List of keys which can be editted: name, description, timestamp, max"""
    obj = await manager.get_event(int(event_id))

    if not obj:
        return await ctx.send(f"Event (ID: {event_id}) Not Found.")
    table = obj.table
    slot = ["name", "description", "timestamp", "max"]
    if not name in slot:
        return await ctx.send("You can only change the name, description, max (max members) and timestamp of the Event")
    if name == 'timestamp':
        value = dateparser.parse(value)
        if not value:
            return await ctx.send("Timestamp Not Recognized")
        value = convert_to_utc(value)
        value = str(value.isoformat())
    if name == 'max':
        value = int(value)
    pl = {name:value}
    await table.update_entry(int(obj.id), **pl)

    await ctx.send(f"Set the **{name}** for the Event (ID {event_id}) to: {str(value)}")


async def update_attendence(event_id):
    event = await manager.get_event(event_id)
    attendence = event.attended
    not_attended = event.pending
    for i in attendence:
        player = await manager.get_player(int(i))
        a = int(player.attendence) + 2
        player.attended.append(int(event_id))
        payload = player.to_json()
        if a>100:
            a = 100
        await player.table.update_entry(int(i), attendence = a, attended = payload["attended"])
    for i in not_attended:
        player = await manager.get_player(int(i))
        a = int(player.attendence) - 2
        player.not_attended.append(int(event_id))
        payload = player.to_json()
        if a>100:
            a = 100
        await player.table.update_entry(int(i), attendence = a, not_attended = payload["not_attended"])

async def add_attended(event_id, player_id):

    obj = await manager.get_event(event_id)
    attrs = {}
    if player_id in obj.pending:
        obj.pending.remove(player_id)
        attrs["pending"] = json.dumps(obj.pending)
    obj.attended.append(player_id)
    attrs["attended"] = json.dumps(obj.attended)

    await obj.table.update_entry(obj.event.id, **attrs)



@ev.command(name="end")
async def _end_pt_ev(ctx, event_id):
    """Ends an event and distributes the attendence automatically.
    Admins and Party Leaders can only use this command"""
    obj = await manager.get_event(int(event_id))
    if not obj:
        return await ctx.send(f"Event (ID: {event_id}) Not Found.")
    leader = obj.leader

    check1 = int(leader) == ctx.author.id
    check2 = await check_guild_permissions(ctx, {'administrator': True})
    if not (check1 or check2):
        return await ctx.send("You need to be the Event Leader or an Admin in order to edit this Event.")
    table = obj.table

    await table.update_entry(int(obj.id), ended=True)
    await update_attendence(obj.id)
    if obj.party:
        await obj.table.update_entry(int(obj.party.id), event_id = None)

    await ctx.send(f"Ended the Event (ID {obj.id})")

@ev.command(name="notattending")
async def _ev_not_attending(ctx, event_id):
    """Set Yourself on **Not Attending** for an **Event**"""
    obj = await manager.get_event(event_id)
    if obj.party:
        return await ctx.send("This Event is linked to a Team. Please use =team notattending to cancel that team's Event.")
    if not obj:
        return await ctx.send(f"Event (ID: {party_id}) Not Found.")
    event = obj
    if not ctx.author.id in (obj.pending + obj.attended):
        return await ctx.send("You are not in the Attending List for this Event.")
    if event.ended:
        return await ctx.send(f"Event {obj.id} has already Ended!")
    if event.started:
        deduct = 2
    if not event.started:
        deduct = 1
    player = await manager.get_player(ctx.author.id)
    at = player.attendence
    at = at - deduct
    if at <0: at = 0
    attrs = {}
    if ctx.author.id in obj.attended:
        obj.attended.remove(ctx.author.id)
        attrs["attended"] = json.dumps(obj.attended)
    if ctx.author.id in obj.pending:
        obj.pending.remove(ctx.author.id)
        attrs["pending"] = json.dumps(obj.pending)
    if attrs:
        await obj.table.update_entry(obj.id, **attrs)
    await player.table.update_entry(player.id, attendence = at)

    await ctx.send("✅")
@ev.command(name="attend")
async def _pt_attend(ctx, event_id:int):
    """Set Yourself on **Attending** for an **Event**"""
    obj = await manager.get_event(event_id)
    if obj.party:
        return await ctx.send("This Event is linked to a Team. Please use =team attend to join that team's Event.")
    if not obj:
        return await ctx.send(f"Event (ID: {party_id}) Not Found.")

    event = obj
    if event.ended:
        return await ctx.send(f"Event {obj.id} has already Ended!")
    if not event.started:
        return await ctx.send(f"Event {obj.id} has not started yet!")
    wait_list = obj.attended
    if ctx.author.id in wait_list:
        return await ctx.send("You are already attending this Event.")
    if len(obj.attended) == int(obj.max):
        return await ctx.send("This Event has reached it's max threshold for Players")
    await add_attended(obj.id, ctx.author.id)

    await ctx.send(f"You have been added to the list of Attending Players to Event (ID:{obj.id})")



@bot.group(name="team")
async def spt(ctx):
    if not ctx.invoked_subcommand:
        return await ctx.send(f"Please mention what you would like to do. for more info do {ctx.prefix}team")

@spt.command(name="view")
async def _view_spt(ctx, *ids):
    """"""
    if not ids:
        return await ctx.send("Please give some ids to view those teams.")
    if len(ids) == 1 and ids[0].lower() != "all":
        party = await manager.get_static_party(ids[0])
        if not party:
            return await ctx.send("Team does not Exist")
        return await ctx.send(embed = party.embed(bot))
    if ids[0].lower() == "all":
        events = await manager.get_all_static_parties()
    if len(ids)> 1:
        events = await manager.get_static_parties(ids)
    if not events:
        return await ctx.send("IDs do not Exist")
    reactor = Visualizer(bot, ctx, events)
    await reactor.start()

@is_admin()
@spt.command(name = "create")
async def _create_spt(ctx, id):
    """"""
    check = await manager.get_static_party(int(id))
    if check:
        return await ctx.send(f"A Team exists with the ID: {id}. Please choose another ID")
    table = manager.static_party
    fut = Templates.STATIC_PARTY
    fut["id"] = int(id)
    fut["leader"] = ctx.author.id
    fut["players"] = f'[{ctx.author.id}]'
    await table.add_entry(**fut)

    obj = StaticParty(manager.static_party,id)
    await obj.initialize()
    await ctx.send(f"A Team has been created with ID **{id}**", embed = obj.embed(bot))

@is_admin()
@spt.command(name="link")
async def _link_spt_ev(ctx, party_id, event_id):
    party = await manager.get_static_party(int(party_id))
    event = await manager.get_event(int(event_id))

    if not party:
        return await ctx.send(f"Team (ID {party_id}) Not Found.")

    if not event:
        return await ctx.send(f"Event (ID {event_id}) Not Found.")

    if party.event:
        return await ctx.send(f"Team (ID {party_id}) already has an event assigned to it. Mark the event in the party as completed in order to get it unlinked.")
    
    if not event.timestamp:
        return await ctx.send("Please assign a timestamp to the event before linking it.")
    await party.table.update_entry(party.id, event_id = event.id)
    await event.table.update_entry(event.id, pending = json.dumps(party.players))
    await ctx.send(f"Linked Event (ID {event_id}) to Team (ID {party_id})")


@spt.command(name="edit")
async def _edit_spt(ctx,party_id, name, *, value):
    """Edit your Team's Info. """
    obj = await manager.get_static_party(int(party_id))

    if not obj:
        return await ctx.send(f"Team (ID: {party_id}) Not Found.")

    leader = obj.leader

    check1 = int(leader) == ctx.author.id
    check2 = await check_guild_permissions(ctx, {'administrator': True})
    if not (check1 or check2):
        return await ctx.send("You need to be the Team Leader or an Admin in order to edit this Team.")
    table = obj.table
    slot = ["name", "descrisption"]
    if not name in slot:
        return await ctx.send("You can only change the name, descrisption and timestamp of the Event")
    pl = {name:str(value)}
    await table.update_entry(int(obj.event.id), **pl)

    await ctx.send(f"Set the **{name}** for the Team (ID {party_id}) to: {str(value)}")

@spt.command(name = "setleader")
async def _set_spt_leader(ctx, user:discord.Member=None, party_id=None):
    """Change the Leader of your Team.
    Admins can change the leaders of any teams provided they give the team id."""
    if party_id:
        obj = await manager.get_static_party(int(party_id))
    else:
        player = await manager.get_player(ctx.author.id)
        obj = player.static_party
    if not obj:
        return await ctx.send(f"Team (ID: {party_id}) Not Found.")
    check1 = int(leader) == ctx.author.id
    check2 = await check_guild_permissions(ctx, {'administrator': True})

    if (not check2) and party_id:
        return await ctx.send("You need to be an admin to execute that command.")
    if not (check1 or check2):
        return await ctx.send("You need to be the Team Leader or an Admin in order to edit this Team.")
    leader = obj.leader
    fmt = f"Set Team Leader to {user.mention} (ID: {user.id})"
    if leader:
        prev = discord.utils.get(bot.get_all_members(), id=int(leader))
        if prev:
            fmt = f"Set Team Leader from {prev.mention} (ID {prev.id}) to {user.mention} (ID {user.id})"
    await obj.table.update_entry(obj.id, leader = int(user.id))
    await ctx.send(fmt)

@spt.command(name = "join")
async def _join_spt(ctx, party_id):
    """Request to Join a Team"""
    obj = await manager.get_static_party(int(party_id))

    player = await manager.get_player(ctx.author.id)

    if player.static_party:
        return await ctx.send("You are already in a Team.")
    if not obj:
        return await ctx.send(f"Team (ID: {party_id}) Not Found.")

    if len(obj.players) == 6:
        return await ctx.send("This Team is Full. Please join a new one")
    if ctx.author.id in obj.players:
        return await ctx.send("You are already in this party!")

    obj.pending.append(ctx.author.id)

    load = obj.to_json()

    data = load["pending"]

    await obj.table.update_entry(obj.id, pending = data)

    await ctx.send(f"You have been add to the Pending List Team (ID: {party_id})")

@spt.command(name = "add")
async def _add_spt_player(ctx, player_id:int=None):
    """Adds a Player from the list of Pending list. If nothing is passed shows the Pending List"""
    check2 = await check_guild_permissions(ctx, {'administrator': True})
    player = await manager.get_player(ctx.author.id)
    if not player.static_party:
        return await ctx.send("You are not in a Team to begin with.")

    party_id = player.static_party.id
    obj = await manager.get_static_party(int(party_id))

    fmt = []
    for i in obj.pending:
        user = discord.utils.get(bot.get_all_members(), id = int(i))
        if not user:
            fmt.append(f"Not Found (ID {i})")
        else:
            fmt.append(f"{user.mention}")
    true = ", ".join(fmt)

    check1 = int(leader) == ctx.author.id
    if not (check1 or check2):
        return await ctx.send("You need to be the Team Leader or an Admin in order to execute this command.")
    if not obj:
        return await ctx.send(f"Team (ID: {party_id}) Not Found.")
    if not player_id:
        return await ctx.author.send(f"Pending List for Team (ID {party_id}): {fmt}")

    if len(obj.players) == 6:
        return await ctx.send("This Team is already full.")
    leader = obj.leader
    
    if not int(player_id) in obj.pending:
        await ctx.send("That player ID is not in this Team's Pending List!")
        return await ctx.author.send(f"Pending List for Team (ID {party_id}): {fmt}")

    obj.pending.remove(player_id)
    obj.players.append(player_id)

    load = obj.to_json()

    newpending = load["pending"]
    newlist = load["players"]

    await obj.table.update_entry(obj.id, players = newlist, pending=newpending)

    await ctx.send(f"Added Player (ID {player_id}) to Team (ID {party_id})")

@spt.command(name="leave")
async def _leave_spt(ctx):
    """Leave your assigned Team."""
    player = await manager.get_player(ctx.author.id)
    if not player.static_party:
        return await ctx.send("You are not in a Team to begin with.")

    party_id = player.static_party.id
    obj = await manager.get_static_party(int(party_id))

    if not obj:
        return await ctx.send(f"Team (ID: {party_id}) Not Found.")

    if not ctx.author.id in obj.players:
        return await ctx.send("You are not in that team.")
    obj.players.remove(ctx.author.id)

    load = obj.to_json()

    data = load["players"]

    await obj.table.update_entry(obj.id, players = load)

    await ctx.send(f"You have left Team (ID: {party_id})")

@spt.command(name = "kick")
async def kick_pl(ctx, player_id:int, party_id :int =None):
    """Kicks a Player from your Team"""
    check1 = int(leader) == ctx.author.id
    check2 = await check_guild_permissions(ctx, {'administrator': True})
    if not (check1 or check2):
        return await ctx.send("You need to be the Team Leader or an Admin in order to execute this command.")

    if (not check2) and party_id:
        return await ctx.send("You need to be an Admin to execute this command.")
    if not party_id:
        player = await manager.get_player(ctx.author.id)
        if not player.static_party:
            return await ctx.send("You are not in a Team to begin with.")

        party_id = player.static_party.id
    obj = await manager.get_static_party(int(party_id))

    if not obj:
        return await ctx.send(f"Team (ID: {party_id}) Not Found.")

    leader = obj.leader
    if not int(player_id) in obj.players:
        return await ctx.send("That player ID is not in this party!")

    obj.players.remove(player_id)

    load = obj.to_json()

    data = load["players"]

    await obj.table.update_entry(obj.id, players = load)

    await ctx.send(f"Kicked Player (ID {party_id}) from Team (ID {player_id})")
@spt.command(name="attend")
async def _spt_attend(ctx):
    """Set Yourself on **Attending** for a **Team Event**"""
    player = await manager.get_player(ctx.author.id)
    if not player.static_party:
        return await ctx.send("You are not in a Team to begin with.")

    party_id = player.static_party.id
    obj = await manager.get_static_party(int(party_id))

    if not obj:
        return await ctx.send(f"Team (ID: {party_id}) Not Found.")

    if not ctx.author.id in obj.players:
        return await ctx.send("You are not in that team.")

    if not obj.event:
        return await ctx.send(f"Team ({obj.id}) currently has no scheduled events!")
    if obj.event.started:
        return await ctx.send(f"Event {obj.event.id} Linked to Team {party_id} has already started!")
    wait_list = obj.event.attended

    if ctx.author.id in wait_list:
        return await ctx.send("You are already attending this Event.")

    await add_attended(obj.event.id, ctx.author.id)

    await ctx.send(f"You have been added to the list of Attending Players to Event (ID:{obj.event.id}) of Team (ID: {party_id})")

@spt.command(name="endevent")
async def _end_spt_ev(ctx, party_id):
    """Ends an event and distributes the attendence automatically.
    Admins and Party Leaders can only use this command"""
    obj = await manager.get_static_party(int(party_id))
    if not obj:
        return await ctx.send(f"Team (ID: {party_id}) Not Found.")
    leader = obj.leader

    check1 = int(leader) == ctx.author.id
    check2 = await check_guild_permissions(ctx, {'administrator': True})
    if not (check1 or check2):
        return await ctx.send("You need to be the Party Leader or an Admin in order to edit the Event for this Party.")

    if not obj.event:
        return await ctx.send("This Team doesn't have an assigned Event. Please ask an admin to link one.")
    table = obj.event.table

    await table.update_entry(int(obj.event.id), ended=True)
    await update_attendence(obj.event.id)
    await obj.table.update_entry(int(obj.id), party_id = None)

    await ctx.send(f"Ended the Event (ID {obj.event.id}) for Team (ID {obj.id})")

@is_admin()
@spt.command(name="checkid")
async def _spt_check(ctx, id):
    check = await manager.get_static_party(int(id))
    if not check:
        return await ctx.send(f"ID : {id} is available to create a Team!")
    await ctx.send(f"ID {id} has been taken!")

bot.loop.create_task(event_announcer())
bot.run(BOT_TOKEN)