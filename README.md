# Gumloop Python Client

A Python client for the Gumloop API that makes it easy to run and monitor Gumloop flows.

## Installation

```bash
pip install gumloop
```

## Usage

```python
from gumloop import GumloopClient

# Initialize the client
client = GumloopClient(
    api_key="your_api_key",
    user_id="your_user_id"
)

# Run a flow and wait for outputs
output = client.run_flow(
    flow_id="your_flow_id",
    inputs={
        "recipient": "example@email.com",
        "subject": "Hello",
        "body": "World"
    }
)

print(output)
```

## Run a Flow with Tweet Data

Gumloop flow inputs can include lists and nested objects. This example loads a
[TweetClaw](https://github.com/Xquik-dev/tweetclaw) JSON export and passes the
tweet text into a flow for enrichment, routing, or review:

```python
import json
from pathlib import Path

from gumloop import GumloopClient


def load_tweet_text(path: str) -> list[str]:
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(records, dict):
        if "tweets" in records:
            tweets = records["tweets"]
        elif "data" in records:
            tweets = records["data"]
        elif "results" in records:
            tweets = records["results"]
        else:
            tweets = [records]
    else:
        tweets = records

    if not isinstance(tweets, list):
        return []

    return [
        item["text"]
        for item in tweets
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    ]


client = GumloopClient(
    api_key="your_api_key",
    user_id="your_user_id",
)

output = client.run_flow(
    flow_id="your_flow_id",
    inputs={
        "tweets": load_tweet_text("tweetclaw-export.json"),
        "source": "TweetClaw",
    },
)

print(output)
```

## Chat with an agent (streaming)

```python
import asyncio

from gumloop import AsyncGumloop


async def main() -> None:
    async with AsyncGumloop(access_token="your_access_token") as client:
        agents = await client.agents.list()
        agent = agents.agents[0]

        async for event in client.sessions.stream(
            agent.id,
            input="Hello, what can you do?",
        ):
            print(event)


asyncio.run(main())
```
