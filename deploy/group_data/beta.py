# frankfurt is a server-setup box: it deploys with that fleet's deploy key
ssh_user = "deploy"
ssh_key = "~/.ssh/deploy"

# the OS user, its group, the database, and the root of every path
name = "new_archon"
# which secrets/ file and directory
stage = "beta"
domain = "archon.krcg.org"
backend_port = 8008
bot_port = 9008
api_port = 7008
public_api = True

environment = "beta"
app_name = "Archon Beta"
vekn_push = "false"
twda_push = False
backend_env_extra = {}
public_api_env_extra = {}
