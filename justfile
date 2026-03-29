serve:
    xdg-open http://localhost:8000  >/dev/null 2>&1 &
    @gunicorn

repl:
    python -i debuginit.py
