import re
import discord
import lavalink
from discord.ext import commands
import sr_api
import asyncio
from duration import to_seconds
import random

api = sr_api.Client()
url_rx = re.compile(r'https?://(?:www\.)?.+')

def convert(time: int):
    mins = time // 60
    time %= 60
    return '%d:%d' % (mins, time)

class LAVALINK(Exception):
    pass

class LavalinkVoiceClient(discord.VoiceClient):
    """
    This is the preferred way to handle external voice sending
    This client will be created via a cls in the connect method of the channel
    see the following documentation:
    https://diskord.readthedocs.io/en/master/api.html#voiceprotocol
    """

    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel
        # ensure there exists a client already
        if hasattr(self.client, 'lavalink'):
            self.lavalink = self.client.lavalink
        else:
            self.client.lavalink = lavalink.Client(client.user.id)
            self.client.lavalink.add_node(
                    'host',
                    2333,
                    'frenchpizza',
                    'us',
                    'default-node')
            self.lavalink = self.client.lavalink

    async def on_voice_server_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
                't': 'VOICE_SERVER_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def on_voice_state_update(self, data):
        # the data needs to be transformed before being handed down to
        # voice_update_handler
        lavalink_data = {
                't': 'VOICE_STATE_UPDATE',
                'd': data
                }
        await self.lavalink.voice_update_handler(lavalink_data)

    async def connect(self, *, timeout: float, reconnect: bool) -> None:
        """
        Connect the bot to the voice channel and create a player_manager
        if it doesn't exist yet.
        """
        # ensure there is a player_manager when creating a new voice_client
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel)

    async def disconnect(self, *, force: bool) -> None:
        """
        Handles the disconnect.
        Cleans up running player and leaves the voice client.
        """
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        # no need to disconnect if we are not connected
        if not force and not player.is_connected:
            return

        # None means disconnect
        await self.channel.guild.change_voice_state(channel=None)

        # update the channel_id of the player to None
        # this must be done because the on_voice_state_update that
        # would set channel_id to None doesn't get dispatched after the 
        # disconnect
        player.channel_id = None
        self.cleanup()

class music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        if not hasattr(bot, 'lavalink'):
            bot.lavalink = lavalink.Client(803405588993540147)
            bot.lavalink.add_node('localhost', 2333, 'youshallnotpass', 'eu', 'default-node')

        lavalink.add_event_hook(self.track_hook)

    def cog_unload(self) -> None:
        self.bot.lavalink._event_hooks.clear()

    async def cog_before_invoke(self, ctx) -> bool:
        guild_check = ctx.guild is not None
        if guild_check:
            await self.ensure_voice(ctx)
        return guild_check

    async def cog_command_error(self, ctx, error) -> None:
        if isinstance(error, commands.errors.CommandInvokeError):
            pass

    async def ensure_voice(self, ctx: commands.Context) -> None:
        player = self.bot.lavalink.player_manager.create(ctx.guild.id, endpoint=str(ctx.guild.region))
        should_connect = ctx.command.name in ('play', 'join')

        if not ctx.author.voice or not ctx.author.voice.channel:
            ctx.command.reset_cooldown(ctx)
            return await ctx.message.reply(
                content='You must be a voice channel to use this command!',
                mention_author=False)

        if not player.is_connected:
            if not should_connect:
                ctx.command.reset_cooldown(ctx)
                return await ctx.message.reply(
                    content='I am currently not connected to any voice channel.',
                    mention_author=False)

            permissions = ctx.author.voice.channel.permissions_for(ctx.me)

            if not permissions.connect or not permissions.speak:
                ctx.command.reset_cooldown(ctx)
                return await ctx.message.reply(
                    content='I am missing `CONNECT` or `SPEAK` permissions!',
                    mention_author=False)

            player.store('channel', ctx.channel.id)

            await ctx.author.voice.channel.connect(cls=LavalinkVoiceClient)

            await asyncio.sleep(1)  ## Kept joining way too fast.
            await ctx.message.reply(
                'Connected to **%s** and bound to **%s**!' % (ctx.me.voice.channel, ctx.channel),
                mention_author=False
            )

        else:
            if int(player.channel_id) != ctx.author.voice.channel.id:
                ctx.command.reset_cooldown(ctx)
                return await ctx.message.reply(
                    content='You need to be in the same voice channel as me!',
                    mention_author=False
                )

    async def track_hook(self, event) -> any:
        if isinstance(event, lavalink.events.QueueEndEvent):
            await asyncio.sleep(30)
            if event.player.is_playing:
                return
            guild_id = int(event.player.guild_id)
            ctx = event.player.fetch('ctx')
            if ctx:
                try:
                    await ctx.send('Left **%s** because I am no longer playing anything.' % ctx.me.voice.channel)
                except AttributeError:
                    await ctx.send('Left the channel because i am no longer playing anything.')

            event.player.delete('ctx')
            guild = self.bot.get_guild(guild_id)
            await guild.voice_client.disconnect(force=True)

        if isinstance(event, lavalink.events.TrackStartEvent):
            ctx = event.player.fetch('ctx')
            track = event.track

            if ctx and not event.player.repeat:
                await ctx.send('Now playing **%s** requested by **%s**' % (
                    track.title, ctx.guild.get_member(int(track.requester))))

        if isinstance(event, lavalink.events.TrackStuckEvent):
            ctx = event.player.fetch('ctx')

            if ctx:
                await ctx.send('An error has occured whilst playing your track!')

    @staticmethod
    async def pretty_convert(num) -> str:
        if num >= (60 * 60):
            hours = num // (60 * 60)
            num %= (60 * 60)
            mins = num // 60
            num %= 60
            return '{}:{}:{}'.format(hours, mins, num)
        elif num > 60:
            mins = num // 60
            num %= 60
            return '{}:{}'.format(mins, num)
        else:
            return '00:{}'.format(num)

    @commands.command()
    @commands.bot_has_guild_permissions(connect=True)
    async def join(self, ctx):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if ctx.author.voice:
            await ctx.message.add_reaction('🎵')
            return await self.ensure_voice(ctx)
        if player.is_connected:
            return await ctx.send("I am already connected to a Voice Channel")
        await ctx.send("You need to be connected to a Voice Channel")

    @commands.command(aliases=['dc', 'leave'])
    async def disconnect(self, ctx: commands.Context):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_connected:
            return await ctx.message.reply(
                content='I am not connected to any voice channels!',
                mention_author=False)

        if not ctx.author.voice or (player.is_connected and ctx.author.voice.channel.id != int(player.channel_id)):
            return await ctx.message.reply(
                content='Your not connected in the same VC as me!',
                mention_author=False)

        channel = ctx.me.voice.channel
        player.queue.clear()
        await player.reset_equalizer()
        await player.set_volume(100)
        player.repeat = False
        await player.stop()
        await ctx.voice_client.disconnect(force=True)

        await ctx.message.reply(
            content='Successfully disconnected from **%s**.' % channel.name,
            mention_author=False)

    @commands.command()
    @commands.bot_has_guild_permissions(connect=True, speak=True)
    async def play(self, ctx, *, query: str = None) -> None:
        if not query:
            return await ctx.send("Please give a song to play")
        try:
            async with ctx.typing():
                player = self.bot.lavalink.player_manager.get(ctx.guild.id)
                await self.ensure_voice(ctx)
                query = query.strip('<>')
                if query.lower().startswith('soundcloud'):
                    query = f'scsearch:{query.lower().split("soundcloud")[-1]}'
                elif not url_rx.match(query):
                    query = f'ytsearch:{query}' #scsearch: query
                results = await player.node.get_tracks(query)
                if not results or not results['tracks']:
                    query = f"scsearch: {query}"
                    results = await player.node.get_tracks(query)
                    if not results or not results['tracks']:
                        return await ctx.send("No songs was found")

                if results['loadType'] == 'PLAYLIST_LOADED':
                    tracks = results['tracks']

                    for track in tracks:
                        player.add(requester=ctx.author.id, track=track)

                    em = discord.Embed(color=discord.Color.blurple(), title='Playlist Enqueued!', description=f'```{results["playlistInfo"]["name"]} - {len(tracks)} tracks```').set_author(name=ctx.author, icon_url=ctx.author.display_avatar.url)
                else:
                    track = results['tracks'][0]
                    em = discord.Embed(color=discord.Color.blurple(), title="Track Enqueued!", description="```{}```".format(track["info"]["title"]))
                    em.set_author(name=ctx.author, icon_url=ctx.author.display_avatar.url)
                    em.add_field(name="Requested By", value=ctx.author.mention)
                    em.add_field(name="URL", value="[Here]({})".format(track["info"]["uri"]))

                    track = lavalink.models.AudioTrack(track, ctx.author.id, recommended=True)
                    player.add(requester=ctx.author.id, track=track)

            await ctx.send(embed=em)

            if not player.is_playing:
                await player.play()
        except asyncio.TimeoutError:
            await ctx.send("Lavalink player had an error. Please try again later.")

    @commands.command()
    async def queue(self, ctx) -> None:
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if not player.queue:
            return await ctx.send("Empty queue")
        embed = discord.Embed(title='Queue - ({})'.format(len(player.queue)),
                              colour=discord.Colour.red(),
                              timestamp=ctx.message.created_at)
        embed.set_author(name=self.bot.user.display_name, icon_url=self.bot.user.display_avatar.url)
        embed.set_footer(text='Requested by {}'.format(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.description='\n'.join(
            ['`{}.` [{}]({})'.format(
                player.queue.index(i)+1, i.title, i.uri) for i in player.queue])
        await ctx.send(embed=embed)

    @commands.command()
    async def loop(self, ctx) -> None:
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if not player.repeat:
            player.repeat = True
            await ctx.send("Looping enabled")
            await ctx.message.add_reaction('🔁')
        else:
            player.repeat = False
            await ctx.send("Looping disabled")
            await ctx.message.add_reaction('🔂')

    @commands.command()
    async def skip(self, ctx) -> None:
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if not player.is_playing:
            return await ctx.send("There is nothing to skip!")
        await player.skip()
        await ctx.send("Successfully skipped the current track")

    @commands.command()
    async def pause(self, ctx) -> None:
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if not player.is_playing:
            ctx.command.reset_cooldown(ctx)
            return await ctx.send("I am not playing anything")
        if not player.paused:
            await player.set_pause(True)
            await ctx.message.add_reaction('⏸️')
            await ctx.send("Successfully paused the track")
        else:
            await ctx.send("The track was paused. To resume, use the `resume` command")

    @commands.command()
    async def resume(self, ctx) -> None:
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        await player.set_pause(False)
        await ctx.message.add_reaction('⏯️')
        await ctx.message.reply("Successfully resumed the track")

    @commands.command(aliases=['sv', 'vol'])
    async def volume(self, ctx, vol: str) -> None:
        try:
            vol = int(vol)
        except ValueError:
            return await ctx.send("Volume must be a number")
        if vol not in range(0, 101):
            return await ctx.message.reply("Volume can only be in a range of **0-100**")
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        await player.set_volume(vol)
        await ctx.message.add_reaction('📶')
        await ctx.message.reply('Volume set at **{}**%.'.format(vol))

    @commands.command()
    async def current(self, ctx):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if not player.is_playing:
            await ctx.send("I am not playing anything")
            return

        em=discord.Embed(title="Current Track", description=f"[{player.current.title}](https://youtube.com/watch?v={player.current.identifier})", color=discord.Color.blue())
        await ctx.send(embed=em)

    @commands.command()
    async def shuffle(self, ctx):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.queue:
            return await ctx.message.reply(
                content='I am currently not playing anything!',
                mention_author=False)

        queue = player.queue
        random.shuffle(queue)
        player.queue = queue

        await ctx.message.reply(
            content='Shuffled the queue for you.',
            mention_author=False)

    @commands.command()
    async def seek(self, ctx, *, time: str):
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)

        if not player.is_playing:
            ctx.command.reset_cooldown(ctx)
            return await ctx.message.reply(
                content='I am currently not playing anything!',
                mention_author=False)
        try:
            seconds = to_seconds(time, strict=False)
        except Exception:
            return await ctx.send(
                'Failed to parse the time, please use a valid format! And make sure it is not in negatives.')
        as_milli = seconds * 1000

        if as_milli > player.current.duration:
            return await ctx.send('This time duration is larger than the song duration!')

        await player.seek(as_milli)
        return await ctx.message.reply(
            content='Moved to postion **%s** of the track!' % await self.pretty_convert(int(seconds)),
            mention_author=False
        )

def setup(bot):
    bot.add_cog(music(bot))
