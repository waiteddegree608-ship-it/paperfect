import sqlite3
c = sqlite3.connect("data/paperfect_library.db")
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT id, title, zh_title, original_filename, abstract, en_abstract, "
    "folder_id, paper_type, venue, research_field FROM documents "
    "WHERE original_filename LIKE '%zipper%' OR title LIKE '%zipper%' OR id=39"
).fetchall()
print("count", len(rows))
for r in rows:
    d = dict(r)
    for k in ("abstract", "en_abstract"):
        if d.get(k) and len(str(d[k])) > 80:
            d[k] = str(d[k])[:80] + "..."
    print(d)
    tags = c.execute(
        "SELECT t.name, t.category FROM tags t "
        "JOIN document_tag dt ON t.id=dt.tag_id WHERE dt.document_id=?",
        (r["id"],),
    ).fetchall()
    print("tags", tags)
