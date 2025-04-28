# CLAUDE.md for Wilma Client

This file contains information for Claude Code to help with working on this project.

## Project Overview

This project is an API client for the Wilma school platform. It allows authentication, fetching messages, and viewing message contents from the Wilma platform. This is the core library package that can be used by other applications.

## Project Structure

- `wilma/` - Main package
  - `__init__.py` - Package exports
  - `client.py` - Main API client implementation
  - `models/` - Data models
    - `__init__.py` - Model exports
    - `messages.py` - Message-related data models
  - `tests/` - Test suite
    - `__init__.py`
    - `conftest.py` - Pytest configuration
    - `test_client.py` - Tests for API client
    - `test_models.py` - Tests for data models
  - `utils/` - Utility functions
    - `__init__.py` - Utility exports

## Development Commands

Run these commands to verify your code before committing:

```bash
# Format with ruff
poetry run ruff format wilma

# Lint with ruff
poetry run ruff check wilma --fix

# Type check with mypy
poetry run mypy wilma

# Run tests
poetry run pytest
```

## API Authentication Flow

1. Call `GET https://turku.inschool.fi/token` to get a `Wilma2LoginID` cookie
2. Use that cookie as the `SESSIONID` parameter when posting to `https://turku.inschool.fi/login`
3. From the login response, get:
   - A `Wilma2SID` cookie for future authentication
   - The user ID from the `Location` header (format: `/!04354289?checkcookie`)
4. Include the `Wilma2SID` header in all subsequent requests

## API Endpoints

- `GET /<USERID>/messages/list` - Get list of messages
- `GET /<USERID>/messages/<MESSAGEID>?format=json` - Get message content

## Data Models

- `Message` - Represents a message in the messages list
- `MessagesList` - Container for a list of messages
- `Sender` - Information about the sender of a message

## Common Issues and Solutions

- Authentication issues: Ensure correct cookie handling and header extraction
- JSON parsing errors: The API sometimes returns malformed JSON
- Cookie handling: Ensure cookies are properly extracted and passed