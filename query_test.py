from google.cloud import bigquery

client = bigquery.Client(project="molbydickproj")
rows = client.query("""
    SELECT book_id, title, num_pages, average_rating, language_code
    FROM `molbydickproj.goodreads.books`
    WHERE language_code = 'eng'
      AND num_pages BETWEEN 150 AND 400
    LIMIT 50
""").result()
for r in rows:
    print(r.title, r.num_pages)