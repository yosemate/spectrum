#!/usr/bin/env python3
"""Consistent SQLite backup; never overwrite source or an existing destination."""
import argparse
from pathlib import Path
import sqlite3


def backup_database(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == destination:
        raise ValueError('Source and destination must differ')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the destination exclusively, so this tool cannot replace existing data.
    with destination.open('xb'):
        pass
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
            with sqlite3.connect(destination) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backup integrity check failed')
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source');parser.add_argument('destination')
    args=parser.parse_args()
    print(backup_database(args.source,args.destination))
