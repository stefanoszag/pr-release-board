# pr-release-board
A lightweight visual board for prioritising and coordinating pull request releases

## Setup

This project uses [Poetry](https://python-poetry.org/) for dependency and environment management.

```bash
# Install dependencies and create the virtual environment
poetry install

# Run the Flask app (use Poetry so dependencies are available)
FLASK_APP=app poetry run flask run

# Or activate the shell and run from there
poetry shell
FLASK_APP=app flask run
```
