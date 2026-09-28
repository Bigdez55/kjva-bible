-- Events are the authoritative transition record. Objects are replayable projections.
PRAGMA user_version = 2;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT;
CREATE TABLE events (
    seq INTEGER PRIMARY KEY,
    previous TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL
) STRICT;
CREATE TRIGGER events_no_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'immutable events'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'immutable events'); END;
CREATE TABLE objects (
    kind TEXT NOT NULL,
    id TEXT NOT NULL,
    workflow TEXT NOT NULL,
    rev INTEGER NOT NULL CHECK(rev > 0),
    data TEXT NOT NULL,
    PRIMARY KEY(kind, id)
) STRICT;
CREATE INDEX objects_scope ON objects(workflow, kind);
CREATE TABLE commands (
    actor TEXT NOT NULL,
    id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response TEXT NOT NULL,
    event_seq INTEGER NOT NULL REFERENCES events(seq),
    PRIMARY KEY(actor, id)
) STRICT;
CREATE TABLE blobs (
    hash TEXT PRIMARY KEY,
    codec TEXT NOT NULL,
    size INTEGER NOT NULL CHECK(size >= 0),
    data BLOB NOT NULL
) STRICT;
CREATE TRIGGER blobs_no_update BEFORE UPDATE ON blobs BEGIN SELECT RAISE(ABORT, 'immutable blobs'); END;
CREATE TRIGGER blobs_no_delete BEFORE DELETE ON blobs BEGIN SELECT RAISE(ABORT, 'immutable blobs'); END;
CREATE INDEX unresolved_actions ON objects(json_extract(data,'$.outcome'),json_extract(data,'$.dispatch')) WHERE kind='action';
CREATE INDEX active_leases ON objects(CAST(json_extract(data,'$.expires') AS REAL)) WHERE kind='lease';
