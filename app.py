from os import environ
import redis
from flask import Flask
from flask_discord_interactions import DiscordInteractions, Response
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
discord = DiscordInteractions(app)
rd = redis.StrictRedis(host='localhost', port=6379, db=0)

MSG_MATCH=""
MSG_DISMATCH=""
MSG_NOEXIST=""

app.config["DISCORD_CLIENT_ID"] = environ["ID"]
app.config["DISCORD_PUBLIC_KEY"] = environ["KEY"]
app.config["DISCORD_CLIENT_SECRET"] = environ["SECRET"]

@discord.command()
def verify(ctx, code: int):
    "마인크래프트 계정을 인증하여 디스코드 계정과 연동합니다."
    if rd.exists(ctx.author.display_name):
        realcode = rd.hget(ctx.author.display_name, "code").decode("UTF-8")
        uuid = rd.hget(ctx.author.display_name, "UUID").decode("UTF-8")
        if realcode == str(code):
            return Response(f"일치 {uuid}", ephemeral=True)
        else:
            return Response("불일치", ephemeral=True)
    else:
        return Response("미존재", ephemeral=True)

discord.set_route("/interactions")

discord.update_slash_commands(guild_id="330997213255827457")
