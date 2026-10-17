"""Pilot Programmatic Partnership: public dashboard and Kobo sync.

The sync script reads ``KOBO_API_TOKEN`` from the environment. It is separate
from the core admin Kobo import screen, which has no token for these projects.

    python plugins/ifrc/ppp/sync.py
    python plugins/ifrc/ppp/sync.py --apply --owner-email you@ifrc.org
    python plugins/ifrc/ppp/sync.py --repair
"""
