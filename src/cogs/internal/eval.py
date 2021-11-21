from discord.ext import commands
import textwrap
import io
import traceback
from contextlib import redirect_stdout
from jishaku.codeblocks import codeblock_converter

class eval(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_result = None
        
    def cleanup_code(self, content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])

        # remove `foo`
        return content.strip('` \n')

    @commands.command(name='eval')
    @commands.is_owner()
    async def eval(self, ctx,*,body: codeblock_converter):
        env = {
            'bot': self.bot,
            'ctx': ctx,
            'channel': ctx.channel,
            'author': ctx.author,
            'guild': ctx.guild,
            'message': ctx.message,
            '_': self._last_result,
            'import': __import__,
            "sys": __import__("sys"),
            "os": __import__("os"),
            "discord": __import__("discord"),
            "aiohttp": __import__("aiohttp"),
            "self": self.bot
        }

        env.update(globals())
        
        body = body.content
        stdout = io.StringIO()

        to_compile = f'async def func():\n{textwrap.indent(body, "  ")}'

        try:
            exec(to_compile, env)
        except Exception as e:
            return await ctx.send(f'```py\n{e.__class__.__name__}: {e}\n```')

        func = env['func']
        try:
            with redirect_stdout(stdout):
                ret = await func()
        except Exception as e:
            value = stdout.getvalue()
            await ctx.send(f'```py\n{value}{traceback.format_exc()}\n```')
        else:
            value = stdout.getvalue()
            try:
                await ctx.message.add_reaction('\u2705')
            except:
                pass

            if ret is None:
                if value:
                    await ctx.send(f'```py\n{value}\n```')
            else:
                self._last_result = ret
                await ctx.send(f'```py\n{value}{ret}\n```')

def setup(bot):
    bot.add_cog(eval(bot))
