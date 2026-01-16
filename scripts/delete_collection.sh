#!/bin/bash
# Delete a Kotaemon collection by name or ID
# Usage: ./delete_collection.sh [collection_name_or_id]
#        ./delete_collection.sh --list

set -e

if [ "$1" == "--list" ] || [ -z "$1" ]; then
    echo "Available collections:"
    docker exec kotaemon python -c "
from sqlalchemy.orm import Session
from ktem.db.engine import engine
from sqlalchemy import text

with Session(engine) as sess:
    result = sess.execute(text('SELECT id, name, index_type FROM ktem__index'))
    for row in result:
        idx_type = row[2].split('.')[-1]
        print(f'  [{row[0]}] {row[1]} ({idx_type})')
"
    if [ -z "$1" ]; then
        echo ""
        echo "Usage: $0 <collection_id_or_name>"
        echo "       $0 --list"
    fi
    exit 0
fi

COLLECTION="$1"

docker exec kotaemon python -c "
from sqlalchemy.orm import Session
from ktem.db.engine import engine
from sqlalchemy import text
import shutil
import os

collection_input = '''$COLLECTION'''

with Session(engine) as sess:
    # Find collection by ID or name
    if collection_input.isdigit():
        result = sess.execute(text(f'SELECT id, name FROM ktem__index WHERE id = {collection_input}'))
    else:
        result = sess.execute(text(f\"SELECT id, name FROM ktem__index WHERE name = '{collection_input}'\"))

    row = result.fetchone()
    if not row:
        print(f'Collection not found: {collection_input}')
        exit(1)

    collection_id, collection_name = row[0], row[1]

    # Don't delete default collections (ID 1-3)
    if collection_id <= 3:
        print(f'Cannot delete default collection: {collection_name}')
        exit(1)

    # Delete from ktem__index
    sess.execute(text(f'DELETE FROM ktem__index WHERE id = {collection_id}'))

    # Drop associated tables
    for table_type in ['source', 'index', 'group']:
        try:
            sess.execute(text(f'DROP TABLE IF EXISTS index__{collection_id}__{table_type}'))
        except:
            pass

    sess.commit()
    print(f'Deleted collection [{collection_id}]: {collection_name}')

# Clean up GraphRAG/LightRAG data directories
for data_type in ['graphrag', 'lightrag']:
    data_dir = f'/app/ktem_app_data/user_data/files/{data_type}'
    if os.path.exists(data_dir):
        for d in os.listdir(data_dir):
            path = os.path.join(data_dir, d)
            if os.path.isdir(path):
                shutil.rmtree(path)
                print(f'Cleaned up {data_type} data: {d}')
"

echo "Done. Restart the app: docker restart kotaemon"
