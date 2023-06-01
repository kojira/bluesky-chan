# bluesky-chan

This is a chatbot using gpt3.5 turbo of openai that works with python.

## startup

```sh
git clone https://github.com/kojira/bluesky-chan.git
cd bluesky-chan
cp .env.example .env
```

Change the contents of .env according to the environment.

```
OPENAI_API_KEY=your openai api key
BOT_HANDLE=bot handle(ex:kojira.bsky.social)
BOT_PASSWORD=bot password
```

Run with this command

```sh
docker compose up -d
```
