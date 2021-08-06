from os import environ
from dotenv import load_dotenv

load_dotenv()

TOKEN = environ['TOKEN']

SQL = {
    'host': "localhost",
    'port': 3306,
    'user': "root",
    'password': "",
    'db': "mcauth",
}

COMMAND_PREFIX = '?'
STATUS_MESSAGE = "Hello World"

GUILD_ID = 330997213255827457
NEWBIE_ROLE_ID = 867576011961139200
