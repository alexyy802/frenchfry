import discord
from discord import commands

bot = commands.Bot(command_prefix="f!")

@bot.event
async def on_ready():
  print('===[FrenchFry]===')
  print(f'Logged in as {bot.user}')
  
@bot.command()
async def ping(ctx):
  await ctx.send('Pong!')
  
bot.run('token')
