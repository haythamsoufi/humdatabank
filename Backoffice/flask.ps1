# Run Flask CLI using the same Python as py -m flask (avoids wrong-env issues).
# Usage: .\flask.ps1 db upgrade   or   .\flask.ps1 run
& py -m flask @args
