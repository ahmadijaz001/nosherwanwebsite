#!/usr/bin/env python3
"""
PrestigeMotors – Dummy Car Image Seeder
Adds 4 real car photos (from Unsplash CDN) to every car that has no images.

Run on PythonAnywhere bash console:
    cd /home/<username>/mysite   (or wherever your app lives)
    python seed_images.py
"""

import sqlite3
import base64
import os
import urllib.request
import time
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, 'db', 'prestigemotors.db')

# ─────────────────────────────────────────────────────────────
# Unsplash photo IDs (stable CDN – no API key needed for direct download)
# Grouped by visual style so each car feels distinct
# ─────────────────────────────────────────────────────────────
PHOTO_SETS = [
    # Set 0 – BMW/Dark sedan
    [
        '1503376780353-7e6692767b70',  # black BMW on road
        '1494976388531-d1058494cdd8',  # BMW i8 studio
        '1552519507-da3b142c6e3d',     # silver sports rear
        '1605816988069-b11383b50717',  # white sports front
    ],
    # Set 1 – Mercedes/Executive
    [
        '1617531653332-bd46c16f7c6b',  # black Mercedes
        '1590362891991-d1c64b313f41',  # luxury interior
        '1541899481282-d53bffe3c35d',  # car lights bokeh
        '1503376780353-7e6692767b70',  # black sedan
    ],
    # Set 2 – SUV/Range Rover
    [
        '1571607388263-1044f9ea01eb',  # white SUV road
        '1489824904134-891ab64532f1',  # off-road SUV field
        '1526726538690-5cbf956ae2fd',  # SUV low angle
        '1555215695-3004980ad54e',     # yellow sports (contrast)
    ],
    # Set 3 – Audi/Estate
    [
        '1606664515524-ed2f786a0bd6',  # grey luxury side
        '1614162692292-7ac56d7f7f1e',  # white BMW style sedan
        '1552519507-da3b142c6e3d',     # silver rear angle
        '1617531653332-bd46c16f7c6b',  # dark executive
    ],
    # Set 4 – Porsche/Sports
    [
        '1580274455191-1c62238fa1c3',  # Porsche 911 rear
        '1555215695-3004980ad54e',     # yellow Porsche
        '1526726538690-5cbf956ae2fd',  # red sports low angle
        '1583121274602-3e2820c69888',  # red Ferrari-style
    ],
    # Set 5 – Jaguar/Saloon
    [
        '1626668893632-6f3a4466d22f',  # green/teal premium
        '1606664515524-ed2f786a0bd6',  # grey luxury
        '1544636331-e26879cd4d9b',     # red sporty
        '1605816988069-b11383b50717',  # white front
    ],
    # Set 6 – VW Golf/Hot hatch
    [
        '1558618666-fcd25c85cd64',     # dark car night scene
        '1541899481282-d53bffe3c35d',  # headlights blur
        '1503376780353-7e6692767b70',  # black road car
        '1552519507-da3b142c6e3d',     # silver rear
    ],
    # Set 7 – BMW X5/SUV
    [
        '1571607388263-1044f9ea01eb',  # white SUV
        '1614162692292-7ac56d7f7f1e',  # white sedan studio
        '1494976388531-d1058494cdd8',  # BMW blue studio
        '1503376780353-7e6692767b70',  # black road
    ],
    # Set 8 – Lexus/Premium
    [
        '1590362891991-d1c64b313f41',  # luxury cabin
        '1617531653332-bd46c16f7c6b',  # executive black
        '1606664515524-ed2f786a0bd6',  # silver luxury
        '1605816988069-b11383b50717',  # clean white front
    ],
]

FALLBACK_SET = PHOTO_SETS[0]

UNSPLASH_BASE = 'https://images.unsplash.com/photo-{id}?w=900&q=72&auto=format&fit=crop'
HEADERS = {'User-Agent': 'Mozilla/5.0 (PrestigeMotors seed script)'}


def download_image(photo_id: str):
    url = UNSPLASH_BASE.format(id=photo_id)
    print(f'    ↓ {url}')
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=40) as resp:
            raw       = resp.read()
            mime      = resp.getheader('Content-Type', 'image/jpeg').split(';')[0].strip()
            b64       = base64.b64encode(raw).decode('utf-8')
            size_kb   = len(raw) // 1024
            print(f'       ✓  {size_kb} KB  ({mime})')
            return b64, mime
    except Exception as exc:
        print(f'       ✗  failed: {exc}')
        return None, None


def seed():
    if not os.path.exists(DB_PATH):
        print(f'ERROR: DB not found at {DB_PATH}')
        print('Start the Flask server once first so it can create the database, then re-run this script.')
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys=ON')

    cars = conn.execute('SELECT id, make, model FROM cars ORDER BY id').fetchall()
    if not cars:
        print('No cars in DB yet. Start the server first (it seeds sample cars on first run).')
        conn.close()
        sys.exit(1)

    print(f'Found {len(cars)} car(s) in database.\n')
    seeded = 0

    for idx, (car_id, make, model) in enumerate(cars):
        existing = conn.execute(
            'SELECT COUNT(*) FROM car_images WHERE car_id=?', (car_id,)
        ).fetchone()[0]

        if existing >= 2:
            print(f'  [{car_id}] {make} {model} — already has {existing} image(s). Skipping.')
            continue

        photo_set = PHOTO_SETS[idx % len(PHOTO_SETS)]
        print(f'\n  [{car_id}] {make} {model} — downloading {len(photo_set)} images …')

        inserted = 0
        for order, photo_id in enumerate(photo_set):
            b64, mime = download_image(photo_id)
            if not b64:
                continue
            is_primary = 1 if order == 0 else 0
            conn.execute(
                'INSERT INTO car_images (car_id, image_data, mime_type, is_primary, sort_order) VALUES (?,?,?,?,?)',
                (car_id, b64, mime, is_primary, order)
            )
            conn.commit()
            inserted += 1
            time.sleep(0.25)   # be polite to CDN

        print(f'       → inserted {inserted} image(s) for {make} {model}')
        seeded += 1

    conn.close()
    print(f'\n✅  Done!  Seeded images for {seeded} car(s).')
    if seeded == 0:
        print('    (All cars already had images — nothing was changed.)')


if __name__ == '__main__':
    seed()
