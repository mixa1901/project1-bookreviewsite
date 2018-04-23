import os
import csv
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

with open('books.csv') as csvfile:
	next(csvfile)
	file = csv.reader(csvfile)

	for q, w, e, r in file:
		print(q, w, e, r)
		db.execute("INSERT INTO books (isbn, title, author, year) VALUES (:isbn, :title, :author, :year)", {"isbn": q, "title": w, "author": e, "year": r})

db.commit()