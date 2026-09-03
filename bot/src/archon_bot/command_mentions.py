import lightbulb

_client: lightbulb.Client | None = None


def bind(client: lightbulb.Client) -> None:
    global _client
    _client = client


def command_mention(name: str) -> str:
    if _client is not None:
        for commands in _client.created_commands.values():
            for command in commands:
                if command.name == name:
                    return f"</{name}:{command.id}>"
    return f"/{name}"
