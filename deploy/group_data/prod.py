name = "archon"
stage = "prod"
domain = "archon.vekn.net"
backend_port = 8007
bot_port = 9007
api_port = 7007
# api.archon.vekn.net has no DNS record: certbot would fail the deploy
public_api = False

environment = "production"
app_name = "Archon"
vekn_push = "true"
twda_push = True
# one async worker on a 1GB box: 8 backends keep the pool's memory bounded
backend_env_extra = {"DB_POOL_MAX_SIZE": 8, "VEKN_PUSH_INTERVAL_HOURS": 1}
public_api_env_extra = {"PUBLIC_API_DB_POOL_MAX_SIZE": 4}
