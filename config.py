from os import environ
from dotenv import load_dotenv

load_dotenv()

TOKEN = environ['TOKEN']

SQL = {
    'host': "localhost",
    'port': 3306,
    'user': "root",
    'passwd': "",
    'db': "mcauth",
}

REDIS = {
    'host': "localhost",
    'port': 6379,
    'db': 0
}

COMMAND_PREFIX = '?'
STATUS_MESSAGE = "Hello World"

EMBED_COLOR = 15844367
GUILD_ID = 330997213255827457
NEWBIE_ROLE_ID = 867576011961139200
