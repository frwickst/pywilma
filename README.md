# Wilhelmina - Wilma API Client

A Python API client for the Wilma school platform. This client allows you to authenticate, fetch messages, and view message contents from the Wilma platform.

Why is this not called Wilma? The reason is simple, PyPi sees "Wilma" as a prohibited packages name. It
is not taken on PyPi, it just is not allowed. Wilhelmina is the long/full version of the name Wilma which
is the reason for the name.

## Wilma API Features

- [X] Messages
  - [X] List (API)
  - [X] Get single (API)
  - [X] Get unread (Scraping w/ Playwright)\*


\* There _is_ an API that returns the `status` of a message (0=read, 1=unread) but this is not enabled on all instances, specifically not on the Turku instance that I was interested in. 

## Home Assistant compatibility

This library has support for passing in an existing `aiohttp` to allow for easier integration with
Home Assistant. The version of `aiohttp` has also been slightly restricted in order to be installable
in Home Assistant. `mashumaro` was chosen for type safe models instead of Pydantic to not need to
go through the v1 vs. v2 hassle.

## Features

- Asynchronous API using `aiohttp`
- Type-safe models using `mashumaro`
- Optional unread message detection using Playwright for JavaScript rendering
- Graceful fallback when Playwright is not installed (messages won't be marked as unread)
- Comprehensive test suite

## Note about AI

Sonnet 3.7 has written a lot code in this repository. Far from one-shotted however and a lot of
refactoring has been done in order to get things into this state. The main purpose for creating
this library was to get quick access to the Wilma API through Python.

## Installation

```bash
# Basic installation
pip install wilhelmina

# (Optional) Installation with Playwright support (for unread message detection)
pip install wilhelmina[playwright]

# Playwright browser will be installed automatically on import

# Using Poetry
poetry add wilhelmina -E playwright
```

## API Client Usage

```python
import asyncio
from wilhelmina import WilmaClient

async def main():
    # Initialize client with an optional existing aiohttp session
    # Use headless=False to see the browser
    session = aiohttp.ClientSession()  # Optional - provide your own session
    
    async with WilmaClient("https://turku.inschool.fi", session=session, headless=True) as client:
        # Login
        await client.login("username", "password")
        
        # Get messages
        messages = await client.get_messages()
        
        # Print messages
        for msg in messages:
            # Show unread status
            unread_status = "UNREAD" if msg.unread else "read"
            print(f"{msg.id}: {msg.subject} - {msg.timestamp} - {msg.sender} - {unread_status}")
            
            # Get message content
            content = await client.get_message_content(msg.id)
            print(f"Content: {content.content[:100]}...")

# Run the main function
asyncio.run(main())
```

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/frwickst/wilhelmina.git
cd wilhelmina

# Install development dependencies
poetry install

# Install Playwright browser
poetry run playwright install chromium
```

### Running Tests

```bash
# Run all tests
poetry run pytest

# Run specific tests
poetry run pytest wilhelmina/tests/test_client.py

# Run with coverage
poetry run pytest --cov=wilhelmina
```

### Linting and Type Checking

```bash
# Format with ruff
poetry run ruff format wilhelmina

# Run ruff for linting
poetry run ruff check wilhelmina --fix

# Run mypy for type checking
poetry run mypy wilhelmina
```

## License

MIT
